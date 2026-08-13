"""Unicode normalization helpers used for accent-insensitive lookup.

Dictionary lookup from the reader passes an inflected/accented form, so
`headword_normalized_stripped` must be stable across Python and ICU
upgrades. `unicodedata` is tied to the CPython build, which makes this a
genuine upgrade risk rather than a formality.

Composed/decomposed forms are built with `unicodedata` rather than written
as literals, so this file's own encoding cannot make the tests vacuous.
"""
import unicodedata

from django.test import SimpleTestCase

from sv_pdl.localdict.normalize import nfc, strip_diacritics


class StripDiacriticsTests(SimpleTestCase):
    def test_strips_greek_accents_and_breathings(self):
        self.assertEqual(strip_diacritics("μῆνις"), "μηνις")
        self.assertEqual(strip_diacritics("ἄνθρωπος"), "ανθρωπος")

    def test_strips_latin_macrons(self):
        self.assertEqual(strip_diacritics("ārma"), "arma")

    def test_precomposed_and_decomposed_agree(self):
        """The same word encoded either way must collapse to one key, or
        lookups silently miss."""
        precomposed = unicodedata.normalize("NFC", "ἄνθρωπος")
        decomposed = unicodedata.normalize("NFD", "ἄνθρωπος")
        self.assertNotEqual(precomposed, decomposed)  # genuinely different
        self.assertEqual(
            strip_diacritics(precomposed), strip_diacritics(decomposed)
        )

    def test_is_idempotent(self):
        once = strip_diacritics("μῆνις")
        self.assertEqual(strip_diacritics(once), once)

    def test_leaves_unaccented_text_alone(self):
        self.assertEqual(strip_diacritics("logos"), "logos")

    def test_empty(self):
        self.assertEqual(strip_diacritics(""), "")


class NfcTests(SimpleTestCase):
    def test_composes_decomposed_input(self):
        decomposed = unicodedata.normalize("NFD", "ἄ")
        self.assertGreater(len(decomposed), 1)
        self.assertEqual(nfc(decomposed), unicodedata.normalize("NFC", "ἄ"))

    def test_idempotent(self):
        once = nfc(unicodedata.normalize("NFD", "ἄ"))
        self.assertEqual(nfc(once), once)
