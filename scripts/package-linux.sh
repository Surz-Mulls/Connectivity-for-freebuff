#!/usr/bin/env bash
# Build the Linux x86_64 deliverables: portable .tar.zst, Arch .pkg.tar.zst and (when appimagetool
# can be fetched) an AppImage.
#
# What is bundled: the daemon package, the QML client, launchers, desktop entry, icon, licence.
# What is NOT bundled: Qt 6 / a Python interpreter. Those are declared host dependencies, because a
# real self-contained AppImage needs a relocatable CPython plus Qt, which cannot be installed on this
# build host (no root). The script never pretends otherwise; see dist/BUILD-MANIFEST.json.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
VERSION="0.1.0"
ARCH="x86_64"
DIST="$ROOT/dist"
WORK="$ROOT/build/linux"
PORTABLE_NAME="continuity-linux-$ARCH-portable"
STAGE="$WORK/$PORTABLE_NAME"
mkdir -p "$DIST" "$WORK"

command -v zstd >/dev/null 2>&1 || {
  if ! .venv/bin/python -c "import zstandard" 2>/dev/null; then
    echo "== installing zstandard (build tool only)"
    .venv/bin/pip install -q zstandard
  fi
}

zstd_tar() {  # zstd_tar <dir> <out.tar.zst>
  if command -v zstd >/dev/null 2>&1; then
    tar -C "$1" -cf - . | zstd -q -19 -T0 -o "$2" -f
  else
    .venv/bin/python - "$1" "$2" <<'PY'
import os, sys, tarfile, zstandard
root, out = sys.argv[1], sys.argv[2]
cctx = zstandard.ZstdCompressor(level=19)
with open(out, "wb") as raw, cctx.stream_writer(raw, closefd=False) as compress:
    with tarfile.open(fileobj=compress, mode="w|") as tar:
        for name in sorted(os.listdir(root)):
            tar.add(os.path.join(root, name), arcname=name)
PY
  fi
}

