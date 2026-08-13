#!/usr/bin/env bash
# Bootstrap a Scaife Viewer instance via Docker Compose, using local
# Perseus corpora (Greek + Latin + reference works / dictionaries).
#
# What this does:
#   1. Verifies Docker is installed and running.
#   2. Stages a host-side "sv-data" tree with:
#        - .scaife-viewer.json stubs so the CTS resolver / /repos endpoint work
#        - a pre-touched sentinel that tells the container's entrypoint to
#          SKIP `load_text_repos` (which would otherwise try to download
#          tarballs from URL "local" and fail).
#   3. Writes deploy/.env if missing.
#   4. Runs `docker compose up --build` with the local override, which
#      builds the image (Node 12 + Python 3.8 inside the container),
#      brings up Postgres 9.6 and Elasticsearch 7.10, runs migrations,
#      prepares the ATLAS db, and indexes the corpora for search.
#
# First run will take a while (image build + npm install + prepare_atlas_db
# + search indexer). Subsequent runs are fast — sentinel files gate the
# expensive one-time work.

set -euo pipefail

# Repo root = directory containing this script. All internal paths derive
# from it so the tree stays portable if you move or rename it.
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCAIFE_ROOT="$REPO_ROOT/scaife/scaife-viewer-2026-03-27-001"
SV_DATA="$REPO_ROOT/sv-data"

# Perseus CTS data. Bundled inside this repo at ./data-sources/. Override with:
#   SCAIFE_DATA_SOURCES=/path/to/data-sources bash bootstrap.sh
DATA_SOURCES="${SCAIFE_DATA_SOURCES:-$REPO_ROOT/data-sources}"

# Export so docker-compose.override.local.yml sees them via ${VAR}
# interpolation for the bind-mount source paths.
export SCAIFE_REPO_ROOT="$REPO_ROOT"
export SCAIFE_DATA_SOURCES="$DATA_SOURCES"

# --- preflight ---
if ! command -v docker >/dev/null 2>&1; then
  cat <<EOF >&2
ERROR: Docker is not installed.

macOS:
  brew install --cask docker            # or https://www.docker.com/products/docker-desktop/
  # Launch Docker Desktop once so the daemon starts.

Linux (Debian/Ubuntu):
  curl -fsSL https://get.docker.com | sh
  sudo usermod -aG docker "\$USER"      # log out + back in so the group takes effect
  sudo systemctl enable --now docker

Linux (Fedora/RHEL):
  sudo dnf install -y docker docker-compose-plugin
  sudo systemctl enable --now docker
EOF
  exit 1
fi

if ! docker info >/dev/null 2>&1; then
  cat <<EOF >&2
ERROR: docker daemon not reachable.

macOS: launch Docker Desktop.
Linux: sudo systemctl start docker  (or check that you're in the 'docker' group;
       run 'id' to verify, and log out + back in if you were just added).
EOF
  exit 1
fi

# --- deps + data fetch (idempotent) ---
# On a fresh checkout, deps/ and data-sources/ are empty because they're
# in .gitignore. Auto-fetch if anything critical is missing.
NEEDS_FETCH=0
for d in \
  "$REPO_ROOT/deps/morpheus-perseids" \
  "$REPO_ROOT/deps/morpheus-perseids-api" \
  "$REPO_ROOT/deps/lexica" \
  "$REPO_ROOT/deps/homer.opencommentaries.org" \
  "$REPO_ROOT/deps/pausanias.opencommentaries.org" \
  "$REPO_ROOT/deps/pindar.opencommentaries.org" \
  "$DATA_SOURCES/canonical-greekLit" \
  "$DATA_SOURCES/canonical-latinLit" \
  "$DATA_SOURCES/canonical-pdlrefwk" \
; do
  [ -d "$d" ] || NEEDS_FETCH=1
done
if [ "$NEEDS_FETCH" -eq 1 ]; then
  echo "[bootstrap] fetching missing deps + data (~3 GB, one-time)"
  bash "$REPO_ROOT/scripts/fetch-data.sh"
fi

for d in canonical-greekLit canonical-latinLit canonical-pdlrefwk; do
  if [ ! -d "$DATA_SOURCES/$d/data" ]; then
    echo "ERROR: expected $DATA_SOURCES/$d/data to exist after fetch" >&2
    exit 1
  fi
done

# --- host-side staging ---
mkdir -p "$SV_DATA/cts" "$SV_DATA/sentinels" "$SV_DATA/atlas"

stub_metadata() {
  local repo_slug="$1"  # e.g. PerseusDL/canonical-greekLit
  local dir="$SV_DATA/cts/${repo_slug//\//-}-local"
  mkdir -p "$dir"
  cat > "$dir/.scaife-viewer.json" <<EOF
{
  "repo": "$repo_slug",
  "ref": "local",
  "sha": "local",
  "tarball_url": "local"
}
EOF
}

stub_metadata PerseusDL/canonical-greekLit
stub_metadata PerseusDL/canonical-latinLit
stub_metadata PerseusDL/canonical-pdlrefwk

# Tell the container's entrypoint the corpora are already in place —
# skips `load_text_repos` and `slim_text_repos`.
touch "$SV_DATA/sentinels/.text_repos_loaded"

# --- .env ---
if [ ! -f "$SCAIFE_ROOT/deploy/.env" ]; then
  cat > "$SCAIFE_ROOT/deploy/.env" <<'EOF'
DEBUG=1
SECURE_SSL_REDIRECT=0
SITE_ID=1
LIBRARY_VIEW_API_VERSION=1
DATABASE_URL=postgres://scaife:scaife@sv-postgres:5432/scaife
SV_POSTGRES_HOST=sv-postgres
SV_POSTGRES_PORT=5432
SV_ELASTICSEARCH_HOST=sv-elasticsearch
SV_ELASTICSEARCH_PORT=9200
ELASTICSEARCH_HOSTS=sv-elasticsearch
ELASTICSEARCH_SNIFF_ON_START=0
ELASTICSEARCH_SNIFF_ON_CONNECTION_FAIL=0
GUNICORN_CMD_ARGS=--log-file=- --timeout=120 -w 2
EOF
  chmod 600 "$SCAIFE_ROOT/deploy/.env"
  echo "wrote $SCAIFE_ROOT/deploy/.env"
fi

# Tighten .env perms even if it existed already (contains DB creds).
chmod 600 "$SCAIFE_ROOT/deploy/.env" 2>/dev/null || true

# --- build the untouched upstream image once, tag as base ---
# Our Dockerfile-local `FROM`s this tag and adds a non-root user.
cd "$SCAIFE_ROOT"
docker build -t scaife-viewer-base:latest -f Dockerfile .

# --- bring it up ---
exec docker compose \
  -f deploy/docker-compose.yml \
  -f deploy/docker-compose.override.local.yml \
  up --build
