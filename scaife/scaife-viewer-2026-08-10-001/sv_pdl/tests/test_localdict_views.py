"""Local dictionary API contract.

These views replace calls the Vue frontend used to make to
atlas.perseus.tufts.edu, so their JSON shape is a contract with the
frontend. Django upgrades touch JsonResponse, Paginator and ORM lookups —
all three are exercised here.
"""
from django.test import TestCase

from sv_pdl.localdict.models import Dictionary, DictionaryEntry
from sv_pdl.localdict.normalize import nfc, strip_diacritics


def make_entry(dictionary, headword, intro="", order=0):
    return DictionaryEntry.objects.create(
        dictionary=dictionary,
        headword=headword,
        headword_normalized=nfc(headword),
        headword_normalized_stripped=strip_diacritics(nfc(headword)).lower(),
        intro_text=intro or f"definition of {headword}",
        sort_order=order,
    )


class DictionariesJsonTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.lsj = Dictionary.objects.create(
            slug="lsj", label="LSJ (Liddell-Scott-Jones)", lang="grc"
        )
        cls.ls = Dictionary.objects.create(
            slug="lewis-and-short-latin-dictionary",
            label="Lewis and Short Latin Dictionary",
            lang="lat",
        )

    def test_lists_dictionaries_with_expected_keys(self):
        resp = self.client.get("/library/dictionaries/json/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("results", data)
        self.assertEqual(len(data["results"]), 2)
        for row in data["results"]:
            self.assertEqual(
                set(row),
                {"id", "label", "data", "slug", "urn", "lang"},
                "frontend depends on this exact key set",
            )

    def test_urn_format(self):
        resp = self.client.get("/library/dictionaries/json/")
        row = next(r for r in resp.json()["results"] if r["slug"] == "lsj")
        self.assertEqual(
            row["urn"], "urn:cite2:scaife-viewer:dictionaries.local:lsj"
        )

    def test_ordered_by_id(self):
        slugs = [r["slug"] for r in
                 self.client.get("/library/dictionaries/json/").json()["results"]]
        self.assertEqual(slugs, ["lsj", "lewis-and-short-latin-dictionary"])


class DictionaryEntriesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.lsj = Dictionary.objects.create(slug="lsj", label="LSJ", lang="grc")
        make_entry(cls.lsj, "μῆνις", "wrath", order=1)
        make_entry(cls.lsj, "μηνίω", "to be wroth", order=2)
        make_entry(cls.lsj, "λόγος", "word", order=3)

    def url(self, slug="lsj"):
        return f"/library/dictionaries/{slug}/entries/"

    def test_response_shape(self):
        data = self.client.get(self.url()).json()
        self.assertEqual(
            set(data), {"results", "current_page", "total_pages"}
        )
        self.assertEqual(
            set(data["results"][0]),
            {"id", "urn", "data", "headword", "headword_normalized",
             "headword_normalized_stripped", "intro_text"},
        )

    def test_entry_shape_matches_widget_expectations(self):
        """WidgetPerseusDictionary dereferences result.data.senses and keys
        on result.urn. Emitting both keeps that widget unpatched against
        upstream; dropping them would throw in the browser, not here."""
        entry = self.client.get(self.url(), {"q": "μῆνις"}).json()["results"][0]
        self.assertIsInstance(entry["data"], dict)
        self.assertEqual(entry["data"].get("senses", []), [])
        self.assertTrue(entry["urn"].startswith("urn:cite2:scaife-viewer:"))

    def test_accent_insensitive_exact_match(self):
        """Reader sends an accented form; lookup is accent-stripped."""
        data = self.client.get(self.url(), {"q": "μῆνις"}).json()
        self.assertEqual([r["headword"] for r in data["results"]], ["μῆνις"])

    def test_unaccented_query_still_matches(self):
        data = self.client.get(self.url(), {"q": "μηνις"}).json()
        self.assertEqual([r["headword"] for r in data["results"]], ["μῆνις"])

    def test_exact_match_preferred_over_prefix(self):
        """μῆνις and μηνίω share the prefix μηνι-; an exact hit must not be
        diluted by prefix matches."""
        data = self.client.get(self.url(), {"q": "μῆνις"}).json()
        self.assertEqual(len(data["results"]), 1)

    def test_prefix_fallback_when_no_exact_match(self):
        data = self.client.get(self.url(), {"q": "μην"}).json()
        headwords = {r["headword"] for r in data["results"]}
        self.assertIn("μηνίω", headwords)

    def test_empty_query_returns_all(self):
        data = self.client.get(self.url()).json()
        self.assertEqual(len(data["results"]), 3)

    def test_no_match_is_empty_not_error(self):
        resp = self.client.get(self.url(), {"q": "ζζζζζ"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["results"], [])

    def test_unknown_dictionary_returns_404_with_shape(self):
        resp = self.client.get(self.url("does-not-exist"))
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(resp.json()["results"], [])

    def test_pagination_fields_present(self):
        data = self.client.get(self.url(), {"page": 1}).json()
        self.assertEqual(data["current_page"], 1)
        self.assertGreaterEqual(data["total_pages"], 1)

    def test_out_of_range_page_clamps(self):
        """Paginator.get_page() clamps rather than raising - behaviour we
        rely on and that has shifted between Django versions."""
        resp = self.client.get(self.url(), {"page": 9999})
        self.assertEqual(resp.status_code, 200)

    def test_results_are_json_serializable_unicode(self):
        """Greek must survive as real characters, not escaped mojibake."""
        resp = self.client.get(self.url(), {"q": "μῆνις"})
        self.assertEqual(resp["Content-Type"], "application/json")
        self.assertEqual(resp.json()["results"][0]["headword"], "μῆνις")
