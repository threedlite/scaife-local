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
class SearchBackendCompatibilityTests(SimpleTestCase):
    """Requires a running OpenSearch; skipped when unreachable.

    History: this class used to hold a deliberate standing failure. The
    server was Elasticsearch 8 while `scaife-viewer-core` capped the client
    at `elasticsearch<8`, so a 7.17 client drove an 8.x server — Elastic's
    supported *transitional* pairing, but a bridge rather than an end state,
    and one the client could not leave.

    That is resolved. The deployment now runs OpenSearch, which forked from
    Elasticsearch 7.10 — the API generation the client targets — with
    `opensearch-py` in place of `elasticsearch-py`. The version check below
    is expected to **pass**, and its passing is the signal that the
    migration achieved something. See UPGRADE-IMPACT.md.

    Integration-tagged because it needs the live service:

        bash scripts/run-tests.sh --integration
    """

    def _host(self):
        from django.conf import settings

        host = getattr(settings, "OPENSEARCH_HOSTS", None) or "sv-opensearch"
        if isinstance(host, (list, tuple)):
            host = host[0]
        return host

    def _server_info(self):
        import json
        import urllib.request

        with urllib.request.urlopen(f"http://{self._host()}:9200", timeout=5) as r:
            return json.loads(r.read())

    def test_search_index_is_queryable(self):
        """Functional counterpart: search actually returns documents."""
        import json
        import urllib.request

        try:
            with urllib.request.urlopen(
                f"http://{self._host()}:9200/scaife-viewer/_count", timeout=5
            ) as r:
                count = json.loads(r.read())["count"]
        except Exception as exc:
            self.skipTest(f"OpenSearch unreachable: {exc}")
        self.assertGreater(count, 0, "search index is empty")

    def test_server_is_opensearch_not_elasticsearch(self):
        """The client would refuse Elasticsearch anyway — opensearch-py and
        elasticsearch-py each verify the product they are talking to — but
        assert it directly so a silent revert of the compose image is
        caught here rather than as a connection error at request time."""
        try:
            info = self._server_info()
        except Exception as exc:
            self.skipTest(f"OpenSearch unreachable: {exc}")
        distribution = info.get("version", {}).get("distribution")
        self.assertEqual(
            distribution,
            "opensearch",
            f"expected an OpenSearch server, got version block {info.get('version')}. "
            f"See Dockerfile-opensearch.",
        )

    def test_client_and_server_major_versions(self):
        """Was a standing known failure under Elasticsearch; must now pass."""
        import opensearchpy

        client_major = int(opensearchpy.__versionstr__.split(".")[0])
        try:
            server_version = self._server_info()["version"]["number"]
        except Exception as exc:
            self.skipTest(f"OpenSearch unreachable: {exc}")

        server_major = int(server_version.split(".")[0])
        self.assertEqual(
            client_major,
            server_major,
            f"opensearch-py {opensearchpy.__versionstr__} is talking to "
            f"OpenSearch {server_version}. These tracked the same major "
            f"after the migration off Elasticsearch; if they have diverged, "
            f"one of the two pins moved. See UPGRADE-IMPACT.md.",
        )
