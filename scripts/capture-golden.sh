#!/usr/bin/env bash
# Regenerate the golden files the upgrade regression tests compare against.
#
#   bash scripts/capture-golden.sh            # everything
#   bash scripts/capture-golden.sh schema     # GraphQL schema only
#   bash scripts/capture-golden.sh passages   # CTS passage rendering only
#   bash scripts/capture-golden.sh morpheus   # Morpheus analyser only
#
# Written to sv_pdl/tests/golden/:
#
#   atlas_schema.json     normalised GraphQL contract (asserted on)
#   atlas_schema.graphql  printed SDL, for human review only
#   passages.json         CTS passage characterisation payloads
#   morpheus.json         Morpheus analyser characterisation payloads
#
# Run this ONLY when a change is intended, and review the diff before
# committing. An unreviewed golden refresh is indistinguishable from the
# regression the file exists to catch — see the docstrings in
# sv_pdl/tests/test_schema_contract.py and test_passage_contract.py.
#
# The stack must be up (bash ./bootstrap.sh). The working tree's copies of
# the snapshot helpers are pushed into the container first, so editing a
# helper and re-running produces a matching golden file without an image
# rebuild.
set -euo pipefail

CONTAINER="${SCAIFE_CONTAINER:-scaife-viewer}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_ROOT="$REPO_ROOT/scaife/scaife-viewer-2026-08-10-001"
TESTS_DIR="$APP_ROOT/sv_pdl/tests"
GOLDEN_DIR="$TESTS_DIR/golden"
SRC_TESTS=/opt/scaife-viewer/src/sv_pdl/tests

WHAT="${1:-all}"
case "$WHAT" in
  all|schema|passages|morpheus) ;;
  *) echo "usage: $0 [all|schema|passages|morpheus]" >&2; exit 2 ;;
esac

if ! docker ps --format '{{.Names}}' | grep -qx "$CONTAINER"; then
  echo "ERROR: container '$CONTAINER' is not running. Start it with:" >&2
  echo "  bash ./bootstrap.sh" >&2
  exit 1
fi

mkdir -p "$GOLDEN_DIR"

# Use the working-tree helpers, not whatever was baked into the image.
docker exec -u 0 "$CONTAINER" mkdir -p "$SRC_TESTS/golden"
for helper in schema_snapshot.py passage_snapshot.py morpheus_snapshot.py; do
  docker cp "$TESTS_DIR/$helper" "$CONTAINER:$SRC_TESTS/$helper" >/dev/null
done
docker exec -u 0 "$CONTAINER" chown -R scaife "$SRC_TESTS"

# Each artifact is streamed over stdout. The pkg_resources warning and the
# resolver's "Removed urn:" chatter both go to stderr, so these redirects
# stay clean.
run_py() {
  docker exec -u scaife "$CONTAINER" python -c "
import json
import os

import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'sv_pdl.settings')
django.setup()
$1
"
}

# Everything before this marker is discarded. The application prints to
# stdout during import and during CTS resolution — the resolver emits
# 'Unable to parse <file>' for corpus files with a bad refsDecl, and a
# cold metadata cache makes it do so for dozens of them. An earlier version
# of this script redirected stdout straight into the golden file and wrote
# that chatter into passages.json, producing a file that was not JSON at
# all. Anchoring on a marker makes the capture independent of whatever the
# app decides to print.
# No leading dash: a marker starting with "-" is read as an option by grep.
MARKER="===BEGIN_GOLDEN_PAYLOAD==="

# capture <python-snippet> <destination> <json|text>
capture() {
  snippet="$1"; dest="$2"; kind="$3"
  tmp="$(mktemp)"

  # `|| rc=$?` matters: without it `set -e` aborts the whole script the
  # moment python exits non-zero, *before* the marker check below can
  # report anything. That produced a silent failure once — the script died
  # mid-function, printed nothing a caller grepping for "wrote|ERROR" would
  # match, left the previous golden file in place, and a subsequent diff
  # compared that stale file against itself and looked clean.
  rc=0
  run_py "
$snippet
" > "$tmp" 2>"$tmp.err" || rc=$?

  if [ "$rc" -ne 0 ]; then
    echo "ERROR: capture for $dest failed (python exit $rc); $dest left unchanged" >&2
    tail -20 "$tmp.err" >&2
    rm -f "$tmp" "$tmp.err"
    exit 1
  fi

  if ! grep -qF -- "$MARKER" "$tmp"; then
    echo "ERROR: capture produced no payload marker; refusing to write $dest" >&2
    echo "--- last 20 lines of output ---" >&2
    tail -20 "$tmp" >&2
    rm -f "$tmp" "$tmp.err"
    exit 1
  fi

  # Keep only what follows the marker line. awk with a literal string match
  # avoids any regex interpretation of the marker.
  awk -v m="$MARKER" 'seen { print } index($0, m) { seen = 1 }' "$tmp" > "$tmp.payload"

  if [ "$kind" = json ] && ! python3 -c "import json,sys; json.load(open(sys.argv[1]))" "$tmp.payload"; then
    echo "ERROR: captured payload for $dest is not valid JSON; refusing to write" >&2
    head -5 "$tmp.payload" >&2
    rm -f "$tmp" "$tmp.payload"
    exit 1
  fi
  if [ ! -s "$tmp.payload" ]; then
    echo "ERROR: captured payload for $dest is empty; refusing to write" >&2
    rm -f "$tmp" "$tmp.payload"
    exit 1
  fi

  mv "$tmp.payload" "$dest"
  rm -f "$tmp" "$tmp.err"
  echo "wrote $dest"
}

if [ "$WHAT" = all ] || [ "$WHAT" = schema ]; then
  capture "
from sv_pdl.tests.schema_snapshot import load_schema, snapshot
payload = json.dumps(snapshot(load_schema()), indent=2, sort_keys=True)
print('$MARKER')
print(payload)
" "$GOLDEN_DIR/atlas_schema.json" json

  capture "
from graphql import print_schema
from sv_pdl.tests.schema_snapshot import core_schema, load_schema
# print_schema wants the graphql-core schema. Under graphene 3 the
# graphene wrapper resolves unknown attributes as type lookups, so
# passing it directly fails with 'Type \"directives\" not found'.
payload = print_schema(core_schema(load_schema()))
print('$MARKER')
print(payload, end='')
" "$GOLDEN_DIR/atlas_schema.graphql" text
fi

if [ "$WHAT" = all ] || [ "$WHAT" = passages ]; then
  capture "
from sv_pdl.tests.passage_snapshot import capture as capture_passages
payload = json.dumps(capture_passages(), indent=2, sort_keys=True, ensure_ascii=False)
print('$MARKER')
print(payload)
" "$GOLDEN_DIR/passages.json" json
fi

if [ "$WHAT" = all ] || [ "$WHAT" = morpheus ]; then
  capture "
from sv_pdl.tests.morpheus_snapshot import capture as capture_morpheus
payload = json.dumps(capture_morpheus(), indent=2, sort_keys=True, ensure_ascii=False)
print('$MARKER')
print(payload)
" "$GOLDEN_DIR/morpheus.json" json
fi

echo
echo "Review the diff before committing:"
echo "  git diff --stat -- '*/golden/*'"
