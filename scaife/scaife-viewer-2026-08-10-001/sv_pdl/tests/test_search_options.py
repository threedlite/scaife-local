"""Exercise the search API's options, not just that search works.

Before this suite, search coverage was: the index has documents, the server
is OpenSearch, and `/search/` returns a 200 HTML shell. Nothing touched an
option. That was a poor place to be while swapping the entire search engine
from Elasticsearch 8 to OpenSearch 2.19 — scoping, faceting and pagination
are exactly the parts an engine change can alter without anything crashing.

`/search/json/` is the endpoint the Vue frontend calls. Its options:

    type        library | reader   (required)
    q           query string       (required)
    kind        form | lemma       (default form)
    size        results per request
    page_num    1-based page
    text_group  scope filter (URN)
    work        scope filter (URN), overrides text_group

Tests assert **totals, narrowing, shape and metadata** rather than exact
result ordering. Documents with identical relevance scores are ordered by
internal Lucene doc id, which follows indexing order, so pinning the order
of tied hits would make this suite fail on a reindex without anything being
wrong. See DJANGO-UPGRADE.md §11.

Tagged `integration`: needs a populated search index.
"""
import math

from django.test import SimpleTestCase, TestCase, tag

from scaife_viewer.core.utils import get_pagination_info

ENDPOINT = "/search/json/"

# Latin, present in many texts, so scoping and paging have room to work.
QUERY = "arma"
# A text group and one of its works, for the scope filters.
TEXT_GROUP = "urn:cts:latinLit:phi0690"
WORK = "urn:cts:latinLit:phi0690.phi003"


