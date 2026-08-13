#!/usr/bin/env bash
# Fetch all external dependencies needed by bootstrap.sh:
#   deps/                — Perseus/Alpheios/Open-Commentaries source repos
#   data-sources/        — three PerseusDL text corpora
#
# All targets are shallow (--depth=1) so total footprint stays ~3 GB.
# Idempotent — re-running skips anything already present.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

mkdir -p deps data-sources

clone_shallow() {
  local url="$1"
  local dest="$2"
  if [ -d "$dest/.git" ] || [ -d "$dest" ] && [ -n "$(ls -A "$dest" 2>/dev/null)" ]; then
    echo "  skip  $dest (already present)"
    return 0
  fi
  echo "  clone $url"
  git clone --depth=1 --quiet "$url" "$dest"
}

echo "==> deps/  (Morpheus + LSJ TEI + Open-Commentaries)"
clone_shallow https://github.com/perseids-tools/morpheus-perseids.git         deps/morpheus-perseids
clone_shallow https://github.com/perseids-tools/morpheus-perseids-api.git     deps/morpheus-perseids-api
clone_shallow https://github.com/PerseusDL/lexica.git                          deps/lexica
clone_shallow https://github.com/Open-Commentaries/homer.opencommentaries.org.git      deps/homer.opencommentaries.org
clone_shallow https://github.com/Open-Commentaries/pausanias.opencommentaries.org.git  deps/pausanias.opencommentaries.org
clone_shallow https://github.com/Open-Commentaries/pindar.opencommentaries.org.git     deps/pindar.opencommentaries.org

echo
echo "==> data-sources/  (Perseus CTS text corpora)"
clone_shallow https://github.com/PerseusDL/canonical-greekLit.git   data-sources/canonical-greekLit
clone_shallow https://github.com/PerseusDL/canonical-latinLit.git   data-sources/canonical-latinLit
clone_shallow https://github.com/PerseusDL/canonical-pdlrefwk.git   data-sources/canonical-pdlrefwk

echo
echo "==> total footprint:"
du -sh deps data-sources 2>/dev/null | awk '{printf "  %-16s  %s\n", $2, $1}'
echo "done."
