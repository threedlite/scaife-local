"""Local commentary API contract and passage-overlap matching.

The overlap query compares zero-padded strings with __lte/__gte in SQL.
That is the most upgrade-fragile thing in this codebase: it depends on
Django's ORM emitting a plain string comparison and on Postgres collation
not reordering the padded keys.
"""
from django.test import TestCase

from sv_pdl.localcomm.models import Commentary, CommentaryEntry
from sv_pdl.localcomm.refs import parse_urn, ref_key, split_range


def make_entry(commentary, target_urn, content="note"):
    key, ref = parse_urn(target_urn)
    start, end = split_range(ref)
    return CommentaryEntry.objects.create(
        commentary=commentary,
        target_urn=target_urn,
        target_key=key,
        ref_start=ref_key(start),
        ref_end=ref_key(end),
        content_html=content,
    )


class CommentaryOverlapTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.c = Commentary.objects.create(slug="nagy", label="Nagy")
        # A range spanning 1.1-1.12 of the Iliad, cited WITHOUT an edition.
        cls.range_note = make_entry(
            cls.c, "urn:cts:greekLit:tlg0012.tlg001:1.1-1.12", "range note"
        )
        # A single-line note.
        cls.point_note = make_entry(
            cls.c, "urn:cts:greekLit:tlg0012.tlg001:1.2", "point note"
        )
        # A note on a different book entirely.
        cls.other_book = make_entry(
            cls.c, "urn:cts:greekLit:tlg0012.tlg001:2.1", "book 2 note"
        )
        # A note on a different work.
        cls.other_work = make_entry(
            cls.c, "urn:cts:greekLit:tlg0011.tlg003:1.1", "other work"
        )

    def get(self, urn, **params):
        return self.client.get(f"/library/commentaries/{urn}/json/", params)

    def test_response_shape(self):
        data = self.get("urn:cts:greekLit:tlg0012.tlg001.perseus-grc2:1.1").json()
        self.assertEqual(set(data), {"results", "current_page", "total_pages"})
        self.assertEqual(
            set(data["results"][0]),
            {"id", "urn", "corresp", "lemma", "content"},
        )

    def test_matches_across_editions(self):
        """Commentary cites tlg0012.tlg001; reader is on .perseus-grc2."""
        data = self.get(
            "urn:cts:greekLit:tlg0012.tlg001.perseus-grc2:1.1"
        ).json()
        self.assertIn("range note", [r["content"] for r in data["results"]])

    def test_range_note_matches_interior_line(self):
        """1.5 falls inside 1.1-1.12 without being an endpoint."""
        data = self.get(
            "urn:cts:greekLit:tlg0012.tlg001.perseus-grc2:1.5"
        ).json()
        self.assertIn("range note", [r["content"] for r in data["results"]])

    def test_line_11_inside_range_ending_at_12(self):
        """Regression guard for lexical vs numeric ordering: naive string
        comparison puts '1.11' after '1.12' and would drop this match."""
        data = self.get(
            "urn:cts:greekLit:tlg0012.tlg001.perseus-grc2:1.11"
        ).json()
        self.assertIn("range note", [r["content"] for r in data["results"]])

    def test_excludes_other_book(self):
        contents = [
            r["content"]
            for r in self.get(
                "urn:cts:greekLit:tlg0012.tlg001.perseus-grc2:1.1"
            ).json()["results"]
        ]
        self.assertNotIn("book 2 note", contents)

    def test_excludes_other_work(self):
        contents = [
            r["content"]
            for r in self.get(
                "urn:cts:greekLit:tlg0012.tlg001.perseus-grc2:1.1"
            ).json()["results"]
        ]
        self.assertNotIn("other work", contents)

    def test_outside_range_returns_nothing(self):
        data = self.get(
            "urn:cts:greekLit:tlg0012.tlg001.perseus-grc2:1.50"
        ).json()
        self.assertEqual(data["results"], [])

    def test_query_range_overlapping_entry_range(self):
        """Reader requests 1.10-1.20; entry covers 1.1-1.12 -> overlap."""
        data = self.get(
            "urn:cts:greekLit:tlg0012.tlg001.perseus-grc2:1.10-1.20"
        ).json()
        self.assertIn("range note", [r["content"] for r in data["results"]])

    def test_malformed_urn_returns_empty_not_error(self):
        resp = self.get("not-a-urn")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["results"], [])

    def test_corresp_preserves_original_target_urn(self):
        data = self.get(
            "urn:cts:greekLit:tlg0012.tlg001.perseus-grc2:1.2"
        ).json()
        corresps = [r["corresp"] for r in data["results"]]
        self.assertIn("urn:cts:greekLit:tlg0012.tlg001:1.2", corresps)

    def test_pagination_present(self):
        data = self.get(
            "urn:cts:greekLit:tlg0012.tlg001.perseus-grc2:1.1"
        ).json()
        self.assertEqual(data["current_page"], 1)
        self.assertGreaterEqual(data["total_pages"], 1)
