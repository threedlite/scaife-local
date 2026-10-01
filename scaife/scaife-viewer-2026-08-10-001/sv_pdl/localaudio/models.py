"""Line-level audio clips keyed by CTS version URN + reference.

The clips themselves stay on a read-only bind mount (`/host-audio`); the
database holds only the package metadata and one row per clip, so a
re-ingest is cheap and the files are never copied.
"""
from django.db import models


class AudioPackage(models.Model):
    # See the note in sv_pdl/localcomm/models.py: an implicit pk changes type
    # between Django versions, so it is pinned here instead.
    id = models.BigAutoField(primary_key=True)
    slug = models.SlugField(max_length=80, unique=True)
    label = models.CharField(max_length=200)
    license = models.CharField(max_length=80)
    # Verbatim attribution notice; CC BY-SA requires it to travel with the
    # audio, so it is stored with the package and shown in the widget.
    attribution = models.TextField(blank=True)
    source_url = models.CharField(max_length=300, blank=True)
    # Absolute directory holding this package's tree (under one of the audio
    # mounts: /host-audio-samples for the bundled sample, /host-audio for
    # user-staged packages). Clip paths are relative to it.
    root_dir = models.CharField(max_length=200)
    clip_count = models.PositiveIntegerField(default=0)

    def __str__(self):
        return self.label


class AudioClip(models.Model):
    id = models.BigAutoField(primary_key=True)
    package = models.ForeignKey(
        AudioPackage, on_delete=models.CASCADE, related_name="clips"
    )
    # Full version URN, e.g. urn:cts:greekLit:tlg0020.tlg001.perseus-grc2.
    # Audio is edition-specific, unlike commentaries, so the edition is kept.
    version_urn = models.CharField(max_length=200)
    # Reference exactly as the viewer cites it: "929a", "2.382a", "21.74_75".
    ref = models.CharField(max_length=40)
    # Zero-padded sort key from sv_pdl.localcomm.refs.ref_key, so a page
    # range query is a plain string comparison.
    ref_key = models.CharField(max_length=120)
    # Path relative to the package root, e.g. Hesiod/Theogony/book_1/line_1.mp4
    path = models.CharField(max_length=400)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["package", "version_urn", "ref"],
                name="localaudio_clip_unique",
            ),
        ]
        indexes = [
            models.Index(
                fields=["version_urn", "ref_key"], name="localaudio_clip_ref_idx"
            ),
        ]
        ordering = ["ref_key", "id"]

    def __str__(self):
        return f"{self.version_urn}:{self.ref}"
