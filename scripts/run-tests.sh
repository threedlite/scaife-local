#!/usr/bin/env bash
# Run the sv_pdl test suite inside the running scaife-viewer container.
#
#   bash scripts/run-tests.sh              # unit suite (default; must be green)
#   bash scripts/run-tests.sh --integration # adds checks needing live services
#   bash scripts/run-tests.sh sv_pdl.tests.test_refs   # a single module
#
# The stack must already be up (bash ./bootstrap.sh). Tests run as the
# `scaife` user for the same reason every other manage.py call does: plain
# `docker exec` lands as root.
set -euo pipefail

CONTAINER="${SCAIFE_CONTAINER:-scaife-viewer}"

if ! docker ps --format '{{.Names}}' | grep -qx "$CONTAINER"; then
  echo "ERROR: container '$CONTAINER' is not running. Start it with:" >&2
  echo "  bash ./bootstrap.sh" >&2
  exit 1
fi

TARGET="sv_pdl.tests"
TAG_ARGS=(--exclude-tag=integration)

args=()
for arg in "$@"; do
  case "$arg" in
    --integration)
      # Run everything, including checks that need Postgres/ES/Morpheus up.
      # NOTE: test_client_and_server_major_versions is a known failure —
      # elasticsearch-py 7.10.1 against an 8.x server. See UPGRADE-IMPACT.md.
      TAG_ARGS=()
      ;;
    -*)
      args+=("$arg")
      ;;
    *)
      TARGET="$arg"
      ;;
  esac
done

# ${arr[@]+"${arr[@]}"} keeps `set -u` happy with empty arrays on bash 3.2
# (the default /bin/bash on macOS).
set -x
docker exec -u scaife "$CONTAINER" \
  python manage.py test "$TARGET" \
  ${TAG_ARGS[@]+"${TAG_ARGS[@]}"} ${args[@]+"${args[@]}"}
