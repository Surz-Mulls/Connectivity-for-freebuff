#!/usr/bin/env bash
# Reproduce the research clones at the exact commits that were verified (2026-10-28).
# Usage: ./clone-research.sh [target_dir]   (default: ./research)
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
T="${1:-research}"; mkdir -p "$T"; cd "$T"
while IFS=$'\t' read -r name url sha date; do
  [ -z "${name:-}" ] && continue
  if [ -d "$name/.git" ]; then echo "skip $name (exists)"; continue; fi
  echo "== $name @ ${sha:0:7} ($date)"
  git init -q "$name"
  git -C "$name" remote add origin "$url"
  if git -C "$name" fetch -q --depth 1 origin "$sha" 2>/dev/null; then
    git -C "$name" checkout -q FETCH_HEAD
  else
    echo "   by-SHA fetch refused; falling back to shallow clone of default branch (may differ from pinned SHA)"
    rm -rf "$name"; git clone -q --depth 1 "$url" "$name"
  fi
done < "$HERE/REPO_SHAS.tsv"
echo "Done. Verify with: git -C <repo> rev-parse HEAD  (compare to REPO_SHAS.tsv)"
