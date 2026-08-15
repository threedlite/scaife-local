"""Characterisation snapshot of the Morpheus morphological analyser.

Morpheus is the only part of this deployment that is not Python. It is a C
engine (`morpheus-perseids`, built with `-std=gnu89`) wrapped in a Sinatra
API (`morpheus-perseids-api`), and the reader calls it every time a user
clicks a word. Neither repository is vendored here — both are fetched at
bootstrap and gitignored — so the *only* thing this project tracks about
them is `deps/morpheus-combined/Dockerfile`. That makes their behaviour
invisible to every other suite: nothing in `sv_pdl/tests` reached the
service at all before this file existed.

That matters now because the container's Ruby stack is being moved. The
risk is not that morpheus stops responding — a broken service is obvious.
The risk is that it responds with *slightly different analyses*, which
looks exactly like working software:

  * `Nokogiri::XML` parses the C engine's raw output (`lib/parser.rb`) and
    regenerates the RDF response. A libxml2 change inside nokogiri can
    alter entity handling, whitespace, attribute order or namespace
    placement without raising anything.
  * `Converter.greek_to_beta_code` transliterates Greek into the beta code
    the C binary expects. Ruby's Unicode tables move between releases, and
    `params[:word].unicode_normalize` in `routes/analysis.rb` normalises
    with whatever tables the runtime ships. A changed decomposition sends
    a different string to the engine, and the analysis silently changes.
  * Ruby's own JSON serialiser produces the response body, so key order
    and numeric formatting are runtime-dependent.

Three layers are captured per word, because each fails differently:

  ``service_json``  the full RDF envelope from the API. Catches engine
                    changes and anything the Django view normalises away.
  ``service_xml``   the same analysis serialised by nokogiri. This is the
                    layer a nokogiri upgrade actually moves; the JSON body
                    is assembled by Ruby's own serialiser and would not
                    show an XML-generation regression at all.
  ``view``          what `sv_pdl.views.morpheus_local` hands the Vue
                    frontend. The contract the UI is written against.

As with the CTS passage snapshots, these are characterisation tests: they
assert behaviour is *unchanged* and take today's behaviour as correct by
definition. That is the right instrument for a runtime upgrade whose goal
is "no functionality regressions".
"""
import json
import os
from urllib.parse import urlencode

import requests

# The word list is organised by the phenomenon each entry exercises rather
# than by text, because the code paths differ by *shape*: how many analyses
# come back, whether the beta-code converter has to handle breathings and
# subscripts, and whether the engine returns a bare dict or a list.
#
# Every entry below was verified to return at least one analysis, except
# the three negatives at the end, which are here precisely because empty
# and error responses have their own code path in both the API and the view.
GOLDEN_WORDS = [
    # -- Greek: accentuation and breathing marks ------------------------
    # These are the beta-code converter's real work. Each diacritic is a
    # separate transliteration rule, so they are covered individually.
    ("μῆνιν", "grc", "circumflex, smooth; the first word of the Iliad"),
    ("ἄειδε", "grc", "smooth breathing + acute, imperative"),
    ("θεά", "grc", "bare acute, no breathing mark"),
    ("ὅς", "grc", "rough breathing on a short word; two analyses"),
    ("ἀνθρώπῳ", "grc", "iota subscript in a dative"),
    ("ᾄδω", "grc", "iota subscript carrying an accent as well"),
    ("Ἀχιλῆος", "grc", "capital with breathing; epic genitive"),
    ("Ζεύς", "grc", "capital without breathing; irregular noun"),
    # -- Greek: morphology ----------------------------------------------
    ("λόγος", "grc", "2nd declension noun, the textbook case"),
    ("πατρός", "grc", "3rd declension with a syncopated stem"),
    ("τῶν", "grc", "article; high-frequency, many possible parses"),
    ("φιλεῖ", "grc", "contract verb, contraction resolved by the engine"),
    ("ἐποίησεν", "grc", "aorist with both augment and movable nu"),
    ("λελυκώς", "grc", "perfect participle, reduplicated"),
    ("δοίη", "grc", "aorist optative of an irregular verb"),
    ("ἐστίν", "grc", "enclitic copula"),
    # -- Latin: declensions ---------------------------------------------
    ("arma", "lat", "neuter plural; two headwords, several inflections"),
    ("virum", "lat", "ambiguous between two headwords and many cases"),
    ("rerum", "lat", "5th declension genitive plural"),
    ("bonus", "lat", "1st/2nd declension adjective"),
    ("fortior", "lat", "comparative adjective"),
    # -- Latin: conjugations and irregulars ------------------------------
    ("cano", "lat", "1sg present; also parses as an adjective form"),
    ("amavisset", "lat", "pluperfect subjunctive, fully inflected"),
    ("sum", "lat", "irregular verb; also a noun form"),
    ("locutus", "lat", "deponent participle"),
    ("regemque", "lat", "enclitic -que, which the engine must strip"),
    # -- Negatives -------------------------------------------------------
    # An analyser that returns nothing must do so cleanly. These pin the
    # empty path through the API, the parser and the view.
    ("zzzznotaword", "lat", "no Latin analysis exists"),
    ("ζζζζ", "grc", "no Greek analysis exists"),
    ("", "lat", "empty word; must not be an error"),
]


