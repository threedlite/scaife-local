# Scaife Viewer — Local, Fully Offline Snapshot

Local Scaife Viewer instance for Ancient Greek + Latin reading, modified to
run **fully offline** with no runtime dependency on `services.perseids.org`
or `atlas.perseus.tufts.edu`.

- `scaife/scaife-viewer-2026-03-27-001/` — the main Django+Vue application (patched)
- `data-sources/` — Perseus CTS text corpora (`.gitignore`d; auto-fetched)
- `deps/` — cloned code dependencies (`.gitignore`d; auto-fetched)
- `sv-data/` — host-side working tree bind-mounted into the container (CTS staging + sentinels + ATLAS DB)
- `scripts/fetch-data.sh` — one-time fetch of everything in `deps/` and `data-sources/`
- `bootstrap.sh` — end-to-end Docker Compose bring-up (calls `fetch-data.sh` on first run)
- `deploy/docker-compose.override.local.yml` (inside the main app) — local overrides

Text corpora (Perseus/CTS content) live inside this tree at
`./data-sources/` (`$SCAIFE_DATA_SOURCES` defaults to that path). They are
bind-mounted read-only into the container. Nothing in the corpora is
downloaded at runtime, and the tree is fully self-contained.

## Requirements

- **macOS** (Intel or Apple Silicon), **Linux** (x86_64 or arm64), or any
  other Docker-capable OS. Only tested end-to-end on macOS + Linux.
