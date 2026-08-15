"""Collection labels must not depend on rdflib iteration order.

MyCapytain's `get_label` returns the *first* label matching a language from
`graph.objects(...)`, and rdflib promises no ordering. 56 collections in the
Perseus corpora carry more than one English label — five in some cases —
so "first" was effectively arbitrary. It was stable within a given
interpreter and changed between Python 3.9 and 3.12, which the side-by-side
comparison in `DJANGO-UPGRADE.md` §11 caught as 34 work titles flipping
between forms like "Olynthiac 1" and "First Olynthiac".

`scaife_viewer.core.cts.collections.deterministic_label` replaces it with
**shortest, then alphabetical**. Shortest is what makes the choice useful
rather than merely stable — it yields the conventional short form
("Matthew", "1 Corinthians", "Romans") instead of alphabetical's
inconsistent mix ("Gospel according to Matthew" beside "Ephesians").

The unit tests below need no corpus. The integration test pins a handful of
real titles so a future change to the rule, or to the data, is visible.
"""
from django.test import SimpleTestCase, tag

from scaife_viewer.core.cts.collections import deterministic_label


class _Literal(str):
    """Minimal stand-in for an rdflib language-tagged Literal."""

    def __new__(cls, value, language=None):
        obj = super().__new__(cls, value)
        obj.language = language
        return obj


class _Metadata:
    """Stub exposing just the surface deterministic_label touches."""

    def __init__(self, labels, fallback="FALLBACK"):
        self._labels = labels
        self._fallback = fallback
        self.graph = self

    def asNode(self):
        return "node"

    def objects(self, node, predicate):
        return iter(self._labels)

    def get_label(self, lang=None):
        return self._fallback


class DeterministicLabelRuleTests(SimpleTestCase):
    def test_picks_the_shortest_matching_label(self):
        md = _Metadata([
            _Literal("Gospel according to Matthew", "eng"),
            _Literal("Matthew", "eng"),
            _Literal("Gospel of Matthew", "eng"),
        ])
        self.assertEqual(str(deterministic_label(md, lang="eng")), "Matthew")

    def test_alphabetical_breaks_exact_length_ties(self):
        md = _Metadata([_Literal("Beta", "eng"), _Literal("Alfa", "eng")])
        self.assertEqual(str(deterministic_label(md, lang="eng")), "Alfa")

    def test_result_does_not_depend_on_iteration_order(self):
        labels = [
            _Literal("First Olynthiac", "eng"),
            _Literal("Olynthiac 1", "eng"),
        ]
        forward = deterministic_label(_Metadata(labels), lang="eng")
        backward = deterministic_label(_Metadata(list(reversed(labels))), lang="eng")
        self.assertEqual(str(forward), str(backward))
        self.assertEqual(str(forward), "Olynthiac 1")

    def test_other_languages_are_ignored(self):
        md = _Metadata([
            _Literal("Ilias", "lat"),
            _Literal("Iliad", "eng"),
        ])
        self.assertEqual(str(deterministic_label(md, lang="eng")), "Iliad")

    def test_falls_back_when_no_label_matches_the_language(self):
        """Previous behaviour is preserved for collections with no English
        label — get_label may still return one in another language."""
        md = _Metadata([_Literal("Ilias", "lat")], fallback="FALLBACK")
        self.assertEqual(deterministic_label(md, lang="eng"), "FALLBACK")

    def test_empty_metadata_falls_back(self):
        self.assertEqual(deterministic_label(_Metadata([]), lang="eng"), "FALLBACK")


@tag("integration")
class RealCorpusLabelTests(SimpleTestCase):
    """Reads the mounted corpora; run with --integration."""

    # urn -> expected label. Each of these has several English titles in its
    # __cts__.xml, so each one was previously arbitrary.
    EXPECTED = {
        "urn:cts:greekLit:tlg0014.tlg001": "Olynthiac 1",
        "urn:cts:greekLit:tlg0014.tlg004": "Philippic 1",
        "urn:cts:greekLit:tlg0031.tlg001": "Matthew",
        "urn:cts:greekLit:tlg0031.tlg007": "1 Corinthians",
        # Single-label control: must be unaffected by the rule.
        "urn:cts:greekLit:tlg0012.tlg001": "Iliad",
    }

    def test_multi_label_works_resolve_to_the_short_form(self):
        from scaife_viewer.core.cts import collection

        for urn, expected in self.EXPECTED.items():
            with self.subTest(urn=urn):
                self.assertEqual(str(collection(urn).label), expected)

    def test_labels_are_stable_across_repeated_resolution(self):
        from scaife_viewer.core.cts import collection

        urn = "urn:cts:greekLit:tlg0031.tlg001"
        first = str(collection(urn).label)
        self.assertEqual(first, str(collection(urn).label))
