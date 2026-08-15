"""Assert the static files backend is the one we think it is.

This exists because of a real, silent regression during the Django 5.2
upgrade. `STATICFILES_STORAGE` was *removed* in Django 5.1 — not deprecated
and still honoured, simply ignored. The setting stayed in `settings.py`,
looked correct in review, and Django quietly fell back to the plain
`StaticFilesStorage`:

* no content-hashed filenames, so cache busting stopped working;
* no gzip/brotli precompression, so whitenoise served uncompressed assets;
* `collectstatic` stopped post-processing.

Every page still returned 200, every existing test still passed, and the
setting that was supposed to control this was sitting right there in
settings.py. Nothing in the suite looked at the *resolved* backend.

So: check the resolved object, not the setting.
"""
from django.contrib.staticfiles.storage import staticfiles_storage
from django.test import SimpleTestCase


class StaticFilesStorageTests(SimpleTestCase):
    def test_whitenoise_compressed_manifest_storage_is_active(self):
        resolved = type(staticfiles_storage)
        # ConfiguredStorage is a lazy proxy; unwrap it if present.
        actual = getattr(staticfiles_storage, "_wrapped", staticfiles_storage)
        name = f"{type(actual).__module__}.{type(actual).__name__}"
        self.assertIn(
            "whitenoise",
            name,
            f"static files are being served by {name}, not whitenoise. "
            f"Django 5.1 removed STATICFILES_STORAGE — the backend is now "
            f"configured under STORAGES['staticfiles']. Resolved class was "
            f"{resolved}.",
        )

    def test_storage_hashes_filenames(self):
        """The manifest behaviour is the point, not just the class name."""
        actual = getattr(staticfiles_storage, "_wrapped", staticfiles_storage)
        self.assertTrue(
            hasattr(actual, "hashed_name"),
            "the active static storage does not hash filenames, so cache "
            "busting is not in effect",
        )

    def test_legacy_setting_is_not_relied_on(self):
        """STATICFILES_STORAGE is inert from Django 5.1. If it reappears,
        someone is configuring something that has no effect."""
        from django.conf import settings

        self.assertFalse(
            hasattr(settings, "STATICFILES_STORAGE"),
            "STATICFILES_STORAGE is set but Django >= 5.1 ignores it; "
            "configure STORAGES['staticfiles'] instead",
        )