# ------------------------------------------------------------------ portable staging
rm -rf "$WORK"/* 2>/dev/null || true
mkdir -p "$STAGE"/{bin,lib,qml,share/applications,share/icons/hicolor/scalable/apps}
cp -r daemon/continuityd "$STAGE/lib/continuityd"
cp -r desktop/qml/. "$STAGE/qml/"
cp LICENSE "$STAGE/LICENSE"
[ -f NOTICE.md ] && cp NOTICE.md "$STAGE/NOTICE.md"
cp desktop/run-continuity.sh "$STAGE/run-continuity.sh"
chmod 0755 "$STAGE/run-continuity.sh"

cat > "$STAGE/bin/continuityd" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PYTHONPATH="$HERE/lib${PYTHONPATH:+:$PYTHONPATH}"
exec python3 -c 'import sys; from continuityd.cli import main; sys.exit(main())' "$@"
SH
chmod 0755 "$STAGE/bin/continuityd"
cp "$STAGE/bin/continuityd" "$STAGE/bin/continuityctl"

cat > "$STAGE/continuity.desktop" <<'DESKTOP'
[Desktop Entry]
Type=Application
Name=Continuity
Comment=Clipboard, files and notifications between this desktop and your phone
Exec=continuity-run
Icon=continuity
Categories=Utility;Network;
Terminal=false
DESKTOP
cp "$STAGE/continuity.desktop" "$STAGE/share/applications/continuity.desktop"

.venv/bin/python - "$STAGE/share/icons/hicolor/scalable/apps/continuity.svg" <<'PY'
import sys
svg = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128">
<rect width="128" height="128" rx="28" fill="#1e1e2e"/>
<rect x="26" y="20" width="38" height="72" rx="8" fill="none" stroke="#89b4fa" stroke-width="6"/>
<rect x="64" y="40" width="38" height="68" rx="8" fill="none" stroke="#a6e3a1" stroke-width="6"/>
<circle cx="45" cy="100" r="4" fill="#89b4fa"/><circle cx="83" cy="34" r="4" fill="#a6e3a1"/>
</svg>
"""
open(sys.argv[1], "w").write(svg)
PY

cat > "$STAGE/continuity-run" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$HERE/run-continuity.sh" "$@"
SH
chmod 0755 "$STAGE/continuity-run"

cat > "$STAGE/README.md" <<'TXT'
# Continuity — portable Linux build

Requires on the host: Python 3.11+, python-cryptography, python-zeroconf, python-qrcode,
and a Qt 6 QML runtime (`qml6`/`qml`, or `pip install PySide6-Essentials`). Nothing is installed
system-wide by this archive.

    ./bin/continuityd run          # start the daemon (writes state under XDG dirs)
    ./continuity-run               # start the QML client

Uninstall: delete this directory, then remove `~/.config/continuity`, `~/.local/share/continuity`
and `~/.local/state/continuity` if you also want the paired-device data gone. No transfer or
clipboard data is deleted unless you remove those directories yourself.
TXT

tar_out="$DIST/continuity-linux-$ARCH-portable.tar.zst"
rm -f "$tar_out"
mkdir -p "$WORK/tarroot"
rm -rf "$WORK/tarroot/$PORTABLE_NAME"
cp -a "$STAGE" "$WORK/tarroot/$PORTABLE_NAME"
zstd_tar "$WORK/tarroot/$PORTABLE_NAME" "$tar_out"
echo "portable: $tar_out ($(stat -c%s "$tar_out") bytes)"

# ------------------------------------------------------------------ Arch package
PKG="$WORK/pkgroot"
rm -rf "$PKG"
mkdir -p "$PKG/usr/lib/continuity" "$PKG/usr/bin" "$PKG/usr/share/applications" \
         "$PKG/usr/share/icons/hicolor/scalable/apps" "$PKG/usr/share/licenses/continuity"
cp -r "$STAGE/lib" "$PKG/usr/lib/continuity/lib"
cp -r "$STAGE/qml" "$PKG/usr/lib/continuity/qml"
cp "$STAGE/run-continuity.sh" "$PKG/usr/lib/continuity/run-continuity.sh"
cp LICENSE "$PKG/usr/share/licenses/continuity/LICENSE"
cp "$STAGE/share/icons/hicolor/scalable/apps/continuity.svg" \
   "$PKG/usr/share/icons/hicolor/scalable/apps/continuity.svg"

cat > "$PKG/usr/bin/continuityd" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
export PYTHONPATH="/usr/lib/continuity/lib${PYTHONPATH:+:$PYTHONPATH}"
exec python3 -c 'import sys; from continuityd.cli import main; sys.exit(main())' "$@"
SH
chmod 0755 "$PKG/usr/bin/continuityd"
cp "$PKG/usr/bin/continuityd" "$PKG/usr/bin/continuityctl"

cat > "$PKG/usr/bin/continuity" <<'SH'
#!/usr/bin/env bash
exec /usr/lib/continuity/run-continuity.sh "$@"
SH
chmod 0755 "$PKG/usr/bin/continuity"

sed 's|Exec=continuity-run|Exec=continuity|' "$STAGE/continuity.desktop" \
  > "$PKG/usr/share/applications/continuity.desktop"

installed_size="$(du -sb "$PKG" | cut -f1)"
cat > "$PKG/.PKGINFO" <<PKGINFO
pkgname = continuity
pkgbase = continuity
pkgver = $VERSION-1
pkgdesc = Local-first Android/Linux continuity: pinned pairing, clipboard, files, notifications
url = https://github.com/Surz-Mulls/Connectivity-for-freebuff
builddate = $(date +%s)
packager = FreeBuff <noreply@codebuff.com>
size = $installed_size
arch = $ARCH
license = GPL-3.0-only
depend = python
depend = python-cryptography
depend = python-zeroconf
depend = python-qrcode
depend = qt6-declarative
optdepend = python-pyside6: QML runtime alternative to qt6-declarative
PKGINFO

pkg_out="$DIST/continuity-linux-$ARCH.pkg.tar.zst"
rm -f "$pkg_out"
zstd_tar "$PKG" "$pkg_out"
echo "arch:     $pkg_out ($(stat -c%s "$pkg_out") bytes)"

# ------------------------------------------------------------------ AppImage (best effort)
appimage_out="$DIST/continuity-linux-$ARCH.AppImage"
if [ "${CONTINUITY_SKIP_APPIMAGE:-0}" != "1" ]; then
  TOOLS="$ROOT/.toolchain/appimage"
  TOOL="$TOOLS/appimagetool"
  if [ ! -x "$TOOL" ]; then
    mkdir -p "$TOOLS"
    if curl -fL --retry 2 --max-time 120 -o "$TOOLS/appimagetool.AppImage" \
        "https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage"; then
      chmod +x "$TOOLS/appimagetool.AppImage"
      (cd "$TOOLS" && ./appimagetool.AppImage --appimage-extract >/dev/null 2>&1) || true
      [ -x "$TOOLS/squashfs-root/AppRun" ] && cp "$TOOLS/squashfs-root/AppRun" "$TOOL" || true
    fi
  fi
  if [ -x "$TOOL" ]; then
    APPDIR="$WORK/AppDir"
    rm -rf "$APPDIR"
    cp -a "$STAGE" "$APPDIR"
    cp "$APPDIR/share/icons/hicolor/scalable/apps/continuity.svg" "$APPDIR/continuity.svg"
    cp "$APPDIR/continuity.svg" "$APPDIR/.DirIcon" 2>/dev/null || true
    cat > "$APPDIR/AppRun" <<'SH'
#!/bin/sh
HERE="$(dirname "$(readlink -f "$0")")"
exec "$HERE/continuity-run" "$@"
SH
    chmod 0755 "$APPDIR/AppRun"
    ARCH="$ARCH" "$TOOL" --no-appstream "$APPDIR" "$appimage_out" >/dev/null 2>&1 \
      && echo "appimage: $appimage_out ($(stat -c%s "$appimage_out" 2>/dev/null || echo 0) bytes)" \
      || echo "appimage: FAILED (appimagetool could not build the image)"
  else
    echo "appimage: SKIPPED (appimagetool unavailable in this environment)"
  fi
fi

# ------------------------------------------------------------------ manifest + checksums
cd "$DIST"
rm -f SHA256SUMS
for asset in continuity-android-debug.apk continuity-linux-x86_64*; do
  [ -f "$asset" ] && sha256sum "$asset" >> SHA256SUMS
done
cat > BUILD-MANIFEST.json <<JSON
{
  "version": "$VERSION",
  "commit": "$(git rev-parse HEAD 2>/dev/null || echo unknown)",
  "architecture": "$ARCH",
  "built_utc": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "python": "$(python3 --version 2>&1)",
  "assets": [
    {"name": "continuity-android-debug.apk", "type": "apk", "signing": "debug"},
    {"name": "continuity-linux-x86_64-portable.tar.zst", "type": "portable", "bundles_qt": false},
    {"name": "continuity-linux-x86_64.pkg.tar.zst", "type": "arch-package", "bundles_qt": false},
    {"name": "continuity-linux-x86_64.AppImage", "type": "appimage", "bundles_qt": false}
  ],
  "host_dependencies": ["python>=3.11", "python-cryptography", "python-zeroconf", "python-qrcode", "qt6-declarative or PySide6-Essentials"],
  "notes": "Qt and Python are declared dependencies, not bundled: this host has no root to install Qt and no relocatable CPython was staged."
}
JSON
cat SHA256SUMS
echo "OK: linux packaging finished"
