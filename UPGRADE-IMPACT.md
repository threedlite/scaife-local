# Upgrade impact analysis

**Written:** 2026-08-13
**Snapshot analysed:** `scaife-viewer-2026-08-10-001`, resynced against
upstream `dev` at `ea3cce4` (2026-08-10) — i.e. upstream's current HEAD, not
a stale capture.
**Companion:** [`SBOM-2026-08-13.md`](SBOM-2026-08-13.md) — what is installed and what is EOL
**Verification:** version facts observed from the running stack; release/EOL
facts checked against upstream sources on 2026-08-13 (cited at the end).
Effort estimates are judgement, not measurement, and are flagged as such.

---

## Bottom line

**The application code in this repo is not the problem. The pinned upstream
packages are.**

A scan of `sv_pdl/` for Django APIs removed in 3.x–5.x found essentially
nothing: no `ugettext`, no `django.conf.urls.url`, no `force_text`, no
`is_ajax`, no `index_together`, no `NullBooleanField`. Three settings need
touching (`USE_L10N`, `STATICFILES_STORAGE`, the JSONField backport) and
`USE_TZ` is already `True`, so Django 5.0's default change is a no-op here.
On its own, this codebase is perhaps a **day** of work to reach Django 5.2.

The blocker is that `scaife-viewer-core` and `scaife-viewer-atlas` — the
packages providing the CTS resolver, the reader, the library, the search
indexer and the ATLAS GraphQL layer — **hard-pin `Django<3.0`**:

```
scaife_viewer_core:   Django <3.0,>=2.2      elasticsearch <8,>=7
scaife_viewer_atlas:  Django <3,>=2.2.15     graphene-django ==2.6.0
```

Those same packages contain `ugettext` (6 files),
`from django.conf.urls import url` (3 files) and `force_text` (5 files) —
**all removed in Django 4.0** — so they will not merely warn under a modern
Django, they will fail at import.

### Confirmed against upstream's current HEAD

This is worth stating precisely, because the natural question is whether our
snapshot was simply out of date. It is not: the tree was resynced against
upstream `dev` at `ea3cce4` (2026-08-10), **59 commits and five months
newer** than the previous capture. At that HEAD, upstream's own
`requirements.txt` reads:

```
Django==2.2.28                     # now an EXPLICIT pin, not just core's <3.0 ceiling
elasticsearch>=7,<8                # still capped below the 8.x server we run
scaife-viewer-atlas @ ...@0.1a15   # byte-identical to the previous snapshot
scaife-viewer-core  @ ...ed7f8777  # byte-identical to the previous snapshot
```

Upstream remains active — 59 commits of feature work in that window (GDPR
notice, rate limiting, a rewritten dictionary widget, a new search module) —
and that work targets the Django 2.2.28 base, with the same two pinned
dependency commits. The practical consequence for us is simply that
**tracking upstream does not itself move this deployment off EOL Django**;
that would be a separate piece of work, described below.

**There is therefore no incremental upgrade path.** You cannot bump Django
one major at a time and keep the app working, because the dependency that
provides most of the application declares an incompatible Django range, and
would fail at import if that constraint were bypassed.

### The three real options

| | Approach | Rough effort | Risk | Ends up where |
|---|---|---|---|---|
| **A** | **Stay put; harden.** Accept EOL, track upstream `dev`, keep dependency CVEs patched (all currently fixed), keep the firewall + loopback binding, treat the box as an appliance. | days, then ongoing | low now, rising | Still EOL Django, but no known unfixed CVEs. Defensible because this is a single-user offline reader. |
| **B** | **Fork the upstream packages.** Vendor `scaife-viewer-core` + `atlas`, port them to Django 5.2, maintain them yourself. | **months** | high | Modern stack, but you now own two libraries you did not write. |
| **C** | **Re-platform.** Keep the corpora, dictionaries, commentaries and Morpheus; replace the Django/GraphQL/Vue-2 application layer. | **quarters** | very high | A different product. |

