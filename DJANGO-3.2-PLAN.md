# Plan: Django 2.2.28 → 3.2 LTS

**Drafted:** 2026-08-14
**Status:** not started
**Prerequisites:** W1 (vendoring) and W1b (removed-API prep), both done
**Companions:** [`DJANGO-UPGRADE.md`](DJANGO-UPGRADE.md) (analysis and the
W-numbered work items), [`packages/README.md`](scaife/scaife-viewer-2026-08-10-001/packages/README.md)
(vendored source provenance)

Version constraints in §2 were read from PyPI on 2026-08-14; code counts
come from the vendored trees on the same date. Reproduction commands are in
§9. Effort figures are estimates and are labelled as such.

---

## 1. Why this step is next, and not graphene

`DJANGO-UPGRADE.md` §10 ordered the work as W2 (graphene 2 → 3) before W5
(Django). **That ordering was wrong**, and the correction is the reason this
plan exists:

```
graphene-django 3.0.0+   requires  Django >= 3.2      <- cannot run on 2.2
graphene-django 2.16.0   requires  Django >= 2.2      <- runs on both
graphene-django 2.x      uses      force_text          <- removed in Django 4.0
```

So graphene 3 cannot be installed before Django 3.2, and graphene 2 cannot
survive Django 4.0. The graphene port has to happen **between** Django 3.2
and Django 4.0, not before either. The sequence in §4 of the analysis had
this right; the summary table in §10 did not, and has been corrected.

This step therefore does the Django 2.2 → 3.2 move while keeping graphene on
the 2.x line, and leaves the application working at every point.

## 2. Version matrix

Everything below is currently held back by pins in the vendored
`setup.py` files. Relaxing those pins is exactly what W1 bought.

| Package | Now | Target | Constraint on target | Pinned by |
|---|---|---|---|---|
| `Django` | 2.2.28 | 3.2.x (latest patch) | — | `requirements.txt`, core `<3.0`, atlas `<3` |
| `graphene-django` | 2.6.0 | 2.16.0 | `Django>=2.2` | atlas `==2.6.0` |
| `graphene` | 2.1.9 | unchanged (2.x) | graphene-django 2.16 needs `<3` | transitive |
| `django-filter` | 2.4.0 | 23.5 | `Django>=3.2`, py`>=3.7` | atlas `<3` |
| `django-treebeard` | 4.5.1 | 4.7.1 | `Django>=3.2`, py`>=3.8` | atlas `<5` |
| `django-extensions` | 2.2.9 | 3.2.3 | `Django>=3.2`, py`>=3.6` | atlas `<3` |
| `django-sortedm2m` | 2.0.0 | 3.1.1 | Django 3.2 classifier | atlas `<3` |
| `django-jsonfield-backport` | 1.0.0 | **removed** | `models.JSONField` since 3.1 | atlas `==1.0.0` |

The chosen targets are deliberately the *newest versions that still support
Django 3.2*, not the newest overall. `django-filter` 26.1, `django-treebeard`
7.0.0 and `django-extensions` 4.1 all now require Django ≥ 4.2 or ≥ 5.2 and
Python ≥ 3.10, so taking them here would force the whole Django and Python
move in one step. `django-filter` 23.5 and `django-treebeard` 4.7.1 both
carry Django 5.0 classifiers, so they should survive the 4.2 step without
further change.

`graphene-django` 2.16.0 is the last of the 2.x line and is the only 2.x
release whose metadata declares `Django>=2.2` rather than `>=1.11`. Moving to
it *before* the Django bump is a small independent change that can be
verified on its own.

## 3. Preconditions — already in place

Do not start until these still hold; they are what make the step reviewable.

- `bash scripts/run-tests.sh` — 90 unit tests, green.
- `bash scripts/run-tests.sh --integration` — 96 tests, exactly one expected
  failure (the elasticsearch client/server major skew).
- `bash scripts/run-vendored-tests.sh` — core 4/1, atlas 12/7, matching
  baseline.
- `bash scripts/capture-golden.sh` reproduces
  `sv_pdl/tests/golden/` byte-identically.
- `bash scripts/lint.sh` — clean.
- Migrations self-consistent: `makemigrations --check` reports no changes,
  and the entrypoint no longer generates migrations at boot (§9.1 of the
  analysis).

## 4. Work items, in order

Each item is independently verifiable. Do not batch them: the golden suites
can only tell you *which* change moved the schema if the changes land one at
a time.