@tag("integration")
class SearchOptionTests(TestCase):
    databases = {"default"}

    def setUp(self):
        # UpdateCacheMiddleware/FetchFromCacheMiddleware cache GET responses
        # process-wide for CACHE_MIDDLEWARE_SECONDS, and Django does not
        # reset that between tests. Without this, one test's response is
        # served to the next — and to other suites.
        from django.core.cache import cache

        cache.clear()
        self.addCleanup(cache.clear)

    def get(self, **params):
        qs = "&".join(f"{k}={v}" for k, v in params.items())
        response = self.client.get(f"{ENDPOINT}?{qs}")
        return response, (response.json() if response["Content-Type"].startswith("application/json") else None)

    def search(self, **params):
        params.setdefault("type", "library")
        params.setdefault("q", QUERY)
        response, data = self.get(**params)
        self.assertEqual(response.status_code, 200, f"{params} -> {response.status_code}")
        return data

    # ---------------------------------------------------------------- validation

    def test_missing_type_is_rejected(self):
        response, data = self.get(q=QUERY)
        self.assertEqual(response.status_code, 400)
        self.assertIn("search type", data["error"])

    def test_missing_query_is_rejected(self):
        response, data = self.get(type="library")
        self.assertEqual(response.status_code, 400)
        self.assertIn("search query", data["error"])

    def test_unknown_search_type_is_rejected(self):
        """`type` is validated against the known values.

        It used to be checked only for being truthy, so an unknown value
        fell through to the reader branch and returned 200 while the error
        message for a *missing* type promised 'library' or 'reader'. That
        was upstream behaviour — identical on the pre-upgrade stack — and
        was pinned here as a known quirk until it was fixed.
        """
        for search_type in ("not-a-real-type", "Library", "readers"):
            with self.subTest(type=search_type):
                response, data = self.get(type=search_type, q=QUERY)
                self.assertEqual(response.status_code, 400)
                self.assertIn("search type", data["error"])

    def test_non_numeric_size_and_page_are_client_errors(self):
        """These used to raise out of the view as a 500.

        `size` and `page_num` were parsed with a bare `int()`. They now
        have to be positive integers, which also protects the pagination
        arithmetic: `size=0` would divide by zero and `page_num=0` would
        request a negative offset from the search backend.
        """
        for params in (
            {"size": "abc"},
            {"size": "0"},
            {"size": "-1"},
            {"page_num": "abc"},
            {"page_num": "0"},
        ):
            with self.subTest(params=params):
                response, _ = self.get(type="library", q=QUERY, **params)
                self.assertEqual(response.status_code, 400)

    # ---------------------------------------------------------------- modes

    def test_library_and_reader_modes_both_return_results(self):
        for search_type in ("library", "reader"):
            with self.subTest(type=search_type):
                data = self.search(type=search_type, size=3)
                self.assertTrue(data["results"], f"{search_type} returned nothing")

    def test_library_mode_reports_total_and_pagination(self):
        """No `size`, so this covers the default stride of 10.

        This test used to pass `size=3` and still assert `total / 10`,
        which only held because the stride ignored `size`. The stride now
        follows `size`, so asserting the default means not passing one.
        """
        data = self.search()
        self.assertGreater(data["total_count"], 0)
        page = data["page"]
        self.assertEqual(page["number"], 1)
        self.assertFalse(page["has_previous"])
        self.assertEqual(len(data["results"]), 10)
        self.assertEqual(page["num_pages"], math.ceil(data["total_count"] / 10))

    def test_echoes_back_the_options_it_was_given(self):
        data = self.search(kind="form", page_num=1)
        self.assertEqual(data["q"], QUERY)
        self.assertEqual(data["kind"], "form")
        self.assertEqual(data["type"], "library")
        self.assertEqual(data["page_num"], 1)

    # ---------------------------------------------------------------- size / paging

    def test_size_controls_how_many_results_come_back(self):
        for size in (1, 3, 10):
            with self.subTest(size=size):
                self.assertEqual(len(self.search(size=size)["results"]), size)

    def test_paging_advances_to_different_results(self):
        first = self.search(size=10, page_num=1)
        second = self.search(size=10, page_num=2)
        urls1 = [r["passage"]["url"] for r in first["results"]]
        urls2 = [r["passage"]["url"] for r in second["results"]]
        self.assertEqual(set(urls1) & set(urls2), set(), "pages overlap")
        self.assertTrue(second["page"]["has_previous"])
        self.assertEqual(second["page"]["number"], 2)

    def test_page_stride_follows_size(self):
        """`size` is the page stride, in results and in the metadata alike.

        The view used to compute `offset = (page_num - 1) * 10` while
        `size` stayed caller-controlled, and built the pagination metadata
        on 10 per page as well. With `size=5`, page 2 began at result 11
        and results 6-10 could not be reached from any page. Pinned here as
        a known quirk until it was fixed; see packages/README.md for the
        matching change to `get_pagination_info`.
        """
        for size in (1, 3, 5):
            with self.subTest(size=size):
                data = self.search(size=size)
                self.assertEqual(len(data["results"]), size)
                self.assertEqual(data["page"]["start_index"], 1)
                self.assertEqual(data["page"]["end_index"], size)
                self.assertEqual(
                    data["page"]["num_pages"],
                    math.ceil(data["total_count"] / size),
                )

    def test_pages_tile_the_result_set_without_gaps(self):
        """The actual point of the stride fix.

        Walking consecutive pages at a non-default size must visit every
        result exactly once. Under the old arithmetic, `size=5` skipped
        results 6-10, 16-20 and so on entirely.
        """
        size = 5
        seen = []
        for page_num in (1, 2, 3):
            data = self.search(size=size, page_num=page_num)
            self.assertEqual(data["page"]["start_index"], ((page_num - 1) * size) + 1)
            seen.extend(r["passage"]["urn"] for r in data["results"])

        self.assertEqual(len(seen), 3 * size, "a page came back short")
        self.assertEqual(len(set(seen)), len(seen), "pages overlap")

        # The same span fetched as one window must contain the same URNs.
        window = self.search(size=3 * size, page_num=1)
        self.assertEqual(
            set(seen),
            {r["passage"]["urn"] for r in window["results"]},
            "paging skipped results that a single window returns",
        )

    # ---------------------------------------------------------------- scope

    def test_scope_filters_narrow_the_result_set(self):
        everything = self.search(size=1)["total_count"]
        by_group = self.search(size=1, text_group=TEXT_GROUP)["total_count"]
        by_work = self.search(size=1, work=WORK)["total_count"]

        self.assertGreater(everything, by_group, "text_group did not narrow")
        self.assertGreaterEqual(by_group, by_work, "work should be within its group")
        self.assertGreater(by_work, 0, "the work scope returned nothing")

    def test_unknown_scope_returns_no_results_rather_than_an_error(self):
        data = self.search(size=3, text_group="urn:cts:latinLit:definitelynotreal")
        self.assertEqual(data["total_count"], 0)
        self.assertEqual(data["results"], [])

    def test_scoped_results_stay_within_the_scope(self):
        data = self.search(size=10, work=WORK)
        self.assertTrue(data["results"])
        for result in data["results"]:
            self.assertIn(
                WORK,
                result["passage"]["urn"],
                "a scoped search returned a passage from outside the work",
            )

    # ---------------------------------------------------------------- facets

    def test_text_group_facet_is_populated_and_shaped(self):
        data = self.search(size=1)
        facets = data["text_groups"]
        self.assertTrue(facets, "no text_group aggregation returned")
        entry = facets[0]
        self.assertEqual(set(entry), {"count", "text_group"})
        self.assertEqual(set(entry["text_group"]), {"urn", "label", "works"})
        self.assertGreater(entry["count"], 0)

    def test_work_facet_appears_only_when_scoped_to_a_text_group(self):
        self.assertIsNone(self.search(size=1)["works"])
        self.assertIsNotNone(self.search(size=1, text_group=TEXT_GROUP)["works"])

    # ---------------------------------------------------------------- kind

    def test_lemma_kind_is_accepted(self):
        """`kind=lemma` needs lemma-annotated content, which this deployment
        does not index (LEMMA_CONTENT is set only in the search-index image
        target). It must still be a clean empty result, not an error."""
        data = self.search(kind="lemma", size=3)
        self.assertEqual(data["kind"], "lemma")
        self.assertEqual(data["results"], [])

    # ---------------------------------------------------------------- queries

    def test_greek_query_returns_results(self):
        """Non-ASCII has to survive the URL, the client and the analyzer."""
        data = self.search(q="%CE%BC%E1%BF%86%CE%BD%CE%B9%CE%BD", size=3)
        self.assertGreater(data["total_count"], 0)
        self.assertTrue(data["results"])

    def test_query_with_no_matches_is_empty_not_an_error(self):
        data = self.search(q="zzzznotarealword", size=3)
        self.assertEqual(data["total_count"], 0)
        self.assertEqual(data["results"], [])
        self.assertFalse(data["page"]["has_next"])
        self.assertFalse(data["page"]["has_previous"])
        # One empty page, matching Django's Paginator. This used to report
        # zero pages with start_index 1 and end_index 10 — "showing 1-10 of
        # 0, page 1 of 0" — because the metadata was built arithmetically
        # and never special-cased an empty result set.
        self.assertEqual(data["page"]["num_pages"], 1)
        self.assertEqual(data["page"]["start_index"], 0)
        self.assertEqual(data["page"]["end_index"], 0)

    # ---------------------------------------------------------------- contract

    def test_result_shape_matches_what_the_frontend_reads(self):
        result = self.search(size=1)["results"][0]
        self.assertEqual(set(result), {"content", "passage"})
        self.assertLessEqual(
            {"url", "urn", "text_url", "json_url", "refs", "ancestors"},
            set(result["passage"]),
            "the reader builds links from these keys",
        )
        self.assertTrue(result["passage"]["url"].startswith("/reader/"))


