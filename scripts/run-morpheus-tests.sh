#!/usr/bin/env bash
# Run the rspec suite that ships with morpheus-perseids-api.
#
#   bash scripts/run-morpheus-tests.sh              # build + run
#   bash scripts/run-morpheus-tests.sh --verbose    # full rspec output
#   bash scripts/run-morpheus-tests.sh --no-build   # reuse the existing image
#
# This is upstream's own suite, not ours, and unlike the vendored Python
# packages it passes cleanly:
#
#   Baseline (recorded 2026-08-15): 28 examples, 0 failures
#
# It covers the Ruby layer as units — the beta-code converter, the bamboo
# JSON and XML builders, engine dispatch and option handling — using
# recorded fixtures rather than the C binary. That makes it complementary
# to sv_pdl/tests/test_morpheus.py, which covers live end-to-end analyses
# but treats the Ruby internals as a black box.
#
# Both matter for a Ruby upgrade: this suite catches a converter or
# serialiser that broke against new Unicode or stdlib behaviour, and would
# localise such a break to a specific unit; the golden suite catches a
# change in what the service actually returns.
#
# The suite needs the development and test gem groups, which the production
# image deliberately omits, so it runs from the Dockerfile's
# `morpheus-test` stage instead.
#
# This script fails if the counts move in EITHER direction. A new failure
# is a regression; a changed total means the upstream suite itself moved
# and the baseline above needs updating.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONTEXT="$REPO_ROOT/deps"
# Absolute: `docker build -f` resolves against the working directory, not
# against the build context.
DOCKERFILE="$CONTEXT/morpheus-combined/Dockerfile"
IMAGE="${MORPHEUS_TEST_IMAGE:-scaife-morpheus-spec:latest}"

EXPECTED_EXAMPLES=28
EXPECTED_FAILURES=0

VERBOSE=0
BUILD=1
for arg in "$@"; do
  case "$arg" in
    --verbose) VERBOSE=1 ;;
    --no-build) BUILD=0 ;;
    *) echo "usage: $0 [--verbose] [--no-build]" >&2; exit 2 ;;
  esac
done

if [ ! -d "$CONTEXT/morpheus-perseids-api" ]; then
  echo "ERROR: deps/morpheus-perseids-api is missing. It is gitignored and" >&2
  echo "fetched on demand; run 'bash scripts/fetch-data.sh' first." >&2
  exit 1
fi

if [ "$BUILD" -eq 1 ]; then
  echo "building $IMAGE (morpheus-test stage)..."
  docker build -f "$DOCKERFILE" --target morpheus-test -t "$IMAGE" "$CONTEXT" \
    >/tmp/morpheus-spec-build.log 2>&1 || {
      echo "ERROR: build failed; last 30 lines:" >&2
      tail -30 /tmp/morpheus-spec-build.log >&2
      exit 1
    }
fi

out="$(mktemp)"
rc=0
docker run --rm "$IMAGE" >"$out" 2>&1 || rc=$?

if [ "$VERBOSE" -eq 1 ]; then
  cat "$out"
fi

# rspec's summary line: "28 examples, 0 failures" (with an optional
# ", N pending" that must not be swallowed into the failure count).
summary="$(grep -E '^[0-9]+ examples?, [0-9]+ failures?' "$out" | tail -1 || true)"
if [ -z "$summary" ]; then
  echo "ERROR: no rspec summary line found. Full output:" >&2
  cat "$out" >&2
  rm -f "$out"
  exit 1
fi

examples="$(echo "$summary" | sed -E 's/^([0-9]+) examples?.*/\1/')"
failures="$(echo "$summary" | sed -E 's/.*, ([0-9]+) failures?.*/\1/')"

echo "morpheus rspec: $summary"

status=0
if [ "$failures" -ne "$EXPECTED_FAILURES" ]; then
  echo "FAIL: expected $EXPECTED_FAILURES failures, got $failures" >&2
  status=1
fi
if [ "$examples" -ne "$EXPECTED_EXAMPLES" ]; then
  echo "FAIL: expected $EXPECTED_EXAMPLES examples, got $examples." >&2
  echo "The upstream suite changed size; update the baseline in this script." >&2
  status=1
fi

if [ "$status" -ne 0 ] && [ "$VERBOSE" -eq 0 ]; then
  echo "--- rspec output ---" >&2
  cat "$out" >&2
fi

rm -f "$out"
[ "$status" -eq 0 ] && echo "OK"
exit "$status"
