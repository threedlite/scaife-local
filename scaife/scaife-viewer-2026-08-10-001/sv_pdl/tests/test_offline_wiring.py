"""Guards on the offline wiring itself.

Upgrading `scaife-viewer-core` is the single most likely way to silently
lose the offline patches: the upstream package ships its own views and
templates for the same routes, so a re-import or reordering can quietly
restore calls to atlas.perseus.tufts.edu or services.perseids.org.

These tests assert the local replacements are the ones actually wired up.
"""
from django.conf import settings
from django.test import SimpleTestCase
from django.urls import resolve

from sv_pdl.localcomm.views import commentaries_json as local_commentaries_json
from sv_pdl.localdict.views import dictionaries_json as local_dictionaries_json
from sv_pdl.localdict.views import dictionary_entries as local_dictionary_entries
from sv_pdl.views import morpheus_local


class UrlWiringTests(SimpleTestCase):
    def test_dictionaries_route_uses_local_view(self):
        self.assertIs(
            resolve("/library/dictionaries/json/").func, local_dictionaries_json
        )

    def test_dictionary_entries_route_uses_local_view(self):
        self.assertIs(
            resolve("/library/dictionaries/lsj/entries/").func,
            local_dictionary_entries,
        )

    def test_commentaries_route_uses_local_view(self):
        match = resolve(
            "/library/commentaries/urn:cts:greekLit:tlg0012.tlg001:1.1/json/"
        )
        self.assertIs(match.func, local_commentaries_json)

    def test_morpheus_route_uses_local_view(self):
        self.assertIs(resolve("/morpheus/").func, morpheus_local)

    def test_local_views_are_not_upstream_views(self):
        """If an upgrade makes these identical, the local override is gone."""
        from scaife_viewer.core import views as upstream

        self.assertIsNot(morpheus_local, getattr(upstream, "morpheus", None))


class InstalledAppsTests(SimpleTestCase):
    def test_local_apps_installed(self):
        self.assertIn("sv_pdl.localcomm", settings.INSTALLED_APPS)
        self.assertIn("sv_pdl.localdict", settings.INSTALLED_APPS)

    def test_vendor_staticfiles_dir_registered(self):
        """jQuery is served locally instead of from unpkg.com.

        (An IntersectionObserver polyfill used to live here too, sourced from
        polyfill.io. Upstream removed that script tag, so the local copy was
        deleted rather than left orphaned in the bundle.)"""
        prefixed = [d for d in settings.STATICFILES_DIRS if isinstance(d, tuple)]
        self.assertIn(
            "vendor",
            [prefix for prefix, _path in prefixed],
            "vendor static dir missing; templates would fall back to CDNs",
        )


class CtsResolverTests(SimpleTestCase):
    def test_local_resolver_configured(self):
        """A local resolver is what keeps text loading off the network.
        Settings express this as {"type": "local", "kwargs": {...}}."""
        resolver = getattr(settings, "CTS_RESOLVER", None)
        self.assertIsInstance(resolver, dict)
        self.assertEqual(resolver.get("type"), "local")

    def test_resolver_reads_from_mounted_corpora(self):
        resolver = getattr(settings, "CTS_RESOLVER", {})
        data_path = resolver.get("kwargs", {}).get("data_path")
        self.assertTrue(data_path, "resolver has no local data_path")
        self.assertFalse(
            str(data_path).startswith("http"),
            "CTS data path points at a URL, not a local mount",
        )


class TemplateCdnTests(SimpleTestCase):
    """Static scan of the patched templates for reintroduced CDN hosts.

    Cheap, but it is exactly the regression an upstream template refresh
    reintroduces, and nothing else in the suite would notice.
    """

    FORBIDDEN_HOSTS = [
        "unpkg.com",
        "polyfill.io",
        "use.fontawesome.com",
        "services.perseids.org",
        "atlas.perseus.tufts.edu",
        "cdn.jsdelivr.net",
        "ajax.googleapis.com",
    ]

    def test_no_cdn_resources_loaded_by_templates(self):
        """Only flags hosts that would actually be *fetched* — `src=` on a
        script/img and `<link href=>` for stylesheets. Naming a host in prose
        is deliberately allowed, because licenses.html has to be free to
        credit a project by name (or link to its licence) without that
        counting as loading from it.
        """
        import pathlib
        import re

        template_root = pathlib.Path(settings.PACKAGE_ROOT) / "templates"
        offenders = []
        for path in template_root.rglob("*.html"):
            text = path.read_text(encoding="utf-8", errors="ignore")
            for host in self.FORBIDDEN_HOSTS:
                loaded = re.search(
                    r"""src\s*=\s*["'][^"']*""" + re.escape(host), text
                ) or re.search(
                    r"""<link[^>]+href\s*=\s*["'][^"']*""" + re.escape(host),
                    text,
                    re.IGNORECASE,
                )
                if loaded:
                    offenders.append(f"{path.name}: loads from {host}")
        self.assertEqual(
            offenders, [], f"templates fetch external resources: {offenders}"
        )
