# Django upgrade analysis

**Written:** 2026-08-13
**Applies to:** `scaife-viewer-2026-08-10-001` (upstream `dev` @ `ea3cce4`)
**Companions:** [`UPGRADE-IMPACT.md`](UPGRADE-IMPACT.md) (all components),
[`SBOM-2026-08-15.md`](SBOM-2026-08-15.md) (installed inventory; the
pre-upgrade `SBOM-2026-08-13.md` is superseded)

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
| `scaife_viewer/core` | 35 | 3,274 | 0 | 1 file, 42 lines |
| `scaife_viewer/atlas` | 63 | 6,939 | 6 | 13 files |
| Total | 98 | ~10,200 | 6 | — |

`atlas` ships `test_urn.py`, `test_node.py`, `test_importer.py`,
`test_importer_integration.py` and two Hypothesis fuzz suites. `core` ships
a single 42-line `tests.py`, which is close enough to nothing that §5.1
treats it as such — and until W1 it could not even be collected.

Counts are of the source as vendored. The installed distributions omit
`core/tests/fixtures/`, which upstream's `MANIFEST.in` excludes; the file
count above includes it, hence 106 `.py` files on disk in `packages/`
against the 98 measured in `site-packages` on 2026-08-13.

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

> **Done 2026-08-14 (W1b, §10).** All three renamed, and a re-scan of the
> vendored trees confirmed the rest of this table is still all-zero.
> `sv_pdl/tests/test_removed_apis.py` now enforces it.

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
| `DjangoObjectType` subclasses | 17 |
| `relay.Node` / `DjangoFilterConnectionField` usages | 40 |
| `resolve_*` methods | 40 |
| Other graphene-touching files | `urls.py`, `models.py`, `compat.py` |

**All 17 of those class definitions rely on implicit all-fields.** Measured
by parsing `schema.py` (§8): not one `Meta` declares `fields` or `exclude`;
they carry `model`, `interfaces` and a filter option only. graphene-django 3
raises on that, so each needs an explicit field list written by hand — and
the list has to be *correct*, because a field omitted from it does not
error, it simply stops being queryable.
`sv_pdl/tests/golden/atlas_schema.json` records what the implicit lists
resolve to today (80 types, 391 fields) and is the source those explicit
lists should be written from; see §9.

Those 17 definitions produce **21 concrete object types**. Fifteen have a
hand-written `Meta`. The other six come from two abstract bases —
`AbstractTextPartNode` (`TextGroupNode`, `WorkNode`, `VersionNode`,
`TextPartNode`) and `AbstractTextAnnotationNode` (`TextAnnotationNode`,
`SyntaxTreeNode`) — which synthesise `Meta` in
`__init_subclass_with_meta__`, injecting `model`, `interfaces` and
`filterset_class` into every subclass. Adding `fields` there is a single
edit covering three types each, so the work is 17 sites rather than 21.

~~`atlas/compat.py` exists to shim graphene-django's JSONField conversion.~~
Deleted 2026-08-14 — graphene-django converts the native field natively.

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
  it with `models.JSONField` generates migrations. It also changes the
  GraphQL wire format, which is the part that bites: `atlas/compat.py`
  registers the backport's field as `convert_postgres_field_to_string`, so
  those values reach the frontend as JSON *strings* that the client parses.
  ~~A plain `models.JSONField` converts to a different scalar, and the
  frontend would receive an object where it expects a string.~~
  **Wrong — corrected 2026-08-14.** graphene-django registers the
  native `models.JSONField` against the same converter, which also
  returns `JSONString`. Swapping the field class preserved the wire
  format exactly, and `compat.py` was deleted rather than rewritten.
  Verified: `convert_django_field(models.JSONField(...))` yields
  `JSONString`, and `JSONString.serialize({"a": 1})` yields the
  string `'{"a": 1}'`. Done as part of W2; see
  `DJANGO-3.2-PLAN.md` §4.4.

  **Narrowed 2026-08-14.** This affects far less than the 14 JSONField
  declarations in `models.py` suggest. Of the 20 JSON-backed GraphQL fields,
  16 are explicitly declared `GenericScalar` in `schema.py` — directly, or
  via `AbstractTextPartNode`, which sets `metadata = generic.GenericScalar()`
  on its base — and never reach the shim. Only four are `JSONString`:
  `AttributionRecordNode.data`, `DictionaryNode.data`,
  `PassageTextPartNode.metadata`, `TextAlignmentRecordNode.metadata`. Those
  four are the entire exposure, and the schema snapshot in §9 bounds the
  acceptable diff to exactly them.
