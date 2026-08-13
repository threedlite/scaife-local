"""
Ingest open-license commentaries from Open-Commentaries markdown files.

Sources (bind-mounted under /host-commentaries in the container):
- homer.opencommentaries.org       (MIT)
- pausanias.opencommentaries.org   (MIT)
- pindar.opencommentaries.org      (MIT)
"""
import glob
import html
import os
import re

from django.core.management.base import BaseCommand

from sv_pdl.localcomm.models import Commentary, CommentaryEntry
from sv_pdl.localcomm.refs import parse_urn, ref_key, split_range


COMM_ROOT = os.environ.get("COMMENTARIES_DATA_PATH", "/host-commentaries")

SOURCES = [
    # (repo-relative glob, source slug)
    ("homer.opencommentaries.org/commentary/*.md", "homer"),
    ("pausanias.opencommentaries.org/static/commentaries/*.md", "pausanias"),
    ("pindar.opencommentaries.org/priv/static/commentary/*.md", "pindar"),
]


def _split_frontmatter(text):
    """Split off leading YAML frontmatter (--- ... ---)."""
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            body = text[end + 4:].lstrip("\n")
            fm = text[3:end].strip()
            return fm, body
    return "", text


def _parse_frontmatter(fm):
    meta = {}
    for line in fm.splitlines():
        m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*):\s*(.*)$", line)
        if m:
            meta[m.group(1)] = m.group(2).strip().strip('"').strip("'")
    return meta


def _md_to_html(md):
    """Very small Markdown-ish -> HTML for commentary body text."""
    if not md:
        return ""
    text = md.strip()
    # Escape raw HTML/entities first, then re-inject our tags
    text = html.escape(text)
    # bold **x**  (before italic single-*)
    text = re.sub(r"\*\*([^*\n]+)\*\*", r"<strong>\1</strong>", text)
    # italic *x*
    text = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"<em>\1</em>", text)
    # paragraphs on blank-line splits
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    return "\n".join(f"<p>{p.replace(chr(10), ' ')}</p>" for p in paragraphs)


# A record within the markdown starts with `@urn:cts:…` on its own line,
# then optional colon-metadata lines, then blank line, then Markdown body.
RECORD_URN_RE = re.compile(r"^@(urn:cts:\S+)\s*$", re.MULTILINE)


def _iter_records(body):
    """Yield (target_urn, metadata_dict, content_md) tuples from a body."""
    matches = list(RECORD_URN_RE.finditer(body))
    for i, m in enumerate(matches):
        target_urn = m.group(1)
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        chunk = body[start:end]
        lines = chunk.splitlines()

        meta = {}
        j = 0
        # skip blank lines before the metadata block
        while j < len(lines) and lines[j].strip() == "":
            j += 1
        # consume :key: value lines
        while j < len(lines):
            mm = re.match(r"^:([A-Za-z_][A-Za-z0-9_]*):\s*(.*)$", lines[j])
            if not mm:
                break
            meta[mm.group(1)] = mm.group(2).strip()
            j += 1
        # skip blanks between metadata and prose
        while j < len(lines) and lines[j].strip() == "":
            j += 1

        prose = "\n".join(lines[j:]).strip()
        prose = re.sub(r"\n---+\s*$", "", prose).strip()
        yield target_urn, meta, prose


class Command(BaseCommand):
    help = "Ingest open commentaries from Open-Commentaries markdown files"

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true",
                            help="Drop existing commentary entries before ingest")

    def handle(self, *args, **options):
        if options["reset"]:
            self.stdout.write("Clearing existing commentaries…")
            CommentaryEntry.objects.all().delete()
            Commentary.objects.all().delete()

        for pattern, src_slug in SOURCES:
            paths = sorted(glob.glob(os.path.join(COMM_ROOT, pattern)))
            if not paths:
                self.stdout.write(self.style.WARNING(
                    f"no files matched {pattern}"
                ))
                continue
            for path in paths:
                self._ingest_file(path, src_slug)

        for c in Commentary.objects.all().order_by("slug"):
            n = c.entries.count()
            self.stdout.write(f"  {c.slug:40s}  {n:>6d} entries")

    def _ingest_file(self, path, src_slug):
        fname = os.path.basename(path)  # e.g. gregory_nagy.md
        shortname = fname.rsplit(".", 1)[0]
        with open(path, encoding="utf-8") as f:
            raw = f.read()
        fm, body = _split_frontmatter(raw)
        meta = _parse_frontmatter(fm)

        author = meta.get("author") or meta.get("authors") or shortname.replace("_", " ").title()
        title = meta.get("title") or f"{src_slug.title()} commentary by {author}"

        slug = f"{src_slug}-{shortname}".lower().replace("_", "-")
        commentary, _ = Commentary.objects.get_or_create(
            slug=slug,
            defaults={
                "label": title[:200],
                "author": author[:200],
                "source_repo": src_slug,
            },
        )
        # If re-running without --reset, replace this commentary's entries
        commentary.entries.all().delete()

        batch = []
        for target_urn, r_meta, prose in _iter_records(body):
            target_key, ref = parse_urn(target_urn)
            if not target_key:
                continue
            start, end = split_range(ref)
            content_html = _md_to_html(prose)
            batch.append(CommentaryEntry(
                commentary=commentary,
                target_urn=target_urn,
                target_key=target_key,
                ref_start=ref_key(start),
                ref_end=ref_key(end) or ref_key(start),
                citation_urn=r_meta.get("citation_urn", ""),
                lemma="",
                content_html=content_html,
            ))
            if len(batch) >= 2000:
                CommentaryEntry.objects.bulk_create(batch, batch_size=500)
                batch = []
        if batch:
            CommentaryEntry.objects.bulk_create(batch, batch_size=500)
