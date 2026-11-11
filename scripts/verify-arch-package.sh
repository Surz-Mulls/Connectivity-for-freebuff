#!/usr/bin/env bash
# Verify a package produced by makepkg from packaging/PKGBUILD (or the generated candidate recipe).
# Fatal on any mismatch. Deliberately rejects the manually assembled
# dist/continuity-linux-x86_64.pkg.tar.zst layout archive, which is not a makepkg product.
#
# Usage: scripts/verify-arch-package.sh PACKAGE.pkg.tar.zst
set -euo pipefail
pkg="${1:?usage: verify-arch-package.sh PACKAGE.pkg.tar.zst}"
test -f "$pkg" || { echo "no such package: $pkg" >&2; exit 1; }
name="$(basename "$pkg")"
case "$name" in
  continuity-linux-x86_64.pkg.tar.zst)
    echo "refusing the manually assembled layout archive: $name" >&2
    exit 1
    ;;
  continuity-*.pkg.tar.zst) ;;
  *)
    echo "unexpected package name: $name" >&2
    exit 1
    ;;
esac

if command -v bsdtar >/dev/null 2>&1; then
  reader=(bsdtar -tf)
  extract=(bsdtar -xOf)
elif tar --help 2>/dev/null | grep -q -- '--zstd'; then
  reader=(tar --zstd -tf)
  extract=(tar --zstd -xOf)
else
  echo "neither bsdtar nor GNU tar with --zstd is available" >&2
  exit 1
fi

listing="$("${reader[@]}" "$pkg")"
for meta in .PKGINFO .BUILDINFO .MTREE; do
  if ! printf '%s\n' "$listing" | sed 's|^\./||' | grep -qx -- "$meta"; then
    echo "package is missing $meta (not a genuine makepkg package?)" >&2
    exit 1
  fi
done

pkgname_line="$("${extract[@]}" "$pkg" .PKGINFO | grep -m1 -E '^pkgname[[:space:]]*=' || true)"
case "$pkgname_line" in
  "pkgname = continuity") ;;
  *)
    echo "unexpected pkgname in .PKGINFO: ${pkgname_line:-<missing>}" >&2
    exit 1
    ;;
esac
"${extract[@]}" "$pkg" .BUILDINFO | grep -q '^builddir = ' ||
  { echo ".BUILDINFO has no builddir entry" >&2; exit 1; }

echo "verify-arch-package: ok ($name: .PKGINFO/.BUILDINFO/.MTREE present, pkgname=continuity)"
