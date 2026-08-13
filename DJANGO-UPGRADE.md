# Django upgrade analysis

**Written:** 2026-08-13
**Applies to:** `scaife-viewer-2026-08-10-001` (upstream `dev` @ `ea3cce4`)
**Companions:** [`UPGRADE-IMPACT.md`](UPGRADE-IMPACT.md) (all components),
[`SBOM-2026-08-13.md`](SBOM-2026-08-13.md) (installed inventory)

Counts in this document were measured against the installed packages on
2026-08-13. Commands for reproducing them are in §8. Effort figures are
estimates and are labelled as such.

---

## 1. Constraint

Django 2.2.28 reached end of life on 2022-04-01 and is the final release on
that line. Two dependencies prevent moving off it:

```
scaife_viewer_core:   Django <3.0,>=2.2
scaife_viewer_atlas:  Django <3,>=2.2.15   graphene-django ==2.6.0
```

These packages supply the CTS resolver, reader, library, search indexer and
the ATLAS GraphQL layer. Upstream's current `dev` additionally pins
`Django==2.2.28` in `requirements.txt`.

Consequence: a move to current Django requires forking both packages. The
remainder of this document assumes that.

### Target version

| Candidate | Status |
|---|---|
| 4.2 LTS | EOL 2026-04-07; not a valid target |
| 5.2 LTS | Supported to 2028-04; requires Python 3.10+ |
| 6.0 | Supported, shorter window than the LTS |

5.2 LTS provides the longest support window for the work involved. Django
moves to an annual release cycle from 2028 (DEP 20), with three years of
support per feature release, so the calculation after 5.2 differs.

---

## 2. Scope of work

### 2.1 Size of the fork

| Package | `.py` files | Lines | Migrations | Tests shipped |
|---|---|---|---|---|
| `scaife_viewer/core` | 35 | 3,274 | 0 | none |
| `scaife_viewer/atlas` | 63 | 6,939 | 6 | 13 files |
| Total | 98 | ~10,200 | 6 | — |

`atlas` ships `test_urn.py`, `test_node.py`, `test_importer.py`,
`test_importer_integration.py` and two Hypothesis fuzz suites. `core` ships
no tests; see §5.1.

### 2.2 Django API removals in the forked code

Scanned per package for APIs removed in Django 3.x–5.x:

| API | Removed in | `core` | `atlas` |
|---|---|---|---|
| `ugettext` / `ugettext_lazy` | 4.0 | 1 file (`apps.py`) | 2 files (`apps.py`, `importers/versions.py`) |
| `force_text` / `smart_text` | 4.0 | — | — |
| `from django.conf.urls import url` | 4.0 | — | — |
| `is_ajax()` | 4.0 | — | — |
| `providing_args` | 4.0 | — | — |
| `NullBooleanField` | 4.0 | — | — |
| `index_together` | 5.1 | — | — |

Three files require a rename (`ugettext` → `gettext`). That is the direct
Django-removal surface in the forked code.

> **Correction to an earlier revision.** `UPGRADE-IMPACT.md` previously
> reported these packages as containing `ugettext` in 6 files,
> `conf.urls.url` in 3 and `force_text` in 5. That scan included
> `graphene_django` alongside `scaife_viewer`. Per package, `force_text` and
> `conf.urls.url` occur only in `graphene_django`, the latter only in its
> test fixtures.

### 2.3 GraphQL layer

`graphene-django==2.6.0` is exact-pinned by atlas and does not support
Django 4+. The Django APIs removed in 4.0 occur in this package
(`force_text` in `converter.py`, `utils/utils.py`, `debug/sql/tracking.py`).
The migration path is graphene-django 3.x, which is a breaking change to the
schema code above it rather than a port of the library.

Surface to migrate, confined to four files in `atlas`:

| Measure | Count |
|---|---|
| `schema.py` | 970 lines |
| `DjangoObjectType` subclasses | 18 |
| `relay.Node` / `DjangoFilterConnectionField` usages | 40 |
| `resolve_*` methods | 40 |
| Other graphene-touching files | `urls.py`, `models.py`, `compat.py` |

`atlas/compat.py` exists to shim graphene-django's JSONField conversion.

Changes between graphene 2 and 3 affecting this schema:

- `graphql-core` 2 → 3 underneath, with a different execution engine
- Resolver signature and `info` object changes
- `DjangoObjectType` requires explicit `fields`/`exclude`; 2.x permitted
  implicit all-fields, 3.x raises
- Relay `Connection`/`Node` API changes
- `DjangoFilterConnectionField` requires `django-filter` 21+, while atlas
  pins `django-filter<3`
- Enum, `Decimal` and datetime scalar handling differ

This is the largest single component of the work; see the estimate in §4.

### 2.4 Model layer

`atlas/models.py` is 685 lines with 19 model classes and 6 migrations. Two
are not plain `models.Model`:

```
class Node(MP_Node):     # CTS text hierarchy
class Sense(MP_Node):    # dictionary sense nesting
```