def key(word, lang):
    """Stable, readable dict key. Sorting these sorts the golden file."""
    return f"{lang}:{word}"


def base_url():
    return os.environ.get("MORPHEUS_LOCAL_URL", "http://morpheus:1500")


def _service(word, lang, accept):
    """One call to the Morpheus API, exactly as the Django view makes it.

    `engine` is derived the same way `views.morpheus_local` derives it, so
    a change to that convention shows up here rather than only in
    production.
    """
    qs = urlencode({"word": word, "lang": lang, "engine": f"morpheus{lang}"})
    response = requests.get(
        f"{base_url()}/analysis/word?{qs}",
        headers={"Accept": accept},
        timeout=30,
    )
    return response


def capture_service_json(word, lang):
    response = _service(word, lang, "application/json")
    return {"status": response.status_code, "body": response.json()}


def capture_service_xml(word, lang):
    response = _service(word, lang, "application/xml")
    return {"status": response.status_code, "body": response.text}


def capture_view(client, word, lang):
    """What the frontend receives, through the real URLconf and middleware."""
    qs = urlencode({"word": word, "lang": lang})
    response = client.get(f"/morpheus/?{qs}")
    body = None
    if response["Content-Type"].startswith("application/json"):
        # Round-trip through JSON so the golden holds plain types only.
        body = json.loads(response.content.decode("utf-8"))
    return {"status": response.status_code, "body": body}


def capture():
    """Build the full payload. Used by scripts/capture-golden.sh.

    `ALLOWED_HOSTS` needs "testserver" added by hand here. Django's test
    *runner* patches it in `setup_test_environment()`, but this capture
    runs as a plain script, so without it every request is rejected by
    `DisallowedHost` — which surfaces as a 400, indistinguishable at a
    glance from the view's own "word and lang are required" 400. The first
    run of this capture recorded 29 such 400s as if they were the golden.
    """
    from django.conf import settings
    from django.test import Client

    if "testserver" not in settings.ALLOWED_HOSTS:
        settings.ALLOWED_HOSTS = list(settings.ALLOWED_HOSTS) + ["testserver"]

    client = Client()
    service_json, service_xml, view = {}, {}, {}
    for word, lang, _why in GOLDEN_WORDS:
        k = key(word, lang)
        service_json[k] = capture_service_json(word, lang)
        service_xml[k] = capture_service_xml(word, lang)
        view[k] = capture_view(client, word, lang)
    return {
        "words": [
            {"word": word, "lang": lang, "why": why}
            for word, lang, why in GOLDEN_WORDS
        ],
        "service_json": service_json,
        "service_xml": service_xml,
        "view": view,
    }
