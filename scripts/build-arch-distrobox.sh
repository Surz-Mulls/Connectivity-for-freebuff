#!/usr/bin/env bash
# Build the Arch package with makepkg inside a disposable Arch distrobox, install it,
# and run scripts/verify-arch-install.sh. Verification failures abort the script.
#
# The project is bind-mounted at /mnt/continuity-src. Distrobox only shares $HOME
# (and a few system paths) by default, so a checkout outside $HOME is invisible
# unless that mount is explicit. The mount is set both at create time and on enter.
#
# This does NOT build dist/continuity-linux-x86_64.pkg.tar.zst. That file is the
# manually assembled layout archive from scripts/package-linux.sh.
#
# Usage:  bash scripts/build-arch-distrobox.sh
#         BOX=arch-build bash scripts/build-arch-distrobox.sh
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BOX="${BOX:-arch-build}"
IMAGE="${IMAGE:-ghcr.io/archlinux/archlinux:latest}"
MOUNT="/mnt/continuity-src"

command -v distrobox >/dev/null 2>&1 || {
  echo "distrobox not found. Install: pacman -S distrobox podman  (or see https://distrobox.it/install)"
  exit 1
}
command -v podman >/dev/null 2>&1 || command -v docker >/dev/null 2>&1 || {
  echo "neither podman nor docker found — distrobox needs one of them"; exit 1
}

volume="${ROOT}:${MOUNT}:rw"
if ! distrobox list --no-color 2>/dev/null | awk 'NR>1 {print $1, $3}' | grep -Eq "(^|[[:space:]])${BOX}([[:space:]]|$)"; then
  echo "== creating distrobox '$BOX' ($IMAGE) with bind mount $volume"
  distrobox create --yes -n "$BOX" -i "$IMAGE" --volume "$volume"
fi

echo "== building with makepkg inside '$BOX' (project bind-mounted at $MOUNT)"
distrobox enter "$BOX" --additional-flags "--volume ${volume}" -- env \
  CONTINUITY_SRC="$MOUNT" bash -s <<'INSIDE'
set -euo pipefail
src="${CONTINUITY_SRC:-/mnt/continuity-src}"
test -f "$src/packaging/PKGBUILD" || {
  echo "project is not visible at $src — the distrobox bind mount did not apply" >&2
  exit 1
}
test -x "$src/scripts/verify-arch-install.sh" || chmod +x "$src/scripts/verify-arch-install.sh"

if [ "$(id -u)" -eq 0 ]; then
  pacman -Sy --noconfirm --needed base-devel git sudo python python-virtualenv zstd curl \
    python-cryptography python-zeroconf python-qrcode python-dbus-next qt6-declarative
else
  sudo pacman -Sy --noconfirm --needed base-devel git sudo python python-virtualenv zstd curl \
    python-cryptography python-zeroconf python-qrcode python-dbus-next qt6-declarative
fi

work="$(mktemp -d)"
cp "$src/packaging/PKGBUILD" "$work/PKGBUILD"
if [ "$(id -u)" -eq 0 ]; then
  id builder >/dev/null 2>&1 || useradd -m builder
  echo 'builder ALL=(ALL) NOPASSWD: ALL' > /etc/sudoers.d/builder
  chmod 0440 /etc/sudoers.d/builder
  chown -R builder:builder "$work"
  runuser -u builder -- bash -lc "cd '$work' && makepkg -sfC --noconfirm --nocheck"
else
  (cd "$work" && makepkg -sfC --noconfirm --nocheck)
fi

mapfile -t built < <(find "$work" -maxdepth 1 -type f -name 'continuity-*.pkg.tar.zst' ! -name '*-debug-*' | sort)
test "${#built[@]}" -eq 1
if [ "$(id -u)" -eq 0 ]; then
  pacman -U --noconfirm "${built[0]}"
else
  sudo pacman -U --noconfirm "${built[0]}"
fi

mkdir -p "$src/dist/makepkg"
cp -v "${built[0]}" "$src/dist/makepkg/"
bash "$src/scripts/verify-arch-install.sh"
echo "== makepkg package installed and verified; copy is in dist/makepkg/"
INSIDE
