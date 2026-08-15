"""Morpheus must analyse identically across Ruby and nokogiri upgrades.

See `morpheus_snapshot.py` for why this exists and what the three captured
layers are. In short: morpheus is the deployment's only non-Python service,
neither of its two source repositories is tracked here, and until this
suite it had no coverage at all — while the reader calls it on every word
click.

Two kinds of test live here, and the distinction matters when one fails:

`MorpheusViewContractTests` needs no running analyser. It stubs the HTTP
call and checks how the view handles arguments, upstream failures and the
shapes the API can return. A failure here is a bug in our code.

`MorpheusGoldenTests` is tagged `integration` and compares live output
against `golden/morpheus.json`. A failure here means the *analyser* changed
— the C engine, the Ruby runtime, nokogiri, or libxml2 underneath it.
Refresh the golden only when the change is intended and reviewed:

    bash scripts/capture-golden.sh morpheus
    git diff -- '*/golden/morpheus.json'

An unreviewed refresh is indistinguishable from the regression this file
exists to catch.
"""
import json
from pathlib import Path
from unittest import mock

from django.test import SimpleTestCase, tag

from .morpheus_snapshot import (
    GOLDEN_WORDS,
    capture_service_json,
    capture_service_xml,
    capture_view,
    key,
)

GOLDEN_PATH = Path(__file__).parent / "golden" / "morpheus.json"

# Words with no analysis. Their golden entries are empty by design, so the
# structural checks below must not demand content from them.
NEGATIVES = {("zzzznotaword", "lat"), ("ζζζζ", "grc"), ("", "lat")}


def load_golden():
    with GOLDEN_PATH.open(encoding="utf-8") as fp:
        return json.load(fp)


class _UncachedRequests(SimpleTestCase):
    """Base class that stops the response cache from crossing tests.

    `UpdateCacheMiddleware` and `FetchFromCacheMiddleware` are in
    MIDDLEWARE with CACHE_MIDDLEWARE_SECONDS = 900, the cache is LocMem
    with no Redis configured, and Django does not reset it between tests.
    This suite requests the *same URL* from several tests with different
    stubs behind it, so without clearing, one test's stubbed analysis is
    replayed to the next — which is how it first failed: a mocked
    connection error returned a fully populated analysis for "arma".

    Same hazard, same remedy as `test_http_smoke.py` and
    `test_search_options.py`.
    """

    def setUp(self):
        from django.core.cache import cache

        cache.clear()
        self.addCleanup(cache.clear)


class MorpheusViewContractTests(_UncachedRequests):
    """How `views.morpheus_local` behaves, with the analyser stubbed out."""

    def get(self, **params):
        qs = "&".join(f"{k}={v}" for k, v in params.items())
        return self.client.get(f"/morpheus/?{qs}")

    # ------------------------------------------------------------ validation

    def test_word_and_lang_are_both_required(self):
        for params in ({}, {"word": "arma"}, {"lang": "lat"}):
            with self.subTest(params=params):
                self.assertEqual(self.get(**params).status_code, 400)

    def test_language_must_be_greek_or_latin(self):
        """The API itself also accepts "la"; the view deliberately does not,
        so that the engine name it builds is always one the API knows."""
        for lang in ("la", "eng", "grc-x", ""):
            with self.subTest(lang=lang):
                self.assertEqual(self.get(word="arma", lang=lang).status_code, 400)

    def test_accepted_languages_reach_the_analyser(self):
        for lang in ("grc", "lat"):
            with self.subTest(lang=lang):
                with mock.patch("sv_pdl.views.requests.get") as get:
                    get.return_value = mock.Mock(
                        status_code=200,
                        json=mock.Mock(return_value={}),
                        raise_for_status=mock.Mock(),
                    )
                    self.assertEqual(self.get(word="x", lang=lang).status_code, 200)
                    url = get.call_args[0][0]
                self.assertIn(f"lang={lang}", url)
                # The engine name is derived from the language. Getting this
                # wrong returns 404 "unknown engine" from the API, which the
                # view would silently turn into an empty analysis.
                self.assertIn(f"engine=morpheus{lang}", url)

    # ------------------------------------------------------- upstream failure

    def _stub(self, **kwargs):
        return mock.patch("sv_pdl.views.requests.get", **kwargs)

    def test_analyser_being_down_returns_an_empty_analysis(self):
        """The reader must keep working when morpheus is unreachable.

        A word click that 500s would break the page; an empty analysis just
        shows nothing for that word.
        """
        import requests

        for exc in (
            requests.ConnectionError("refused"),
            requests.Timeout("slow"),
            requests.HTTPError("503"),
        ):
            with self.subTest(exc=type(exc).__name__):
                with self._stub(side_effect=exc):
                    response = self.get(word="arma", lang="lat")
                self.assertEqual(response.status_code, 200)
                self.assertEqual(json.loads(response.content), {"Body": []})

    def test_error_status_from_the_analyser_is_swallowed(self):
        raiser = mock.Mock()
        raiser.raise_for_status.side_effect = __import__("requests").HTTPError("404")
        with self._stub(return_value=raiser):
            response = self.get(word="arma", lang="lat")
        self.assertEqual(json.loads(response.content), {"Body": []})

    # ------------------------------------------------------------ RDF shapes

    def _view_with_body(self, body):
        payload = {"RDF": {"Annotation": {"Body": body}}}
        with self._stub(
            return_value=mock.Mock(
                status_code=200,
                json=mock.Mock(return_value=payload),
                raise_for_status=mock.Mock(),
            )
        ):
            return json.loads(self.get(word="w", lang="lat").content)

    def test_empty_bodies_all_normalise_to_an_empty_list(self):
        for body in (None, {}, []):
            with self.subTest(body=body):
                self.assertEqual(self._view_with_body(body), {"Body": []})

    def test_a_single_analysis_is_wrapped_into_a_list(self):
        """The API emits a bare object rather than a list when there is
        exactly one analysis, which is the common case for Greek."""
        one = {
            "rest": {
                "entry": {
                    "uri": None,
                    "dict": {"hdwd": {"$": "arma"}, "pofs": {"$": "noun"}},
                    "infl": {"term": {"stem": {"$": "arm"}, "suff": {"$": "a"}},
                             "case": {"$": "nominative"}},
                }
            }
        }
        data = self._view_with_body(one)
        self.assertEqual(len(data["Body"]), 1)
        entry = data["Body"][0]
        self.assertEqual(entry["hdwd"], "arma")
        self.assertEqual(entry["pofs"], "noun")
        self.assertEqual(entry["infl"][0]["stem"], "arm")
        self.assertEqual(entry["infl"][0]["case"], "nominative")

    def test_missing_optional_fields_do_not_raise(self):
        """Not every analysis carries decl, suff or a dict at all."""
        data = self._view_with_body({"rest": {"entry": {}}})
        self.assertEqual(data["Body"], [{"uri": None, "hdwd": "", "pofs": "", "infl": []}])
        self.assertNotIn("decl", data["Body"][0])


