"""Keep `sv_pdl/django_compat.py` honest, and temporary.

The shim restores Django APIs removed in 4.0 for a small set of
unmaintained dependencies (see that module's docstring). A shim like this
tends to outlive its reason: a package gets replaced, nobody notices the
shim is now dead, and it quietly becomes permanent.

These tests pin both directions:

* The shim works — the names it restores are actually importable.
* The shim is still *needed*, and by exactly the packages documented. If a
  dependency is upgraded or dropped and no longer uses a removed API, the
  corresponding entry here fails and that part of the shim can go. If a new
  dependency starts relying on it, that shows up too.

Deliberately a static scan of installed source rather than a runtime check:
the point is which packages *contain* the calls, not whether a particular
request happened to reach one.
"""
import os
import re

from django.test import SimpleTestCase

# package directory -> removed APIs it still uses, as of 2026-08-14.
# Keep in step with the table in sv_pdl/django_compat.py.
EXPECTED_DEPENDENTS = {
    "pinax_theme_bootstrap": {"force_text", "installed"},
    "pinax": {"ugettext"},  # pinax/webanalytics/apps.py
    # raven is in INSTALLED_APPS as raven.contrib.django.raven_compat.
    # Upstream deprecated it in favour of sentry-sdk, so there is no fixed
    # release; with egress blocked it can never report anyway, which makes
    # it the strongest candidate for removal of the four.
    "raven": {"force_text", "smart_text"},
}

# API -> regex that finds a real use of it in installed code.
PATTERNS = {
    "is_ajax": r"\.is_ajax\s*\(",
    "force_text": r"\bforce_text\b",
    "smart_text": r"\bsmart_text\b",
    "ugettext": r"\bugettext\w*\b",
    "installed": r"_meta\.installed\b",
    "providing_args": r"\bproviding_args\b",
}


def _site_packages():
    import django

    return os.path.dirname(os.path.dirname(os.path.abspath(django.__file__)))


def _packages_using(api):
    """Top-level installed package names whose source matches ``api``."""
    regex = re.compile(PATTERNS[api])
    root = _site_packages()
    found = set()
    for entry in sorted(os.listdir(root)):
        path = os.path.join(root, entry)
        if not os.path.isdir(path) or entry.endswith((".dist-info", ".egg-info")):
            continue
        if entry in {"django", "pip", "setuptools", "pkg_resources", "__pycache__"}:
            continue
        for dirpath, dirnames, filenames in os.walk(path):
            dirnames[:] = [d for d in dirnames if d != "__pycache__"]
            # A package's own tests are not loaded by this project.
            if os.path.basename(dirpath) in {"tests", "test"}:
                continue
            for name in filenames:
                if not name.endswith(".py"):
                    continue
                try:
                    with open(os.path.join(dirpath, name), encoding="utf-8") as fp:
                        if regex.search(fp.read()):
                            found.add(entry)
                            break
                except (OSError, UnicodeDecodeError):  # pragma: no cover
                    continue
            if entry in found:
                break
    return found


class CompatShimWorksTests(SimpleTestCase):
    def test_restored_names_are_importable(self):
        from django.db.models.options import Options
        from django.utils import encoding, translation

        self.assertTrue(hasattr(encoding, "force_text"))
        self.assertTrue(hasattr(encoding, "smart_text"))
        self.assertTrue(hasattr(translation, "ugettext_lazy"))
        self.assertTrue(hasattr(Options, "installed"))

    def test_restored_names_behave_like_the_originals(self):
        from django.contrib.sites.models import Site
        from django.utils import encoding

        self.assertEqual(encoding.force_text(b"abc"), "abc")

        # sites is in INSTALLED_APPS, so this must be True — it is what
        # pinax-theme-bootstrap's context processor checks on every request.
        self.assertTrue(Site._meta.installed)


class CompatShimIsStillNeededTests(SimpleTestCase):
    """When one of these fails, delete the corresponding shim."""

    def test_dependents_match_the_documented_set(self):
        for package, apis in EXPECTED_DEPENDENTS.items():
            for api in sorted(apis):
                with self.subTest(package=package, api=api):
                    users = _packages_using(api)
                    self.assertIn(
                        package,
                        users,
                        f"{package} no longer uses {api}. If nothing else "
                        f"does either ({sorted(users)}), remove that part of "
                        f"sv_pdl/django_compat.py and this entry.",
                    )

    def test_no_undocumented_dependents(self):
        """A new package leaning on the shim should be a deliberate decision."""
        documented = set(EXPECTED_DEPENDENTS)
        for api in sorted({a for apis in EXPECTED_DEPENDENTS.values() for a in apis}):
            with self.subTest(api=api):
                extra = _packages_using(api) - documented
                self.assertEqual(
                    extra,
                    set(),
                    f"packages using {api} that are not in the table in "
                    f"sv_pdl/django_compat.py: {sorted(extra)}",
                )