**Recommendation: A, with the targeted fixes in "Do these regardless"
below.** This is an offline, loopback-bound, single-user reading tool with
no untrusted input and no network egress. The realistic threat model does
not justify B, and B's cost is severe and open-ended — you would be taking
on long-term maintenance of two libraries you did not write, against a
Django line their authors have not targeted. Revisit only if the deployment
model changes
(multi-user, LAN- or internet-exposed, or handling untrusted uploads).

Note that **A is not "do nothing"**: it now explicitly includes tracking
upstream `dev`, which is where the app's actual bug fixes and features come
from (see below). It just accepts that upstream's floor is Django 2.2.

### Tracking upstream: what the resync cost, and what it buys

This tree has been resynced once, from `e4b4616` (2026-03-27) to `ea3cce4`
(2026-08-10). That is the realistic maintenance cadence for option A, so
its cost is now measured rather than guessed:

- **14 files carried local modifications**; upstream had independently
  changed 9 of them. Only 5 needed genuine hand-reapplication.
- **4 local patches became obsolete** because upstream fixed the same
  problem (they deleted the polyfill.io script; added the dictionary
  widget's `selectedDictionary` watcher; dropped `flake8`/`isort` from the
  build). Divergence shrank rather than grew.
- **3 integration hazards** appeared that no file diff would reveal: the
  sentinel directory moved under `ATLAS_DATA_DIR`; a new manifest-hash check
  treats an absent hash as a mismatch and would have retried a network
  fetch; and a new `copy_corpus_repo_metadata` step stages a file that makes
  ATLAS call `api.github.com` once per repo.

That last category is the real lesson: **the risk in tracking upstream is
behavioural, not textual.** Budget for reading their diff, not just merging
it, and re-run `bash scripts/run-tests.sh` afterwards — the offline-wiring
tests exist precisely to catch a re-introduced external call.

#### New runtime behaviour this resync brought in

