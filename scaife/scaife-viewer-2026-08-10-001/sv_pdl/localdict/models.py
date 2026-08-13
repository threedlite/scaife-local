from django.db import models


class Dictionary(models.Model):
    slug = models.SlugField(max_length=80, unique=True)
    label = models.CharField(max_length=200)
    lang = models.CharField(max_length=8)  # grc | lat

    def __str__(self):
        return self.label

    @property
    def urn(self):
        return f"urn:cite2:scaife-viewer:dictionaries.local:{self.slug}"


class DictionaryEntry(models.Model):
    dictionary = models.ForeignKey(
        Dictionary, on_delete=models.CASCADE, related_name="entries"
    )
    # Display form (Unicode Greek / Latin as it appears)
    headword = models.CharField(max_length=200)
    # Same as headword but NFC-normalized (used for lookup)
    headword_normalized = models.CharField(max_length=200, db_index=True)
    # Stripped: no accents, no macrons/breves, lowercase (used for lemma lookup)
    headword_normalized_stripped = models.CharField(max_length=200, db_index=True)
    # HTML-ish rendering of the first paragraph of the entry
    intro_text = models.TextField()
    # Preserve original insertion order for stable pagination
    sort_order = models.PositiveIntegerField(default=0, db_index=True)

    class Meta:
        indexes = [
            models.Index(fields=["dictionary", "headword_normalized_stripped"]),
        ]
        ordering = ["sort_order", "id"]

    def __str__(self):
        return f"{self.headword} ({self.dictionary.slug})"
