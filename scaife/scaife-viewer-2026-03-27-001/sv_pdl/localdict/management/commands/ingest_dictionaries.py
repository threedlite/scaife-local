"""
Ingest dictionaries into local Django DB from TEI XML on disk.

Sources (all bind-mounted read-only into the container):
- LSJ full (Greek): /host-lexica/CTS_XML_TEI/perseus/pdllex/grc/lsj/*.xml
- Lewis & Short (Latin): /host-lexica/CTS_XML_TEI/perseus/pdllex/lat/ls/*.xml
- Middle Liddell (Greek): /host-pdlrefwk/data/viaf66541464/001/*.xml
"""
import glob
import os
import re
from xml.etree import ElementTree as ET

from django.core.management.base import BaseCommand

from sv_pdl.localdict.betacode import beta_to_unicode
from sv_pdl.localdict.models import Dictionary, DictionaryEntry
from sv_pdl.localdict.normalize import nfc, strip_diacritics


LEXICA_ROOT = os.environ.get("LEXICA_DATA_PATH", "/host-lexica")
PDLREFWK_ROOT = os.environ.get(
    "PDLREFWK_DATA_PATH", "/sv-data/cts/PerseusDL-canonical-pdlrefwk-local"
)


def _clean_text(text):
    if not text:
        return ""
    return re.sub(r"\s+", " ", text).strip()


def _entry_intro_text(entry_el, max_chars=1200, greek_element_betacode=False):
    """Serialize entry element to a plain-text summary, capped.

    If greek_element_betacode is True, elements tagged lang="greek" (foreign,
    orth, gen, itype, etc.) contain Betacode and are converted to Unicode.
    """
    parts = []
    if greek_element_betacode:
        for token in _walk_with_lang(entry_el):
            parts.append(token)
    else:
        for t in entry_el.itertext():
            parts.append(t)
    txt = _clean_text("".join(parts))
    if len(txt) > max_chars:
        txt = txt[:max_chars].rsplit(" ", 1)[0] + " …"
    return txt


def _walk_with_lang(el):
    """Yield text tokens; if an element carries lang="greek", its text is
    treated as Betacode and converted to polytonic Unicode."""
    is_greek = el.get("lang") == "greek"
    if el.text:
        yield beta_to_unicode(el.text) if is_greek else el.text
    for child in el:
        yield from _walk_with_lang(child)
        if child.tail:
            yield child.tail


