# Vendored packages

`scaife-viewer-core` and `scaife-viewer-atlas` are the upstream Scaife
Viewer backend packages. They were previously installed from GitHub archive
URLs listed in `requirements.txt`; the source now lives here.

## Why

Both packages pin `Django<3.0`, and `atlas` additionally exact-pins
`graphene-django==2.6.0`. They supply the CTS resolver, reader, library,
search indexer and the ATLAS GraphQL layer, so nothing above them can move
to a supported Django while those pins are external metadata that this repo
cannot edit. Vendoring converts the constraint from someone else's package
metadata into code in this repository. See `DJANGO-UPGRADE.md` §10 (W1).

This is a one-way door: upstream's ongoing changes no longer merge
directly. See `DJANGO-UPGRADE.md` §5.3 for the trade.

## Provenance

Taken from <https://github.com/scaife-viewer/backend/> at exactly the refs
`requirements.txt` previously pinned, so vendoring changed no behaviour:

| Package | Upstream ref | Subdirectory | Archive SHA-256 |
|---|---|---|---|
| `scaife-viewer-core` | `ed7f8777be86b9f58ae58a303d34913261f4f7df` | `core/` | `7f73aa6082aec62a87c78b986e1ac14107d477d3e514b69d51c7dcbf4dbfad5c` |
| `scaife-viewer-atlas` | tag `scaife-viewer-atlas@0.1a15` | `atlas/` | `b0b1bac812fee3a60880e090f3505c5569dbb8e47aaddcb6c27594b7d5b22e32` |

Verified against the packages installed in `scaife-viewer-base:latest`
before vendoring: `scaife_viewer/atlas` was byte-identical, and
`scaife_viewer/core` differed only by `core/tests/fixtures/`, which the
upstream `MANIFEST.in` omits from the built distribution. Nothing that runs
was changed.

Reproduce the download:

```bash
curl -sSL -o core.zip \
  "https://github.com/scaife-viewer/backend/archive/ed7f8777be86b9f58ae58a303d34913261f4f7df.zip"
curl -sSL -o atlas.zip \
  "https://github.com/scaife-viewer/backend/archive/scaife-viewer-atlas@0.1a15.zip"
shasum -a 256 core.zip atlas.zip
```

## How they are installed

`requirements.txt` refers to them by relative path
(`./packages/scaife-viewer-core`). The Dockerfile copies `packages/` into
the build context before `pip install -r requirements.txt` runs, so pip
builds them from this source. They install as ordinary distributions with
real `dist-info` metadata, which matters: `scaife_viewer/core/__init__.py`
calls `pkg_resources.get_distribution("scaife-viewer-core").version` at
import time and raises without it.

The two trees are kept as upstream ships them — `setup.py`, `MANIFEST.in`,
`tox.ini`, `runtests.py`, `scripts/` and their test suites included — so
they remain buildable and testable on their own terms, and so a future
diff against upstream stays meaningful.

## Local changes

Any edit to these trees is a divergence from upstream and belongs in this
list.

