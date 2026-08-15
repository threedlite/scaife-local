#!/usr/bin/env bash
# Run the test suites that ship with the vendored packages.
#
#   bash scripts/run-vendored-tests.sh          # both, checked against baseline
#   bash scripts/run-vendored-tests.sh core     # one package
#   bash scripts/run-vendored-tests.sh atlas
#   bash scripts/run-vendored-tests.sh --verbose atlas   # full pytest output
#
# These are upstream's own suites, not ours. They do NOT pass cleanly, and
# they did not pass before vendoring either — the failures below are
# properties of upstream at the pinned refs, reproduced here so that an edit
# to packages/ which breaks something *new* is visible immediately.
#
# Baseline (recorded 2026-08-14, upstream refs in packages/README.md):
#
#   core    4 passed, 1 failed
#     - test_reader_version_urn_redirects_to_first_passage: the shipped
#       fixture ti.xml declares an invalid refsDecl for
#       urn:cts:greekLit:tlg0096.tlg002.First1K-grc1.
#
#   atlas  12 passed, 7 failed  (two root causes)
#     - 4x the importer emits "metadata": {} on non-workpart nodes while the
#       tests expect the key to be absent. Stale tests, live code is right.
#     - 3x exemplar URNs. CTSImporter.is_workpart() does not account for the
#       exemplar depth, so "exemplar" falls through to the citation branch
#       and raises ValueError: 'exemplar' is not in list. This is a real
#       latent bug, flagged by upstream's own "TODO: Support exemplars";
#       it is unreachable with the corpora this deployment loads, none of
#       which use exemplar URNs.
#
# This script fails if the counts move in EITHER direction. A new failure is
# a regression; an unexpected pass means a baseline above was fixed and this
# header plus the counts need updating.
set -euo pipefail

CONTAINER="${SCAIFE_CONTAINER:-scaife-viewer}"
SRC=/opt/scaife-viewer/src/packages

# package:expected_passed:expected_failed
BASELINE_CORE="4:1"
BASELINE_ATLAS="12:7"

VERBOSE=0
TARGETS=()
for arg in "$@"; do
  case "$arg" in
    --verbose|-v) VERBOSE=1 ;;
    core|atlas) TARGETS+=("$arg") ;;
    -h|--help) sed -n '2,30p' "${BASH_SOURCE[0]}"; exit 0 ;;
    *) echo "unknown argument: $arg" >&2; exit 2 ;;
  esac
done
[ ${#TARGETS[@]} -eq 0 ] && TARGETS=(core atlas)

if ! docker ps --format '{{.Names}}' | grep -qx "$CONTAINER"; then
  echo "ERROR: container '$CONTAINER' is not running. Start it with:" >&2
  echo "  bash ./bootstrap.sh" >&2
  exit 1
fi

status=0

for pkg in "${TARGETS[@]}"; do
  case "$pkg" in
    core)  expected="$BASELINE_CORE"  ; dir="$SRC/scaife-viewer-core"  ;;
    atlas) expected="$BASELINE_ATLAS" ; dir="$SRC/scaife-viewer-atlas" ;;
  esac
  exp_pass="${expected%%:*}"
  exp_fail="${expected##*:}"

  echo "==> $pkg"
  # --no-cov: the coverage report is noise here and upstream's addopts turn
  # it on unconditionally. DeprecationWarnings from pkg_resources namespace
  # declarations are silenced for the same reason.
  out="$(docker exec -u scaife -w "$dir" "$CONTAINER" \
    python -m pytest -q --no-header -p no:cacheprovider --no-cov \
    -W ignore::DeprecationWarning 2>&1 || true)"

  if [ "$VERBOSE" -eq 1 ]; then
    echo "$out" | grep -vE 'UserWarning|import pkg_resources'
  fi

  summary="$(echo "$out" | grep -E '^[0-9]+ (passed|failed)|passed|failed' | tail -1)"
  got_pass="$(echo "$summary" | grep -oE '[0-9]+ passed' | grep -oE '[0-9]+' || echo 0)"
  got_fail="$(echo "$summary" | grep -oE '[0-9]+ failed' | grep -oE '[0-9]+' || echo 0)"

  if [ "$got_pass" = "$exp_pass" ] && [ "$got_fail" = "$exp_fail" ]; then
    echo "    ${got_pass} passed, ${got_fail} failed — matches baseline"
  else
    echo "    ${got_pass} passed, ${got_fail} failed — EXPECTED ${exp_pass} passed, ${exp_fail} failed" >&2
    echo "    $summary" >&2
    echo "    Re-run with --verbose to see which tests moved." >&2
    status=1
  fi
done

if [ "$status" -ne 0 ]; then
  echo >&2
  echo "Vendored-package results moved from the recorded baseline. If the" >&2
  echo "change was intended, update the counts and notes at the top of" >&2
  echo "$(basename "${BASH_SOURCE[0]}")." >&2
fi
exit "$status"