`MP_Node` is django-treebeard's materialised-path tree, pinned `<5`. `Node`
represents the corpus hierarchy — text groups, works, versions and passages
— so a treebeard major upgrade affects the structure the reader and library
traverse. `atlas/tests/test_node.py` covers this model.

The remaining 17 models use standard field types. Two further items:

- `django-jsonfield-backport==1.0.0` is obsolete from Django 3.1; replacing
  it with `models.JSONField` generates migrations.
- `DEFAULT_AUTO_FIELD` is unset. From Django 3.2 this emits `models.W042`
  per app and defaults new primary keys to `BigAutoField`. Setting it before
  generating migrations avoids an unnecessarily large diff.

Related pins below their Django-4-compatible majors: `django-filter<3`,
`django-extensions<3`, `django-sortedm2m<3`, `django-treebeard<5`,
`django-webpack-loader==0.6.0`, `django-user-accounts`,
`django-oidc-provider`, and the `pinax-*` packages.

### 2.5 Local application code

Covered in `UPGRADE-IMPACT.md`; summarised here. `sv_pdl/` requires
`USE_L10N` removed (removed in 5.0), `STATICFILES_STORAGE` moved into
`STORAGES` (removed in 5.1), and the JSONField backport dropped. `USE_TZ` is
already `True`, so the Django 5.0 default change has no effect. Estimated at
one day.

---

## 3. Python version coupling

Django 5.2 requires Python 3.10+. The current interpreter is 3.9.25, which
is the maximum Django 2.2 supports, so the interpreter upgrade is part of
this work rather than separable.

| | Current | After |
|---|---|---|
| Python | 3.9.25 (EOL 2025-10) | 3.12 or 3.13 |
| Alpine | 3.22.2 | 3.24.1 (via the newer Python image) |
| `urllib3` | 1.26.20 (capped by 3.9) | 2.x available |
| `gunicorn` | 23.0.0 (capped by 3.9) | 26.x available |

C extensions require wheels for the new interpreter on arm64: `psycopg2`
(migrate to `psycopg[binary]` 3.x), `lxml`, `grpcio`, `PyNaCl`,
`ruamel.yaml.clib`. The 3.8 → 3.9 move required adopting upstream's
`setuptools==81.0` pin, because newer setuptools no longer provides
`pkg_resources`, which `django-user-accounts` imports at module load.
Similar issues should be expected.

`typing==3.7.4.3` must be uninstalled before any interpreter change; it
shadows the standard library module.

---

## 4. Sequence and estimates

Nothing installs until the fork exists, which fixes the order:

```
0. Vendor core + atlas into the repo at current commits.
   Run atlas's 13 test files. Add characterisation tests
   for core.                                            ~1 week

1. ugettext -> gettext (3 files). Set DEFAULT_AUTO_FIELD.
   Remains on Django 2.2.                               ~1 day

2. Django 2.2 -> 3.2 LTS. Replace JSONField backport with
   models.JSONField; regenerate migrations. Bump
   django-filter/extensions/sortedm2m/treebeard.        ~1-2 weeks

3. graphene 2 -> 3, graphene-django 3.x.
   970-line schema, 18 types, 40 resolvers.             ~3-6 weeks

4. Python 3.9 -> 3.12. C-extension wheels, setuptools,
   psycopg2 -> psycopg3.                                ~1 week

5. Django 3.2 -> 4.2 -> 5.2, one major at a time.        ~2-3 weeks

6. sv_pdl settings cleanup (USE_L10N, STORAGES).         ~1 day

7. Verify offline invariants: bash scripts/run-tests.sh,
   then exercise /library/, /reader/, /search/.          ~2-3 days
```

Estimated total: 2–3 months of focused work, with step 3 accounting for the
largest share. These are estimates, not measurements.

### Out of scope

The frontend. Vue 2 reached EOL on 2023-12-31, and the application depends
on `@scaife-viewer/*` Vue 2 component libraries with a similar constraint
structure to the Python packages. Node 12 and webpack 4 are EOL, and
`node-sass` does not build on current Node. This is a separate project of
comparable size. The Django work does not require it, since the bundle is
built once and baked into the image.

---

## 5. Risks

### 5.1 `core` has no tests

3,274 lines covering CTS resolution and search indexing, with no test suite.
The reader and library depend on it. Mitigation: write characterisation
tests during step 0 — capture current output for a set of passages and
compare after each subsequent step.

### 5.2 graphene 3 is a rewrite

Expect behavioural differences in the schema rather than import failures
alone. The frontend consumes this API, so defects may present as incorrect
reader output rather than errors.

### 5.3 Divergence from upstream becomes permanent

The repository currently tracks upstream `dev`, and the measured cost of the
2026-08-10 resync was moderate (see `UPGRADE-IMPACT.md`). After forking,
upstream's ongoing changes no longer merge directly. The trade is between a
current application on an EOL framework and a current framework on a forked
application.

### 5.4 arm64 wheel availability

