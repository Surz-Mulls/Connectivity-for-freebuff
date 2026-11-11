#!/usr/bin/env bash
# Optional isolated Arch build environment. Distrobox is NOT a runtime requirement for Continuity
# and is not needed on a machine that already runs Arch: there, use `cd packaging && makepkg -sfC`.
#
# Contract:
#  * the host checkout is bind-mounted at container creation time only (never `--volume` on enter);
#  * an existing container without that mount is reused as-is and the script stops with recovery
#    instructions — it never deletes or recreates a user container;
#  * `pacman -Syu` (full upgrade), never a partial `-Sy`;
#  * makepkg runs as the unprivileged container user; this script adds no sudoers rule and refuses
#    to build as root;
#  * every scripted step uses `distrobox enter --no-tty`, and the build exit code is propagated.
#
# The package is built from scripts/prepare-candidate-pkgbuild.sh (git archive of this checkout),
# never from the manual dist/*.pkg.tar.zst layout archive and never from the published tag.
#
# Usage:  bash scripts/build-arch-distrobox.sh
#         BOX=arch-build bash scripts/build-arch-distrobox.sh
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BOX="${BOX:-arch-build}"
IMAGE="${IMAGE:-ghcr.io/archlinux/archlinux:latest}"
MOUNT="/mnt/continuity-src"

die() { printf 'error: %s\n' "$*" >&2; exit 1; }

case "$ROOT" in
  *:*)
    die "project path contains a colon, which cannot be expressed as a distrobox volume: $ROOT"
    ;;
esac

command -v distrobox >/dev/null 2>&1 || {
  echo "distrobox not found. On Arch: pacman -S distrobox podman" >&2
  echo "Distrobox is optional. On Arch itself, run: cd packaging && makepkg -sfC" >&2
  exit 1
}
command -v podman >/dev/null 2>&1 || command -v docker >/dev/null 2>&1 ||
  die "neither podman nor docker found — distrobox needs one of them"

box_exists() {
  distrobox list --no-color 2>/dev/null | awk -F'|' -v box="$BOX" 'NF >= 2 {
    name = $2
    gsub(/^[ \t]+|[ \t]+$/, "", name)
    if (name == box) found = 1
  } END { exit (found ? 0 : 1) }'
}

recovery() {
  cat <<EOF >&2

'$BOX' exists but does not expose ${MOUNT}/packaging/PKGBUILD.
This script will not delete or recreate an existing container.

Recovery, when you are ready to replace that container:
  distrobox stop '$BOX'
  distrobox rm '$BOX'
  BOX='$BOX' bash scripts/build-arch-distrobox.sh

Or leave it alone and use another name:
  BOX='$BOX-fresh' bash scripts/build-arch-distrobox.sh
EOF
}

if ! box_exists; then
  echo "== creating distrobox '$BOX' ($IMAGE)"
  echo "   volume (create time only): ${ROOT} -> ${MOUNT}"
  distrobox create --yes -n "$BOX" -i "$IMAGE" --volume "${ROOT}:${MOUNT}:rw"
else
  echo "== reusing existing distrobox '$BOX'"
  echo "   not passing --volume to distrobox enter; the create-time mount must already be there"
fi

mount_rc=0
distrobox enter --no-tty "$BOX" -- test -f "${MOUNT}/packaging/PKGBUILD" || mount_rc=$?
if [ "$mount_rc" -ne 0 ]; then
  recovery
  exit 1
fi

echo "== makepkg of the checked-out commit inside '$BOX'"
build_rc=0
distrobox enter --no-tty "$BOX" -- env CONTINUITY_SRC="$MOUNT" bash -s <<'INSIDE' || build_rc=$?
set -euo pipefail
src="${CONTINUITY_SRC:?CONTINUITY_SRC is not set}"
test -f "$src/packaging/PKGBUILD" || {
  echo "project is not visible at $src" >&2
  exit 1
}

if [ "$(id -u)" -eq 0 ]; then
  echo "refusing to build as root: makepkg must run as an unprivileged user" >&2
  echo "Distrobox enters containers as your host user; do not run this script as root." >&2
  exit 1
fi

pkgs=(base-devel git python python-virtualenv zstd curl
      python-cryptography python-zeroconf python-qrcode python-dbus-next qt6-declarative)
# Full upgrade, never a partial one: `pacman -Sy` alone is unsupported on Arch.
sudo pacman -Syu --noconfirm --needed "${pkgs[@]}"

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
bash "$src/scripts/prepare-candidate-pkgbuild.sh" "$work"
if grep -q 'refs/tags/v0.1.0-test.2' "$work/PKGBUILD"; then
  echo "refusing to build: candidate recipe still points at the published tag" >&2
  exit 1
fi

(cd "$work" && makepkg -sfC --noconfirm --nocheck)

mapfile -t built < <(find "$work" -maxdepth 1 -type f -name 'continuity-*.pkg.tar.zst' ! -name '*-debug-*' | sort)
test "${#built[@]}" -eq 1
case "${built[0]}" in
  *continuity-linux-x86_64.pkg.tar.zst)
    echo "refusing the manually assembled archive name" >&2
    exit 1
    ;;
esac
bash "$src/scripts/verify-arch-package.sh" "${built[0]}"
sudo pacman -U --noconfirm "${built[0]}"
mkdir -p "$src/dist/makepkg"
cp -v "${built[0]}" "$src/dist/makepkg/"
bash "$src/scripts/verify-arch-install.sh"
echo "== makepkg package installed and verified; copy is in dist/makepkg/"
echo "   build method: makepkg (candidate git archive, not the manual layout archive)"
INSIDE

if [ "$build_rc" -ne 0 ]; then
  echo "distrobox build failed (exit $build_rc)" >&2
  exit "$build_rc"
fi
