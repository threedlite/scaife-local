"""Local audio API contract: passage-range lookup and byte-range clip serving.

The range query reuses `ref_key` from localcomm, so the same zero-padded
string comparison that orders commentary notes orders clips; the lettered
Theogony lines (929a…929t) are the case that exercises it.
"""
import os
import shutil
import tempfile

from django.test import TestCase

from sv_pdl.localaudio.models import AudioClip, AudioPackage
from sv_pdl.localcomm.refs import ref_key


THEOGONY = "urn:cts:greekLit:tlg0020.tlg001.perseus-grc2"
DELOS_GRC3 = "urn:cts:greekLit:tlg0533.tlg018.perseus-grc3"
DELOS_GRC4 = "urn:cts:greekLit:tlg0533.tlg018.perseus-grc4"


def make_clip(package, version_urn, ref, path=None):
    return AudioClip.objects.create(
        package=package,
        version_urn=version_urn,
        ref=ref,
        ref_key=ref_key(ref),
        path=path or f"X/Y/book_1/line_{ref}.mp4",
    )


class AudioJsonTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.pkg = AudioPackage.objects.create(
            slug="hesiod-test", label="Hesiod test", license="CC BY-SA 4.0",
            attribution="credit line", root_dir="hesiod-test",
        )
        # Live text_html order for 928-931 is 928, 929, 929a..929t, 930, 931.
        cls.refs = ["927", "928", "929"] + [f"929{c}" for c in "abcdefghijklmnopqrst"] + ["930", "931", "932"]
        for r in cls.refs:
            make_clip(cls.pkg, THEOGONY, r)
        make_clip(cls.pkg, DELOS_GRC3, "1")

    def _get(self, urn):
        return self.client.get(f"/library/audio/{urn}/json/")

    def test_range_with_lettered_lines_in_order(self):
        r = self._get(f"{THEOGONY}:928-931")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual(data["package"]["slug"], "hesiod-test")
        self.assertEqual(data["package"]["license"], "CC BY-SA 4.0")
        self.assertEqual(data["package"]["attribution"], "credit line")
        self.assertEqual(
            [c["ref"] for c in data["clips"]],
            ["928", "929"] + [f"929{c}" for c in "abcdefghijklmnopqrst"] + ["930", "931"],
        )
        self.assertEqual(len(data["clips"]), 24)
        # Natural-key URLs: stable across re-ingests, no database id.
        self.assertEqual(
            data["clips"][2]["url"], f"/library/audio/clip/hesiod-test/{THEOGONY}/929a/"
        )

    def test_single_line_and_single_lettered_line(self):
        self.assertEqual([c["ref"] for c in self._get(f"{THEOGONY}:930").json()["clips"]], ["930"])
        self.assertEqual([c["ref"] for c in self._get(f"{THEOGONY}:929c").json()["clips"]], ["929c"])

    def test_text_with_no_package_is_empty_200(self):
        r = self._get("urn:cts:greekLit:tlg0012.tlg001.perseus-grc2:1.1-1.30")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), {"package": None, "clips": []})

    def test_bad_urn_is_404(self):
        self.assertEqual(self._get("not-a-urn").status_code, 404)
        # Version without a passage reference is not a passage.
        self.assertEqual(self._get(THEOGONY).status_code, 404)

    def test_edition_specific(self):
        """Clips for perseus-grc3 must not answer a perseus-grc4 passage."""
        self.assertEqual(len(self._get(f"{DELOS_GRC3}:1-5").json()["clips"]), 1)
        self.assertEqual(self._get(f"{DELOS_GRC4}:1-5").json(), {"package": None, "clips": []})

    def test_lowest_package_wins_when_two_cover_a_text(self):
        other = AudioPackage.objects.create(
            slug="second", label="Second", license="x", root_dir="second"
        )
        make_clip(other, THEOGONY, "930")
        data = self._get(f"{THEOGONY}:930").json()
        self.assertEqual(data["package"]["slug"], "hesiod-test")
        self.assertEqual(len(data["clips"]), 1)