class PaginationInfoTests(SimpleTestCase):
    """Unit coverage for `get_pagination_info`, which is pure arithmetic.

    It is a vendored-package function (packages/scaife-viewer-core), and it
    was the source of two of the three search quirks this suite pinned. The
    integration tests above prove the fixes hold against a live index;
    these prove the arithmetic itself, including the boundaries a real
    corpus does not conveniently produce.
    """

    def test_empty_result_set_is_one_empty_page(self):
        page = get_pagination_info(0, 1)
        self.assertEqual(page["num_pages"], 1)
        self.assertEqual(page["start_index"], 0)
        self.assertEqual(page["end_index"], 0)
        self.assertFalse(page["has_next"])
        self.assertFalse(page["has_previous"])

    def test_default_per_page_is_unchanged_at_ten(self):
        """Callers that do not pass `per_page` must see the old behaviour.

        Core's own search view and the Vue frontend both rely on this.
        """
        page = get_pagination_info(25, 1)
        self.assertEqual(page["num_pages"], 3)
        self.assertEqual(page["start_index"], 1)
        self.assertEqual(page["end_index"], 10)
        self.assertTrue(page["has_next"])

    def test_indices_follow_per_page(self):
        page = get_pagination_info(25, 2, per_page=5)
        self.assertEqual(page["num_pages"], 5)
        self.assertEqual(page["start_index"], 6)
        self.assertEqual(page["end_index"], 10)
        self.assertTrue(page["has_next"])
        self.assertTrue(page["has_previous"])

    def test_last_page_stops_at_the_total(self):
        page = get_pagination_info(23, 3, per_page=10)
        self.assertEqual(page["num_pages"], 3)
        self.assertEqual(page["start_index"], 21)
        self.assertEqual(page["end_index"], 23)
        self.assertFalse(page["has_next"])

    def test_exactly_full_last_page(self):
        page = get_pagination_info(20, 2, per_page=10)
        self.assertEqual(page["num_pages"], 2)
        self.assertEqual(page["end_index"], 20)
        self.assertFalse(page["has_next"])

    def test_pages_tile_the_total_without_gaps_or_overlap(self):
        """Every result index belongs to exactly one page."""
        for total, per_page in ((25, 5), (23, 10), (1, 10), (100, 7)):
            with self.subTest(total=total, per_page=per_page):
                covered = []
                num_pages = get_pagination_info(total, 1, per_page)["num_pages"]
                for page_num in range(1, num_pages + 1):
                    page = get_pagination_info(total, page_num, per_page)
                    covered.extend(range(page["start_index"], page["end_index"] + 1))
                self.assertEqual(covered, list(range(1, total + 1)))