Historically where interpreter upgrades stall on this stack.

### 5.5 Migration regeneration

The JSONField and `DEFAULT_AUTO_FIELD` changes both alter migration state.
Verify by rebuilding the database from scratch — which this project can do
in minutes — rather than by migrating in place.

---

## 6. Security implications

All confirmed CVEs in the dependency set are currently fixed
(`SBOM-2026-08-13.md` §2). That describes the state of the CVE database on
2026-08-13 rather than a durable property of the deployment, for four
reasons.

### 6.1 The pin cascade

`core` and `atlas` constrain more than Django:

| Package | Constraint | Installed | Current | Gap |
|---|---|---|---|---|
| `graphene` / `graphene-django` | atlas `==2.6.0` | 2.1.9 / 2.6.0 | 3.4.3 | 2.1.9 released 2021-07 |
| `django-filter` | atlas `<3` | 2.4.0 | 26.1 (2026-07) | ~5 years |
| `django-treebeard` | atlas `<5` | 4.5.1 | 7.0.0 (2026-08) | ~5 years |
| `django-extensions` | atlas `<3` | 2.2.9 | 4.x | ~5 years |
| `django-sortedm2m` | atlas `<3` | 2.0.0 | 4.x | ~5 years |
| `certifi` | core `==2018.11.29` | overridden | 2026.7.22 | pin is 7 years old |
| `requests` | core `==2.22.0` | overridden | 2.32.5 | — |
| `elasticsearch` | core `<8` | 7.17.13 | 9.x | one major |

Python 3.9, the maximum Django 2.2 supports, further caps `urllib3` at
1.26.x (2.7 requires 3.10+) and `gunicorn` at 23.0.0 (26.0.0 requires
3.10+). These are the newest versions available under the constraint.

### 6.2 No patch path for future CVEs

Django 2.2 receives no security releases; 2.2.28 is the last on that line.
Any Django CVE published from this point has no in-place fix. The same
applies to the packages capped at unmaintained majors above.

### 6.3 The applied overrides are not a general mechanism

The `certifi` and `requests` fixes are installed in violation of `core`'s
exact pins. `pip` reports a dependency conflict and proceeds. This works for
leaf packages with stable APIs. It is not applicable to packages that
`core` or `atlas` import against, and each override can be reverted by an
upstream change without an obvious signal.

### 6.4 Mitigating factors

The deployment is loopback-bound, single-user, accepts no untrusted input,
and blocks egress at the container. A Django CVE requiring a request from an
untrusted party is not reachable in that configuration. These are
configuration properties rather than architectural ones, and change with
`SCAIFE_BIND=0.0.0.0` or the addition of a proxy.

---

## 7. Recommendation

The security consideration in §6 supports scheduling this work rather than
deferring it indefinitely — not because of present exploitability, but
because the framework constraint prevents approximately eight packages from
being updated, and that set does not shrink.

Suggested approach:

1. **Step 0 first.** Vendoring `core` and `atlas` takes about a week, leaves
   the application on Django 2.2, and fixes no CVE directly. It converts the
   constraint from an external pin into code in this repository, after which
   the overrides in §6.3 become ordinary edits and steps 1–7 can be
   scheduled against evidence.
2. **Reassess after step 0.** Step 3 carries most of the cost and can be
   judged by reading the 970-line schema rather than by estimate.
3. **Prioritise higher if the deployment model changes** — multi-user, LAN
   or internet exposure, or untrusted input — since those remove the
   mitigations in §6.4.

---

## 8. Reproducing the measurements

```bash
SP=/opt/scaife-viewer/lib/python3.9/site-packages

# package size
docker run --rm scaife-viewer-base:latest sh -c \
  "find $SP/scaife_viewer/atlas -name '*.py' | xargs cat | wc -l"

# removed-API scan, per package. Scanning scaife_viewer and graphene_django
# together produces the error corrected in §2.2.
docker run --rm scaife-viewer-base:latest sh -c \
  "grep -rl ugettext $SP/scaife_viewer"

# graphene surface
docker run --rm scaife-viewer-base:latest sh -c \
  "grep -c 'DjangoObjectType\|def resolve_' $SP/scaife_viewer/atlas/schema.py"

# model classes
docker run --rm scaife-viewer-base:latest sh -c \
  "grep -c '^class ' $SP/scaife_viewer/atlas/models.py"
```

## Sources

- [Django download / supported versions](https://www.djangoproject.com/download/)
- [Django 5.2 release notes](https://docs.djangoproject.com/en/6.0/releases/5.2/)
- [Django security releases, April 2026 (4.2 LTS EOL)](https://www.djangoproject.com/weblog/2026/apr/07/security-releases/)
- [Django moving to an annual release cycle (DEP 20)](https://www.djangoproject.com/weblog/2026/aug/10/annual-release-cycle/)
- [scaife-viewer-core on PyPI](https://pypi.org/project/scaife-viewer-core/)
- [Python EOL schedule](https://endoflife.date/python)
