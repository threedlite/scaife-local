"""Beta Code -> polytonic Greek conversion.

The LSJ TEI source is Beta Code encoded, so every Greek headword in the
dictionary passes through this. A regression here silently corrupts 116,497
LSJ entries at ingest time, which no view test would notice.
"""
from django.test import SimpleTestCase

from sv_pdl.localdict.betacode import beta_to_unicode
from sv_pdl.localdict.normalize import nfc


class BetaToUnicodeTests(SimpleTestCase):
    def test_plain_lowercase(self):
        self.assertEqual(beta_to_unicode("logos"), "λογος")

    def test_acute_accent(self):
        self.assertEqual(nfc(beta_to_unicode("lo/gos")), nfc("λόγος"))

    def test_circumflex(self):
        self.assertEqual(nfc(beta_to_unicode("mh=nis")), nfc("μῆνις"))

    def test_smooth_breathing_with_acute(self):
        self.assertEqual(nfc(beta_to_unicode("a)/nqrwpos")), nfc("ἄνθρωπος"))

    def test_capital_with_breathing(self):
        """`*` marks a capital and precedes its diacritics."""
        self.assertEqual(nfc(beta_to_unicode("*)axilleu/s")), nfc("Ἀχιλλεύς"))

    def test_final_sigma_handling(self):
        """Whatever the sigma convention is, a word-final sigma must render
        as a sigma character, not be dropped."""
        out = beta_to_unicode("logos")
        self.assertTrue(out.endswith("ς") or out.endswith("σ"), out)

    def test_empty_input(self):
        self.assertEqual(beta_to_unicode(""), "")

    def test_output_is_greek_not_latin(self):
        """Catches a table regression that would leave ASCII passthrough."""
        out = beta_to_unicode("mh=nis")
        self.assertFalse(any(c.isascii() and c.isalpha() for c in out), out)

    def test_is_deterministic(self):
        self.assertEqual(beta_to_unicode("mh=nis"), beta_to_unicode("mh=nis"))
