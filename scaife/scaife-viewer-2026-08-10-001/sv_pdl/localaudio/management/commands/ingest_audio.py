"""
Ingest line-level audio packages from the read-only audio mount.

Layout expected under each audio root. Roots come from AUDIO_DATA_PATHS
(os.pathsep-separated; default "/host-audio-samples:/host-audio", i.e. the
sample package tracked in this repo, then the user-staged packages):

    <package-dir>/package.yaml
    <package-dir>/<Author>/<Work>/book_<N>/line_<ref>.mp4

`package.yaml` supplies what the audio tree does not carry: the CTS
version URN for each `<Author>/<Work>` folder and whether the text is
cited `<book>.<line>` (cited_by_book: true) or `<line>` alone. See
AUDIO-PROPOSAL.md, sections 4.1–4.2 and Appendix A.3.

Idempotent: the package row is get_or_create'd by slug and its clips are
replaced, so re-running never duplicates. Nothing is copied; the database
stores paths relative to the package directory.
"""
import os
import re
from xml.etree import ElementTree as ET

import yaml

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction

from sv_pdl.localaudio.models import AudioClip, AudioPackage
from sv_pdl.localaudio.urns import tei_path_for_version
from sv_pdl.localcomm.refs import ref_key


AUDIO_ROOTS = [
    p for p in os.environ.get("AUDIO_DATA_PATHS", "/host-audio-samples:/host-audio").split(os.pathsep)
    if p
]
MANIFEST = "package.yaml"
_LINE_RE = re.compile(r"^line_([^/]+)\.mp4$")
_BOOK_RE = re.compile(r"^book_([^/]+)$")
_TEI_NS = "{http://www.tei-c.org/ns/1.0}"


def _work_entry(entry, default_cited_by_book):
    """A `works:` value is either a URN string or {urn, cited_by_book}."""
    if isinstance(entry, str):
        return entry, default_cited_by_book
    return entry["urn"], bool(entry.get("cited_by_book", default_cited_by_book))


def tei_line_refs(path):
    """All `<l n>` references in a TEI file as the viewer cites them:
    `<book>.<line>` when the edition has top-level textpart divs, else
    `<line>`. Parses the XML directly rather than asking the CTS resolver,
    which cannot see lines nested inside <sp> (AUDIO-PROPOSAL.md A.4)."""
    root = ET.parse(path).getroot()
    edition = root.find(f".//{_TEI_NS}text/{_TEI_NS}body/{_TEI_NS}div")
    if edition is None:
        return set()
    tops = [
        d for d in edition.findall(f"./{_TEI_NS}div")
        if d.get("type") == "textpart" and d.get("n")
    ]
    refs = set()
    if tops:
        for top in tops:
            for line in top.iter(f"{_TEI_NS}l"):
                if line.get("n"):
                    refs.add(f"{top.get('n')}.{line.get('n')}")
    else:
        for line in edition.iter(f"{_TEI_NS}l"):
            if line.get("n"):
                refs.add(line.get("n"))
    return refs