### 4.1 — graphene-django 2.6.0 → 2.16.0 (still Django 2.2) — **DONE 2026-08-14**

Relaxed to `graphene-django>=2.16,<3` in the vendored atlas `setup.py`.

- **Why first:** it is the only change here that can be made and verified
  without moving Django, so it isolates any graphene-2.x behaviour change
  from the framework move. That turned out to be worth doing.
- **Predicted:** no schema change.
- **Actual:** the schema *did* change. The prediction was wrong.

**What broke first.** `atlas/compat.py` failed to import:
`graphene_django.converter.convert_postgres_field_to_string` was renamed to
`convert_pg_and_json_field_to_string` when it took on Django's built-in
`models.JSONField` alongside the postgres one. The shim now tries both
names, so it works either side of the bump. Returned type is `JSONString`
in both, so this rename alone moves nothing.

**The actual schema delta**, from the golden snapshot:

| Change | Count | Assessment |
|---|---|---|
| `offset: Int` added to connection fields | 92 | Additive. 2.16 added offset pagination. |
| `ID` → `String` on filter args | 13 | Benign; both accept a string literal. |
| `[ID]` → `String` on filter args | 7 | See below. |
| `String` → `NamedEntityKind` on `kind` | 2 | See below. |
| Types added or removed | 0 | |
| Fields added or removed | 0 | |
| Field types changed | 0 | |

The two that look breaking are graphene-django correcting its own type
inference, not a capability loss:

- `[ID]` → `String` affects `textParts_Urn`. `CitationFilterSet` declares
  `{"text_parts__urn": ["exact"]}` — a **single-value** filter. 2.6 was
  typing it as a list; 2.16 matches the declared lookup.
- `String` → `NamedEntityKind` affects `kind`. `NamedEntity.kind` is a
  `CharField(choices=NAMED_ENTITY_KINDS)`, and 2.16 converts choice fields
  in filters to the enum that already existed for the output field
  (`PERSON`, `PLACE`). Stricter, and correct.

**Frontend exposure: none.** The built bundle (`static/dist/*.js`) contains
no occurrence of `textParts_Urn`, `textPart_Urn`, `entry_Urn`,
`alignment_Urn`, `senseCitations` or `namedEntities` in any spelling. None
of the 22 retyped arguments is reachable from the current frontend.

`passages.json` is byte-identical, as required.

The golden was regenerated and the delta accepted on that evidence. If the
frontend is ever rebuilt against newer `@scaife-viewer/*` packages, re-check
the seven `textParts_Urn` sites specifically.

- **Estimate was:** half a day. **Actual:** about that, most of it spent
  characterising the delta rather than making the change.

### 4.2 + 4.3 — Co-dependency bumps and Django 3.2.25 — **DONE 2026-08-14**

Landed together, as anticipated: the three co-dependencies below all require
`Django>=3.2`, so they cannot be installed separately from the framework.

**Versions now installed:** Django 3.2.25, django-filter 23.5,
django-treebeard 4.7.1, django-extensions 3.2.3, django-sortedm2m 3.1.1,
whitenoise 6.7.0. Python remains 3.9.25.

**Six things broke. None was the framework itself.**

1. **`django-extensions==2.2.9`** in `requirements.txt` conflicted with
   atlas's new `>=3.2.3` floor — the only hard pip conflict in the set.
   Every other top-level pin declares `Django>=1.11` or no Django
   requirement at all, so pip would not have caught them.
2. **`pinax-webanalytics` app label.** Its `AppConfig` sets
   `label = "pinax-webanalytics"`, and from Django 3.2 a label must be a
   valid Python identifier. Release 5.0.0 — the latest — still has the
   hyphen, so there is nothing to upgrade to. Replaced with
   `sv_pdl.apps.WebAnalyticsConfig`, which declares a valid label and is
   written out rather than subclassing, so `pinax/webanalytics/apps.py`
   (which also imports `ugettext_lazy`) is never imported. The app itself
   is still needed: `site_base.html` calls `{% analytics %}`.
3. **`sv_pdl/changelog/apps.py` and `sv_pdl/reading/apps.py`** declared
   `name = "changelog"` / `"reading"` instead of the full dotted path.
   Django 2.2 never loaded these classes — no `default_app_config`, so they
   were never auto-discovered — and 3.2 discovers `apps.py` automatically.
   Our own latent bug, exposed rather than caused by the upgrade. The
   default label is the last component either way, so no migration state
   moved.
