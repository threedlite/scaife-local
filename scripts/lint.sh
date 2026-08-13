#!/usr/bin/env bash
# Run the project's style checks WITHOUT rebuilding the image.
#
#   bash scripts/lint.sh          # python: flake8 + isort (fast, no stack needed)
#   bash scripts/lint.sh --js     # also run eslint (needs the node build stage)
#   bash scripts/lint.sh --fix    # apply isort's import ordering in place
#
# These checks used to run inside `docker build` and would fail the whole
# image over a formatting error. They are now opt-in there
# (--build-arg RUN_LINT=1); this script is the everyday way to run them.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_ROOT="$REPO_ROOT/scaife/scaife-viewer-2026-08-10-001"
IMAGE="${SCAIFE_LINT_IMAGE:-scaife-viewer-base:latest}"

RUN_JS=0
FIX=0
for arg in "$@"; do
  case "$arg" in
    --js) RUN_JS=1 ;;
    --fix) FIX=1 ;;
    -h|--help) sed -n '2,10p' "${BASH_SOURCE[0]}"; exit 0 ;;
    *) echo "unknown option: $arg" >&2; exit 2 ;;
  esac
done

if ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
  echo "ERROR: image '$IMAGE' not found. Build it first: bash ./bootstrap.sh" >&2
  exit 1
fi

status=0

if [ "$FIX" -eq 1 ]; then
  echo "==> isort (writing changes)"
  docker run --rm -v "$APP_ROOT":/w -w /w "$IMAGE" sh -c 'isort **/*.py'
  echo "    imports reordered in place; re-run without --fix to verify"
  exit 0
fi

echo "==> flake8 sv_pdl"
docker run --rm -v "$APP_ROOT":/w -w /w "$IMAGE" flake8 sv_pdl || status=1

echo "==> isort -c"
docker run --rm -v "$APP_ROOT":/w -w /w "$IMAGE" sh -c 'isort -c **/*.py' || status=1

if [ "$RUN_JS" -eq 1 ]; then
  echo "==> npm run lint"
  # eslint lives in the node static-build stage, not the runtime image.
  docker run --rm -v "$APP_ROOT":/w -w /w node:12.13-alpine \
    sh -c 'npm ci --silent && npm run lint' || status=1
fi

if [ "$status" -eq 0 ]; then
  echo "lint clean"
else
  echo "lint reported problems (this does not affect the image build)" >&2
fi
exit "$status"
