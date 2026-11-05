#!/usr/bin/env bash
# Build the Arch package (and delegate the AppImage to the canonical builder) inside a user-owned
# Arch distrobox. This is the one-command flow for a machine that HAS distrobox+podman; in the
# Freebuff cloud VM both tools were absent and no new-privileges/sudo was allowed, so this script
# is the reproducible user-side path (see docs/VALIDATION_REPORT_v0.1.0-test.2.md §4).
#
# Usage:  bash scripts/build-arch-distrobox.sh            # create/enter box, build all artifacts
#         BOX=pkgname bash scripts/build-arch-distrobox.sh
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BOX="${BOX:-arch-build}"
IMAGE="${IMAGE:-ghcr.io/archlinux/archlinux:latest}"

command -v distrobox >/dev/null 2>&1 || {
  echo "distrobox not found. Install: pacman -S distrobox podman  (or see https://distrobox.it/install)"
  exit 1
}
command -v podman >/dev/null 2>&1 || command -v docker >/dev/null 2>&1 || {
  echo "neither podman nor docker found — distrobox needs one of them"; exit 1
}

if ! distrobox list 2>/dev/null | awk '{print $2}' | grep -qx "$BOX"; then
  echo "== creating distrobox '$BOX' ($IMAGE)"
  distrobox create -n "$BOX" -i "$IMAGE"
fi

echo "== building inside the box ( mounts project at /mnt/continuity-src )"
distrobox enter "$BOX" -- bash -s <<'INSIDE'
set -euo pipefail
src="/mnt/continuity-src"
cd "$src"
if ! command -v python >/dev/null 2>&1; then
  pacman -Sy --noconfirm --needed base-devel python python-virtualenv zstd curl
fi
python -m venv .venv
.venv/bin/pip install --disable-pip-version-check -e "daemon[dev]" zstandard
bash scripts/package-linux.sh
./scripts/verify-release.sh 2>/dev/null || true
echo ""
echo "== box build finished; artifacts are in ./dist on the host"
INSIDE
