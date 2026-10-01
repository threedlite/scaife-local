"""`ingest_audio` against a temporary package tree: path parsing, the
book-cited reference rule, per-work overrides, idempotency, and skipping.
"""
import os
import shutil
import tempfile
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from sv_pdl.localaudio.models import AudioClip, AudioPackage


THEOGONY = "urn:cts:greekLit:tlg0020.tlg001.perseus-grc2"
ARGONAUTICA = "urn:cts:greekLit:tlg0001.tlg001.perseus-grc2"
FRAGMENTA = "urn:cts:greekLit:tlg0036.tlg003.perseus-grc2"

MANIFEST = f"""
slug: test-pkg
label: Test package
license: CC BY-SA 4.0
attribution: |
  Keep this notice.
source: https://example.invalid/pkg
cited_by_book: false
works:
  "Hesiod/Theogony": {THEOGONY}
  "Apollonius Rhodius/Argonautica": {{urn: {ARGONAUTICA}, cited_by_book: true}}
  "Bion of Phlossa/Fragmenta": {{urn: {FRAGMENTA}, cited_by_book: true}}
"""


def touch(root, rel, size=16):
    path = os.path.join(root, *rel.split("/"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(b"\0" * size)


class IngestAudioTests(TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="sv-audio-ingest-")
        self.addCleanup(shutil.rmtree, self.root, True)
        pkg = os.path.join(self.root, "test-pkg")
        os.makedirs(pkg)
        with open(os.path.join(pkg, "package.yaml"), "w", encoding="utf-8") as fh:
            fh.write(MANIFEST)
        touch(pkg, "Hesiod/Theogony/book_1/line_1.mp4")
        touch(pkg, "Hesiod/Theogony/book_1/line_929a.mp4")
        touch(pkg, "Apollonius Rhodius/Argonautica/book_2/line_382a.mp4")
        touch(pkg, "Apollonius Rhodius/Argonautica/book_2/line_382.mp4")
        touch(pkg, "Bion of Phlossa/Fragmenta/book_3/line_1.mp4")
        touch(pkg, "Nonnus/Dionysiaca/book_1/line_0.mp4")        # not in manifest
        touch(pkg, "Hesiod/Theogony/book_1/notes.txt")           # not mp4
        touch(pkg, "Hesiod/Theogony/line_5.mp4")                 # no book_ segment
        touch(pkg, "Hesiod/Theogony/book_1/line_7.mp4", size=0)  # empty file

    def _run(self, *extra):
        out = StringIO()
        call_command("ingest_audio", "--root", self.root, "--no-coverage", *extra, stdout=out)
        return out.getvalue()

    def test_rows_refs_and_keys(self):
        out = self._run()
        pkg = AudioPackage.objects.get(slug="test-pkg")
        self.assertEqual(pkg.label, "Test package")
        self.assertEqual(pkg.license, "CC BY-SA 4.0")
        self.assertIn("Keep this notice.", pkg.attribution)
        self.assertEqual(pkg.root_dir, os.path.join(self.root, "test-pkg"))
        self.assertEqual(pkg.clip_count, 5)
        refs = {(c.version_urn, c.ref): c for c in pkg.clips.all()}
        self.assertEqual(
            set(refs),
            {
                (THEOGONY, "1"), (THEOGONY, "929a"),
                (ARGONAUTICA, "2.382a"), (ARGONAUTICA, "2.382"),
                (FRAGMENTA, "3.1"),
            },
        )
        self.assertEqual(refs[(THEOGONY, "929a")].ref_key, "000929a")
        self.assertEqual(refs[(ARGONAUTICA, "2.382a")].ref_key, "000002.000382a")
        self.assertEqual(refs[(THEOGONY, "1")].path, "Hesiod/Theogony/book_1/line_1.mp4")
        # Skips are reported, not raised.
        self.assertIn("skipped 3 file(s)", out)
        self.assertIn("Nonnus/Dionysiaca/book_1/line_0.mp4", out)
        self.assertIn("line_7.mp4 (empty)", out)

    def test_idempotent(self):
        self._run()
        first = sorted(AudioClip.objects.values_list("version_urn", "ref"))
        self._run()
        self.assertEqual(AudioPackage.objects.count(), 1)
        self.assertEqual(sorted(AudioClip.objects.values_list("version_urn", "ref")), first)

    def test_reset_clears_previous_packages(self):
        AudioPackage.objects.create(slug="stale", label="stale", license="x", root_dir="stale")
        self._run("--reset")
        self.assertEqual(list(AudioPackage.objects.values_list("slug", flat=True)), ["test-pkg"])

    def test_missing_root_is_a_warning_not_an_error(self):
        out = StringIO()
        call_command("ingest_audio", "--root", os.path.join(self.root, "nope"), stdout=out)
        self.assertIn("not found", out.getvalue())
        self.assertEqual(AudioPackage.objects.count(), 0)

    def test_multiple_roots_are_all_walked(self):
        second = tempfile.mkdtemp(prefix="sv-audio-ingest2-")
        self.addCleanup(shutil.rmtree, second, True)
        os.makedirs(os.path.join(second, "other"))
        with open(os.path.join(second, "other", "package.yaml"), "w", encoding="utf-8") as fh:
            fh.write(f'slug: other\nworks:\n  "Hesiod/Theogony": {THEOGONY}\n')
        touch(os.path.join(second, "other"), "Hesiod/Theogony/book_1/line_2.mp4")
        out = StringIO()
        call_command(
            "ingest_audio", "--root", self.root, "--root", second, "--no-coverage", stdout=out
        )
        self.assertEqual(
            sorted(AudioPackage.objects.values_list("slug", flat=True)), ["other", "test-pkg"]
        )
        self.assertEqual(AudioPackage.objects.get(slug="other").root_dir, os.path.join(second, "other"))