4. **`whitenoise==4.1.2` imports `django.utils.six`**, removed in Django
   3.0, so the middleware failed to import and every worker died. Bumped to
   6.7.0 — the newest release still supporting Python 3.8+ and Django 3.2,
   which also covers the 4.2 step.
5. **`{% load staticfiles %}`**, removed in Django 3.0, in two *third-party*
   templates: `pinax_theme_bootstrap/base.html` — which `site_base.html`
   extends, so every page was a 500 — and `oidc_provider`'s session iframe.
   Both packages are at their latest release with no fix. Resolved by
   re-registering the old library name in `TEMPLATES["OPTIONS"]["libraries"]`
   against `django.templatetags.static`, which is a one-line settings change
   instead of vendoring someone else's base template.
6. **`TextAnnotation.kind` was `max_length=7`** but its choices include
   `"syntax-tree"` (11 characters). Django 3.2's new `fields.E009` refuses
   to start on it. A genuine latent data bug: SQLite does not enforce
   varchar length, so it was invisible here, but Postgres would have
   rejected every syntax-tree annotation. Widened to 11 with a local
   migration, `atlas/migrations/0007_textannotation_kind_length.py`. The
   table is empty, so no rows were affected.

**Golden diff: none, as predicted.** `atlas_schema.json` and
`passages.json` are byte-identical across the framework move. The printed
SDL differs by one line — `SenseNode`'s `id` field moved position — which
is field ordering only, and is why the normalised JSON rather than the SDL
is the artifact tests assert on.

**Verification:** 94 unit tests green; 100 integration with only the known
elasticsearch failure; vendored baselines unchanged; lint clean;
`/library/`, `/reader/`, `/search/` and `/atlas/graphql/` all serve 200.

### 4.2 (original note) — Co-dependency bumps

Relax `django-filter<3`, `django-treebeard<5`, `django-extensions<3`,
`django-sortedm2m<3` in atlas's `setup.py`.

Note that `django-filter` 23.5, `django-treebeard` 4.7.1 and
`django-extensions` 3.2.3 all require `Django>=3.2`, so they can only be
*installed* together with 4.3. Pin them in the same commit as the Django
bump; this item is the setup.py edit, not the install.

`django-sortedm2m` 3.1.1 has no Django floor in its metadata and can land
independently.

- **Estimate:** half a day.

### 4.3 — Django 2.2.28 → 3.2.x

Relax `Django<3.0` (core) and `Django<3` (atlas) in the vendored
`setup.py` files, and change the `Django==2.2.28` pin in
`requirements.txt`. Install the co-dependencies from 4.2 in the same step.

Expected work beyond the version numbers:

- **`django-treebeard` 4.5 → 4.7 touches `Node` and `Sense`**, both
  `MP_Node` subclasses (analysis §2.4). `Node` is the corpus hierarchy the
  reader and library traverse. `atlas/tests/test_node.py` covers it and is
  part of the vendored baseline, so a regression there shows up in
  `run-vendored-tests.sh`.
- **`DEFAULT_AUTO_FIELD` is already set** to `AutoField` (W1b), so 3.2 will
  not emit `models.W042` and will not propose primary-key migrations.
- **Run the suite with deprecation warnings visible.** Django 3.2 warns
  about what 4.0 removes, and that list is the input to the next step:
  ```
  docker exec -u scaife scaife-viewer \
    python -W error::DeprecationWarning manage.py test sv_pdl.tests
  ```
- **Expect:** no schema change. Any diff in `atlas_schema.json` at this
  point is a finding, not a version bump.
- **Estimate:** 1–2 weeks, dominated by shaking out deprecations rather than
  by the version change itself.

### 4.4 — Drop the JSONField backport — **DONE 2026-08-14**

**Decision taken (§8.1): preserve the wire format.** The frontend does not
change unless absolutely required, so the four `JSONString` fields had to
stay `JSONString`.

That turned out to need no shim at all. graphene-django 2.16 already
registers `django.db.models.JSONField` against the same
`convert_pg_and_json_field_to_string` converter it uses for the postgres
one, and that returns `JSONString` — precisely what `atlas/compat.py` was
hand-registering for the backport. Verified directly:

```
convert_django_field(models.JSONField(...))  ->  JSONString
JSONString.serialize({"a": 1})               ->  '{"a": 1}'   (str)
```

So swapping the field class preserved the encoding for free, and
`compat.py` was deleted rather than rewritten.