- **Docker** (Engine 20.10+ with the Compose v2 plugin — comes bundled
  with Docker Desktop; on Linux it's `docker-compose-plugin` or newer).
- **Disk**: ~4 GB free for images + data + build cache.
- **RAM allocated to Docker**: 4 GB minimum, 6 GB comfortable.
  Docker Desktop users: Settings → Resources → Memory.
- **Internet during the first build only.** Everything is downloaded then
  and baked into images. Runtime is fully offline.

### Installing Docker

**macOS:**
```
brew install --cask docker            # then launch Docker Desktop once
# or: https://www.docker.com/products/docker-desktop/
```

**Linux (Debian/Ubuntu):**
```
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker "$USER"       # log out + back in so it takes effect
sudo systemctl enable --now docker
```

**Linux (Fedora/RHEL):**
```
sudo dnf install -y docker docker-compose-plugin
sudo systemctl enable --now docker
sudo usermod -aG docker "$USER"       # log out + back in
```

## Running it (fresh machine)

```
# 1. Clone this repo somewhere.
git clone <this repo> scaife-local
cd scaife-local

# 2. One command. First run takes ~30-45 min (image builds + one-time
#    3 GB fetch of Perseus + Morpheus + LSJ sources). Subsequent runs
#    start in ~30 s.
bash ./bootstrap.sh
```

That's it. When it prints `Listening at: http://0.0.0.0:8000`, open
<http://localhost:8000/library/> in your browser.

The bootstrap script:

1. Checks Docker is running.
2. Runs `scripts/fetch-data.sh` if `deps/` or `data-sources/` are empty —
   clones nine open-license repos (~3 GB shallow, one-time).
3. Stages a writable `sv-data/` tree with sentinels so the container
   entrypoint skips its own tarball downloads.
4. Writes `deploy/.env` (mode 0600) if missing.
5. Builds `scaife-viewer-base:latest` from the untouched upstream Dockerfile.
6. Runs `docker compose up --build` which builds the hardened + morpheus
   images on top and starts everything.

Optional environment overrides:

- `SCAIFE_DATA_SOURCES=<abs path>` — Perseus corpora location. Defaults to
  `./data-sources/` inside this repo. Override if you keep the corpora
  elsewhere.
- `SCAIFE_BIND=0.0.0.0` — expose ports to your LAN. Defaults to `127.0.0.1`
  (loopback only). See "Security hardening applied" below.

### Linux notes

Most Linux distros work out of the box. Two occasional gotchas:

- **SELinux (Fedora / RHEL / Rocky):** bind mounts may be blocked with
  "Permission denied". Fix by adding `:z` to each host-side bind mount in
  `scaife/scaife-viewer-2026-03-27-001/deploy/docker-compose.override.local.yml`
  — e.g. `- ${SCAIFE_REPO_ROOT}/sv-data:/sv-data:z`. This relabels the
  files with a shared SELinux context so the container can read/write them.
- **Host UID mismatch:** the container runs gunicorn as UID 1000. If your
  host user is not UID 1000, the container may fail to write into
  `sv-data/` (the sentinel/atlas dir). Check with `id -u`; if you're not
  1000, either `chown -R 1000:1000 sv-data/` on the host, or edit
  `Dockerfile-local` to `adduser -u <your-uid>` and rebuild.
- **Rootless Docker:** `cap_add: NET_ADMIN` needs the rootless daemon to
  have `CAP_NET_ADMIN` in its bounding set. If bootstrap fails during the
  `entrypoint-locked.sh` step with `iptables: Permission denied`, either
  run as root Docker or drop the firewall layer (comment out the
  `cap_add`, `user: "0"`, and `entrypoint:` lines in the override — you
  still have the widget patches + DNS block as defenses).

The bootstrap script derives its own root from `$(dirname "$0")` and
exports `SCAIFE_REPO_ROOT` for the compose file, so nothing here is
pinned to a specific home directory. The whole tree can be moved or
renamed freely.

### Stopping / restarting

To stop the stack cleanly:

```
cd scaife/scaife-viewer-2026-03-27-001
SCAIFE_REPO_ROOT=<abs path to repo root> \
SCAIFE_DATA_SOURCES=<abs path to data-sources> \
docker compose -f deploy/docker-compose.yml -f deploy/docker-compose.override.local.yml down
```

Or just Ctrl-C the foreground `bootstrap.sh` — it uses `exec` for compose
so the signal propagates. Data is persistent in Docker volumes
(`sv-postgres-data`, `sv-elasticsearch-data`) — the next `bootstrap.sh`
comes back with the same DB + search index.

### Applying updates

If you edit any of the frontend (`static/src/js/**`), templates, or Python
source, `bootstrap.sh` will rebuild the affected Docker layers
automatically — no separate step needed. The upstream image is cached
until the source in the static-build stage actually changes.

### API access

Once the app is running:

- Interactive Swagger UI: <http://localhost:8000/api/docs/>
- Machine-readable OpenAPI 3.0 spec: <http://localhost:8000/api/openapi.json>

Both are served from local static assets — no external CDN.

## Offline architecture

Four containers, all built locally. Images are compiled from source for
whatever architecture your machine reports (arm64 or x86_64). No image
pulls from Docker Hub at runtime.

| Container | Role | Source |
|---|---|---|
| `scaife-viewer` | Django + Gunicorn + built Vue bundle | `scaife/scaife-viewer-2026-03-27-001/Dockerfile` |
| `morpheus` | Perseids Morpheus (C) + Ruby Sinatra JSON API | `deps/morpheus-combined/Dockerfile` |
| `sv-postgres` | Postgres 9.6 (Perseus data + ATLAS DB + local dictionaries + local commentaries) | official image |
| `sv-elasticsearch` | ES 7.10 (text search index) | `Dockerfile-elasticsearch` in the app |

### Features and what backs each

| Feature | Endpoint | Data path | Offline? |
|---|---|---|---|
| Read Greek/Latin texts | `/reader/…`, `/library/passage/…` | CTS resolver → mounted `canonical-greekLit`/`-latinLit`/`-pdlrefwk` | ✓ |
| Library browse | `/library/`, `/library/json/` | CTS resolver | ✓ |
| Text search | `/search/` | Elasticsearch (indexed at first boot) | ✓ |
| **Morphology** (form → lemma) | `/morpheus/?word=…&lang=…` | `morpheus` container | ✓ |
| **Dictionaries** (LSJ, Middle Liddell, Lewis & Short) | `/library/dictionaries/…` | Postgres via `sv_pdl/localdict` app | ✓ |
| **Commentaries** (Nagy et al. on Homer/Pausanias/Pindar) | `/library/commentaries/…/json/` | Postgres via `sv_pdl/localcomm` app | ✓ |

### Data volumes

| Feature | Rows |
|---|---|
| CTS text groups | 154 authors (Greek + Latin + reference works) |
| LSJ entries | 116,497 |
| Lewis & Short entries | 103,232 |
| Middle Liddell entries | 36,491 |
| Commentary entries | 7,656 across 14 named commentaries |

## Changes made to the upstream app for offline operation

### 1. Frontend CDN scripts pulled locally

Upstream templates loaded jQuery from `unpkg.com`, an `IntersectionObserver`
polyfill from `polyfill.io` (a domain hijacked in 2024), and Font Awesome
icons from `use.fontawesome.com`. All replaced:

- `sv_pdl/templates/site_base.html` — jQuery URL swapped for `{% static 'vendor/jquery.min.js' %}`; the `use.fontawesome.com` script tag removed (icons are already bundled via `@fortawesome/*` npm deps).
- `sv_pdl/templates/app.html` — polyfill URL swapped for `{% static 'vendor/polyfill.min.js' %}`.
- `sv_pdl/templates/reader/reader.html` (new) — local override of the same-named template in `scaife_viewer.core`; polyfill URL swapped.
- `static/vendor/{jquery,polyfill}.min.js` — the two files themselves.
- `sv_pdl/settings.py` — `STATICFILES_DIRS` extended with `("vendor", <path>)` so `collectstatic` picks up the vendor files.

### 2. Morpheus service brought in-cluster

Upstream `scaife_viewer.core.views.morpheus` proxied to
`services.perseids.org/bsp/morphologyservice/`. Replaced with a container:

- `deps/morpheus-perseids/` — cloned upstream (Perseids C fork of Morpheus, MPL 2.0).
- `deps/morpheus-perseids-api/` — cloned upstream (Ruby Sinatra JSON wrapper, MIT).
- `deps/morpheus-combined/Dockerfile` — multi-stage build that compiles Morpheus on Ubuntu 22.04 (arm64 or x86_64 — whatever the host is) and layers the Ruby wrapper on top (glibc match required).
- `deploy/docker-compose.override.local.yml` — adds the `morpheus` service, port 1500.
- `sv_pdl/views.py` — new `morpheus_local` view calls the local service and reshapes the response to the flat `{Body: [...]}` shape the frontend expects.
- `sv_pdl/urls.py` — `/morpheus/` re-routed to `morpheus_local` instead of the upstream import.

### 3. Local dictionaries app

Upstream `dictionaries` / `dictionary_entries` views proxied to
`atlas.perseus.tufts.edu`. Replaced with a Django app backed by TEI XML
ingested at setup time:

- `sv_pdl/localdict/` (new app)
  - `models.py` — `Dictionary`, `DictionaryEntry` (headword, normalized headword, accent-stripped headword for lemma lookup, HTML intro text).
  - `betacode.py` — minimal TLG Beta Code → polytonic Greek Unicode converter (LSJ TEI is Betacode-encoded).
  - `normalize.py` — NFC and accent-strip helpers.
  - `views.py` — `dictionaries_json`, `dictionary_entries` matching the atlas API response shape.
  - `management/commands/ingest_dictionaries.py` — parses TEI from three sources:
    - LSJ from `PerseusDL/lexica/CTS_XML_TEI/perseus/pdllex/grc/lsj/` (Betacode → Unicode inline)
    - Lewis & Short from `PerseusDL/lexica/…/lat/ls/`
    - Middle Liddell from `canonical-pdlrefwk/data/viaf66541464/`
  - `migrations/0001_initial.py`.
- `sv_pdl/settings.py` — app added to `INSTALLED_APPS`.
- `sv_pdl/urls.py` — `/library/dictionaries/json/` and `/library/dictionaries/<slug>/entries/` re-routed to the local views.

### 4. Local commentaries app

Upstream `commentaries` view proxied to `atlas.perseus.tufts.edu`. Replaced
with a Django app backed by Open-Commentaries markdown files:

- `sv_pdl/localcomm/` (new app)
  - `models.py` — `Commentary`, `CommentaryEntry` (target URN + normalized textgroup+work key + zero-padded ref range for range-overlap lookup + HTML content).
  - `refs.py` — CTS URN parser + reference range/zero-pad helpers (edition-agnostic, so a commentary on `tlg0012.tlg001:1.1-1.12` matches a passage under `tlg0012.tlg001.perseus-grc2:1.5`).
  - `views.py` — `commentaries_json` matching the atlas API response shape.
  - `management/commands/ingest_commentaries.py` — parses `@urn:…` records from markdown files in three source repos, converts a subset of Markdown to HTML.
  - `migrations/0001_initial.py`.
- `sv_pdl/settings.py` — app added.
- `sv_pdl/urls.py` — `/library/commentaries/<urn>/json/` re-routed to the local view.

### 5. Docker Compose local override

`scaife/scaife-viewer-2026-03-27-001/deploy/docker-compose.override.local.yml`
(new) does the wiring:

- Adds the `morpheus` service (built from `deps/morpheus-combined/Dockerfile`).
- Wires `scaife-viewer` to depend on `morpheus`.
- Sets `CTS_RESOLVER=local`, `CTS_LOCAL_DATA_PATH=/sv-data/cts`, `CONTENT_MANIFEST_PATH=…/local.yaml`, `MORPHEUS_LOCAL_URL=http://morpheus:1500`.
- Bind-mounts:
  - Corpora: `canonical-greekLit/data`, `canonical-latinLit/data`, `canonical-pdlrefwk/data` → `/sv-data/cts/PerseusDL-canonical-*-local/data` (read-only).
  - LSJ + L&S TEI: `deps/lexica` → `/host-lexica` (read-only).
  - Commentaries: `deps/` → `/host-commentaries` (read-only).
  - Writable: `sv-data/` → `/sv-data` (sentinels + ATLAS DB).

### 6. Bootstrap script

`bootstrap.sh` stages `sv-data/`, pre-creates the `.text_repos_loaded`
sentinel (so the container's `entrypoint.sh` skips the network fetch of
tarballs from GitHub), writes `deploy/.env` with sane defaults, then runs
`docker compose up --build`.

## Re-ingesting data

Corpora are mounted read-only, so nothing to re-run for text updates.
Dictionaries and commentaries are Postgres-backed; the ingest commands can
be re-run at any time inside the container:

```
docker exec scaife-viewer python manage.py ingest_dictionaries --reset
docker exec scaife-viewer python manage.py ingest_commentaries --reset
```

## Remaining external network use

None at *runtime*. During initial `docker compose up --build`:
- Base OS images are pulled once from Docker Hub (`ubuntu:22.04`, `postgres:9.6-alpine`, `node:12.13-alpine`, `python:3.8-alpine`).
- `pip install` and `npm ci` fetch language deps.

Once the images are built, a fully offline host can run the stack with
`docker compose up` (no `--build`) and no network access.

## Security hardening applied

The upstream Scaife Viewer deployment is intended to run behind a real
load balancer with hosts-side firewall rules. Since this local snapshot is
run on a workstation, some defaults were tightened.

### 1. Host ports bound to loopback

Upstream `deploy/docker-compose.yml` exposed ports on `0.0.0.0`, meaning any
peer on the same LAN could talk to Django, Postgres, and Elasticsearch
without authentication (Postgres has a trivial `scaife/scaife` password;
ES 7.10 has no auth at all). Changed to bind on `127.0.0.1` for all four
services (Django 8000, Postgres 5433, ES 9200, Morpheus 1500):

```yaml
ports:
  - ${SCAIFE_BIND:-127.0.0.1}:${SCAIFE_VIEWER_PORT:-8000}:8000
```

The env var `SCAIFE_BIND` lets you explicitly opt in to LAN exposure
(e.g. `SCAIFE_BIND=0.0.0.0 bash ./bootstrap.sh`).

### 2. `.env` file permissions

`deploy/.env` (containing `DATABASE_URL` with the DB password) is written
with mode `0600` by `bootstrap.sh` so it isn't world-readable. Re-run of
bootstrap re-chmods any existing file for safety.

### 3. Non-root container

Upstream `Dockerfile` runs gunicorn as UID 0. Added `Dockerfile-local` that
`FROM`s the untouched upstream image (built and tagged as
`scaife-viewer-base:latest` by `bootstrap.sh`) and adds a `scaife` user
(UID 1000) plus a locked-down launcher. The upstream Dockerfile is not
modified.

### 4. In-container outbound firewall (`entrypoint-locked.sh`)

`Dockerfile-local` installs `iptables` + `su-exec` and copies
`deploy/entrypoint-locked.sh` in. The compose override starts the
container with `user: "0"` + `cap_add: NET_ADMIN` — just long enough to
install the following `OUTPUT` chain, then `su-exec`s down to `scaife`:

```
ACCEPT  -o lo
ACCEPT  ctstate RELATED,ESTABLISHED
ACCEPT  -d 127.0.0.0/8
ACCEPT  -d 172.16.0.0/12
ACCEPT  -d 10.0.0.0/8
ACCEPT  -d 192.168.0.0/16
ACCEPT  -d 169.254.0.0/16
REJECT  --reject-with icmp-net-unreachable
```

Net effect: the app can reach loopback, `sv-postgres`, `sv-elasticsearch`,
`morpheus`, and Docker's embedded DNS at 172.16-172.31 — but **any packet
addressed to the public internet is dropped by the kernel**, with an
immediate `Network unreachable` error to the caller. This is stronger
than the earlier hostname-allowlist approach (`extra_hosts:` DNS
mapping, kept as an additional layer) because it catches unknown
hostnames, direct-IP connections, and future upstream deps I didn't audit.

Verified with:
- `wget 1.1.1.1` inside the container → `Network unreachable`
- `wget morpheus:1500/analysis/word?…` → real Morpheus JSON
- `curl http://localhost:8000/*` from the host → 200

The firewall did catch one leak I'd missed: `sv_pdl/views.py::_latest_release()`
was still calling `github.com` via the PyGithub client to display the
latest scaife-viewer release on the home page. Replaced with a stub
returning `{}`.

### 5. Dead-code proxy views removed

`sv_pdl/views.py` still had two functions (`dictionaries`,
`dictionary_entries`) that proxied to `atlas.perseus.tufts.edu` with no
`timeout=` on the `requests.get()` call. After the local dictionaries app
took over these URLs, the functions were unreachable but still present;
removed both.

### 6. Frontend widgets that hit external hosts

Three widgets (`WidgetTokenList`, `WidgetWordList`, `NewAlexandriaWidget`)
called `morph.perseus.org`, `vocab.perseus.org`, and
`chs-homer-proxy.herokuapp.com`. Each was patched to force
`enabled()` to return `false`, and — because the `passage` watcher fires
regardless of `enabled` — each fetch method now starts with an
`if (!this.enabled) return;` early exit. Belt-and-suspenders so no code
path can leak.

### Verified safe

- **XSS via commentary content.** `sv_pdl/localcomm` runs source markdown
  through `html.escape()` before re-injecting only `<em>`, `<strong>`,
  and `<p>` tags. The frontend `WidgetPerseusCommentary.vue` uses
  `v-html="entry.content"` but the payload is pre-escaped, and the source
  files themselves are trusted (open-license markdown from Open-Commentaries).
- **SQL injection.** Both new apps (`localdict`, `localcomm`) are
  ORM-only. No `raw()`, `extra()`, or string-built queries.
- **Path traversal in ingest commands.** Paths come from environment
  variables set by `bootstrap.sh` (`LEXICA_DATA_PATH`,
  `COMMENTARIES_DATA_PATH`, etc.), not from HTTP request data.

### Not fixed (accepted for offline single-user context)

- **`DEBUG=1`** in `deploy/.env`. Leaks tracebacks. Fine on loopback for a
  single user; set `DEBUG=0` + `SECRET_KEY=<random>` in `.env` and
  `SECURE_SSL_REDIRECT=0` (still — no HTTPS locally) to tighten.
- **Postgres `scaife/scaife` password.** Now only reachable via loopback,
  so not network-exploitable. Any local process on the host can still
  reach it; rotate the password if that matters for you.
- **Django 2.2.28 is EOL** as of 2022. Several CVEs since. Upgrading is a
  large project (migrations across many apps, MyCapytain fork, deprecated
  APIs); out of scope for this snapshot.

## Licenses

**Almost all of this project is Perseus / upstream code and data, not
mine.** The Scaife Viewer Django+Vue application, `scaife-viewer-core`,
`scaife-viewer-atlas`, `MyCapytain`, `Morpheus`, `PerseusDL/lexica` (LSJ +
Lewis & Short TEI), the Open Commentaries markdown, and the three Perseus
text corpora are all authored by other people and remain under their
original upstream licenses (MIT, MPL 2.0, or CC BY-SA 4.0 as noted below).

The **MIT license at `LICENSE`** applies **only** to files I newly authored
for this local offline build — roughly `bootstrap.sh`, `scripts/`,
`Dockerfile-local`, `entrypoint-locked.sh`, the two new Django apps
under `sv_pdl/localdict/` and `sv_pdl/localcomm/`, the OpenAPI schema,
the `homepage.html` / `licenses.html` / `swagger.html` / `reader/reader.html`
templates I added or overrode, and small edits to `sv_pdl/settings.py`,
`sv_pdl/urls.py`, `sv_pdl/views.py`, and four widget `.vue` files. The
`LICENSE` file itself enumerates the exact list. The rest of the tree is
not mine to relicense.

The full breakdown of every upstream code library and every data source
(with license, source repo, and redistribution obligations) is at
<http://localhost:8000/licenses/> when the app is running, or in the tables
below.

All entries below reflect the license as declared in each repo at the time of
cloning (2026-08-10). Repos that ship with no `LICENSE` file are noted
explicitly — under default copyright law, absence of a license means "all
rights reserved" unless a repo README says otherwise.

### Main application

| Path | License | Copyright |
|---|---|---|
| Local additions (small — see `LICENSE`) | MIT | 2026 Dan Meany |
| `scaife/scaife-viewer-2026-03-27-001/` (bulk of the tree) | MIT | 2017–2020 Perseus Digital Library |

### `deps/` — dependencies and ecosystem repos

| Repo | License | Copyright | Notes |
|---|---|---|---|
| `backend` | MIT | 2017–2020 Perseus Digital Library | Licenses live in `core/LICENSE` and `atlas/LICENSE` (no top-level LICENSE) |
| `frontend` | MIT | 2017–2020 Perseus Digital Library | Top-level `package.json` declares MIT; every one of the 42 sub-packages carries its own MIT `LICENSE` |
| `scaife-widgets` | MIT | 2017–2020 Perseus Digital Library | |
| `MyCapytain` | **MPL 2.0** | (see `LICENSE.txt`) | `jacobwegner` fork used by `requirements.txt` |
| `scaife-cts-api` | MIT | 2017–2018 Perseus Digital Library | |
| `scaife-search-indexer` | MIT | 2017–2019 Perseus Digital Library | |
| `scaife-skeleton` | MIT | 2017–2020 Perseus Digital Library | |
| `scaife-stack` | MIT (placeholder) | *unspecified* | Both `frontend/LICENSE` and `backend/LICENSE` say `FIXME: Licensee?` in place of a copyright holder |
| `ogl-pdl-annotations` | MIT | 2017–2021 Perseus Digital Library | |
| `explorehomer` | MIT | 2017–2020 Perseus Digital Library | |
| `explorehomer-atlas` | MIT | 2017–2020 Perseus Digital Library | |
| `sv-mini-atlas` | MIT | 2017–2020 Perseus Digital Library | |
| `morpheus-perseids` | **MPL 2.0** | Perseids Project | C morphology engine |
| `morpheus-perseids-api` | MIT | 2018 Perseids Project | Ruby JSON wrapper around Morpheus |
| `morpheus-combined` | (local) | — | Multi-stage Dockerfile that builds Morpheus + API natively for the host architecture (arm64 or x86_64) |
| `lexica` | CC BY-SA 4.0 | Perseus Digital Library | Full LSJ (27 shards, Betacode) + Lewis & Short TEI |
| `harrington-trees` | MIT | 2018 Perseids Project | Treebank commentaries (cloned but not currently ingested) |
| `homer.opencommentaries.org` | MIT | 2026 New Alexandria Foundation | Homer commentary markdown |
| `pausanias.opencommentaries.org` | MIT | 2025 New Alexandria Foundation | Pausanias commentary markdown |
| `pindar.opencommentaries.org` | MIT | 2026 New Alexandria Foundation | Pindar commentary markdown |

### Removed

The following downstream demo/atlas repos were cloned but removed because they
shipped with no license and are not required dependencies of the main app:
`delarose`, `hmt-cite-atlas`, `readbeowulf-atlas`, `readhomer`, `treebank-atlas`.

### Summary

- **MIT**: main app + 11 original deps + 4 offline-added deps (morpheus API, harrington-trees, 3 Open-Commentaries content repos)
- **MPL 2.0**: `MyCapytain` (fork) + `morpheus-perseids` (C morphology engine)
- **CC BY-SA 4.0**: `lexica` (LSJ + L&S TEI) + all three Perseus text corpora on disk
- **Placeholder / FIXME**: `scaife-stack`

### Perseus data (dictionaries + text corpora, external to this snapshot)

Data lives inside this tree at `./data-sources/` (overridable via
`$SCAIFE_DATA_SOURCES`), copied in from `PerseusDL/*` clones. Every corpus
is under **Creative Commons Attribution-ShareAlike 4.0 International
(CC BY-SA 4.0)**:

| Repo | License | Contents |
|---|---|---|
| `PerseusDL/canonical-greekLit` | CC BY-SA 4.0 | Ancient Greek texts (Homer, Plato, tragedians, etc.) |
| `PerseusDL/canonical-latinLit` | CC BY-SA 4.0 | Latin texts (Vergil, Cicero, Ovid, etc.) |
| `PerseusDL/canonical-pdlrefwk` | CC BY-SA 4.0 | Reference works / dictionaries: Liddell–Scott–Jones, Lewis & Short, Autenrieth, Smith's dictionaries (VIAF-keyed) |

CC BY-SA 4.0 obligations if you redistribute or serve these:
- **Attribution**: credit Perseus Digital Library and preserve copyright notices.
- **ShareAlike**: any adapted/derived version of these texts or dictionaries
  must be released under CC BY-SA 4.0 (or a compatible license). Code that
  merely reads or serves the data is not a derivative work; edits to the XML
  themselves are.
- **No additional restrictions**: don't apply DRM or extra legal terms that
  would prevent downstream reuse of the data.

Full license text: `<data-source>/license.md` in each corpus repo.

### MPL 2.0 obligations (`MyCapytain`)

MPL 2.0 is *file-level* copyleft. It behaves like MIT in most day-to-day cases,
with one added obligation:

- **Using `MyCapytain` as an unmodified dependency**: keep the `LICENSE.txt`
  and copyright notice. No other obligations. Surrounding Scaife code stays
  under whatever license you like.
- **Modifying any file in `MyCapytain`**: the modified files must be made
  available under MPL 2.0 (source form). Files you add alongside them —
  and the rest of your project — are not affected; MPL does not "spread"
  the way GPL does.
- **Redistributing a build that includes `MyCapytain`**: point users to where
  they can obtain the MPL-licensed source of `MyCapytain` (a link to the fork
  is sufficient).
- **Patent grant**: contributors grant a patent license covering their
  contributions; it terminates automatically if you initiate patent
  litigation over the covered code.

Full license texts are in each repo's `LICENSE` (or `LICENSE.txt`) file.