@tag("integration")
class MorpheusGoldenTests(_UncachedRequests):
    """Live analyser output versus the recorded baseline."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.golden = load_golden()

    def test_the_golden_covers_the_declared_word_list(self):
        """Guards the golden itself: a partial capture must not pass."""
        recorded = [(w["word"], w["lang"]) for w in self.golden["words"]]
        self.assertEqual(recorded, [(w, l) for w, l, _ in GOLDEN_WORDS])
        for layer in ("service_json", "service_xml", "view"):
            with self.subTest(layer=layer):
                self.assertEqual(
                    sorted(self.golden[layer]),
                    sorted(key(w, l) for w, l, _ in GOLDEN_WORDS),
                )

    def test_golden_is_not_a_recording_of_empty_responses(self):
        """The first capture of this file recorded 29 rejected requests as
        if they were the baseline (ALLOWED_HOSTS lacked "testserver", so
        every view call was a DisallowedHost 400). A golden full of errors
        compares clean against itself forever, so assert it has content."""
        for word, lang, why in GOLDEN_WORDS:
            entry = self.golden["view"][key(word, lang)]
            with self.subTest(word=word, lang=lang, why=why):
                self.assertEqual(entry["status"], 200)
                analyses = entry["body"]["Body"]
                if (word, lang) in NEGATIVES:
                    self.assertEqual(analyses, [])
                    continue
                self.assertTrue(analyses, "no analysis recorded")
                for analysis in analyses:
                    self.assertTrue(analysis["hdwd"], "analysis without a headword")
                    self.assertTrue(analysis["pofs"], "analysis without a part of speech")

    def test_view_output_matches_the_golden(self):
        """The contract the Vue frontend is written against."""
        for word, lang, why in GOLDEN_WORDS:
            with self.subTest(word=word, lang=lang, why=why):
                self.assertEqual(
                    capture_view(self.client, word, lang),
                    self.golden["view"][key(word, lang)],
                )

    def test_service_json_matches_the_golden(self):
        """The full RDF envelope, including fields the view drops."""
        for word, lang, why in GOLDEN_WORDS:
            with self.subTest(word=word, lang=lang, why=why):
                self.assertEqual(
                    capture_service_json(word, lang),
                    self.golden["service_json"][key(word, lang)],
                )

    def test_service_xml_matches_the_golden(self):
        """Byte-for-byte, because this is nokogiri's own serialisation.

        Attribute order, namespace placement, self-closing tags and
        entity escaping are all decided by libxml2 inside nokogiri, and all
        of them can move on an upgrade without any analysis changing. This
        is the assertion a nokogiri bump is actually tested by.
        """
        for word, lang, why in GOLDEN_WORDS:
            with self.subTest(word=word, lang=lang, why=why):
                self.assertEqual(
                    capture_service_xml(word, lang),
                    self.golden["service_xml"][key(word, lang)],
                )

    def test_analysis_is_deterministic_across_repeated_calls(self):
        """Nothing in the golden comparison would catch a service that
        alternates between two valid answers; the capture and the test
        would simply disagree at random. Assert stability directly."""
        for word, lang in (("μῆνιν", "grc"), ("arma", "lat"), ("locutus", "lat")):
            with self.subTest(word=word):
                first = capture_service_json(word, lang)
                self.assertEqual(first, capture_service_json(word, lang))