class Command(BaseCommand):
    help = "Ingest audio packages (package.yaml + mp4 tree) from the audio mount"

    def add_arguments(self, parser):
        parser.add_argument(
            "--root", action="append", default=None,
            help="Directory holding one sub-directory per package; repeatable "
                 f"(default {os.pathsep.join(AUDIO_ROOTS)})",
        )
        parser.add_argument(
            "--reset", action="store_true",
            help="Delete every package and clip before ingesting",
        )
        parser.add_argument(
            "--no-coverage", action="store_true",
            help="Skip the TEI coverage report",
        )
        parser.add_argument(
            "--resolver-check", action="store_true",
            help="Also report lines the CTS resolver cannot address (slow on big texts)",
        )

    def handle(self, *args, **options):
        roots = options["root"] or AUDIO_ROOTS
        if options["reset"]:
            self.stdout.write("Clearing existing audio packages…")
            AudioClip.objects.all().delete()
            AudioPackage.objects.all().delete()

        found = 0
        for root in roots:
            if not os.path.isdir(root):
                self.stdout.write(self.style.WARNING(f"audio root {root} not found — skipping"))
                continue
            manifests = sorted(
                d for d in os.listdir(root)
                if os.path.isfile(os.path.join(root, d, MANIFEST))
            )
            if not manifests:
                self.stdout.write(self.style.WARNING(f"no {MANIFEST} under {root} — nothing to ingest"))
                continue
            for package_dir in manifests:
                self._ingest_package(root, package_dir, options)
                found += 1
        if not found:
            return

        for p in AudioPackage.objects.all().order_by("id"):
            self.stdout.write(f"  {p.slug:48s}  {p.clip_count:>8d} clips")

    def _ingest_package(self, root, package_dir, options):
        base = os.path.join(root, package_dir)
        with open(os.path.join(base, MANIFEST), encoding="utf-8") as fh:
            manifest = yaml.safe_load(fh) or {}

        slug = manifest.get("slug") or package_dir
        default_cited_by_book = bool(manifest.get("cited_by_book", False))
        works = {
            folder: _work_entry(entry, default_cited_by_book)
            for folder, entry in (manifest.get("works") or {}).items()
        }
        if not works:
            self.stdout.write(self.style.WARNING(f"{package_dir}: manifest has no works — skipping"))
            return

        package, _ = AudioPackage.objects.get_or_create(
            slug=slug, defaults={"label": manifest.get("label", slug), "root_dir": base}
        )
        package.label = manifest.get("label", slug)
        package.license = manifest.get("license", "")
        package.attribution = manifest.get("attribution", "") or ""
        package.source_url = manifest.get("source", "") or ""
        # Absolute path of the package directory (packages may live under
        # any of the configured roots); clip paths are relative to it.
        package.root_dir = os.path.abspath(base)

        clips, per_work, skipped = [], {}, []
        for dirpath, _dirs, files in os.walk(base):
            for name in sorted(files):
                if not name.endswith(".mp4"):
                    continue
                rel = os.path.relpath(os.path.join(dirpath, name), base)
                parts = rel.split(os.sep)
                m_line = _LINE_RE.match(parts[-1])
                m_book = _BOOK_RE.match(parts[-2]) if len(parts) == 4 else None
                folder = "/".join(parts[:2]) if len(parts) == 4 else None
                if not (m_line and m_book and folder in works):
                    skipped.append(rel)
                    continue
                if os.path.getsize(os.path.join(dirpath, name)) == 0:
                    skipped.append(rel + " (empty)")
                    continue
                version_urn, cited_by_book = works[folder]
                ref = f"{m_book.group(1)}.{m_line.group(1)}" if cited_by_book else m_line.group(1)
                clips.append(AudioClip(
                    package=package, version_urn=version_urn, ref=ref,
                    ref_key=ref_key(ref), path=rel.replace(os.sep, "/"),
                ))
                per_work[folder] = per_work.get(folder, 0) + 1

        with transaction.atomic():
            package.clips.all().delete()
            AudioClip.objects.bulk_create(clips, batch_size=2000)
            package.clip_count = len(clips)
            package.save()

        self.stdout.write(f"{slug}: {len(clips)} clips from {package.root_dir}/")
        for folder, n in sorted(per_work.items()):
            self.stdout.write(f"    {folder:50s} {n:>7d}  -> {works[folder][0]}")
        for folder in works:
            if folder not in per_work:
                self.stdout.write(self.style.WARNING(f"    {folder}: declared in manifest but no files found"))
        if skipped:
            self.stdout.write(self.style.WARNING(f"    skipped {len(skipped)} file(s) that did not parse or are unmapped:"))
            for rel in skipped[:20]:
                self.stdout.write(f"      {rel}")

        if not options["no_coverage"]:
            self._coverage(package, works, options["resolver_check"])

    def _coverage(self, package, works, resolver_check):
        """Compare clip refs with the TEI's <l n> values, per version URN."""
        data_path = getattr(settings, "CTS_LOCAL_DATA_PATH", None)
        if not data_path:
            self.stdout.write("    coverage: CTS_LOCAL_DATA_PATH not set — skipped")
            return
        columns = "TEI lines / clips / missing / extra"
        if resolver_check:
            columns += " / unreachable-in-viewer"
        self.stdout.write(f"    coverage ({columns}):")
        for folder, (version_urn, _cited) in sorted(works.items()):
            tei = tei_path_for_version(version_urn, data_path)
            if not tei:
                self.stdout.write(f"      {version_urn}: TEI file not found under {data_path}")
                continue
            tei_refs = tei_line_refs(tei)
            clip_refs = set(
                package.clips.filter(version_urn=version_urn).values_list("ref", flat=True)
            )
            missing = sorted(tei_refs - clip_refs, key=ref_key)
            extra = sorted(clip_refs - tei_refs, key=ref_key)
            line = (f"      {version_urn}: {len(tei_refs)} / {len(clip_refs)} / "
                    f"{len(missing)} / {len(extra)}")
            if resolver_check:
                line += f" / {self._unreachable(version_urn, tei_refs)}"
            self.stdout.write(line)
            if missing:
                self.stdout.write(f"        missing: {', '.join(missing[:15])}{' …' if len(missing) > 15 else ''}")
            if extra:
                self.stdout.write(self.style.WARNING(
                    f"        extra (no such TEI line): {', '.join(extra[:15])}{' …' if len(extra) > 15 else ''}"
                ))

    def _unreachable(self, version_urn, tei_refs):
        """Lines the viewer's TOC cannot address (deepest-level getReffs)."""
        try:
            from scaife_viewer.core.cts import collection
            from scaife_viewer.core.cts.capitains import default_resolver

            depth = collection(version_urn).metadata.citation.depth
            reachable = {
                str(r) for r in default_resolver().getReffs(version_urn, level=depth)
            }
        except Exception as exc:  # noqa: BLE001 — informational only
            return f"resolver error: {exc}"
        return len(tei_refs - reachable)
