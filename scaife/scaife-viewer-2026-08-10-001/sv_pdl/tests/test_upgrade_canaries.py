"""Canaries that fire when a dependency upgrade shifts behaviour.

Nothing here tests product features; each one is a tripwire for a specific
class of upgrade breakage that is otherwise discovered in production.
"""
from io import StringIO

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase, tag


class SystemCheckTests(SimpleTestCase):
    def test_django_system_checks_pass(self):
        """`manage.py check` catches most deprecations-turned-errors on a
        Django major upgrade."""
        out = StringIO()
        call_command("check", stdout=out, stderr=out)


class MigrationStateTests(TestCase):
    # makemigrations inspects every configured connection.
    databases = {"default", "atlas"}

    def test_no_missing_migrations_for_local_apps(self):
        """A Django upgrade can change how fields deconstruct, leaving model
        state and migrations out of sync. Scoped to the apps this repo owns,
        since upstream apps carry their own drift."""
        for app_label in ["localdict", "localcomm"]:
            with self.subTest(app=app_label):
                out = StringIO()
                try:
                    call_command(
                        "makemigrations",
                        app_label,
                        "--check",
                        "--dry-run",
                        stdout=out,
                        stderr=out,
                    )
                except SystemExit:  # --check exits non-zero on drift
                    self.fail(
                        f"{app_label} has un-migrated model changes:\n{out.getvalue()}"
                    )


class OrmBehaviourTests(TestCase):
    """String range comparison in the DB underpins commentary lookup."""

    def test_charfield_range_comparison_is_lexical(self):
        from sv_pdl.localcomm.models import Commentary, CommentaryEntry

        c = Commentary.objects.create(slug="t", label="t")
        CommentaryEntry.objects.create(
            commentary=c,
            target_urn="urn:cts:greekLit:tlg0012.tlg001:1.1-1.12",
            target_key="greekLit:tlg0012.tlg001",
            ref_start="000001.000001",
            ref_end="000001.000012",
            content_html="x",
        )
        # 000001.000011 must fall between start and end as plain strings.
        found = CommentaryEntry.objects.filter(
            ref_start__lte="000001.000011", ref_end__gte="000001.000011"
        )
        self.assertEqual(
            found.count(),
            1,
            "DB collation no longer orders zero-padded refs as expected",
        )


@tag("integration")
class ElasticsearchCompatibilityTests(SimpleTestCase):
    """Requires a running Elasticsearch; skipped when unreachable.

    Excluded from the default run because the version check below is a
    KNOWN FAILURE today: elasticsearch-py 7.17.x runs against an 8.19.11
    server. Since the 2026-08-10 resync that is Elastic's supported
    transitional pairing rather than an unsupported one, but the majors
    still differ and the client is capped below 8 — see UPGRADE-IMPACT.md.
    Run deliberately with:

        manage.py test sv_pdl.tests --tag=integration
    """

    def _server_version(self):
        import json
        import urllib.request

        from django.conf import settings

        host = getattr(settings, "ELASTICSEARCH_HOSTS", None) or "sv-elasticsearch"
        if isinstance(host, (list, tuple)):
            host = host[0]
        with urllib.request.urlopen(f"http://{host}:9200", timeout=5) as r:
            return json.loads(r.read())["version"]["number"]

    def test_search_index_is_queryable(self):
        """Functional counterpart: whatever the version skew, search works."""
        import json
        import urllib.request

        from django.conf import settings

        host = getattr(settings, "ELASTICSEARCH_HOSTS", None) or "sv-elasticsearch"
        if isinstance(host, (list, tuple)):
            host = host[0]
        try:
            with urllib.request.urlopen(
                f"http://{host}:9200/scaife-viewer/_count", timeout=5
            ) as r:
                count = json.loads(r.read())["count"]
        except Exception as exc:
            self.skipTest(f"Elasticsearch unreachable: {exc}")
        self.assertGreater(count, 0, "search index is empty")

    def test_client_and_server_major_versions(self):
        import elasticsearch

        client_major = int(elasticsearch.__version__[0])
        try:
            server_version = self._server_version()
        except Exception as exc:
            self.skipTest(f"Elasticsearch unreachable: {exc}")

        server_major = int(server_version.split(".")[0])
        self.assertEqual(
            client_major,
            server_major,
            f"elasticsearch-py {elasticsearch.__version__} is talking to "
            f"server {server_version}. A 7.17+ client against an 8.x server "
            f"is Elastic's *supported transitional* configuration "
            f"(compatibility mode is always on in the Python client), so "
            f"this is not an outage — but it is a transition, not an end "
            f"state, and the client is capped at <8 by scaife-viewer-core. "
            f"See UPGRADE-IMPACT.md.",
        )