class Command(BaseCommand):
    help = "Ingest LSJ, Lewis & Short, and Middle Liddell into local DB"

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true",
                            help="Drop existing dictionary entries before ingest")

    def handle(self, *args, **options):
        if options["reset"]:
            self.stdout.write("Clearing existing dictionaries…")
            DictionaryEntry.objects.all().delete()
            Dictionary.objects.all().delete()

        self._ingest_lsj()
        self._ingest_lewis_and_short()
        self._ingest_middle_liddell()

        for d in Dictionary.objects.all().order_by("id"):
            n = d.entries.count()
            self.stdout.write(f"  {d.slug:40s}  {n:>8d} entries")

    # ---------------- LSJ ----------------
    def _ingest_lsj(self):
        pattern = os.path.join(
            LEXICA_ROOT, "CTS_XML_TEI/perseus/pdllex/grc/lsj/grc.lsj.perseus-eng*.xml"
        )
        files = sorted(glob.glob(pattern), key=lambda p: int(re.search(r"eng(\d+)", p).group(1)))
        if not files:
            self.stdout.write(self.style.WARNING(f"LSJ files not found at {pattern} — skipping"))
            return
        d, _ = Dictionary.objects.get_or_create(
            slug="lsj", defaults={"label": "LSJ (Liddell-Scott-Jones)", "lang": "grc"}
        )
        d.entries.all().delete()
        self._ingest_entryfree(d, files, headword_from_key=True)

    # ---------------- Lewis & Short ----------------
    def _ingest_lewis_and_short(self):
        pattern = os.path.join(
            LEXICA_ROOT, "CTS_XML_TEI/perseus/pdllex/lat/ls/lat.ls.perseus-eng*.xml"
        )
        files = sorted(glob.glob(pattern), key=lambda p: int(re.search(r"eng(\d+)", p).group(1)))
        if not files:
            self.stdout.write(self.style.WARNING(f"L&S files not found at {pattern} — skipping"))
            return
        # Slug matches upstream widget's hardcoded default for Latin pages
        # (WidgetPerseusDictionary.vue) so it auto-selects on first load.
        d, _ = Dictionary.objects.get_or_create(
            slug="lewis-and-short-latin-dictionary",
            defaults={"label": "Lewis and Short Latin Dictionary", "lang": "lat"},
        )
        d.entries.all().delete()
        self._ingest_entryfree(d, files, headword_from_key=False)

    # ---------------- Middle Liddell ----------------
    def _ingest_middle_liddell(self):
        pattern = os.path.join(PDLREFWK_ROOT, "data/viaf66541464/001/*.xml")
        files = sorted(glob.glob(pattern))
        if not files:
            self.stdout.write(self.style.WARNING(f"Middle Liddell not found at {pattern} — skipping"))
            return
        d, _ = Dictionary.objects.get_or_create(
            slug="middle-liddell",
            defaults={"label": "Middle Liddell", "lang": "grc"},
        )
        d.entries.all().delete()
        self._ingest_entries(d, files)

    # ---------------- shared parsers ----------------
    def _ingest_entryfree(self, d, files, headword_from_key):
        """Parse <entryFree> style TEI (LSJ, L&S).

        Always convert lang="greek" element text via Beta Code, since both
        LSJ (main text) and L&S (embedded Greek etymology) use Betacode.
        The converter is a no-op for non-Greek text passed to it.
        """
        greek = True
        sort_order = 0
        batch = []
        for path in files:
            self.stdout.write(f"  parsing {os.path.basename(path)}")
            for _, entry in ET.iterparse(path, events=("end",)):
                tag = entry.tag.split("}")[-1]
                if tag != "entryFree":
                    continue
                headword_raw, orth_display = self._extract_headword(entry, d.lang, headword_from_key)
                if not orth_display:
                    entry.clear()
                    continue

                normalized = nfc(orth_display)
                stripped = strip_diacritics(normalized).lower()
                intro = _entry_intro_text(entry, greek_element_betacode=greek)

                batch.append(DictionaryEntry(
                    dictionary=d,
                    headword=orth_display,
                    headword_normalized=normalized,
                    headword_normalized_stripped=stripped,
                    intro_text=intro,
                    sort_order=sort_order,
                ))
                sort_order += 1
                entry.clear()
                if len(batch) >= 5000:
                    DictionaryEntry.objects.bulk_create(batch, batch_size=1000)
                    batch = []
        if batch:
            DictionaryEntry.objects.bulk_create(batch, batch_size=1000)

    def _ingest_entries(self, d, files):
        """Parse <entry> style TEI (Middle Liddell)."""
        import io
        # HTML-ish entities the file uses that ETree does not know
        entity_map = {
            "&lpar;": "(", "&rpar;": ")", "&ast;": "*", "&plus;": "+",
            "&equals;": "=", "&colon;": ":", "&quest;": "?",
            "&dagger;": "†", "&mdash;": "—", "&breve;": "̆", "&macr;": "̄",
            "&agrave;": "à", "&eacute;": "é",
        }
        sort_order = 0
        batch = []
        for path in files:
            self.stdout.write(f"  parsing {os.path.basename(path)}")
            with open(path, encoding="utf-8") as fh:
                raw = fh.read()
            for from_ent, to_ent in entity_map.items():
                raw = raw.replace(from_ent, to_ent)
            source = io.StringIO(raw)
            for _, entry in ET.iterparse(source, events=("end",)):
                tag = entry.tag.split("}")[-1]
                if tag != "entry":
                    continue
                # Middle Liddell orth is inside <form><orth>...
                orth_el = entry.find(".//{*}orth")
                if orth_el is None:
                    orth_el = entry.find(".//orth")
                orth_display = _clean_text(orth_el.text if orth_el is not None else "")
                if not orth_display:
                    # fallback to key attribute (rare)
                    orth_display = entry.get("key") or ""
                if not orth_display:
                    entry.clear()
                    continue

                normalized = nfc(orth_display)
                stripped = strip_diacritics(normalized).lower()
                intro = _entry_intro_text(entry)

                batch.append(DictionaryEntry(
                    dictionary=d,
                    headword=orth_display,
                    headword_normalized=normalized,
                    headword_normalized_stripped=stripped,
                    intro_text=intro,
                    sort_order=sort_order,
                ))
                sort_order += 1
                entry.clear()
                if len(batch) >= 5000:
                    DictionaryEntry.objects.bulk_create(batch, batch_size=1000)
                    batch = []
        if batch:
            DictionaryEntry.objects.bulk_create(batch, batch_size=1000)

    def _extract_headword(self, entry_el, lang, from_key):
        """Return (raw_key, display_headword)."""
        key = entry_el.get("key") or ""
        # <orth> child gives display form (may be betacode for LSJ, Unicode for L&S)
        orth_el = entry_el.find(".//{*}orth")
        if orth_el is None:
            orth_el = entry_el.find(".//orth")
        raw_orth = _clean_text(orth_el.text if orth_el is not None else "")

        if lang == "grc":
            # Prefer key (betacode) -> Unicode. Numbers like "a)/1" — strip trailing digit.
            src = re.sub(r"[\d]+$", "", key) if from_key else raw_orth
            if src and any(c.isascii() for c in src):
                # betacode
                display = beta_to_unicode(src)
            else:
                display = src
        else:
            # Latin: <orth> is display, strip trailing digit noise from key
            display = raw_orth or key
            display = re.sub(r"\s*\d+\s*$", "", display).strip()
        return key, display
