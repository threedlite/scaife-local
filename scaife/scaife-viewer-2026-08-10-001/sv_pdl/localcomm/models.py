from django.db import models


class Commentary(models.Model):
    """A named commentary source (e.g. Nagy on Iliad)."""

    # Declared explicitly rather than left to the framework default. An
    # implicit pk is AutoField under Django 2.2 but BigAutoField from 3.2
    # once this app's AppConfig.default_auto_field is honoured, which would
    # silently ALTER the column mid-upgrade. Naming it here pins the type
    # across every Django version.
    id = models.BigAutoField(primary_key=True)
    slug = models.SlugField(max_length=120, unique=True)
    label = models.CharField(max_length=200)
    author = models.CharField(max_length=200, blank=True)
    source_repo = models.CharField(max_length=200, blank=True)

    def __str__(self):
        return self.label


class CommentaryEntry(models.Model):
    """A single note keyed to a target CTS passage URN."""

    id = models.BigAutoField(primary_key=True)
    commentary = models.ForeignKey(
        Commentary, on_delete=models.CASCADE, related_name="entries"
    )
    # The target URN as written by the commentary source, e.g.
    #   urn:cts:greekLit:tlg0012.tlg001:1.1-1.12
    target_urn = models.CharField(max_length=300, db_index=True)
    # Canonicalized textgroup+work "greekLit:tlg0012.tlg001" for join lookup
    target_key = models.CharField(max_length=120, db_index=True)
    # First and last reference tokens covered ("1.1" and "1.12"), zero-padded
    ref_start = models.CharField(max_length=64, db_index=True)
    ref_end = models.CharField(max_length=64, db_index=True)

    citation_urn = models.CharField(max_length=300, blank=True)
    lemma = models.CharField(max_length=200, blank=True)
    content_html = models.TextField()

    class Meta:
        indexes = [
            # Named explicitly. An unnamed Index gets a generated name whose
            # hash is not stable across Django versions, so the migration and
            # the live database disagree about what the index is called and
            # every makemigrations proposes to drop and recreate it.
            models.Index(
                fields=["target_key", "ref_start", "ref_end"],
                name="localcomm_entry_target_idx",
            ),
        ]
        ordering = ["target_key", "ref_start", "id"]

    def __str__(self):
        return f"{self.commentary.slug}: {self.target_urn}"
