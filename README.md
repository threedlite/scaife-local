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

> ### ⚠️ Known limitation: full-text search is a 1,000-passage sample
>
> Out of the box, **`/search/` covers only a tiny fraction of the corpus.**
> First boot runs the indexer with `--limit=1000`, so all but 1,000 passages
> — across 154 authors of Greek and Latin — are invisible to search. A query
> returning nothing usually means the text was never indexed, not that the
> phrase is absent.
>
> Everything else is complete and unaffected: reading, library browse, all
> 256,220 dictionary entries, all 7,656 commentary entries, and morphology.
>
> This is a deliberate trade for a fast first boot. To fix it, re-run the
> indexer with a higher cap — safe to repeat, and it overwrites rather than
> duplicates. Against a running stack, no restart needed:
>
> ```
> curl -s localhost:9200/scaife-viewer/_count      # what you have now
> docker exec -u scaife scaife-viewer \
>     python manage.py indexer --max-workers=1 --limit=25000
> ```
>
> Drop `--limit` entirely for the whole corpus — budget hours. To make it
> the default for future boots instead, see
> [How to fix it](#how-to-fix-it) under Search index coverage.

## Requirements

- **macOS** (Intel or Apple Silicon) or **Linux** (x86_64 or arm64) —
  the two platforms tested end to end. **Windows** should work via WSL2 but
  is **untested**; see "Windows notes" below before trying. Any other
  Docker-capable OS is fair game on the same terms.
- **Docker** (Engine 20.10+ with the Compose v2 plugin — comes bundled
  with Docker Desktop; on Linux it's `docker-compose-plugin` or newer).
- **Disk**: budget **~10 GB** free. Measured on a completed arm64 install:
  ~4.1 GB of images (the app image layers over the base, so they share
  most of their size), ~1.3 GB of Docker volumes once Postgres is
  populated, and ~1.4 GB of cloned corpora and deps in the working tree —
  call it 7 GB at rest, plus headroom for intermediate build layers.
- **RAM allocated to Docker**: 4 GB minimum, 6 GB comfortable.
  Docker Desktop users: Settings → Resources → Memory. On the WSL2 backend
  that slider does nothing — use `.wslconfig` (see "Windows notes"); under
  Colima, size the VM at `colima start` (see "macOS notes").
- **Internet during the first build only.** Everything is downloaded then
  and baked into images. Runtime is fully offline.

### Installing Docker

**macOS:**
```
brew install --cask docker            # then launch Docker Desktop once
# or: https://www.docker.com/products/docker-desktop/
```

Note the `--cask` — that's Docker Desktop, which bundles Compose. The
similarly-named `brew install docker` formula is the bare CLI and needs
extra wiring; see "macOS notes" below.

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

**Windows (untested — see "Windows notes"):**
```
wsl --install                         # then reboot
winget install Docker.DockerDesktop   # or https://www.docker.com/products/docker-desktop/
# Docker Desktop → Settings → Resources → WSL Integration → enable your distro
```
Run everything from inside the WSL2 distro, not PowerShell.

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

Reading, browsing, dictionaries, and morphology are fully populated at this
point. **Search is not** — it holds a 1,000-passage sample until you index
the full corpus. See the callout at the top and
[Search index coverage](#search-index-coverage).

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

### macOS notes

Docker Desktop works out of the box. Two gotchas if you installed Docker
via Homebrew instead:

- **`docker: unknown command: docker compose`.** The `docker` formula ships
  only the CLI; the Compose v2 plugin comes from the separate
  `docker-compose` formula, which Homebrew installs to
  `/opt/homebrew/lib/docker/cli-plugins/` — a directory the Docker CLI does
  not search. `bootstrap.sh` preflights this and stops immediately with the
  fix, but the link is worth doing up front:
  ```
  brew install docker-compose
  mkdir -p ~/.docker/cli-plugins
  ln -sfn /opt/homebrew/lib/docker/cli-plugins/docker-compose ~/.docker/cli-plugins/docker-compose
  docker compose version     # should print v2.x or later
  ```
  (On Intel Macs the Homebrew prefix is `/usr/local` rather than
  `/opt/homebrew`.)
- **[Colima](https://github.com/abiosoft/colima) as the daemon.** Works
  fully, including the `NET_ADMIN` firewall layer. The VM's memory *is* the
  "RAM allocated to Docker" figure under Requirements above, and Colima's
  default is well under the 4 GB minimum, so size it explicitly:
  ```
  colima start --cpu 4 --memory 6 --disk 60
  colima list      # verify MEMORY before running bootstrap
  ```
  (Verified on a 6-CPU / 12 GiB / 100 GiB aarch64 Colima VM.)
  Both Linux gotchas below are moot under Colima: virtiofs maps bind-mount
  ownership so the UID-1000 mismatch never appears (your macOS UID is
  typically 501), and Colima's in-VM daemon is rootful so `cap_add:
  NET_ADMIN` is granted normally.

### Linux notes

Most Linux distros work out of the box. Three occasional gotchas:

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

### Windows notes (UNTESTED)

**Nobody has run this stack on Windows end to end.** Everything below is
reasoned from how the pieces work, not from a successful run — treat it as
a starting point, and please correct this section once you've done it.

The intended path is **WSL2 + Docker Desktop with the WSL2 backend**, with
`bootstrap.sh` run from inside the WSL2 distro. Four things are worth
getting right before you start:

- **Run it from WSL2, not PowerShell / CMD / Git Bash.** `bootstrap.sh` is
  bash, and it exports `SCAIFE_REPO_ROOT` as a POSIX path that the compose
  file interpolates directly into bind-mount sources. Git Bash's MSYS path
  translation mangles those into Windows paths, and the mounts will not
  resolve. In Docker Desktop, enable Settings → Resources → WSL Integration
  for your distro so `docker` works inside it.
- **Clone into the WSL2 filesystem, not `/mnt/c/`.** Put it at something
  like `~/git/scaife-local`. The corpora bind mounts see heavy small-file
  I/O (~1.4 GB across the three CTS repos), and mounts served out of
  `/mnt/c` cross the drvfs boundary — the usual result is a drastic
  slowdown, and Linux ownership/permission semantics there differ from the
  native ext4 the containers expect.
- **Line endings.** `deploy/entrypoint.sh` is read by `/bin/sh` inside a
  Linux container, so a CRLF checkout breaks it with
  `$'\r': command not found`. The `.gitattributes` in this repo pins `*.sh`
  (and Dockerfiles / compose YAML) to `eol=lf`, so a default
  `core.autocrlf=true` checkout is already safe. If you obtained this tree
  some other way — a zip, a file copy off a Windows share — verify before
  building: `file deploy/entrypoint.sh` should say `ASCII text`, *not*
  `with CRLF line terminators`.
- **Memory is set in `.wslconfig`, not the Docker Desktop slider.** On the
  WSL2 backend, Docker Desktop's Settings → Resources → Memory control is
  inactive; the limit comes from `%UserProfile%\.wslconfig`. To meet the
  4 GB minimum from Requirements:
  ```ini
  [wsl2]
  memory=6GB
  processors=4
  ```
  Then `wsl --shutdown` from PowerShell and restart Docker Desktop.

Two further notes, both unverified:

- The WSL2 default user is normally UID 1000, which happens to match the
  container's `scaife` user — so the "Host UID mismatch" gotcha above
  likely does *not* apply.
- The `cap_add: NET_ADMIN` firewall layer needs the WSL2 kernel to honour
  the container's `iptables` calls. If `entrypoint-locked.sh` fails there,
  fall back exactly as described in the rootless-Docker bullet above.

Browsing works normally: `SCAIFE_BIND` defaults to `127.0.0.1`, and WSL2
forwards localhost, so <http://localhost:8000/library/> resolves from a
Windows browser.

The bootstrap script derives its own root from `$(dirname "$0")` and
exports `SCAIFE_REPO_ROOT` for the compose file, so nothing here is
pinned to a specific home directory. The whole tree can be moved or
renamed freely.

### Expected first-boot log noise

Two things scroll past that look like failures and are not:

- **`toc error: urn:cts:latinLit:phi0474.phi051.perseus-eng1 has an invalid
  refsDecl`** — a handful of Perseus texts (mostly Cicero, `phi0474`) ship
  malformed `refsDecl` metadata upstream. The affected editions are skipped;
  every other text loads. Not caused by anything local.
- **Elasticsearch JSON at `log.level: INFO`** — ES 8 logs its whole plugin
  and index-template startup as structured JSON. Only `log.level` of `WARN`
  or `ERROR` is worth reading.

A genuinely failed boot looks different: a Python `Traceback`, a
`CommandError`, or the `scaife-viewer` container exiting non-zero. The
success line to wait for is:

```
scaife-viewer | [INFO] Listening at: http://0.0.0.0:8000
```

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
| `sv-elasticsearch` | ES 8.19.11 (text search index), `analysis-icu` plugin added | `Dockerfile-elasticsearch` in the app |

### Features and what backs each

| Feature | Endpoint | Data path | Offline? |
|---|---|---|---|
| Read Greek/Latin texts | `/reader/…`, `/library/passage/…` | CTS resolver → mounted `canonical-greekLit`/`-latinLit`/`-pdlrefwk` | ✓ |
| Library browse | `/library/`, `/library/json/` | CTS resolver | ✓ |
| Text search | `/search/` | Elasticsearch — **⚠ only 1,000 passages indexed by default; see below** | ✓ (partial) |
| **Morphology** (form → lemma) | `/morpheus/?word=…&lang=…` | `morpheus` container | ✓ |
| **Dictionaries** (LSJ, Middle Liddell, Lewis & Short) | `/library/dictionaries/…` | Postgres via `sv_pdl/localdict` app | ✓ |
| **Commentaries** (Nagy et al. on Homer/Pausanias/Pindar) | `/library/commentaries/…/json/` | Postgres via `sv_pdl/localcomm` app | ✓ |

### Search index coverage

First boot runs the indexer with `--limit=1000`, so **only 1,000 passages
are searchable** — a fast-boot sample, not the corpus. Those 1,000 are
simply whichever passages the indexer walked first; they are not a curated
or representative selection, so coverage is effectively arbitrary from a
reader's point of view.

**What this looks like in practice:** you search a word you are certain
appears in the text open in front of you, and get nothing back. That is
the index missing the passage, not the search being broken.

Everything else is complete regardless — reading, library browse,
dictionaries, commentaries, morphology. Only `/search/` is affected.
Verify what you currently have indexed:

```
curl -s localhost:9200/scaife-viewer/_count
# {"count":1000,...}  <- the default sample
```

#### How to fix it

**Re-indexing is safe to repeat.** Documents are keyed by passage URN, so
re-running the indexer overwrites rather than duplicates — verified by
re-running at `--limit=1200` against an existing 1,000-doc index and
getting exactly 1,200 documents, not 2,200. You never need to delete the
index first, and a run that dies partway can simply be run again.

There are two ways to do it. **Option A — run it directly**, against the
already-running stack. Nothing to restart, and you see progress as it goes:

```
# raise the cap (any number), or drop --limit entirely for the full corpus
docker exec -u scaife scaife-viewer \
    python manage.py indexer --max-workers=1 --limit=25000
```

It prints `Committing N doc(s) to scaife-viewer` as it works and
`Finished in Ns` at the end. Check progress at any time from another shell:

```
curl -s localhost:9200/scaife-viewer/_count
```

**Option B — make it the permanent default**, so future boots index fully.
`SV_INDEXER_LIMIT=0` means "no limit"; the sentinel must be cleared or the
entrypoint skips indexing entirely:

```
echo 'SV_INDEXER_LIMIT=0' >> scaife/scaife-viewer-2026-03-27-001/deploy/.env
rm sv-data/sentinels/.es_indexed
bash ./bootstrap.sh
```

`SV_INDEXER_MAX_WORKERS` (default 1) parallelizes it if you have the RAM.

**How long?** Budget hours for the full corpus. As a rough rate to
extrapolate from: 1,200 passages indexed in ~19 s at `--max-workers=1` on
an arm64 laptop. Treat that as indicative only — it is measured over the
cheapest passages the indexer walks first, and the ES volume grows roughly
in proportion to what you index.

**What you cannot do:** index a single work or author. The indexer accepts
a `--urn-prefix` flag, but it is unimplemented upstream and raises
`NotImplementedError: URN prefix is not currently supported`. The only
lever is *how many* passages, not *which* — so the practical middle ground
is a raised `--limit` (say 25,000) rather than a targeted subset.

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
`docker compose up --build`. It preflights Docker, the Compose v2 plugin,
and the presence of `deps/` + `data-sources/` (auto-fetching if absent).

### 7. Entrypoint runs the local ingests

`deploy/entrypoint.sh` gained two sentinel-gated steps so a fresh install
comes up with dictionaries and commentaries already populated:

```sh
if [ ! -f ${SENTINEL_DIR}/.dictionaries_ingested ] && [ -d /host-lexica ]; then
    python manage.py ingest_dictionaries && touch ${SENTINEL_DIR}/.dictionaries_ingested
fi
```

...and the same for `.commentaries_ingested` / `/host-commentaries`. The
`-d` guard matters: those bind mounts exist only under the local override,
so the steps skip cleanly when the same entrypoint runs under the upstream
or CI compose files. Both commands are idempotent (`get_or_create` on the
parent row, then entries replaced), so re-running never duplicates.

The same section makes the indexer's passage cap configurable via
`SV_INDEXER_LIMIT` / `SV_INDEXER_MAX_WORKERS` instead of hard-coding
`--limit=1000`; the default is unchanged.

## Re-ingesting data

Corpora are mounted read-only, so nothing to re-run for text updates.
Dictionaries and commentaries are Postgres-backed and are ingested
automatically on first boot (see "Entrypoint runs the local ingests"). To
force a rebuild of those tables:

```
docker exec -u scaife scaife-viewer python manage.py ingest_dictionaries --reset
docker exec -u scaife scaife-viewer python manage.py ingest_commentaries --reset
```

Use `-u scaife` so the command runs as the same user the app itself runs
as. Without it `docker exec` lands as root, because the container starts as
UID 0 to install firewall rules before `su-exec`ing down to `scaife` — any
file it then creates under the writable `/sv-data` mount is root-owned,
which the unprivileged app cannot later rewrite.

Expected output on success — if you see fewer dictionaries or zero
commentary entries, the `deps/` clones are incomplete:

```
  lsj                                         116497 entries
  lewis-and-short-latin-dictionary            103232 entries
  middle-liddell                               36491 entries
```

## Remaining external network use

None at *runtime*. During initial `docker compose up --build`:
- Base OS images are pulled once from Docker Hub (`ubuntu:22.04`, `postgres:9.6-alpine`, `node:12.13-alpine`, `python:3.8-alpine`) and the
  Elasticsearch image from `docker.elastic.co`.
- `pip install`, `npm ci`, and `elasticsearch-plugin install analysis-icu`
  fetch language deps and the ES plugin.

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
ES runs with `xpack.security.enabled=false`, so it has no auth at
all). Changed to bind on `127.0.0.1` for all four services — Django 8000,
Postgres 5432, ES 9200, Morpheus 1500. (The compose default for Postgres is
5433, but the `.env` that `bootstrap.sh` writes sets `SV_POSTGRES_PORT=5432`
and that wins; check with `docker ps` rather than assuming.)

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