**What changed**

- `atlas/models.py`: import switched to `django.db.models.JSONField`; the
  14 field declarations are untouched.
- **16 call sites across five historical migrations** (`0001`, `0002`,
  `0004`, `0005`, `0006`) rewritten from
  `django_jsonfield_backport.models.JSONField(` to `models.JSONField(`.
  This was necessary, not cosmetic: leaving them would have required the
  backport to stay installed forever purely so old migrations could import.
- `atlas/compat.py` deleted, along with its import in `schema.py`.
- `django_jsonfield_backport` removed from `INSTALLED_APPS` in both
  `sv_pdl/settings.py` and atlas's own test settings, and from atlas's
  `setup.py`.
- `pinax-eventlog[django-lts]` → `pinax-eventlog`. The extra's only effect
  is to pull in the backport for Django < 3.1; on 3.2
  `pinax.eventlog.compat` imports the native field directly and none of its
  migrations reference the backport. Without this the package would have
  stayed installed but unused.

**No migration was generated.** `makemigrations --check` reports no changes
for `scaife_viewer_atlas`: the rewritten historical migrations already
describe `models.JSONField`, and the SQLite column definition (`text` with
a `JSON_VALID` check) is identical either way, so there is nothing to alter.

**Golden diff: none.** `atlas_schema.json` is byte-identical, including all
four fields, and `passages.json` is unchanged.

**Limitation worth stating.** None of the four `JSONString` fields has rows
in this deployment — ATLAS holds only the collection hierarchy here — so
equivalence rests on the schema type being unchanged plus the converter and
serialiser check above, not on observed payloads. The `GenericScalar`
fields, which do carry data, were exercised live and return objects exactly
as before.

### 4.4 (original note) — Drop the JSONField backport

`django-jsonfield-backport` is obsolete from Django 3.1. This is the item
with real frontend-visible risk, and it is more contained than the analysis
first suggested.

Surface, measured:

| Site | Count |
|---|---|
| `atlas/models.py` JSONField declarations | 14 |
| `atlas/compat.py` | the whole file exists only for this |
| `atlas/migrations/0006_dictionary_models.py` | references the backport |
| `sv_pdl/settings.py` `INSTALLED_APPS` | `"django_jsonfield_backport"` |

Steps: swap the import in `models.py` to `django.db.models.JSONField`,
delete `compat.py` and its import, rewrite the reference in migration 0006,
drop the `INSTALLED_APPS` entry, then generate a migration for the field
change.

**The wire-format question, narrowed.** The analysis said these values
"reach the frontend as JSON strings". That is true of only **4 of the 20**
JSON-backed GraphQL fields. The other 16 are explicitly declared as
`GenericScalar` in `schema.py` (directly, or on the `AbstractTextPartNode`
base) and never touch the compat shim. From the golden schema:

| Field | Current type | Via |
|---|---|---|
| `AttributionRecordNode.data` | `JSONString!` | `compat.py` |
| `DictionaryNode.data` | `JSONString!` | `compat.py` |
| `PassageTextPartNode.metadata` | `JSONString` | `compat.py` |
| `TextAlignmentRecordNode.metadata` | `JSONString!` | `compat.py` |
| 16 others (`GenericScalar`) | unchanged | explicit declaration |

So the acceptable golden diff for this item is **at most those four fields
changing type, and nothing else**. Anything wider means the change reached
further than intended. Whether those four *should* stay `JSONString` is a
product decision: keeping them means re-registering a converter for
`models.JSONField`; letting them become `GenericScalar` means the frontend
receives an object where it currently receives a string it parses.
**Decide before implementing** — see §8.

- **Estimate:** 2–3 days, plus whatever the frontend decision costs.

### 4.5 — `default_app_config` (optional here)

Deprecated in 3.2, removed in 4.1. Present in three files:

```
packages/scaife-viewer-atlas/scaife_viewer/atlas/__init__.py:4
packages/scaife-viewer-core/scaife_viewer/core/__init__.py:4
sv_pdl/__init__.py:10
```

Django 3.2 auto-discovers a single `AppConfig` subclass per app, and each of
these has exactly one, so deleting the lines should be a no-op. It is
optional at 3.2 and mandatory at 4.1. Doing it here removes three
deprecation warnings and shrinks the 4.x step; deferring it keeps this step
smaller. Either is defensible — but if deferred, add it to
`test_removed_apis.py`'s `DEFERRED` table so it is not forgotten.