| Date | Package | Change | Why |
|---|---|---|---|
| 2026-08-14 | `core` | `setup.py`: `certifi==2018.11.29` → `>=2018.11.29`, `requests==2.22.0` → `>=2.22.0` | The image already installs patched `certifi` and `requests` over the top of these exact pins. Previously pip reported a dependency conflict and proceeded; the installed versions were correct but the metadata disagreed with reality. Relaxing the floors makes the resolver agree with what is installed. See `DJANGO-UPGRADE.md` §6.3. |
| 2026-08-14 | `core` | `scaife_viewer/core/tests/settings.py`: added a `CACHES` entry for `cts-resolver` | Without it `scaife_viewer.core.cts.resolvers` raises `InvalidCacheBackendError` at import and the suite cannot be collected at all. Test settings only; never imported by the application. |
| 2026-08-14 | `atlas` | `setup.py`: `graphene-django==2.6.0` → `>=2.16,<3` | Staging step for the graphene 3 port, which cannot happen until Django is on 3.2. `DJANGO-3.2-PLAN.md` §4.1. **Does change the schema** — 92 additive `offset` arguments and 22 filter-argument retypes, all of them graphene-django correcting its own type inference, none reachable from the built frontend. The delta is characterised in full in that section. |
| 2026-08-14 | `atlas` | `scaife_viewer/atlas/compat.py`: import the JSON converter under either name | graphene-django renamed `convert_postgres_field_to_string` to `convert_pg_and_json_field_to_string` at 2.16. Both are tried, so the shim spans the bump. Returned type is `JSONString` either way. **Superseded the same day**: the file was deleted outright when the backport was dropped — see the row below. |
| 2026-08-14 | `atlas` | `scaife_viewer/atlas/schema.py`: `LimitedConnectionField.connection_resolver` signature updated for graphene-django 2.16 | 2.16 moved filtering into `get_queryset_resolver()` and passes a single `queryset_resolver` where 2.6 passed `filterset_class` and `filtering_args`. The old signature did not fail at import and did not change the schema — it failed at *query* time, leaving every paginated list empty. `sv_pdl/tests/test_graphql_execution.py` exists because of this. |
| 2026-08-14 | `atlas` | `setup.py`: `Django<3` → `>=3.2,<4`; `django-filter`, `django-treebeard`, `django-extensions`, `django-sortedm2m` raised to their newest Django-3.2-compatible releases | The Django 3.2 move. `DJANGO-3.2-PLAN.md` §4.2–4.3. |
| 2026-08-14 | `core` | `setup.py`: `Django>=2.2,<3.0` → `>=3.2,<4` | Same step, in lockstep with atlas. |
| 2026-08-14 | `atlas` | Dropped `django-jsonfield-backport`: `models.py` imports `django.db.models.JSONField`, 16 call sites across five historical migrations rewritten, `compat.py` deleted, dependency and `INSTALLED_APPS` entries removed | Django has shipped `models.JSONField` since 3.1. The wire format is unchanged — graphene-django converts the native field to the same `JSONString` scalar the shim produced — so the frontend is unaffected. The migrations had to be rewritten, not just the model: otherwise the backport would have to stay installed forever so old migrations could import it. No new migration is generated. `DJANGO-3.2-PLAN.md` §4.4. |
| 2026-08-14 | `core` | `setup.py`: `elasticsearch>=7,<8` → `opensearch-py>=2.8,<3`; client swapped in `search.py`, `indexer.py` and `management/commands/create_index.py` | This cap was what pinned the client an API generation behind the Elasticsearch 8 server, and was the standing `--integration` failure. OpenSearch forked from ES 7.10, so `opensearch-py` — itself a fork of `elasticsearch-py` 7.x — matches the server again; the swap is close to a rename. It is also mandatory rather than optional: from 7.14 `elasticsearch-py` raises `UnsupportedProductError` against a non-Elasticsearch server. `<3` because opensearch-py 3.1+ needs Python 3.10. See UPGRADE-IMPACT.md. |
| 2026-08-14 | `atlas` | `schema.py`: `fields = "__all__"` on all 15 concrete `DjangoObjectType.Meta` blocks, plus injected into both abstract bases' `__init_subclass_with_meta__` | graphene-django 3 requires `fields` or `exclude`. `"__all__"` reproduces 2.x's implicit behaviour exactly, which is what kept the schema — and the frontend contract — byte-identical. A hand-curated subset would have risked silently dropping a field. |
| 2026-08-14 | `atlas` | `setup.py`: `graphene-django` → `>=3.2,<4` | Required before Django 4.0, which removes `force_text` used throughout graphene-django 2.x. |
| 2026-08-14 | `atlas` | `setup.py`: `django-sortedm2m` → `>=4.0,<5` | 3.1.1 calls `rel.is_hidden()`, replaced by the `hidden` property in Django 5.0. |
| 2026-08-14 | both | `setup.py`: `Django` → `>=5.2,<6`; test extras raised to `pytest-django>=4.5`, `hypothesis>=6,<7`, `pytest-cov>=4` | The framework move. The old test caps predate Python 3.12 — `hypothesis<6` calls `entry_points().get()`, removed in 3.12, so the suites could not even be collected. |
| 2026-08-14 | both | `tests/urls.py`: `django.conf.urls.url` → `django.urls.re_path` | Removed in Django 4.0. Found by the removed-API canary only after its pattern was broadened — it required a bare `import url` and these files write `import include, url`. |
| 2026-08-14 | `core` | `setup.py`: `elasticsearch` → `opensearch-py`; client swapped in `search.py`, `indexer.py`, `create_index.py` | See the OpenSearch row above. |
| 2026-08-15 | both | `__init__.py`: `pkg_resources.get_distribution(...).version` → `importlib.metadata.version(...)` | `pkg_resources` is a setuptools API removed after 81.0, which is why the image pinned `setuptools==81.0`. These two files were two of the three remaining users in the entire image; the third is `pinax-webanalytics`, which is unmaintained. `importlib.metadata` is the stdlib replacement (3.8+). The pin still stands for that one package — see SBOM-2026-08-15.md §4c. |
| 2026-08-15 | `core` | `setup.py`: `anytree==2.4.3` → `>=2.13,<3` | 2.4.3's `Resolver.__translate` returns `re_pat + r"\Z(?ms)"` — a global inline regex flag in *trailing* position. Python 3.11 turned that from a deprecation into `re.error: global flags not at the start of the expression`, so every anytree path resolution raised. That is the CTS table-of-contents resolver: `/library/<version>/json/` returned 500 and no text could be opened from the library. 2.13.0 moves the flag to the front. Found by a user click, not by the suite — see `sv_pdl/tests/test_http_smoke.py`. |
| 2026-08-14 | `core` | `cts/collections.py`: new `deterministic_label()`, used by `Collection.label` in place of MyCapytain's `get_label` | `get_label` returns the first match from `graph.objects(...)`, and rdflib guarantees no ordering. 56 collections in the Perseus corpora carry 2–5 English labels, so the winner was arbitrary — it changed between Python 3.9 and 3.12, flipping 34 work titles. The rule is shortest-then-alphabetical, which is both total and useful: "Matthew", "Romans", "1 Corinthians" rather than alphabetical's inconsistent "Gospel according to Matthew" beside "Ephesians". Falls back to `get_label` when no label matches the language. Guarded by `sv_pdl/tests/test_label_determinism.py`. |
| 2026-08-15 | `core` | `utils.py`: `get_pagination_info()` gained a `per_page` argument (default 10) and now reports one empty page instead of zero | Two defects in the search JSON API, both pinned as known quirks by `sv_pdl/tests/test_search_options.py` before being fixed. (1) The page stride was hardcoded to 10 in all five expressions while the caller's `size` was free to differ, so with `size=5` page 2 started at result 11 and results 6-10 were unreachable. (2) An empty result set reported `num_pages: 0` with `start_index: 1`/`end_index: 10`, i.e. "showing 1-10 of 0, page 1 of 0"; Django's `Paginator` yields one empty page with both indices 0, which is what this now matches. `per_page` defaults to 10, so core's own search view and the Vue frontend — which never sends `size` — are unaffected. |
| 2026-08-14 | `atlas` | `models.py`: `TextAnnotation.kind` `max_length` 7 → 11, plus new migration `0007_textannotation_kind_length.py` | The `choices` include `"syntax-tree"` (11 characters), so the column could never hold every valid value. Django 3.2's `fields.E009` refuses to start on it. SQLite does not enforce varchar length, which is why it went unnoticed; Postgres would have rejected every syntax-tree annotation. The table is empty here, so no rows were affected. **This adds a migration upstream does not have** — if upstream ever ships its own `0007`, this file must be renumbered. |

