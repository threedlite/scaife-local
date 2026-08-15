# Scaife Viewer — Local, Fully Offline Snapshot

Local Scaife Viewer instance for Ancient Greek + Latin reading, modified to
run **fully offline** with no runtime dependency on `services.perseids.org`
or `atlas.perseus.tufts.edu`.

- `scaife/scaife-viewer-2026-08-10-001/` — the main Django+Vue application (patched)
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

> ### Everything is populated by default, including search
>
> A default install indexes the **entire corpus** — measured at 779,099
> passages in 5 min 42 s — so `/search/` works across every text from the
> first boot. Reading, library browse, 256,220 dictionary entries, 7,656
> commentary entries, and morphology are likewise complete.
>
> That full index is the bulk of the extra time on first boot and produces
> a ~1 GB OpenSearch index. **For the quickest possible start instead**,
> set a sample size before running `bootstrap.sh` — search will then cover
> only that many passages:
>
> ```
> echo 'SV_INDEXER_LIMIT=1000' >> scaife/scaife-viewer-2026-08-10-001/deploy/.env
> ```
>
> See [Search index coverage](#search-index-coverage) for the trade-off,
> how to check what you have, and how to change it later.

## Requirements

- **macOS** (Intel or Apple Silicon) or **Linux** (x86_64 or arm64) —
  the two platforms tested end to end. **Windows** should work via WSL2 but
  is **untested**; see "Windows notes" below before trying. Any other
  Docker-capable OS is fair game on the same terms.
- **Docker** (Engine 20.10+ with the Compose v2 plugin — comes bundled
  with Docker Desktop; on Linux it's `docker-compose-plugin` or newer).
- **Disk**: budget **~10 GB** free. Measured on a completed arm64 install:
  ~4.1 GB of images (the app image layers over the base, so they share most
  of their size), ~1.4 GB of cloned corpora and deps in the working tree,
  and Docker volumes of 1.2 GB (Postgres) plus 1.2 GB (OpenSearch *after
  the default full text index* — only ~1 MB if you opt into a small sample).
  Call it ~8 GB at rest fully populated, plus headroom for intermediate
  build layers.
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

# 2. One command. First run measured at ~21 min on a 6-CPU arm64 machine:
#    ~15 min of cold image builds plus a one-time ~1.4 GB source fetch,
#    then ~6 min indexing the full corpus for search. Budget 45-60 min on
#    slower hardware or a thin network. Subsequent runs start in ~30-40 s.
bash ./bootstrap.sh
```

That's it. When it prints `Listening at: http://0.0.0.0:8000`, open
<http://localhost:8000/library/> in your browser.

Everything is populated at this point, search included — the full-corpus
index is what accounts for the last few minutes before that line appears.

The bootstrap script:

1. Checks Docker is installed, the daemon is reachable, and the Compose v2
   plugin is present (all three fail fast, before any long work).
2. Runs `scripts/fetch-data.sh` if `deps/` or `data-sources/` are empty —
   clones nine open-license repos (measured ~1.4 GB shallow, one-time:
   ~745 MB of corpora, ~620 MB of deps, of which `lexica` alone is 484 MB).
3. Stages a writable `sv-data/` tree with sentinels so the container
   entrypoint skips its own tarball downloads.
4. Writes `deploy/.env` (mode 0600) if missing.
5. Builds `scaife-viewer-base:latest` from the upstream Dockerfile, using
   `--target webapp`. Four local changes to that file are documented in
   sections 9–12 below: lint made opt-in, `urllib3`/`gunicorn`/`certifi`
   pinned to patched releases (see §10-11 — the urllib3 and certifi
   overrides were removed on 2026-08-15 once the interpreter upgrade made
   them unnecessary), the base image moved to Python 3.12, and
   upstream's `setuptools==81.0` pin adopted.
6. Runs `docker compose up --build` which builds the hardened + morpheus
   images on top and starts everything.

On first boot the container's `deploy/entrypoint.sh` then does the one-time
data work, each step gated by a sentinel file in `sv-data/atlas/sentinels/` so it
never repeats: Django migrations → `prepare_atlas_db` → `ingest_dictionaries`
→ `ingest_commentaries` → OpenSearch indexing (the full corpus by
default). Delete the matching sentinel to force any one of them to run
again.

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
  `scaife/scaife-viewer-2026-08-10-001/deploy/docker-compose.override.local.yml`
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
  I/O (~745 MB across the three CTS repos), and mounts served out of
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

### Running the tests

```
bash scripts/run-tests.sh                      # 123 unit tests; must be green
bash scripts/run-tests.sh --integration        # 160 tests; adds live-service checks
bash scripts/run-tests.sh sv_pdl.tests.test_refs   # one module
bash scripts/run-morpheus-tests.sh             # 28 rspec examples in the morpheus image
```

The stack must be up. Tests live in
`scaife/scaife-viewer-2026-08-10-001/sv_pdl/tests/` and exist to make
**dependency upgrades observable** — they assert the offline patches are
still in force (URLs resolve to the local views, templates fetch nothing
from CDNs), the JSON contracts the Vue frontend depends on, and the
Unicode/ordering invariants behind dictionary lookup and commentary
matching. See "What the test suite covers, and what it does not" in
[`UPGRADE-IMPACT.md`](UPGRADE-IMPACT.md) — a green suite means the local
patches survived, not that the whole app works.

#### Vendored upstream packages

`scaife-viewer-core` and `scaife-viewer-atlas` live in
`scaife/scaife-viewer-2026-08-10-001/packages/` rather than being fetched
from GitHub at build time. They supply the CTS resolver, reader, library,
search indexer and the ATLAS GraphQL layer, and both pin `Django<3`, so
nothing above them could move to a supported Django while those pins were
external metadata. See `packages/README.md` for provenance, the local
changes, and the dependency delta; `DJANGO-UPGRADE.md` §10 for why.

Their own test suites run against a recorded baseline:

```
bash scripts/run-vendored-tests.sh            # both packages
bash scripts/run-vendored-tests.sh --verbose atlas
```

Upstream's suites do **not** pass cleanly at these refs and did not before
vendoring — core is 4 passed / 1 failed, atlas 12 passed / 7 failed. The
script fails if those counts move in either direction, so an edit to
`packages/` that breaks something new shows up immediately. The individual
failures, including one real latent bug in atlas's exemplar handling, are
documented in the script's header.

#### Golden-file regression tests

Three of the suites compare against committed snapshots rather than
hand-written expectations, because the code they cover is large, untested
upstream, and about to be rewritten by the Django/graphene upgrade:

| Suite | Golden file | Covers |
|---|---|---|
| `test_schema_contract.py` | `golden/atlas_schema.json` | the whole GraphQL schema — 80 types, 391 fields |
| `test_passage_contract.py` | `golden/passages.json` | CTS rendering of 7 passages: text, HTML, word tokens, navigation |
| `test_morpheus.py` | `golden/morpheus.json` | morphological analysis of 29 Greek and Latin words, at three layers: the service's RDF/JSON, nokogiri's XML, and the `/morpheus/` view |

`golden/atlas_schema.graphql` is the printed SDL, kept for human review; no
test asserts on it. Regenerate after an *intended* change:

```
bash scripts/capture-golden.sh            # all three
bash scripts/capture-golden.sh schema     # or just one
bash scripts/capture-golden.sh passages
bash scripts/capture-golden.sh morpheus
```

Read the resulting diff before committing it. An unreviewed golden refresh
is indistinguishable from the regression the file exists to catch — a
removed GraphQL field or a shifted token offset silently blanks part of the
reader rather than raising. The passage suite is tagged `integration`
because it reads the mounted corpora; the morpheus suite because it calls
the running analyser.

The morpheus golden exists specifically because that service is the only
non-Python part of the stack and neither of its source repositories is
tracked here — so a Ruby, nokogiri or libxml2 change has nothing else
standing in its way. It is what verified that moving Ruby 3.0.2 → 3.4.10
and nokogiri 1.14.3 → 1.19.4 left every analysis byte-identical.

`--integration` is **fully green** as of 2026-08-15. It previously carried
one deliberate expected failure — a 7.x `elasticsearch` client driving an
8.x server, which the client's `<8` cap could not escape. That was fixed
at the root by moving to OpenSearch (which forked from Elasticsearch 7.10,
the client's own API generation), not by relaxing the test. A failure here
now means something is actually wrong.

### Lint is not part of the build

Upstream's Dockerfile ran `npm run lint`, `flake8 sv_pdl` and `isort -c` as
build steps, so an unused import failed the entire image build. Those three
steps are now opt-in:

```
bash scripts/lint.sh          # flake8 + isort (seconds, no rebuild)
bash scripts/lint.sh --js     # also eslint (pulls the node build stage)
bash scripts/lint.sh --fix    # apply isort ordering in place
```

To restore the old behaviour and gate the image on lint again:

```
docker build --build-arg RUN_LINT=1 -t scaife-viewer-base:latest -f Dockerfile .
```

`npm run unit` (the frontend unit tests) still runs in the build; only the
style checks were made optional.

### Dependency and upgrade documentation

- [`SBOM-2026-08-15.md`](SBOM-2026-08-15.md) — current dated inventory:
  every installed package, EOL status and confirmed CVEs, plus which
  dependencies the platform upgrade has just unblocked. Regenerate the
  raw version data with `bash scripts/sbom-refresh.sh`.
  [`SBOM-2026-08-13.md`](SBOM-2026-08-13.md) is the superseded
  pre-upgrade snapshot, kept as the record the upgrade was planned against.
- [`UPGRADE-IMPACT.md`](UPGRADE-IMPACT.md) — what it would take to move to
  current Django/Python/Postgres, and the Elasticsearch → OpenSearch swap
  (now done — see its "Elasticsearch 8 → OpenSearch" section).
- [`DJANGO-UPGRADE.md`](DJANGO-UPGRADE.md) — a deeper, measured analysis of
  the Django 2.2 → 5.2 LTS path specifically: what had to be forked, what
  actually breaks, and the numbered work items (§10) with their status.
- [`DJANGO-3.2-PLAN.md`](DJANGO-3.2-PLAN.md) — the execution plan for the
  next step, Django 2.2 → 3.2 LTS: measured version matrix, ordered work
  items, the golden diff each one is allowed to produce, and the decisions
  needed before starting.

Short version: five of six platform components are past end of life, and
`scaife-viewer-core` hard-pinned `Django<3.0`, so there was no incremental
upgrade path without forking upstream. That fork happened on 2026-08-14 —
both packages are now vendored under `packages/` and the pins are editable.
Read those documents before attempting any dependency bump.

### Expected first-boot log noise

Two things scroll past that look like failures and are not:

- **`toc error: urn:cts:latinLit:phi0474.phi051.perseus-eng1 has an invalid
  refsDecl`** — a handful of Perseus texts (mostly Cicero, `phi0474`) ship
  malformed `refsDecl` metadata upstream. The affected editions are skipped;
  every other text loads. Not caused by anything local.
- **OpenSearch JVM warnings at boot** — `Using incubator modules:
  jdk.incubator.vector`, `A terminally deprecated method in java.lang.System
  has been called`, `System::setSecurityManager has been called`, and
  `Disabling OpenSearch Security Plugin`. All expected: the last is our own
  `DISABLE_SECURITY_PLUGIN=true` (safe only behind the loopback binding), and
  the rest are the JVM complaining about OpenSearch's own bootstrap code.

A genuinely failed boot looks different: a Python `Traceback`, a
`CommandError`, or the `scaife-viewer` container exiting non-zero. The
success line to wait for is:

```
scaife-viewer | [INFO] Listening at: http://0.0.0.0:8000
```

### Stopping / restarting

To stop the stack cleanly:

```
cd scaife/scaife-viewer-2026-08-10-001
SCAIFE_REPO_ROOT=<abs path to repo root> \
SCAIFE_DATA_SOURCES=<abs path to data-sources> \
docker compose -f deploy/docker-compose.yml -f deploy/docker-compose.override.local.yml down
```

Or just Ctrl-C the foreground `bootstrap.sh` — it uses `exec` for compose
so the signal propagates. Data is persistent in Docker volumes
(`sv-postgres-17-data`, `sv-opensearch-data`) — the next `bootstrap.sh`
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
| `scaife-viewer` | Django + Gunicorn + built Vue bundle | `scaife/scaife-viewer-2026-08-10-001/Dockerfile` |
| `morpheus` | Perseids Morpheus (C) + Ruby Sinatra JSON API | `deps/morpheus-combined/Dockerfile` |
| `sv-postgres` | Postgres 17 (Perseus data + ATLAS DB + local dictionaries + local commentaries) | official image |
| `sv-opensearch` | OpenSearch 2.19.2 (text search index), `analysis-icu` plugin added | `Dockerfile-opensearch` in the app |

### Features and what backs each

| Feature | Endpoint | Data path | Offline? |
|---|---|---|---|
| Read Greek/Latin texts | `/reader/…`, `/library/passage/…` | CTS resolver → mounted `canonical-greekLit`/`-latinLit`/`-pdlrefwk` | ✓ |
| Library browse | `/library/`, `/library/json/` | CTS resolver | ✓ |
| Text search | `/search/` | OpenSearch — full corpus indexed on first boot (779,099 passages) | ✓ |
| **Morphology** (form → lemma) | `/morpheus/?word=…&lang=…` | `morpheus` container | ✓ |
| **Dictionaries** (LSJ, Middle Liddell, Lewis & Short) | `/library/dictionaries/…` | Postgres via `sv_pdl/localdict` app | ✓ |
| **Commentaries** (Nagy et al. on Homer/Pausanias/Pindar) | `/library/commentaries/…/json/` | Postgres via `sv_pdl/localcomm` app | ✓ |

### Search index coverage

**The default is a full index.** First boot runs the indexer with no
`--limit`, so every passage is searchable. This is a deliberate departure
from upstream, whose entrypoint hard-coded `--limit=1000`.

Check what you actually have at any time:

```
curl -s localhost:9200/scaife-viewer/_count
# {"count":779099,...}  <- full corpus
# {"count":1000,...}    <- a sample; search will miss most texts
```

#### Opting into a sample instead

If you want the fastest possible first boot and don't need working search,
set a passage cap in `deploy/.env` **before** the first `bootstrap.sh`:

```
echo 'SV_INDEXER_LIMIT=1000' >> scaife/scaife-viewer-2026-08-10-001/deploy/.env
```

The trade-off: the capped passages are whichever ones the indexer walks
first, not a curated or representative selection, so coverage is arbitrary
with respect to what a reader is likely to look up. The observable symptom
is a search for a word that appears in the open text returning nothing —
the passage was not indexed, rather than search failing.
Reading, browse, dictionaries, commentaries, and morphology are unaffected
either way.

`SV_INDEXER_MAX_WORKERS` (default 4) is the other lever — lower it on a
small machine, at roughly 10x the runtime for a single worker.

#### Changing it later

Already installed, and want to switch? The `.search_indexed` sentinel means the
entrypoint will not re-index on its own — **changing `.env` alone does
nothing to an existing install.** Either re-run the indexer directly
(below), or delete `sv-data/atlas/sentinels/.search_indexed` and re-run
`bootstrap.sh`.

**Re-indexing is safe to repeat.** Documents are keyed by passage URN, so
re-running the indexer overwrites rather than duplicates — verified by
re-running at `--limit=1200` against an existing 1,000-doc index and
getting exactly 1,200 documents, not 2,200. You never need to delete the
index first, and a run that terminates partway can be repeated.

Run it directly against the already-running stack — nothing to restart,
and you see progress as it goes:

```
# omit --limit for the full corpus; add --limit=N to build a sample
docker exec -u scaife scaife-viewer \
    python manage.py indexer --max-workers=4
```

For a long run, detach it so it survives your shell, and log somewhere the
host can read (`/sv-data` is the writable bind mount):

```
docker exec -d -u scaife scaife-viewer \
    sh -c 'python -u manage.py indexer --max-workers=4 > /sv-data/fullindex.log 2>&1'
```

It prints `Committing N doc(s) to scaife-viewer` as it works, then a
per-language `Word Count Summary` and `Finished in Ns`. Watch progress from
another shell at any time:

```
curl -s localhost:9200/scaife-viewer/_count
```

Note that a sampled index is not *reduced* by re-running with a smaller
`--limit`: documents already in the index stay there. To shrink one, delete
the index first with `--delete-index` (untested here) or remove the
`deploy_sv-opensearch-data` volume and re-index.

For reference, `SV_INDEXER_LIMIT=0` is what "no limit" means to the
entrypoint, and it is the default — you only need to set it explicitly to
undo a sample you configured earlier:

```
echo 'SV_INDEXER_LIMIT=0' >> scaife/scaife-viewer-2026-08-10-001/deploy/.env
rm sv-data/atlas/sentinels/.search_indexed
bash ./bootstrap.sh
```

**How long, and how big?** Measured on a 6-CPU / 12 GiB aarch64 Colima VM,
indexing the entire corpus at `--max-workers=4`:

| | |
|---|---|
| Passages indexed | **779,099** |
| Wall time | **5 min 42 s** (`Finished in 339.92s`) |
| Resulting index | ~1 GB (`deploy_sv-opensearch-data` volume ~1.2 GB) |
| Words indexed | grc 10,837,549 · eng 21,070,271 · lat 6,748,008, plus deu/fre/ita/ara |

Worker count dominates: the same indexer at `--max-workers=1` ran at
roughly a tenth of that throughput. A single-worker rate does not
extrapolate to a parallel run.

A handful of `toc error: … has an invalid refsDecl` lines during the run
are the same benign upstream Perseus defects described under "Expected
first-boot log noise" — four of them, all Cicero and one other Latin text.

**What you cannot do:** index a single work or author. The indexer accepts
a `--urn-prefix` flag, but it is unimplemented upstream and raises
`NotImplementedError: URN prefix is not currently supported`. The only
parameter is *how many* passages, not *which*. Since a full run completes
in under six minutes, indexing everything is the simpler option.

### Data volumes

| Feature | Rows |
|---|---|
| CTS text groups | 154 authors (Greek + Latin + reference works) |
| LSJ entries | 116,497 |
| Lewis & Short entries | 103,232 |
| Middle Liddell entries | 36,491 |
| Commentary entries | 7,656 across 14 named commentaries |
| Searchable passages | **779,099** (full corpus, the default) |

## Changes made to the upstream app for offline operation

### 1. Frontend CDN scripts pulled locally

Upstream templates loaded jQuery from `unpkg.com`, an `IntersectionObserver`
polyfill from `polyfill.io` (a domain hijacked in 2024), and Font Awesome
icons from `use.fontawesome.com`. All replaced:

- `sv_pdl/templates/site_base.html` — jQuery URL swapped for `{% static 'vendor/jquery.min.js' %}`; the `use.fontawesome.com` script tag removed (icons are already bundled via `@fortawesome/*` npm deps).
- `static/vendor/jquery.min.js` — the file itself.
- `sv_pdl/settings.py` — `STATICFILES_DIRS` extended with `("vendor", <path>)` so `collectstatic` picks up the vendor files.

**The polyfill part of this is now retired.** It previously needed local
copies in `app.html` and a `reader/reader.html` override, but upstream
removed the `polyfill.io` script tag entirely, so both local patches and
`static/vendor/polyfill.min.js` were dropped at the 2026-08-10 resync rather
than left as an unreferenced file and a misleading licence credit. The host
is still in the test suite's forbidden list, so reintroducing it would fail
`test_no_cdn_resources_loaded_by_templates`.

### 2. Morpheus service brought in-cluster

Upstream `scaife_viewer.core.views.morpheus` proxied to
`services.perseids.org/bsp/morphologyservice/`. Replaced with a container:

- `deps/morpheus-perseids/` — cloned upstream (Perseids C fork of Morpheus, MPL 2.0).
- `deps/morpheus-perseids-api/` — cloned upstream (Ruby Sinatra JSON wrapper, MIT).
- `deps/morpheus-combined/Dockerfile` — multi-stage build. The C engine is compiled on Ubuntu 22.04 (arm64 or x86_64 — whatever the host is); gems are built in a separate stage; the runtime is `ruby:3.4.10-slim-bookworm` carrying only the bundle, the app and the Morpheus binary. The binary links against libc alone, so it runs unchanged on bookworm's newer glibc.
  Neither `morpheus-perseids` nor `morpheus-perseids-api` is tracked in this repo, so this Dockerfile is the only place their build can be pinned — `nokogiri` is held at 1.19.4 there (1.14.3 carries a critical advisory).
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

`scaife/scaife-viewer-2026-08-10-001/deploy/docker-compose.override.local.yml`
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

### 8. Search indexes the full corpus by default

The entrypoint in the 2026-03-27 snapshot ran `python manage.py indexer
--max-workers=1 --limit=1000`, which left `/search/` covering 1,000 passages
of a 779,099-passage corpus. That suits a fast CI or preview build; for a
local reading instance it is worth indexing everything.

(Upstream has since removed the `--limit` themselves, so current `dev` also
indexes the full corpus. What remains local is the configurability.)

That cap is now configurable and inverted: `SV_INDEXER_LIMIT` defaults to
`0` (no `--limit`, index everything) and `SV_INDEXER_MAX_WORKERS` defaults
to `4` rather than `1`, since worker count dominates runtime. Setting
`SV_INDEXER_LIMIT=<N>` restores a capped sample for a faster first boot.
`bootstrap.sh` writes both as commented-out lines in `deploy/.env` so the
choice is discoverable without reading this file.

### 9. Lint made opt-in in the upstream Dockerfile

The first of four local changes to the upstream `Dockerfile` (see also
sections 10-12). The file is otherwise unmodified, so `Dockerfile-local`
can layer on top of it.

Upstream gated the image build on three style checks — `npm run lint` in the
static-build stage, then `flake8 sv_pdl` and `isort -c **/*.py` in the final
stage. An unused import therefore failed the whole build, discarding a long
image build over formatting. Each is now wrapped in a `RUN_LINT` guard that
defaults to off:

```dockerfile
ARG RUN_LINT=0
RUN if [ "$RUN_LINT" = "1" ]; then flake8 sv_pdl && isort -c **/*.py; \
    else echo "skipping flake8 + isort (build with --build-arg RUN_LINT=1 to enable)"; fi
```

`scripts/lint.sh` runs the same checks against the built image without a
rebuild. `npm run unit` was left mandatory: it tests behaviour rather than
formatting.

Note that upstream's current `dev` no longer runs `flake8`/`isort` in the
build at all — they removed both. Only the `npm run lint` guard is still a
local change.

### 10. `urllib3` pinned forward to a patched release

The second of four local changes to the upstream `Dockerfile`. Upstream
uninstalls whatever `pip` resolved and pins `urllib3==1.26.15` "to avoid
conflicts". That release is affected by three disclosure issues:

| CVE | Leak | Fixed in |
|---|---|---|
| CVE-2023-43804 | `Cookie` header on cross-origin redirect | 1.26.17 |
| CVE-2023-45803 | request body retained on a 303 redirect | 1.26.18 |
| CVE-2024-37891 | `Proxy-Authorization` on cross-origin redirect | 1.26.19 |

We pin **1.26.20** — the final release of the 1.26.x line, which carries all
three fixes. Staying on 1.26.x is deliberate: upstream pins there to avoid
resolver conflicts, and urllib3 2.7 requires Python 3.10+ while this image
is Python 3.9. Worth revisiting only if the interpreter is upgraded.

### 11. `gunicorn` and `certifi` upgraded off vulnerable pins

The third of four local changes to the upstream `Dockerfile`. It closes the
other two confirmed CVEs in the dependency set, using the same post-install
pattern:

| Package | Upstream pin | Ours | Closed |
|---|---|---|---|
| `gunicorn` | 19.9.0 | **23.0.0** | CVE-2024-1135 (HTTP request smuggling) |
| `certifi` | 2018.11.29 | **2026.7.22** | CVE-2023-37920, CVE-2022-23491 (removed-for-cause CA roots) |

`gunicorn` 23.0.0 is the newest release supporting Python 3.9 — 26.0.0
requires 3.10+. `certifi` is declared as `==2018.11.29` by
`scaife-viewer-core`, so pip warns about the conflict and proceeds, exactly
as it already does for `requests`.

Together with §10 this leaves **no known unfixed CVE** in the Python
dependency set. Re-check after any upstream resync — these are overrides on
top of upstream pins.

### 12. Base image moved to Python 3.12

The fourth local change to the upstream `Dockerfile`.

`python:3.8-alpine` is frozen at Alpine **3.20.3**: the tag stopped being
rebuilt when Python 3.8 reached end of life. The image moved to 3.9, and
then on 2026-08-14 to **`python:3.12-alpine`** as part of the Django 5.2
upgrade — Django 5.2 requires Python 3.10+. 3.12 rather than 3.13 because
it is supported by both Django 4.2 and 5.2, which kept the interpreter move
and the framework move independently revertible.

Two things this required:

- **Dropping the `typing` PyPI backport.** `MyCapytain` declares it as a
  dependency; it shadows the standard library module and breaks on modern
  interpreters. It is uninstalled after `pip install`, in the same
  post-install pattern already used for `urllib3`.
- **`six` 1.12.0 → 1.17.0.** Its `six.moves` lazy-import machinery relies on
  import internals that changed in 3.12, so `from six.moves import _thread`
  (reached via `python-dateutil`) failed outright.

The `setuptools==81.0` pin remains: newer setuptools drops `pkg_resources`,
which the vendored `scaife-viewer-core` and `scaife-viewer-atlas` still call
at import time. Replacing that with `importlib.metadata` would let the pin
go.

### 13. Search API pagination and validation fixed

Three defects in `/search/json/`, inherited from upstream and identical on
the pre-upgrade stack. Each was first *pinned* by a test in
`sv_pdl/tests/test_search_options.py` — recording the wrong behaviour so
the upgrade could be shown not to have caused it — and then fixed.

| | Was | Now |
|---|---|---|
| `type` | checked only for being non-empty, so an unknown value fell through to the reader branch and returned 200 — while the message for a *missing* type promised 'library' or 'reader' | validated against `library`/`reader`, 400 otherwise |
| page stride | `offset = (page_num - 1) * 10` with `size` caller-controlled, so `size=5` made page 2 start at result 11 and results 6-10 unreachable from any page | stride follows `size`; consecutive pages tile the result set exactly |
| empty results | `num_pages: 0` with `start_index: 1`, `end_index: 10` — "showing 1-10 of 0, page 1 of 0" | one empty page with both indices 0, matching Django's `Paginator` |

**The frontend is unaffected**, which is both why these survived and why
fixing them was safe. `static/src/js/library/search/Search.vue` never sends
`size`, so it gets the default 10 and the arithmetic is unchanged; the
reader widget sends its own explicit `offset` and does not use the
paginated branch; and the pagination control is not rendered at all when a
search returns nothing (`v-if="results.length || textGroups.length"`).
Verified against the pre-upgrade stack: for the exact parameter set the Vue
code sends, page metadata and totals are identical.

Fixing the stride meant `size` had to be validated — `size=0` would divide
by zero and `page_num=0` would ask the backend for a negative offset. Both
are now required to be positive integers, which also turns `?size=abc` from
a 500 into a 400.

The pagination half lives in the vendored `scaife-viewer-core`
(`get_pagination_info`, which gained a `per_page` argument defaulting to
10); see `packages/README.md`.

### 14. Site header no longer claims Tufts hosting

Upstream's `sv_pdl/templates/site_base.html` renders "Hosted by Tufts
University" beneath the Scaife Viewer wordmark. Nothing in this deployment
is served by Tufts, so the line now reads **"Local version"**.

Cosmetic, but it is a factual claim about who is running the service, and
it is exactly the sort of string an upstream template refresh restores
without anyone noticing. `sv_pdl/tests/test_offline_wiring.py` pins it —
against the *rendered* output rather than the file, so that the comment
naming the replaced string does not itself satisfy the check.

The home page shows no brand line at all; `homepage.html` overrides the
`site_brand` block with an empty one. That is upstream behaviour and is
unchanged.

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
- Base OS images are pulled once from Docker Hub (`ubuntu:22.04`, `postgres:17-alpine`, `node:12.13-alpine`, `python:3.8-alpine`) and the
  OpenSearch image from Docker Hub (`opensearchproject/opensearch`).
- `pip install`, `npm ci`, and `opensearch-plugin install analysis-icu`
  fetch language deps and the ES plugin.

Once the images are built, a fully offline host can run the stack with
`docker compose up` (no `--build`) and no network access.

## Security hardening applied

The upstream Scaife Viewer deployment is intended to run behind a real
load balancer with hosts-side firewall rules. Since this local snapshot is
run on a workstation, some defaults were tightened.

### 1. Host ports bound to loopback

Upstream `deploy/docker-compose.yml` exposed ports on `0.0.0.0`, meaning any
peer on the same LAN could talk to Django, Postgres, and OpenSearch
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
`FROM`s the upstream image (built and tagged as
`scaife-viewer-base:latest` by `bootstrap.sh`) and adds a `scaife` user
(UID 1000) plus a locked-down launcher. The upstream Dockerfile carries four
local changes of its own, documented in sections 9-12; none affects the
non-root layering described here.

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

Net effect: the app can reach loopback, `sv-postgres`, `sv-opensearch`,
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
- ~~**Django 2.2.28 is EOL**~~ — resolved 2026-08-14. The stack now runs
  **Django 5.2.17 on Python 3.12**, with **PostgreSQL 17** and
  **OpenSearch 2.19**. See `DJANGO-UPGRADE.md` and `DJANGO-3.2-PLAN.md` for
  how it was sequenced and what was verified at each step.

## Licenses

**Almost all of this project is Perseus / upstream code and data, not
mine.** The Scaife Viewer Django+Vue application, `scaife-viewer-core`,
`scaife-viewer-atlas`, `MyCapytain`, `Morpheus`, `PerseusDL/lexica` (LSJ +
Lewis & Short TEI), the Open Commentaries markdown, and the three Perseus
text corpora are all authored by other people and remain under their
original upstream licenses (MIT, MPL 2.0, or CC BY-SA 4.0 as noted below).

My own contributions are split across **two** grants by kind, both in
`LICENSE`:

- **MIT — software.** `bootstrap.sh`, `scripts/*.sh`, `Dockerfile-local`,
  `entrypoint-locked.sh`, the two new Django apps under `sv_pdl/localdict/`
  and `sv_pdl/localcomm/`, the test suite under `sv_pdl/tests/`, the OpenAPI
  schema, the `licenses.html` / `swagger.html` templates, the compose
  override, and small edits to `sv_pdl/settings.py`, `sv_pdl/urls.py`,
  `sv_pdl/views.py`, `sv_pdl/context_processors.py`, `deploy/entrypoint.sh`,
  the `Dockerfile`, and three widget `.vue` files.
- **[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) —
  documentation.** This README, `CLAUDE.md`, `SBOM-*.md`,
  `UPGRADE-IMPACT.md`, and the prose on the `/licenses/` page. Reuse freely
  with credit.

The split is deliberate: MIT is written for code and grants rights that
make little sense for prose, while Creative Commons explicitly advises
against using CC licenses for software.

`LICENSE` enumerates the exact file list for each grant. The rest of the
tree is not mine to relicense.

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
| `scaife/scaife-viewer-2026-08-10-001/` (bulk of the tree) | MIT | 2017–2020 Perseus Digital Library |

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
