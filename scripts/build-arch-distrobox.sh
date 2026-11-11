#!/usr/bin/env bash
# Optional Arch build environment. Distrobox is not required to run FreeBuff and
# not required on a machine that already has Arch: use `makepkg -sfC` there.
#
# The host checkout is bind-mounted when the container is created. `distrobox enter`
# is not given another --volume; an existing container without the mount is left
# in place and the script stops with recovery instructions.
#
# The package is built with makepkg from scripts/prepare-candidate-pkgbuild.sh
# (this checkout), not from the manual dist/*.pkg.tar.zst layout archive and not
# by downloading the published v0.1.0-test.2 tag.
#
# Usage:  bash scripts/build-arch-distrobox.sh
#         BOX=arch-build bash scripts/build-arch-distrobox.sh
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BOX="${BOX:-arch-build}"
IMAGE="${IMAGE:-ghcr.io/archlinux/archlinux:latest}"
MOUNT="/mnt/continuity-src"

case "$ROOT" in
  *:*)
    echo "project path contains a colon, which cannot be expressed as a distrobox volume: $ROOT" >&2
    exit 1
    ;;
esac

command -v distrobox >/dev/null 2>&1 || {
  echo "distrobox not found. On Arch: pacman -S distrobox podman" >&2
  echo "Distrobox is optional. On Arch itself, run: cd packaging && makepkg -sfC" >&2
  exit 1
}
command -v podman >/dev/null 2>&1 || command -v docker >/dev/null 2>&1 || {
  echo "neither podman nor docker found — distrobox needs one of them" >&2
  exit 1
}

box_exists() {
  distrobox list --no-color 2>/dev/null | awk -F'|' -v box="$BOX" 'NF >= 2 {
    name = $2
    gsub(/^[ \t]+|[ \t]+$/, "", name)
    if (name == box) found = 1
  } END { exit (found ? 0 : 1) }'
}

recovery() {
  cat <<EOF >&2

'$BOX' does not show ${MOUNT}/packaging/PKGBUILD.
This script will not delete or recreate an existing container.

Recovery, when you are ready to replace that container:
  distrobox stop '$BOX'
  distrobox rm '$BOX'
  BOX='$BOX' bash scripts/build-arch-distrobox.sh

Or leave it alone and use another name:
  BOX='${BOX}-fresh' bash scripts/build-arch-distrobox.sh
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

if ! distrobox enter "$BOX" -- test -f "${MOUNT}/packaging/PKGBUILD"; then
  recovery
  exit 1
fi

echo "== makepkg of the checked-out commit inside '$BOX'"
distrobox enter "$BOX" -- env CONTINUITY_SRC="$MOUNT" bash -s <<'INSIDE'
set -euo pipefail
src="${CONTINUITY_SRC:-/mnt/continuity-src}"
test -f "$src/packaging/PKGBUILD" || {
  echo "project is not visible at $src" >&2
  exit 1
}
test -x "$src/scripts/prepare-candidate-pkgbuild.sh" || chmod +x "$src/scripts/prepare-candidate-pkgbuild.sh"
test -x "$src/scripts/verify-arch-install.sh" || chmod +x "$src/scripts/verify-arch-install.sh"

pkgs=(base-devel git sudo python python-virtualenv zstd curl
      python-cryptography python-zeroconf python-qrcode python-dbus-next qt6-declarative)
if [ "$(id -u)" -eq 0 ]; then
  pacman -Sy --noconfirm --needed "${pkgs[@]}"
else
  sudo pacman -Sy --noconfirm --needed "${pkgs[@]}"
fi

work="$(mktemp -d)"
bash "$src/scripts/prepare-candidate-pkgbuild.sh" "$work"
if grep -q 'refs/tags/v0.1.0-test.2' "$work/PKGBUILD"; then
  echo "refusing to build: candidate recipe still points at the published tag" >&2
  exit 1
fi

if [ "$(id -u)" -eq 0 ]; then
  id builder >/dev/null 2>&1 || useradd -m builder
  echo 'builder ALL=(ALL) NOPASSWD: ALL' > /etc/sudoers.d/builder
  chmod 0440 /etc/sudoers.d/builder
  chown -R builder:builder "$work"
  runuser -u builder -- bash -lc "cd $(printf '%q' "$work") && makepkg -sfC --noconfirm --nocheck"
else
  (cd "$work" && makepkg -sfC --noconfirm --nocheck)
fi

mapfile -t built < <(find "$work" -maxdepth 1 -type f -name 'continuity-*.pkg.tar.zst' ! -name '*-debug-*' | sort)
test "${#built[@]}" -eq 1
case "${built[0]}" in
  *continuity-linux-x86_64.pkg.tar.zst)
    echo "refusing the manually assembled archive name" >&2
    exit 1
    ;;
esac
if [ "$(id -u)" -eq 0 ]; then
  pacman -U --noconfirm "${built[0]}"
else
  sudo pacman -U --noconfirm "${built[0]}"
fi
mkdir -p "$src/dist/makepkg"
cp -v "${built[0]}" "$src/dist/makepkg/"
bash "$src/scripts/verify-arch-install.sh"
echo "== makepkg package installed and verified; copy is in dist/makepkg/"
echo "   build method: makepkg (candidate git archive, not the manual layout archive)"
INSIDE
