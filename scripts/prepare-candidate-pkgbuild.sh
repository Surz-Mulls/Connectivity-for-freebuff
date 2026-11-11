#!/usr/bin/env bash
# Write a makepkg recipe that packages the current git commit, not the pinned
# v0.1.0-test.2 tag. The release file packaging/PKGBUILD is left unchanged.
#
# Usage: scripts/prepare-candidate-pkgbuild.sh DEST_DIR
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST="${1:-}"
if [ -z "$DEST" ]; then
  echo "usage: scripts/prepare-candidate-pkgbuild.sh DEST_DIR" >&2
  exit 1
fi
if [ ! -d "$ROOT/.git" ] && ! git -C "$ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "prepare-candidate-pkgbuild: $ROOT is not a git checkout" >&2
  exit 1
fi
mkdir -p "$DEST"
commit="$(git -C "$ROOT" rev-parse HEAD)"
echo "candidate commit: $commit"
git -C "$ROOT" archive --format=tar.gz --prefix="continuity-candidate/" \
  -o "$DEST/continuity-candidate.tar.gz" HEAD
sum="$(sha256sum "$DEST/continuity-candidate.tar.gz" | awk '{print $1}')"
echo "candidate archive sha256: $sum"
git -C "$ROOT" show "${commit}:packaging/PKGBUILD" > "$DEST/pkgbuild.from-git"
tar -xOzf "$DEST/continuity-candidate.tar.gz" continuity-candidate/packaging/PKGBUILD > "$DEST/pkgbuild.from-tar"
cmp -s "$DEST/pkgbuild.from-git" "$DEST/pkgbuild.from-tar"
rm -f "$DEST/pkgbuild.from-git" "$DEST/pkgbuild.from-tar"
echo "candidate archive matches git show ${commit}:packaging/PKGBUILD"
python3 - "$ROOT/packaging/PKGBUILD" "$DEST/PKGBUILD" "$sum" "$commit" <<'PY'
import pathlib, re, sys
src, dest, digest, commit = sys.argv[1:]
text = pathlib.Path(src).read_text()
old_name = '_srcdir_name="Connectivity-for-freebuff-0.1.0-test.2"'
if old_name not in text:
    sys.exit("PKGBUILD is missing the pinned _srcdir_name marker")
text = text.replace(old_name, '_srcdir_name="continuity-candidate"', 1)
text, n = re.subn(
    r'^source=\(.*\)$',
    'source=("continuity-candidate.tar.gz")',
    text,
    count=1,
    flags=re.M,
)
if n != 1:
    sys.exit("could not replace source=")
text, n = re.subn(
    r"^sha256sums=\('.*'\)$",
    f"sha256sums=('{digest}')",
    text,
    count=1,
    flags=re.M,
)
if n != 1:
    sys.exit("could not replace sha256sums")
if "v0.1.0-test.2.tar.gz" in text or "refs/tags/v0.1.0-test.2" in text:
    sys.exit("generated recipe still references the v0.1.0-test.2 tag archive")
banner = (
    f"# GENERATED candidate recipe for commit {commit}.\n"
    "# Not the release PKGBUILD. Source is git archive of that commit.\n"
)
pathlib.Path(dest).write_text(banner + text)
print(f"wrote {dest}")
PY
grep -n -E '^_srcdir_name=|^source=|^sha256sums=' "$DEST/PKGBUILD"