Three upstream additions change how the app behaves at runtime. All are kept
(upstream's API/UI behaviour is authoritative here), but they are worth
knowing about:

- **Rate limiting is now on by default.** `django-ratelimit==4.0.0` with
  `RATELIMIT_ENABLE=1` and `RATELIMIT_DEFAULT_RATE=200/m`, keyed per client
  IP by a custom `ratelimit_key` in `sv_pdl/middleware.py`. Generous for a
  single reader, but it is a new way for the app to return 429s. Disable
  with `RATELIMIT_ENABLE=0` in `deploy/.env` if it interferes.
- **Redis is now supported but optional.** `django-redis==5.2.0` is
  installed and `CACHES["default"]` uses it **only when `REDIS_URL` is
  set**; otherwise it falls back to `LocMemCache`. We do not set it, so no
  new service is required. Note the consequence: with `LocMemCache` the
  rate-limit counter is per gunicorn worker (2 here), not shared.
- **A GDPR notice** (`gdprNotice.js`, `_gdpr_notice.html`) and a rewritten
  Perseus dictionary widget with a new `PerseusDictionarySense` component.
  Both audited — neither makes any outbound request.

### Dependency CVEs — all fixed

Every confirmed CVE in the dependency set has been closed in this repo,
without touching the Django wall. Each package was pinned at a vulnerable
version upstream and is overridden in the `Dockerfile` using upstream's own
post-install pattern.

| Package | Was | Now | Closed |
|---|---|---|---|
| `gunicorn` | 19.9.0 | **23.0.0** | CVE-2024-1135 (request smuggling) |
| `certifi` | 2018.11.29 | **2026.7.22** | CVE-2023-37920, CVE-2022-23491 |
| `urllib3` | 1.26.15 | **1.26.20** | CVE-2023-43804, CVE-2023-45803, CVE-2024-37891 |

Two of the three are capped by the interpreter rather than by choice:
gunicorn 26 and urllib3 2.7 both require Python 3.10+, so 23.0.0 and
1.26.20 are the newest releases available to us on 3.9. They move again
when the interpreter does. See `SBOM-2026-08-13.md` §2 for detail.

**Re-verify after every resync.** These are overrides on top of upstream
pins; an upstream change could reintroduce a vulnerable version silently.

### Still worth doing — cheap, no upgrade needed

1. **Remove the `typing==3.7.4.3` backport.** It shadows the stdlib module
   and should not be installed on any Python 3 this project runs on. Needs
   removing before any further interpreter bump.
2. **Keep the loopback binding and the egress firewall.** They are doing
   more for your actual risk than any dependency bump on this list.

---

## Django 2.2.28 → 5.2 LTS, in detail

Target **5.2 LTS** (supported to 2028-04), not 6.0. Django 4.2 LTS is no
longer a candidate — it went EOL 2026-04-07.

### What this codebase actually has to change

Confirmed by scanning `sv_pdl/`:

| Change | Introduced | Where | Fix |
|---|---|---|---|
| `USE_L10N` deprecated, then removed | dep. 4.0, removed 5.0 | `settings.py:53` | Delete the line; localisation is always on. |
| `STATICFILES_STORAGE` → `STORAGES` | dep. 4.2, removed 5.1 | `settings.py:90` | Move `whitenoise.storage.CompressedManifestStaticFilesStorage` into `STORAGES["staticfiles"]`. |
| `django-jsonfield-backport` obsolete | Django 3.1 | atlas dependency | Replace with `models.JSONField`. Requires an atlas fork. |
| `DEFAULT_AUTO_FIELD` unset | 3.2 | `settings.py` | Set explicitly, or every app emits `models.W042` and new PKs silently become `BigAutoField`. |
| `CSRF_TRUSTED_ORIGINS` format | 4.0 | not currently set | Only relevant if you add it — entries now need a scheme (`https://host`). |
| `USE_TZ` default flips to `True` | 5.0 | `settings.py:56` | **Already `True` — no action.** |

That is the whole local surface. It is genuinely small.

### What upstream has to change (the actual work)

Removed-in-4.0 APIs present in `scaife_viewer` / `graphene_django`:

- **`ugettext` / `ugettext_lazy`** → `gettext` / `gettext_lazy` (6 files)
- **`from django.conf.urls import url`** → `re_path` (3 files)
- **`force_text` / `smart_text`** → `force_str` / `smart_str` (5 files)

These are mechanical, but they are in packages you do not control, and they
are the *shallow* layer. Below them sit the genuinely hard parts:

1. **`graphene-django==2.6.0` is exact-pinned by atlas and does not support
   Django 4+.** Graphene 3 is a breaking rewrite (schema declaration,
   resolver signatures, `graphql-core` 2→3). The ATLAS GraphQL API is a
   substantial schema. This alone is a large project.
2. **The pinned dependency set is not internally consistent already.** Core
   declares `requests==2.22.0` but the image ships 2.32.4, so the pins are
   not being enforced today. Any fork starts by untangling that.
3. **`MyCapytain` is a git-zip fork**, not the released `==3.0.1` core asks
   for. The CTS resolver behaviour depends on that fork's specifics.

### Sequencing, if you attempt B

Django's own guidance — upgrade one major at a time, with tests green
between each — applies, but you must fork first or nothing installs:

```
fork core+atlas → 2.2 → 3.2 LTS → 4.2 → 5.2 LTS
                        ↑ graphene 2→3 rewrite lands here
```

Python must move in step: **Django 5.2 requires Python 3.10+**, so the
3.8 → 3.12/3.13 jump is not optional, it is part of the same change.

---

## Python and Alpine: how much further can we go?

We already moved **3.8.20 → 3.9.25**, which took Alpine from a frozen 3.20.3
to a current 3.22.2. The question is whether more is available without the
Django work. **It is not** — 3.9 is the ceiling, and it is a hard one.

### The ceiling is Django 2.2

Django 2.2 supports Python 3.5–3.8, and 3.9 as of 2.2.17. **It does not
support 3.10.** Python 3.10 requires Django 3.2 or later — which means
`scaife-viewer-core`'s `Django<3.0`, which means the fork. So:

| | Now | Next step up | Gated on |
|---|---|---|---|
| Python | **3.9.25** (EOL 2025-10) | 3.10+ | Django 3.2+ → **fork** |
| Alpine | **3.22.2** | 3.24.1 | the Python bump above |

Measured from the official images on 2026-08-13:

```
python:3.9-alpine   -> alpine 3.22.2   Python 3.9.25    <- our ceiling
python:3.10-alpine  -> alpine 3.24.1   Python 3.10.20
python:3.11-alpine  -> alpine 3.24.1   Python 3.11.15
python:3.12-alpine  -> alpine 3.24.1   Python 3.12.13
python:3.13-alpine  -> alpine 3.24.1   Python 3.13.15
python:3.14-alpine  -> alpine 3.24.1   Python 3.14.7
```

### Alpine currency is a side effect, not a lever

This is the part worth internalising: **we do not choose the Alpine version
at all.** It comes from whichever `python:X-alpine` tag we build on. There
is no way to pull Alpine 3.24 while staying on Python 3.9.

That also makes the current win **temporary**. The `python:3.8-alpine` tag
froze at Alpine 3.20.3 once Python 3.8 went EOL and the image stopped being
rebuilt. Python 3.9 went EOL in October 2025, so `python:3.9-alpine` is on
the same path: at some point it stops being rebuilt, Alpine freezes at
3.22.2, and OS-level patches stop arriving exactly as they did on 3.8.
Alpine 3.22 itself has support runway (Alpine keeps releases ~2 years, so
into 2027), but the *image* is the constraint, not the distro.

**Practical consequence:** "keep the base image patched" is not an
independent maintenance task. It is downstream of the Django work. Until
then the honest position is that we are on the last Python the framework
supports, and the base image will age out on a timer we do not control.

### When the interpreter does move (3.12 / 3.13 as part of the fork)

- **Forced by Django 5.2** (needs 3.10+). Target 3.12 or 3.13 — 3.14 is
  fine for the language but wait for the C-extension ecosystem.
- **Risk is in C extensions**, not the language: `psycopg2` (prefer
  `psycopg[binary]` 3.x), `lxml`, `grpcio`, `PyNaCl`, `ruamel.yaml.clib`.
  All need wheels for the new interpreter **on arm64**, which is where a
  build like this usually stalls.
- **`typing==3.7.4.3` must be removed** before any further interpreter bump.
- Distutils removal in 3.12 breaks old `setup.py`-style installs — relevant
  for the git-zip pins.
- The 3.8→3.9 move already showed the shape of this: it required adopting
  upstream's `setuptools==81.0` pin, because newer setuptools drops
  `pkg_resources` and `django-user-accounts` imports it at module load.
  Expect more of that class of problem, not fewer, further up.
- **urllib3 can return to the 2.x line** at 3.10+; we are held on 1.26.20
  only because 2.7 requires Python 3.10+.

## PostgreSQL 9.6.24 → 18

EOL since 2021-11-11 — **nearly five years**. Current 18.4; 19 due 2026-09.

- Nine major versions is far outside `pg_upgrade`'s comfort; realistically
  **dump and restore**. For this app the data is regenerable anyway
  (dictionaries and commentaries are re-ingested from source in minutes,
  ATLAS is rebuilt by `prepare_atlas_db`), so a **rebuild is simpler than a
  migration** — drop the volume, bump the image, re-bootstrap.
- Watch: `standard_conforming_strings`, removal of implicit casts,
  `psycopg2` → `psycopg3`, and collation changes affecting index ordering.
  **The commentary range query depends on string ordering of zero-padded
  refs** — `test_upgrade_canaries.OrmBehaviourTests` exists precisely to
  catch a collation regression here.
- Low coupling otherwise: no stored procedures, no extensions beyond the
  default, no replication.

## Node 12 / Vue 2 / webpack 4 (frontend)

The heaviest lift after graphene, and entirely build-time.

- **Node 12 EOL 2022-04**; **Vue 2 EOL 2023-12-31**; webpack 4, `node-sass` 5
  (deprecated in favour of dart-sass), eslint 5 all EOL.
- Vue 2 → 3 is a breaking rewrite, and this app depends on
  `@scaife-viewer/scaife-widgets`, `@scaife-viewer/store` and
  `@scaife-viewer/common` — **upstream Vue 2 component libraries** with the
  same abandonment problem as the Python side.
- `node-sass` will not build on modern Node at all, so even "just bump Node"
  forces a sass migration.
- **Mitigation:** the bundle is built once and baked into the image. Nothing
  is served from a CDN and no Node runtime exists in production. An EOL
  build toolchain is a supply-chain and maintainability problem, not a
  runtime attack surface.

---

## Elasticsearch 8 → OpenSearch, in detail

### The situation today is already wrong

| | Version |
|---|---|
| Server | Elasticsearch **8.19.11** |
| Python client | `elasticsearch` **7.17.13** |
| Client pin source | `scaife-viewer-core`: `elasticsearch<8,>=7` — **and** upstream's own `requirements.txt`: `elasticsearch>=7,<8` |

**A 7.x client is driving an 8.x server** — but the resync improved this
materially. Relaxing the pin from `==7.10.1` to `>=7,<8` let pip resolve to
**7.17.13**, and a 7.17 client against an 8.x server is Elastic's
*documented transitional* configuration: compatibility mode is always on in
the Python client, and their guidance is to upgrade the server first and the
client afterwards. So this is no longer unsupported-by-luck; it is a
supported bridge. Search returns correct results across all 779,099 indexed
passages.

What remains is that a bridge is not an end state, and the client cannot
leave it while `scaife-viewer-core` caps `elasticsearch<8`.

The resync clarified this. Upstream's current `dev` changed the pin from
`elasticsearch==7.10.1` to the range `elasticsearch>=7,<8`, with a comment
pointing at Bonsai's supported versions — so the `<8` ceiling is a current,
intentional constraint with a stated reason behind it, and the 8.x server is
our own local choice rather than something upstream targets. Planning around
an upstream move to an 8.x client is not a
plan.
`sv_pdl/tests/test_upgrade_canaries.py::test_client_and_server_major_versions`
asserts this and **fails today, deliberately**, as a standing marker.

### Why OpenSearch is the natural fix, not a lateral move

**OpenSearch forked from Elasticsearch 7.10** — the same API generation the
`elasticsearch<8` cap keeps this application on. That inverts the usual
calculus:

- Migrating to OpenSearch means the **7.x client matches the server's API
  generation again**, rather than relying on a compatibility bridge.
  `opensearch-py` is itself a fork of `elasticsearch-py` 7.x, so the client
  swap is close to a rename.
- Staying on Elasticsearch means either forking core to lift
  `elasticsearch<8`, or continuing to run an unsupported pairing.

In other words, **OpenSearch resolves a defect that Elasticsearch 8
perpetuates**, without touching the `Django<3.0` wall at all. It is the one
modernisation on this page that does not require forking upstream Python.

### Portability assessment — this index is unusually portable

Inspected `deploy/scaife-viewer-es-template.json`:

| Aspect | Finding | OpenSearch |
|---|---|---|
| Template API | legacy `PUT /_template/...` | ✅ fully supported (OpenSearch kept it) |
| Field types | `text`, `keyword`, `date`, `integer` only (12 fields) | ✅ identical |
| Analysis | `icu_tokenizer` + `icu_folding` custom analyzer/normalizer | ✅ `analysis-icu` plugin exists |
| `term_vector` | `with_positions_offsets` | ✅ supported |
| ES 8-only features | **none** — no runtime fields, no `dense_vector`, no semantic/ELSER | ✅ nothing to port |
| Security | ES runs with `xpack.security.enabled=false` | equivalent: disable the OpenSearch security plugin |
| Shards/replicas | 5 / 0 | ✅ identical |

The template does not use a single post-7.10 feature. **Runtime fields —
the headline ES 8 incompatibility with OpenSearch — are not used.**

### Migration plan

The index is **derived data**: it is rebuilt from the mounted corpora in
under six minutes. Do not migrate data; re-index.

1. Swap the image in `Dockerfile-elasticsearch`:
   `opensearchproject/opensearch:2.x`, install `analysis-icu`, disable the
   security plugin (`DISABLE_SECURITY_PLUGIN=true`) to match the current
   no-auth posture behind the loopback binding.
2. Rename the compose service/env (`SV_ELASTICSEARCH_HOST` etc. can stay —
   they are just hostnames).
3. Swap `elasticsearch==7.10.1` for `opensearch-py`. Because core pins
   `elasticsearch<8`, the pragmatic route is to keep the `elasticsearch`
   package installed for import compatibility and point it at OpenSearch —
   the 7.10 wire protocol is what OpenSearch speaks. A clean swap needs a
   core fork; a working swap may not.
4. `rm sv-data/atlas/sentinels/.es_indexed` and re-bootstrap. Verify with
   `bash scripts/run-tests.sh --integration` — `test_search_index_is_queryable`
   should pass and the version-skew test should **now also pass**, which is
   the signal that this migration achieved something.

**Rough effort:** days, not weeks — and materially less than any other item
on this page.

### Licensing note

Relevant because this repo documents its licences carefully. Elasticsearch
was relicensed away from Apache 2.0 in 2021 (SSPL/ELv2); since **8.16**
Elastic added **AGPLv3** as a third option, so the *source* is OSI
open-source again. Elastic stated binary distributions were unchanged, so
the `docker.elastic.co` image this project pulls is still governed by
Elastic's binary terms rather than a plain OSI licence. **OpenSearch is
Apache 2.0 throughout, including binaries** — a better fit for a
"fully offline, open-licence snapshot", and worth reflecting in the
README's licence section either way.

---

## What the test suite covers, and what it does not

`sv_pdl/tests/` (79 tests, `bash scripts/run-tests.sh`) was written to make
these upgrades observable. It is a **canary, not a safety net.**

**Covers** — the things most likely to break silently:

- URL wiring still resolves to the *local* offline views, not upstream ones
  (`test_offline_wiring.py`) — the specific regression an upstream bump
  causes.
- Templates do not fetch from CDNs.
- JSON response shapes for dictionaries, commentaries and Morpheus — the
  contract the Vue frontend depends on.
- Cross-edition commentary matching and the zero-padded range ordering that
  the SQL depends on (collation regressions).
- Beta Code → Unicode and accent-stripping, which `unicodedata` upgrades can
  shift.
- Django system checks and migration drift for the local apps.
- Client/server version skew for Elasticsearch (`--integration`).

**Does not cover:**

- The CTS resolver, reader, library browse and search indexer — all live in
  `scaife-viewer-core`, are untested here, and are where a Django upgrade
  will actually explode.
- The GraphQL/ATLAS layer.
- Any frontend JavaScript (the repo has a `npm run unit` step in the
  Dockerfile; it is not part of this suite).
- Real Morpheus responses (mocked) and real corpus parsing.

So: a green suite after a dependency bump means *the offline patches and
local apps survived*. It does not mean the application works. Boot the stack
and exercise `/library/`, `/reader/`, `/search/` before believing anything.

---

## Sources

- [scaife-viewer-core on PyPI](https://pypi.org/project/scaife-viewer-core/) — latest 0.3rc1, 2023-12-24, `Django<3.0`
- [Django download / supported versions](https://www.djangoproject.com/download/)
- [Django security releases, April 2026 (6.0.4, 5.2.13, 4.2.30)](https://www.djangoproject.com/weblog/2026/apr/07/security-releases/)
- [Django moving to an annual release cycle (DEP 20)](https://www.djangoproject.com/weblog/2026/aug/10/annual-release-cycle/)
- [Python EOL schedule](https://endoflife.date/python)
- [PostgreSQL versioning policy](https://www.postgresql.org/support/versioning/)
- [CVE-2024-1135 — Gunicorn](https://github.com/advisories/GHSA-w3h3-4rj7-4ph4)
- [CVE-2023-37920 — certifi](https://www.wiz.io/vulnerability-database/cve/cve-2023-37920)
- [Migrating from Elasticsearch to OpenSearch](https://docs.opensearch.org/latest/migration-assistant/is-migration-assistant-right-for-you/)
- [Elasticsearch is Open Source, Again (AGPLv3 from 8.16)](https://www.elastic.co/blog/elasticsearch-is-open-source-again)