- **Estimate:** an hour, including verifying app labels are unchanged
  (`scaife_viewer_core`, `scaife_viewer_atlas` are set explicitly in
  `apps.py`, so they should be).

## 5. Verification gates

Run after **every** item in §4, not only at the end:

```
bash scripts/run-tests.sh                 # 94 tests, must stay green
bash scripts/run-tests.sh --integration   # 100, one expected failure
bash scripts/run-vendored-tests.sh        # core 4/1, atlas 12/7
bash scripts/lint.sh
bash scripts/capture-golden.sh && git diff -- '*/golden/*'
```

### The gap this step exposed: shape is not behaviour

The golden schema pins which types, fields and arguments exist. It says
nothing about whether a query *runs*. graphene-django 2.16 changed the
signature of `DjangoConnectionField.connection_resolver`, and
`atlas.schema.LimitedConnectionField` overrode it with the 2.6 signature.
The result:

- the schema built without error,
- `atlas_schema.json` was byte-identical for every field involved,
- every unit test passed,
- and **every paginated GraphQL query failed at execution** with
  `connection_resolver() missing 1 required positional argument: 'info'`.

In a browser that is a reader with no text in it. It was found by hand,
POSTing a query at the running server, not by any gate.

`sv_pdl/tests/test_graphql_execution.py` closes this. It executes a set of
representative queries — connections with and without `first`/`last`,
filtered connections, nested connections, relay `pageInfo`, an enum-typed
filter argument — against the *test* database and asserts no GraphQL
`errors` are returned. Running against an empty database is deliberate: the
failure mode is in resolver plumbing, which breaks regardless of whether
rows come back, so empty `edges` is a pass and an entry in `errors` is not.
It was verified to fail on the real defect by restoring the 2.6 signature
and watching four queries break.

**Add a query there before touching graphene versions again.** The schema
snapshot cannot see this class of breakage, and W3 is entirely made of it.

The golden diff is the primary signal. Expected behaviour per item:

| Item | Expected `atlas_schema.json` diff |
|---|---|
| 4.1 graphene-django 2.16 | ~~none~~ — **was wrong**; see §4.1 for the delta that actually landed and why it was accepted |
| 4.2 co-dependency setup.py | none |
| 4.3 Django 3.2 | none |
| 4.4 JSONField | at most the 4 fields in the table above |
| 4.5 `default_app_config` | none |

Treat the remaining predictions with the same suspicion 4.1 earned. The
value of the gate is not that the prediction is right; it is that a wrong
prediction surfaces immediately, with the exact delta, instead of reaching
the reader as a blank widget.

**A note on the capture script.** During 4.1 the golden capture wrote a
corrupt `passages.json`: the CTS resolver prints `Unable to parse <file>`
to **stdout** for corpus files with a bad refsDecl, and the script had been
redirecting stdout straight into the golden file. It only surfaced now
because the resolver's metadata cache was cold after a rebuild. The script
now anchors on a payload marker and validates JSON before writing, and
refuses to write rather than emit a bad file;
`test_passage_contract.py` reports an unparseable golden as a capture
problem rather than a bare `JSONDecodeError`. Worth knowing because a
corrupt golden was briefly baked into an image.

`passages.json` should not move at any point in this step — nothing here
touches CTS resolution. If it does, stop: that is `core` behaviour
changing under a framework bump, which is the exact failure mode the
characterisation suite exists to catch.

Beyond the automated gates, exercise `/library/`, `/reader/` and `/search/`
by hand once at the end. The golden suites cover the GraphQL contract and
CTS output, not rendering.

## 6. Known hazards

- **`django-treebeard` 4.5 → 4.7 on the corpus tree.** The highest-risk
  dependency in the set, because `Node` is the structure the reader
  traverses. Rebuild the ATLAS database from scratch rather than migrating
  in place (`rm sv-data/atlas/sentinels/.atlas_db_prepared`), and compare
  reader output through `passages.json`.
- **Migration regeneration.** The JSONField change alters migration state.
  Verify by rebuilding the database from empty, not by migrating in place —
  the technique used in §9.1 of the analysis, which is cheap here.
- **`graphene-django` 2.16 on Django 3.2 is a thin-ice combination.** Its
  metadata allows it, but 2.16 predates Django 3.2's release. It only has
  to hold long enough to reach graphene 3; if it does not, that forces
  4.1 and the graphene port into a single step, which is the main way this
  plan could go wrong.