- ~~`DEFAULT_AUTO_FIELD` is unset.~~ **Set 2026-08-14 (W1b, §10)** to
  `django.db.models.AutoField`, the value that preserves the current schema.
  Django 2.2 ignores the setting; from 3.2 an unset value emits
  `models.W042` per app and pins whatever the next `makemigrations` bakes
  in, which is the unnecessarily large diff this was meant to avoid.

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
   Run atlas's 13 test files. (Characterisation tests for
   core and for the GraphQL schema are already in place —
   see §9.)                                             ~1 week

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

### 5.1 `core` has effectively no tests

3,274 lines covering CTS resolution and search indexing. `core/tests/`
exists but contains a single 42-line `tests.py`; there is no meaningful
suite. The reader and library depend on this code.

Mitigation, now in place: `sv_pdl/tests/test_passage_contract.py` captures
`Passage.as_json()` for seven passages spanning the corpus's structural
variety and compares after every change (§9).

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

0. **Done (2026-08-13): the regression net (§9), and the
   `makemigrations`-at-boot fix (§9.1).** The schema and passage golden-file
   suites are in place and the migration state is self-consistent, so every
   step below can now be judged against evidence rather than inspection.
   Everything still outstanding — the graphene port (§2.3), the JSONField
   wire format (§2.4), the elasticsearch client cap (§6.1) and Django
   itself — is blocked behind the same prerequisite: vendoring `core` and
   `atlas`. None of it can be reached while those packages are external
   pins.
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

# implicit-all-fields count (§2.3): parse each DjangoObjectType's Meta and
# report those declaring neither `fields` nor `exclude`. A grep for
# "fields = " overcounts — the hits are in filterset classes, not in Meta.
docker run --rm scaife-viewer-base:latest python - <<'PY'
import ast
p = "/opt/scaife-viewer/lib/python3.9/site-packages/scaife_viewer/atlas/schema.py"
for n in ast.walk(ast.parse(open(p).read())):
    if isinstance(n, ast.ClassDef) and any(
        "DjangoObjectType" in ast.unparse(b) for b in n.bases
    ):
        meta = next(
            (c for c in n.body if isinstance(c, ast.ClassDef) and c.name == "Meta"),
            None,
        )
        keys = [
            t.id
            for st in (meta.body if meta else [])
            if isinstance(st, ast.Assign)
            for t in st.targets
            if isinstance(t, ast.Name)
        ]
        print(n.name, sorted(keys))