class AudioClipRangeTests(TestCase):
    """The clip view must honour single byte ranges (206) because browsers
    request `bytes=0-` for media and Safari requires range support."""

    @classmethod
    def setUpClass(cls):
        # The files must exist before super().setUpClass(), which is what
        # runs setUpTestData (and therefore needs cls.root).
        cls.root = tempfile.mkdtemp(prefix="sv-audio-")
        os.makedirs(os.path.join(cls.root, "pkg", "A", "B", "book_1"))
        cls.payload = bytes(range(256)) * 4  # 1024 distinctive bytes
        with open(os.path.join(cls.root, "pkg", "A", "B", "book_1", "line_1.mp4"), "wb") as fh:
            fh.write(cls.payload)
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.root, ignore_errors=True)
        super().tearDownClass()

    @classmethod
    def setUpTestData(cls):
        cls.pkg = AudioPackage.objects.create(
            slug="pkg", label="pkg", license="x", root_dir=os.path.join(cls.root, "pkg")
        )
        cls.clip = make_clip(cls.pkg, THEOGONY, "1", path="A/B/book_1/line_1.mp4")
        cls.missing = make_clip(cls.pkg, THEOGONY, "2", path="A/B/book_1/line_2.mp4")

    def _url(self, clip=None):
        c = clip or self.clip
        return f"/library/audio/clip/{c.package.slug}/{c.version_urn}/{c.ref}/"

    def test_plain_get_is_200_with_full_body_and_headers(self):
        r = self.client.get(self._url())
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r["Content-Type"], "audio/mp4")
        self.assertEqual(r["Accept-Ranges"], "bytes")
        self.assertEqual(r["Content-Length"], str(len(self.payload)))
        self.assertIn("max-age=86400", r["Cache-Control"])
        self.assertTrue(r.streaming)
        self.assertEqual(b"".join(r.streaming_content), self.payload)

    def test_open_ended_range_is_206_with_full_length(self):
        r = self.client.get(self._url(), HTTP_RANGE="bytes=0-")
        self.assertEqual(r.status_code, 206)
        self.assertEqual(r["Content-Range"], f"bytes 0-{len(self.payload) - 1}/{len(self.payload)}")
        self.assertEqual(b"".join(r.streaming_content), self.payload)

    def test_bounded_range_is_exact(self):
        r = self.client.get(self._url(), HTTP_RANGE="bytes=100-199")
        self.assertEqual(r.status_code, 206)
        self.assertEqual(r["Content-Range"], f"bytes 100-199/{len(self.payload)}")
        self.assertEqual(r["Content-Length"], "100")
        self.assertEqual(b"".join(r.streaming_content), self.payload[100:200])

    def test_range_past_end_is_clamped(self):
        r = self.client.get(self._url(), HTTP_RANGE="bytes=1000-5000")
        self.assertEqual(r.status_code, 206)
        self.assertEqual(b"".join(r.streaming_content), self.payload[1000:])

    def test_suffix_range(self):
        r = self.client.get(self._url(), HTTP_RANGE="bytes=-24")
        self.assertEqual(r.status_code, 206)
        self.assertEqual(b"".join(r.streaming_content), self.payload[-24:])

    def test_unsatisfiable_range_is_416(self):
        r = self.client.get(self._url(), HTTP_RANGE="bytes=5000-")
        self.assertEqual(r.status_code, 416)
        self.assertEqual(r["Content-Range"], f"bytes */{len(self.payload)}")

    def test_malformed_range_falls_back_to_200(self):
        r = self.client.get(self._url(), HTTP_RANGE="bytes=0-10,20-30")
        self.assertEqual(r.status_code, 200)

    def test_head_carries_headers_and_no_body(self):
        r = self.client.head(self._url(), HTTP_RANGE="bytes=0-9")
        self.assertEqual(r.status_code, 206)
        self.assertEqual(r["Content-Length"], "10")
        self.assertEqual(r.content, b"")

    def test_unknown_key_and_missing_file_are_404(self):
        self.assertEqual(
            self.client.get(f"/library/audio/clip/nope/{THEOGONY}/1/").status_code, 404
        )
        self.assertEqual(
            self.client.get(f"/library/audio/clip/pkg/{THEOGONY}/999/").status_code, 404
        )
        self.assertEqual(self.client.get(self._url(self.missing)).status_code, 404)

    def test_url_survives_reingest(self):
        """Delete and recreate the row: the JSON URL must not change."""
        before = self.client.get(f"/library/audio/{THEOGONY}:1/json/").json()["clips"][0]["url"]
        self.clip.delete()
        type(self).clip = make_clip(self.pkg, THEOGONY, "1", path="A/B/book_1/line_1.mp4")
        after = self.client.get(f"/library/audio/{THEOGONY}:1/json/").json()["clips"][0]["url"]
        self.assertEqual(before, after)
        self.assertEqual(self.client.get(after).status_code, 200)

    def test_path_outside_package_root_is_404(self):
        escaped = make_clip(self.pkg, THEOGONY, "3", path="../../etc/passwd")
        self.assertEqual(self.client.get(self._url(escaped)).status_code, 404)
