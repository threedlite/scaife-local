"""Reference/URN helpers behind commentary passage matching.

These are pure functions with no Django dependency, but the invariants they
encode are what the commentary ORM query relies on. If an upgrade changes
string handling or regex behaviour, these fail before the view tests do.
"""
from django.test import SimpleTestCase

from sv_pdl.localcomm.refs import parse_urn, ref_key, split_range


class ParseUrnTests(SimpleTestCase):
    def test_drops_version_for_cross_edition_matching(self):
        """The whole point of target_key: a commentary written against
        `tlg0012.tlg001` must match a passage read from a specific edition
        such as `tlg0012.tlg001.perseus-grc2`."""
        with_version, _ = parse_urn(
            "urn:cts:greekLit:tlg0012.tlg001.perseus-grc2:1.5"
        )
        without_version, _ = parse_urn("urn:cts:greekLit:tlg0012.tlg001:1.1-1.12")
        self.assertEqual(with_version, "greekLit:tlg0012.tlg001")
        self.assertEqual(with_version, without_version)

    def test_returns_passage_ref(self):
        _, ref = parse_urn("urn:cts:greekLit:tlg0012.tlg001.perseus-grc2:1.5")
        self.assertEqual(ref, "1.5")

    def test_missing_ref_is_empty_not_none(self):
        key, ref = parse_urn("urn:cts:greekLit:tlg0012.tlg001")
        self.assertEqual(key, "greekLit:tlg0012.tlg001")
        self.assertEqual(ref, "")

    def test_rejects_non_cts_input(self):
        for bad in ["", None, "not-a-urn", "urn:cite2:foo:bar", "urn:cts:"]:
            with self.subTest(bad=bad):
                self.assertEqual(parse_urn(bad), (None, None))

    def test_latin_namespace(self):
        key, ref = parse_urn("urn:cts:latinLit:phi0690.phi003.perseus-lat2:1.1")
        self.assertEqual(key, "latinLit:phi0690.phi003")
        self.assertEqual(ref, "1.1")


class SplitRangeTests(SimpleTestCase):
    def test_range(self):
        self.assertEqual(split_range("1.1-1.12"), ("1.1", "1.12"))

    def test_single_ref_becomes_degenerate_range(self):
        self.assertEqual(split_range("1.1"), ("1.1", "1.1"))

    def test_empty(self):
        self.assertEqual(split_range(""), ("", ""))

    def test_strips_word_anchor(self):
        """Open-Commentaries targets can carry an `@word` anchor, which must
        not leak into range comparison."""
        self.assertEqual(split_range("1.1@προΐαψεν"), ("1.1", "1.1"))
        self.assertEqual(split_range("1.1@a-1.5@b"), ("1.1", "1.5"))


class RefKeyTests(SimpleTestCase):
    def test_zero_pads_each_component(self):
        self.assertEqual(ref_key("1.11"), "000001.000011")
        self.assertEqual(ref_key("1.1"), "000001.000001")

    def test_ordering_is_numeric_not_lexical(self):
        """This is the invariant that makes the SQL range query correct:
        the DB compares these as strings, so 9 must sort before 11."""
        self.assertLess(ref_key("1.9"), ref_key("1.11"))
        self.assertLess(ref_key("2.1"), ref_key("10.1"))
        self.assertLess(ref_key("1.1"), ref_key("1.2"))

    def test_naive_string_compare_would_be_wrong(self):
        """Guards against someone 'simplifying' ref_key away."""
        self.assertGreater("1.9", "1.11")  # the bug we are avoiding

    def test_non_numeric_tokens_survive(self):
        self.assertEqual(ref_key("pr.1"), "pr.000001")

    def test_alpha_suffix_preserved(self):
        self.assertEqual(ref_key("1.1a"), "000001.000001a")

    def test_empty(self):
        self.assertEqual(ref_key(""), "")