The first two changes were made immediately after vendoring and alter
nothing the application does — the golden schema and passage snapshots were
byte-identical before and after. The graphene-django bump does move the
schema, deliberately and within a characterised, reviewed delta; the
passage snapshots stayed byte-identical through it.

### Dependency delta from vendoring

Relaxing the two exact pins above changed the resolved dependency set in
exactly one place, and it was a correction. The old build installed
`chardet==3.0.4` and `idna==2.8` — the dependencies of `requests` **2.22.0**
— while the `requests` that actually ran was 2.32.5, installed over the top.
With the metadata no longer contradicting reality, pip resolves for the
version in use: `chardet` is gone (2.32.x uses `charset-normalizer`, already
present) and `idna` is 3.18. `requests`, `urllib3`, `certifi` and
`charset-normalizer` are unchanged.

The `[test]` extras additionally bring in the pytest and hypothesis stack;
see `scripts/run-vendored-tests.sh`.

## Running their test suites

```bash
bash scripts/run-vendored-tests.sh            # both, checked against baseline
bash scripts/run-vendored-tests.sh --verbose atlas
```

Upstream's suites do **not** pass cleanly at these refs. The script records
the exact baseline — core 4 passed / 1 failed, atlas 12 passed / 7 failed —
and fails if the counts move in either direction, so an edit to `packages/`
that breaks something new is visible immediately. The individual failures
are documented in the script's header.

These counts were first measured *after* vendoring, because the test
dependencies were not installed before it and the source was not in the
tree. They are nonetheless properties of upstream rather than of vendoring:
the vendored source is byte-identical to what was previously installed, and
every failure is an assertion mismatch between upstream's code and its own
tests, or the exemplar `ValueError` below — none of which depend on how the
package was installed.

One of them is a real latent bug rather than a stale test:
`CTSImporter.is_workpart()` does not account for the exemplar depth, so for
an exemplar URN the `exemplar` kind falls through to the citation branch and
raises `ValueError: 'exemplar' is not in list`. Upstream's own
`TODO: Support exemplars` sits on that method. It is unreachable with the
corpora this deployment loads, none of which use exemplar URNs, and it is
left unfixed because vendoring is meant to be behaviour-preserving.

The Django and graphene pins are deliberately left as upstream set them.
Vendoring is step W1 and is meant to be behaviour-preserving; relaxing those
pins is W2 onward — planned in `DJANGO-3.2-PLAN.md` — and is gated on the
golden-file suites in `sv_pdl/tests/`.