- **`pkg_resources` in both vendored `__init__.py` files.** Not a problem at
  Django 3.2, but `core/__init__.py` and `atlas/__init__.py` call
  `pkg_resources.get_distribution(...)` at import, and `pkg_resources` is
  gone from setuptools 81+. This is why the image pins `setuptools==81.0`.
  It becomes blocking at the Python 3.12 step, not here. Replace with
  `importlib.metadata` when that step arrives.

## 7. Rollback

Every change in this step is either a version pin or an edit inside
`packages/`. There are no destructive data operations except the ATLAS
rebuild in §6, which is reproducible from the corpora in minutes.

To abandon: revert the working tree and rebuild the image. The live
Postgres database is only written by item 4.4; if that item has been
applied, restore by rebuilding the database from empty and re-running the
ingest steps (delete the relevant sentinels in `sv-data/atlas/sentinels/`).

## 8. Decisions

1. ~~**The four `JSONString` fields (§4.4).**~~ **Decided 2026-08-14:
   preserve the wire format.** The frontend does not change unless
   absolutely required. This cost nothing — graphene-django 2.16 converts
   the native `models.JSONField` to the same `JSONString` scalar, so the
   encoding is identical and `compat.py` was deleted rather than rewritten.
   See §4.4.

   **This decision is now a standing constraint on the rest of the
   upgrade**, and it bites hardest in W3: graphene 3 rewrites the layer that
   produces every one of these types. Any change that alters the GraphQL
   contract has to be justified against the prebuilt bundle, which is baked
   into the image and not a one-line edit. `atlas_schema.json` is the
   instrument for holding that line.
2. **`default_app_config` now or later** (§4.5). Still open; deferred, and
   optional until Django 4.1.
3. **Whether to take `django-sortedm2m` 4.0.0** instead of 3.1.1. Still
   open. 4.0.0 declares no Django floor at all, which may mean it is
   untested rather than compatible. 3.1.1 is installed and working.

## 9. Reproducing the measurements

```bash
# Version constraints (run on the host, needs network)
python3 -c "
import json,urllib.request
for p,v in [('graphene-django','3.0.0'),('graphene-django','2.16.0'),
            ('django-filter','23.5'),('django-treebeard','4.7.1'),
            ('django-extensions','3.2.3')]:
    d=json.load(urllib.request.urlopen(f'https://pypi.org/pypi/{p}/{v}/json'))
    print(p,v,[r for r in (d['info']['requires_dist'] or [])
               if r.lower().startswith('django') and 'extra ==' not in r])
"

APP=scaife/scaife-viewer-2026-08-10-001

# JSONField surface
grep -c 'JSONField(default=dict' \
  $APP/packages/scaife-viewer-atlas/scaife_viewer/atlas/models.py

# Which GraphQL fields are JSON-backed, and how each is currently typed
python3 -c "
import json
d=json.load(open('$APP/sv_pdl/tests/golden/atlas_schema.json'))
for t,s in sorted(d['types'].items()):
    for f,fs in sorted(s.get('fields',{}).items()):
        if f in ('metadata','data'): print(f'{t}.{f}: {fs[\"type\"]}')
"

# Type topology: which Meta blocks are hand-written vs synthesised
# (matters for the graphene step that follows this one)
grep -n '__init_subclass_with_meta__' \
  $APP/packages/scaife-viewer-atlas/scaife_viewer/atlas/schema.py
```

## 10. What this step does not do

Out of scope, and each still blocked afterwards:

- **graphene 2 → 3.** Unblocked *by* this step; must land before Django 4.0.
  21 concrete GraphQL object types are configured from 17 class definitions
  — 15 with hand-written `Meta`, plus 2 abstract bases whose
  `__init_subclass_with_meta__` covers the other 6. That structure means the
  explicit-`fields` requirement is 17 edit sites, not 21, and two of them
  are centralised.
- **Python 3.9 → 3.12.** Django 3.2 supports Python 3.9, so the interpreter
  can stay put for this step. It becomes mandatory at Django 5.2.
- **elasticsearch client 7.17 → 8/9.** Independent of Django; still capped
  by core's `elasticsearch<8`, now editable.
- **`USE_L10N` / `STATICFILES_STORAGE`.** Pinned in
  `test_removed_apis.py`'s `DEFERRED` table; neither can move before Django
  4.2.
- **The frontend.** Vue 2, Node 12 and webpack 4 remain as they are.
