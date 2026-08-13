#!/usr/bin/env bash
# Re-collect the raw version inventory behind SBOM-<date>.md.
#
#   bash scripts/sbom-refresh.sh            # print to stdout
#   bash scripts/sbom-refresh.sh -o out.txt # write to a file
#
# This only gathers OBSERVED VERSIONS. It does not determine EOL status or
# look up CVEs — those are researched and written by hand into the dated
# SBOM, with sources. For automated vulnerability data run pip-audit or
# Trivy (see "Getting authoritative results" in the SBOM).
#
# The stack must be running: bash ./bootstrap.sh
set -euo pipefail

CONTAINER="${SCAIFE_CONTAINER:-scaife-viewer}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_ROOT="$REPO_ROOT/scaife/scaife-viewer-2026-08-10-001"

OUT=""
if [ "${1:-}" = "-o" ]; then OUT="${2:?-o needs a path}"; exec > "$OUT"; fi

if ! docker ps --format '{{.Names}}' | grep -qx "$CONTAINER"; then
  echo "ERROR: '$CONTAINER' is not running; start it with bash ./bootstrap.sh" >&2
  exit 1
fi

echo "# Observed version inventory"
echo "# collected: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "# host arch: $(uname -m)"
echo

echo "## runtimes"
docker exec "$CONTAINER" python --version 2>&1 | sed 's/^/  /'
docker exec "$CONTAINER" python -c 'import django; print("Django", django.__version__)' | sed 's/^/  /'
docker exec sv-postgres postgres --version 2>/dev/null | sed 's/^/  /' || echo "  postgres: not running"
docker exec morpheus ruby --version 2>/dev/null | sed 's/^/  /' || echo "  ruby: not running"
curl -s localhost:9200 2>/dev/null \
  | python3 -c 'import sys,json; d=json.load(sys.stdin); print("  Elasticsearch", d["version"]["number"], "lucene", d["version"]["lucene_version"])' \
  2>/dev/null || echo "  elasticsearch: unreachable"
echo

echo "## base images"
docker exec "$CONTAINER" sh -c 'cat /etc/alpine-release 2>/dev/null | sed "s/^/  alpine /"' || true
docker exec morpheus sh -c 'grep PRETTY_NAME /etc/os-release 2>/dev/null | sed "s/^/  /"' || true
echo

echo "## python packages"
docker exec "$CONTAINER" pip freeze 2>/dev/null | sed 's/^/  /'
echo

echo "## npm dependencies (declared)"
python3 - "$APP_ROOT/package.json" <<'PY'
import json, sys
with open(sys.argv[1]) as fh:
    pkg = json.load(fh)
for section in ("dependencies", "devDependencies"):
    print(f"  [{section}]")
    for name, ver in sorted(pkg.get(section, {}).items()):
        print(f"    {name}=={ver}")
PY
echo

echo "## upstream constraints that block upgrades"
for dist in scaife_viewer_core scaife_viewer_atlas; do
  echo "  [$dist]"
  docker exec "$CONTAINER" sh -c \
    "grep -h '^Requires-Dist' /opt/scaife-viewer/lib/python3.8/site-packages/${dist}-*.dist-info/METADATA 2>/dev/null" \
    | grep -Ei 'django|elasticsearch|graphene' | sed 's/^/    /' || echo "    (not found)"
done

if [ -n "$OUT" ]; then echo "wrote $OUT" >&2; fi
