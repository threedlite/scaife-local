#!/usr/bin/env bash
# Fetch line-level audio packages from the GitHub release and stage them
# where bootstrap.sh and `ingest_audio` expect them:
#   data-sources/audio/<package>/        (or $SCAIFE_AUDIO_SOURCES)
#
#   bash scripts/fetch-audio.sh hesiod hymns    # named packages
#   bash scripts/fetch-audio.sh all             # all 15: 4.4 GB to download,
#                                               # the same again on disk
#   bash scripts/fetch-audio.sh --list
#
# Opt-in — nothing else calls this. Each zip is checked against the
# release's SHA256SUMS before it is unpacked, and the matching manifest
# from audio-manifests/ is placed beside the clips as package.yaml (the
# zips hold only .mp4 files). See AUDIO-RELEASE.md.
#
# Idempotent — re-running skips anything already staged.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MANIFESTS="$REPO_ROOT/audio-manifests"
DEST="${SCAIFE_AUDIO_SOURCES:-$REPO_ROOT/data-sources/audio}"
RELEASE_REPO="${SCAIFE_AUDIO_REPO:-threedlite/scaife-local}"
RELEASE_TAG="${SCAIFE_AUDIO_RELEASE:-audio-v1}"
BASE="https://github.com/$RELEASE_REPO/releases/download/$RELEASE_TAG"
SUFFIX=".package.yaml"

list_packages() {
  local m
  for m in "$MANIFESTS"/*"$SUFFIX"; do
    basename "$m" "$SUFFIX"
  done
}

usage() {
  echo "usage: bash scripts/fetch-audio.sh <name>... | all | --list"
  echo
  echo "available packages (short name, then the release asset it fetches):"
  local p
  for p in $(list_packages); do
    printf "  %-14s %s.zip\n" "${p%%_chamberlain_*}" "$p"
  done
}

# Short name ("hesiod") or full package name -> full package name.
resolve() {
  local name="$1" m
  if [ -f "$MANIFESTS/$name$SUFFIX" ]; then
    echo "$name"
    return 0
  fi
  for m in "$MANIFESTS/${name}_chamberlain_"*"$SUFFIX"; do
    if [ -f "$m" ]; then
      basename "$m" "$SUFFIX"
      return 0
    fi
  done
  return 1
}

sha256_of() {
  # macOS has shasum, not sha256sum; both print the same hex digest.
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1" | cut -d' ' -f1
  else
    shasum -a 256 "$1" | cut -d' ' -f1
  fi
}

TMP=""
PARTIAL=""
cleanup() {
  [ -n "$PARTIAL" ] && rm -rf "$PARTIAL"
  [ -n "$TMP" ] && rm -rf "$TMP"
  return 0
}
trap cleanup EXIT

# Called from an `if`, where `set -e` does not apply: every step that can
# fail returns explicitly.
fetch_one() {
  local pkg="$1"
  local final="$DEST/$pkg" zip="$TMP/$pkg.zip" expected actual count

  if [ -f "$final/package.yaml" ]; then
    echo "  skip  $pkg (already staged)"
    return 0
  fi
  if [ -e "$final" ]; then
    echo "  ERROR $final exists but has no package.yaml; remove it and re-run" >&2
    return 1
  fi

  expected="$(awk -v f="$pkg.zip" '$2 == f { print $1 }' "$TMP/SHA256SUMS")"
  if [ -z "$expected" ]; then
    echo "  ERROR $pkg.zip is not listed in the release's SHA256SUMS" >&2
    return 1
  fi

  echo "  fetch $pkg.zip"
  if ! curl -fL --retry 3 --progress-bar -o "$zip" "$BASE/$pkg.zip"; then
    echo "  ERROR download failed: $BASE/$pkg.zip" >&2
    rm -f "$zip"
    return 1
  fi
  actual="$(sha256_of "$zip")"
  if [ "$actual" != "$expected" ]; then
    echo "  ERROR checksum mismatch for $pkg.zip (expected $expected, got $actual)" >&2
    rm -f "$zip"
    return 1
  fi

  # Unpack beside the destination and rename once complete, so an
  # interrupted run never leaves a half-staged package that looks whole.
  PARTIAL="$DEST/.$pkg.partial"
  rm -rf "$PARTIAL"
  mkdir -p "$PARTIAL" || return 1
  if ! unzip -q "$zip" -d "$PARTIAL"; then
    echo "  ERROR unzip failed for $pkg.zip" >&2
    return 1
  fi
  rm -f "$zip"
  cp "$MANIFESTS/$pkg$SUFFIX" "$PARTIAL/package.yaml" || return 1
  mv "$PARTIAL" "$final" || return 1
  PARTIAL=""

  count="$(find "$final" -name '*.mp4' | wc -l | tr -d ' ')"
  echo "  ok    $pkg (checksum verified, $count clips)"
}

if [ "$#" -eq 0 ]; then
  usage
  exit 1
fi

PACKAGES=""
for arg in "$@"; do
  case "$arg" in
    -h|--help|--list)
      usage
      exit 0
      ;;
    all)
      PACKAGES="$(list_packages)"
      ;;
    *)
      if ! pkg="$(resolve "$arg")"; then
        echo "unknown package: $arg" >&2
        echo >&2
        usage >&2
        exit 1
      fi
      PACKAGES="$PACKAGES $pkg"
      ;;
  esac
done

for tool in curl unzip; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    echo "ERROR: $tool is required but not installed" >&2
    exit 1
  fi
done

mkdir -p "$DEST"
TMP="$(mktemp -d)"

echo "==> audio packages from $RELEASE_REPO release $RELEASE_TAG -> $DEST"
if ! curl -fsSL --retry 3 -o "$TMP/SHA256SUMS" "$BASE/SHA256SUMS"; then
  echo "ERROR: could not fetch $BASE/SHA256SUMS" >&2
  exit 1
fi

failed=0
for pkg in $PACKAGES; do
  if ! fetch_one "$pkg"; then
    failed=1
  fi
done

echo
if [ "$failed" -ne 0 ]; then
  echo "some packages failed; fix the errors above and re-run (finished ones are skipped)." >&2
  exit 1
fi

cat <<EOF
done. To index what was staged:
  stack already running:  docker exec -u scaife scaife-viewer python manage.py ingest_audio
  first bring-up:         bash bootstrap.sh   (the first boot ingests automatically)
EOF