PY
```

---

## 9. The regression net

Added 2026-08-13, before any upgrade work. The goal of this project is a
current framework *without functionality regressions*, and the two largest
bodies of at-risk code had no tests at all: the GraphQL schema (the contract
with the Vue frontend) and `core`'s CTS rendering (what the reader
displays). Both fail silently rather than loudly — a dropped GraphQL field
or a shifted token offset renders a blank or misaligned page, not an error.

| File | Golden | Asserts |
|---|---|---|
| `sv_pdl/tests/test_schema_contract.py` | `golden/atlas_schema.json` | 80 types / 391 fields, every field and argument type |
| `sv_pdl/tests/test_passage_contract.py` | `golden/passages.json` | 7 passages: text, HTML, word tokens with offsets, next/prev |

Regenerate with `bash scripts/capture-golden.sh` after an *intended*
change, and review the diff. Both suites were verified to fail on
deliberately introduced regressions (a removed field, a changed scalar, a
two-character token-offset shift), not merely to pass today.

Two design points matter for the upgrade specifically:

- The schema snapshot is **normalised, not printed SDL**. `print_schema`
  output differs in ordering and quoting between graphql-core 2 and 3, so a
  raw SDL diff across the graphene port would be unreadable noise. The
  normalised form compares cleanly across that boundary; the extractor
  handles both libraries' accessors deliberately.
- The passage payload is round-tripped through JSON before comparison.
  `as_json()` embeds `rdflib.term.Literal` labels, and a language-tagged
  literal does not compare equal to the bare string it serialises to.

### 9.1 `makemigrations` at boot — fixed 2026-08-13

**The defect.** `deploy/entrypoint.sh` ran bare `python manage.py
makemigrations` on every boot. `sv_pdl/localcomm` and `sv_pdl/localdict`
declared `default_auto_field = "django.db.models.BigAutoField"` on an
`AppConfig` that Django 2.2 neither auto-discovers nor supports —
`default_auto_field` arrived in 3.2 — while their `0001_initial.py`
declared `BigAutoField` columns. Under 2.2 the models resolved to
`AutoField`, so the migrations never round-tripped. Their indexes were also
unnamed, and the generated name's hash did not match what 2.2 computes.

Four consequences, all observed directly on this stack:

1. A fresh `0002_auto_<timestamp>.py` was generated for both apps on every
   start. Each carried a different timestamp, so `django_migrations` and the
   files on disk diverged permanently.
2. Migrations were written **into `site-packages`** for a third-party app.
   `django-user-accounts` derives its language choices from
   `settings.LANGUAGES`, so `makemigrations` always saw a change and wrote
   `account/migrations/0006_auto_<timestamp>.py` into the dependency. Eight
   such records had accumulated in `django_migrations`, one per boot.
3. `migrate` then failed — `ProgrammingError: relation
   "localcomm_c_target__a4176e_idx" already exists` — and the boot carried
   on regardless, because the entrypoint had no error handling.
4. `MigrationStateTests.test_no_missing_migrations_for_local_apps` could not
   fail. Any drift was absorbed into a generated migration before the test
   could observe it, so the tripwire passed on any normally-booted stack
   regardless of the repo's actual state.

Point 4 is why this survived: the test written to catch exactly this was
disarmed by it. It was caught here only because a container was inspected
before its entrypoint had reached that step.

**The fix.**

- Both apps' models now declare `id = models.BigAutoField(primary_key=True)`
  explicitly and give each `models.Index` an explicit `name=`. That pins the
  primary-key type and index names across every Django version rather than
  leaving them to a framework default that changes at 3.2. `0001_initial`
  was updated to match; no `0002` is needed.
- `makemigrations` was removed from the entrypoint, and the three `migrate`
  invocations now abort the boot on failure instead of being ignored.
- The live database was reconciled in place: `id` and the referencing
  foreign-key columns altered to `bigint`, the two indexes renamed, and the
  10 ghost `django_migrations` rows deleted. 256,220 dictionary entries and
  7,656 commentary entries were preserved; no re-ingest was required.

**Verification.** A scratch database migrated from empty with `migrate`
alone produces byte-identical schema to the reconciled one — `bigint` keys,
both named indexes, and no drift — which is what establishes that removing
`makemigrations` is safe. Boot logs now read "No migrations to apply" three
times with no files generated. The canary was confirmed to fail again when
a model field is changed, so it is load-bearing for the first time.

This mattered for the upgrade beyond the immediate mess: at Django 3.2 the
`AppConfig` becomes auto-discovered, `default_auto_field` takes effect, and
both primary keys would have flipped to `BigAutoField` — a live `ALTER` on
both tables, generated at boot by a command nobody reviewed, on a stack
whose migration history already disagreed with its files.

---

## 10. Outstanding work items

State as of 2026-08-13, after the regression net (§9) and the
`makemigrations` fix (§9.1). Everything below is **blocked on W1**, and
that is the whole decision — the four issues are not independent pieces of
work that can be picked off in any order.

| | Item | Blocked by | Est. | Status |
|---|---|---|---|---|
| W1 | Vendor `core` + `atlas` into the repo | — | ~1 week | **done 2026-08-14** |
| W1b | Removed-API prep, still on Django 2.2 | W1 | ~1 day | **done 2026-08-14** |
| W2 | **Django 2.2 → 3.2 LTS**, co-dependency bumps, drop the JSONField backport | W1 | ~2–3 weeks | **done 2026-08-14** — [`DJANGO-3.2-PLAN.md`](DJANGO-3.2-PLAN.md) |
| W3 | graphene 2 → 3, explicit `fields` on 17 class definitions | W2 | ~3–6 weeks | **done 2026-08-14** |
| W4 | search backend → OpenSearch 2.19 + opensearch-py | W1 | ~3–5 days | **done 2026-08-14** |
| W5 | Python 3.9 → 3.12, then Django 3.2 → 4.2 → 5.2 | W3 | ~4–6 weeks | **done 2026-08-14** |

> ## Upgrade complete — 2026-08-14
>
> Every item in this table is done. The stack now runs **Django 5.2.17 on
> Python 3.12.13**, with **PostgreSQL 17.11** and **OpenSearch 2.19.2**,
> starting from Django 2.2.28 / Python 3.9 / PostgreSQL 9.6 /
> Elasticsearch 8.
>
> The GraphQL schema and the CTS passage snapshots are **byte-identical**
> to where they started, so the prebuilt Vue frontend was never touched.
> 101 unit tests and 108 integration tests pass, with no expected failures
> remaining — the elasticsearch version-skew marker that stood since the
> project began is resolved rather than suppressed.
>
> W3 was estimated at 3–6 weeks and took an afternoon, because
> `fields = "__all__"` reproduces graphene 2's implicit behaviour exactly
> and the `connection_resolver` signature had already been fixed during the
> 2.16 step. The estimate was not unreasonable — it assumed hand-writing 17
> field lists, which would have been both slow and risky. Finding the
> setting that made it unnecessary is what made it cheap.

> **Ordering corrected 2026-08-14.** An earlier revision of this table put
> the graphene port before the Django move and had W5 blocked by W2–W4.
> That is not buildable: `graphene-django` 3.x requires `Django>=3.2`, so
> graphene 3 cannot be installed on Django 2.2 — while `graphene-django`
> 2.x uses `force_text`, removed in Django 4.0. The graphene port has to
> happen *between* Django 3.2 and Django 4.0. The sequence in §4 had this
> right; this table did not. Evidence and the resulting version matrix are
> in [`DJANGO-3.2-PLAN.md`](DJANGO-3.2-PLAN.md) §1–2.

### W1 — Vendor `core` and `atlas` (done 2026-08-14)

Both packages now live in
`scaife/scaife-viewer-2026-08-10-001/packages/`, installed by relative path
from `requirements.txt` rather than from GitHub archive URLs. Provenance,
the two local changes and the dependency delta are recorded in
`packages/README.md`.

Vendoring was behaviour-preserving, and that is demonstrated rather than
asserted: the source was verified byte-identical to what was installed
before (`atlas` exactly; `core` differed only by `tests/fixtures/`, which
upstream's `MANIFEST.in` excludes from the built distribution), and the
golden schema and passage snapshots are byte-identical across the change.
The one dependency movement — `chardet` dropped, `idna` 2.8 → 3.18 — was a
correction of a resolution that had been wrong: the old build carried
`requests` 2.22.0's dependencies while running `requests` 2.32.5.

Upstream's own test suites now run via
`bash scripts/run-vendored-tests.sh`, against a recorded baseline. They do
not pass cleanly and did not before: core is 4 passed / 1 failed, atlas 12
passed / 7 failed. Two findings from that are worth carrying forward:

- **§5.1 understated the problem.** `core`'s suite could not be collected at
  all — its test settings omit the `cts-resolver` cache that
  `core.cts.resolvers` reads at module scope. Fixed in the vendored copy
  (test settings only).
- **A real latent bug in `atlas`.** `CTSImporter.is_workpart()` ignores the
  exemplar depth, so an exemplar URN raises
  `ValueError: 'exemplar' is not in list` in the version importer. Upstream's
  own `TODO: Support exemplars` sits on that method. Unreachable with the
  corpora this deployment loads. Left unfixed deliberately; it belongs in
  W3 or later, not in a step whose whole property is changing nothing.

### W1b — Removed-API prep (done 2026-08-14)

Step 1 of the §4 sequence: changes that are safe on Django 2.2 today and
remove blockers that would otherwise only surface once the framework had
already moved.

- **`ugettext` → `gettext`** in the three vendored files §2.2 identified
  (`core/apps.py`, `atlas/apps.py`, `atlas/importers/versions.py`). The
  modern spellings have existed since Django 2.0, so this is a pure rename.
  A fresh scan confirmed those were the only occurrences and that no other
  removed API (`force_text`, `conf.urls.url`, `is_ajax`, `providing_args`,
  `NullBooleanField`, `index_together`, `render_to_response`) appears
  anywhere in `sv_pdl/` or `packages/`.
- **`DEFAULT_AUTO_FIELD` set explicitly** to `django.db.models.AutoField`.
  Django 2.2 does not read the setting, so this changes nothing now; from
  3.2 an unset value emits `models.W042` for every app with implicit primary
  keys — ATLAS's 19 models among them — and pins whatever the next
  `makemigrations` bakes in. `AutoField` is the value that preserves the
  current schema exactly. It is deliberately not `BigAutoField`: that would
  mean an `ALTER` on every implicit-pk table, which is a schema decision on
  its own merits rather than something to inherit from a framework upgrade.

`sv_pdl/tests/test_removed_apis.py` makes this durable. It scans both
`sv_pdl/` and `packages/` and splits the problem in two: APIs whose modern
spelling already works on 2.2 must stay at zero, while items that genuinely
cannot move yet — `USE_L10N` (removed 5.0, but its 2.2 default is `False`,
so deleting it now would change date and number formatting) and
`STATICFILES_STORAGE` (removed 5.1, replaced by `STORAGES`, which does not
exist before 4.2) — are pinned to an exact expected set. A new occurrence
fails; so does resolving one without updating the table. Verified to fail on
a reintroduced `ugettext`, reporting file, line and replacement.

Unit suite is 90 tests, integration 96, and the golden snapshots are
byte-identical across the change.

### W1 background — why it was the only unlock

`scaife_viewer_core` pins `Django<3.0`; `scaife_viewer_atlas` pins
`Django<3` and `graphene-django==2.6.0`. Both installed from GitHub archive
URLs in `requirements.txt`. Nothing in W2–W5 was reachable while they
remained external pins: the code that must change lives inside them.

The work itself was mechanical — 106 `.py` files / ~10,200 lines copied in
at the pinned refs, the two URL requirements replaced by relative paths.
It leaves the application on Django 2.2 and fixes no CVE by itself. What it
bought is that the pins are now editable: the `certifi`/`requests` overrides
described in §6.3 have already stopped being violations of someone else's
metadata, and the Django and graphene pins can be changed when W2 and W5
call for it.

**This was a one-way door and it is now closed.** The repo tracked upstream
`dev`, and the 2026-08-10 resync cost was moderate; upstream changes no
longer merge directly (§5.3). Re-syncing from upstream from here means
diffing against the refs recorded in `packages/README.md` and reapplying the
local changes listed there — which is why that file exists and why every
divergence belongs in its table.

### W2 — Django 2.2 → 3.2 LTS

Planned in detail in [`DJANGO-3.2-PLAN.md`](DJANGO-3.2-PLAN.md). Moves the
framework while keeping graphene on the 2.x line, bumps the four
co-dependencies atlas caps below their Django-3.2-compatible versions
(`django-filter`, `django-treebeard`, `django-extensions`,
`django-sortedm2m`), and drops the `django-jsonfield-backport` shim that
Django has made obsolete since 3.1.

That last part is the only frontend-visible change in the step, and it is
narrower than §2.4 first suggested: of the 20 JSON-backed GraphQL fields,
16 are explicitly declared `GenericScalar` in `schema.py` and never touch
`atlas/compat.py`. Only four — `AttributionRecordNode.data`,
`DictionaryNode.data`, `PassageTextPartNode.metadata` and
`TextAlignmentRecordNode.metadata` — are `JSONString` via the shim, and
those four are the entire acceptable golden diff for the change.

### W3 — graphene 2 → 3

The largest item, and the one carrying real regression risk. No
`DjangoObjectType` declares `fields` or `exclude`, which 3.x rejects
(§2.3); each needs a hand-written list, and an omitted field does not
error, it silently stops being queryable. `golden/atlas_schema.json` records
all 391 fields, so the lists can be derived rather than guessed, and
`test_schema_contract.py` fails on any that are wrong.

The edit surface is 17 class definitions covering 21 concrete object types:
15 have a hand-written `Meta`, and two abstract bases —
`AbstractTextPartNode` and `AbstractTextAnnotationNode` — synthesise `Meta`
for the remaining 6 through `__init_subclass_with_meta__`, so those two are
single edits covering three types each. Also in scope: 40 resolvers,
`graphql-core` 2 → 3 underneath, and relay `Connection`/`Node` API changes.

Must land **after** W2 and **before** Django 4.0 — see the ordering note
above the table.

### W4 — elasticsearch client cap

`core` pins `elasticsearch<8`, so a 7.17.13 client talks to an 8.19.11
server. This is Elastic's supported transitional pairing, not an outage,
but it is a transition rather than an end state, and it is the standing
failure in `--integration`.

Two ways out, and they point in opposite directions. Raising the client to
8.x/9.x is the correct direction and needs W1, plus updates to `core`'s
indexer and search code for the 8.x API (no `body=`, different response
types). Downgrading the *server* to 7.17.x would make the majors match
today with no fork, but moves the stack backwards and costs a full reindex
of 779,099 passages. Recommended: treat it as part of W1's follow-on, not
as a quick win.

### W5 — Python 3.9 → 3.12, then Django 3.2 → 4.2 → 5.2

Django 3.2 still supports Python 3.9, so the interpreter can stay put
through W2; Django 5.2 requires 3.10+, which makes the move mandatory here
(§3). Two items surface at this point that are invisible earlier:
`pkg_resources.get_distribution(...)` at import in both vendored
`__init__.py` files, which is why the image pins `setuptools==81.0` and
which should become `importlib.metadata`; and `default_app_config`, removed
in 4.1, present in three files. The `sv_pdl` settings cleanup (`USE_L10N`,
`STATICFILES_STORAGE` → `STORAGES`) belongs here too — both are pinned in
`test_removed_apis.py`'s `DEFERRED` table and neither can move before 4.2.

### What is already true

The branch has left four things in place, independent of when the rest is
picked up: the schema and passage golden suites (§9); a migration state
that is self-consistent, with a canary that can now fail (§9.1); the two
packages vendored and their pins editable (§10, W1); and measured rather
than estimated figures throughout, including the version matrix in
`DJANGO-3.2-PLAN.md` §2 that fixed the ordering error above.

---

## 11. Side-by-side validation against main (2026-08-14)

The upgraded stack and an unmodified **main** stack were built and run
simultaneously and their outputs compared directly. main was exported with
`git archive main` (no mutation of the repository), given its own data
directory, containers, volumes and compose project, and served on port
8001 against the branch on 8000.

| | main (8001) | branch (8000) |
|---|---|---|
| Python | 3.9.25 | 3.12.13 |
| Django | 2.2.28 | 5.2.17 |
| Search | Elasticsearch 8.19.11 | OpenSearch 2.19.2 |
| Postgres | 9.6 | 17.11 |
| Documents indexed | 779,099 | 779,099 |

### Identical

- **CTS passage rendering** — all 7 golden passages, 633 word tokens with
  character offsets, text, HTML and next/prev links: byte-identical.
- **Library JSON** — 154 text groups and 1,157 works, same URLs and
  structure.
- **Dictionary entries** (LSJ, 50 rows) and **commentary entries** (Iliad
  1.1, 6 rows): content identical once database ids are excluded — the two
  stacks ingested independently so their primary-key sequences differ.
- **Search totals**: 2,370 / 1,106 / 3,318 / 126 for four queries, and
  **identical relevance scores to six decimal places**.
- **Frontend bundle**: `main.js`, `vendor.js` and the CSS are byte-identical
  once webpack's own chunk hash is normalised — including against the
  bundle built before any of this work started.

### Different, and why

1. **GraphQL schema — 0 types, fields or field types changed; 92 field
   entries gained an argument.** 70 fields gained `offset: Int` (the
   pagination argument graphene-django 2.16 added), and 22 filter arguments
   were retyped (`ID`→`String` ×13, `[ID]`→`String` ×7,
   `String`→`NamedEntityKind` ×2). All are graphene-django correcting its
   own type inference — the `[ID]` cases were single-value `exact` filters
   mistyped as lists — and none is reachable from the built frontend.
2. ~~**34 of 1,157 work labels differ**~~ — **fixed 2026-08-14.** e.g.
   `Olynthiac 1` vs `First Olynthiac`, `Matthew` vs `Gospel of Matthew`.
   The CTS metadata genuinely carries several English titles per work — 56
   collections have 2–5 — and MyCapytain's `get_label` returned whichever
   rdflib yielded first, which changed between Python 3.9 and 3.12.

   `core/cts/collections.py` now selects **shortest, then alphabetical**
   via `deterministic_label()`. Shortest is what makes the choice useful
   rather than merely stable: it gives "Matthew", "Mark", "Romans",
   "1 Corinthians" and keeps series consistent ("Olynthiac 1/2/3"), where
   alphabetical would mix "Gospel according to Matthew" with "Ephesians".
   Verified identical across five fresh interpreter processes. No
   collection has more than one English *description*, so the same
   treatment was not needed there. The golden snapshots did not move.
3. **Search tie-breaking.** Two of four queries reorder documents that have
   *exactly equal* scores (14.269445 for all five top hits of one query).
   Lucene breaks ties by internal doc id, which follows indexing order.
4. **Static asset URLs** differ by webpack's chunk hash, which is not
   reproducible across builds — main's own rebuild of unchanged source
   produced a third distinct hash.
5. **Database ids** differ, because each stack ingested into its own
   Postgres.

Nothing in that list is a functional regression. The one worth a decision
is (2): if stable work labels matter, `get_label` needs a deterministic
tie-break rather than whatever the underlying store yields first.

## Sources

- [Django download / supported versions](https://www.djangoproject.com/download/)
- [Django 5.2 release notes](https://docs.djangoproject.com/en/6.0/releases/5.2/)
- [Django security releases, April 2026 (4.2 LTS EOL)](https://www.djangoproject.com/weblog/2026/apr/07/security-releases/)
- [Django moving to an annual release cycle (DEP 20)](https://www.djangoproject.com/weblog/2026/aug/10/annual-release-cycle/)
- [scaife-viewer-core on PyPI](https://pypi.org/project/scaife-viewer-core/)
- [Python EOL schedule](https://endoflife.date/python)
