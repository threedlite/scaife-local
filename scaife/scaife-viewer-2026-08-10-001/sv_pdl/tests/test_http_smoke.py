"""Every URL the reading UI touches must return, not 500.

This suite exists because of a bug the rest of the suite did not catch.
After the Python 3.12 move, `/library/<version>/json/` returned 500 for
every text: `anytree` 2.4.3 built regexes ending in `\\Z(?ms)`, a global
inline flag in trailing position, which Python 3.11 turned from a
deprecation into `re.error`. That is the CTS table-of-contents resolver, so
clicking a text in the library — the primary thing this application does —
failed outright.

Nothing noticed. The golden schema covers GraphQL, the passage snapshots
cover CTS rendering through the Python API, and the offline-wiring tests
check that URLs *resolve to the right view*. No test actually asked a view
for a response. A page that 500s is invisible to all of them.

So this suite is deliberately shallow and broad: request each endpoint the
frontend uses and assert the status. It will not tell you the page is
*correct* — the golden suites do that — only that it is not broken, which
is the failure mode a framework or dependency upgrade actually produces.

Tagged `integration`: the library and reader views read the mounted
corpora.
"""
from django.test import TestCase, tag

# A representative URN per shape. Homer is used throughout because it is
# present in every corpus configuration this project ships.
WORK = "urn:cts:greekLit:tlg0012.tlg001"
GREEK = f"{WORK}.perseus-grc2"
ENGLISH = f"{WORK}.perseus-eng3"
PASSAGE = f"{GREEK}:1.1-1.5"

# (path, expected status, why it matters)
ENDPOINTS = [
    ("/library/", 200, "library index"),
    ("/library/json/", 200, "library index data — the whole corpus tree"),
    (f"/library/{WORK}/", 200, "work page"),
    (f"/library/{WORK}/json/", 200, "work data"),
    (f"/library/{GREEK}/", 302, "version page redirects into the reader"),
    (f"/library/{GREEK}/json/", 200, "version data — this is what returned 500"),
    (f"/library/{ENGLISH}/json/", 200, "version data for a translation"),
    (f"/library/{GREEK}/redirect/", 302, "reader redirect target"),
    (f"/reader/{PASSAGE}/", 200, "the reader itself"),
    (f"/reader/{GREEK}/", 302, "bare version URN redirects to the first passage"),
    (f"/library/passage/{PASSAGE}/text/", 200, "plain-text passage export"),
    # A version URN carries no reference, so this is a client error, not a
    # server one. Pinned so a 500 here cannot hide behind "not 200".
    (f"/library/passage/{GREEK}/text/", 400, "passage URL without a reference"),
    ("/library/dictionaries/json/", 200, "dictionary list"),
    # Uses a slug this suite creates itself. Deliberately not "lsj": that
    # collides with the fixtures in test_localdict_views, and a unique
    # primary key is not worth borrowing another suite's data for.
    ("/library/dictionaries/smoke-dict/entries/?headword=test", 200, "dictionary lookup"),
    (f"/library/commentaries/{WORK}:1.1/json/", 200, "commentary lookup"),
    ("/search/?q=arma", 200, "search page"),
    ("/about/", 200, "about page"),
]


@tag("integration")
class HttpSmokeTests(TestCase):
    # Dictionary and commentary views are database-backed; ATLAS lives in
    # its own database.
    databases = {"default", "atlas"}

    def setUp(self):
        """Clear the response cache, then give the lookup something to find.

        `UpdateCacheMiddleware` and `FetchFromCacheMiddleware` are in
        MIDDLEWARE with CACHE_MIDDLEWARE_SECONDS = 900, and with no Redis
        configured the cache is LocMem — process-wide and *not* reset
        between tests. This suite is the first to request the same URL as
        another suite, so it was the first to trip over it: the dictionary
        list it cached here was then served to test_localdict_views, whose
        own fixtures appeared to vanish.

        Clearing on both sides keeps this suite from reading a stale entry
        and from leaving one behind.

        Created per test rather than in setUpTestData on purpose. Class-level
        fixtures are shared through a class-wide atomic, and this class
        declares a different `databases` set from the other suites that touch
        Dictionary — mixing the two leaked rows between classes and broke
        test_localdict_views. A per-test atomic is unambiguously rolled back.
        """
        from django.core.cache import cache

        cache.clear()
        self.addCleanup(cache.clear)

        from sv_pdl.localdict.models import Dictionary, DictionaryEntry

        smoke = Dictionary.objects.create(
            slug="smoke-dict", label="Smoke Test Dictionary", lang="grc"
        )
        DictionaryEntry.objects.create(
            dictionary=smoke,
            headword="test",
            headword_normalized="test",
            headword_normalized_stripped="test",
            intro_text="",
            sort_order=0,
        )

    def test_endpoints_return_expected_status(self):
        for path, expected, why in ENDPOINTS:
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(
                    response.status_code,
                    expected,
                    f"{path} returned {response.status_code}, expected "
                    f"{expected} ({why})",
                )

    def test_no_endpoint_returns_a_server_error(self):
        """Stated separately so a 5xx reads as its own failure rather than
        as a mismatched status code."""
        broken = []
        for path, _expected, _why in ENDPOINTS:
            response = self.client.get(path)
            if response.status_code >= 500:
                broken.append(f"{path} -> {response.status_code}")
        self.assertEqual(broken, [], f"endpoints returning 5xx: {broken}")
