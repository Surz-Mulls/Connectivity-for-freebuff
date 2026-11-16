#!/usr/bin/env bash
# Build a genuinely self-contained x86_64 AppImage: CPython, the daemon's dependencies, PySide6/Qt
# (including the QML modules) and the app itself, all inside the image.
#
# This is the ONE canonical AppImage builder (scripts/package-linux.sh delegates to it). It works
# from a clean checkout: it provisions its own build venv, a pinned appimagetool, and a pinned
# relocatable CPython. Both downloads are checked against a hard-coded SHA-256 before anything
# downloaded is executed. A host Python on PATH is not copied into the image.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PY_VER="3.12"
PYSIDE="6.12.0"
# Whole-image minimum, measured across every bundled ELF (not just the interpreter).
# docs/PINNED_TOOLING.md and README.md must state the same value.
GLIBC_FLOOR="2.34"
APPIMAGETOOL_TAG="1.9.0"
APPIMAGETOOL_URL="https://github.com/AppImage/appimagetool/releases/download/${APPIMAGETOOL_TAG}/appimagetool-x86_64.AppImage"
# Measured 2026-11-15 from the URL above. Size 12632352. The asset's own text identifies a
# continuous build; the tag is 1.9.0. Provenance: docs/PINNED_TOOLING.md.
APPIMAGETOOL_SHA256="46fdd785094c7f6e545b61afcfb0f3d98d8eab243f644b4b17698c01d06083d1"
# python-build-standalone install_only, tag 20261110. Max GLIBC symbol on the interpreter is 2.17.
CPYTHON_NAME="cpython-3.12.16+20261110-x86_64-unknown-linux-gnu-install_only.tar.gz"
CPYTHON_URL="https://github.com/astral-sh/python-build-standalone/releases/download/20261110/${CPYTHON_NAME}"
CPYTHON_SHA256="c2f87d4b4e8db3abddb0f116c6ccfc503d0cbdbb9ee8faacddad1b679ec12e99"
DIST="$ROOT/dist"
WORK="$ROOT/build/appimage"
APPDIR="$WORK/AppDir"
BUNDLE="$APPDIR/usr/lib/python$PY_VER"
OUT="$DIST/continuity-linux-x86_64.AppImage"
TOOL="$ROOT/.toolchain/appimage/squashfs-root/AppRun"
VENV="$ROOT/build/appimage-venv"

is_elf() { [ "$(head -c4 "$1" 2>/dev/null | od -An -tx1 | tr -d ' \n')" = "7f454c46" ]; }

# Regression hook only. Production builds leave this unset and use the pinned tarball below.
if [ -n "${CONTINUITY_APPIMAGE_PYTHON_OVERRIDE:-}" ]; then
  PYTHON_BIN="$(readlink -f "$CONTINUITY_APPIMAGE_PYTHON_OVERRIDE")"
  is_elf "$PYTHON_BIN" || {
    echo "python$PY_VER resolves to $PYTHON_BIN, which is not an ELF executable." >&2
    echo "Use a real CPython $PY_VER (or a relocatable python-build-standalone build)." >&2
    exit 1
  }
  echo "CONTINUITY_APPIMAGE_PYTHON_OVERRIDE is not a substitute for the pinned CPython." >&2
  exit 1
fi

USE_DEV_VENV=1
if [ ! -x "$ROOT/.venv/bin/pip" ]; then
  USE_DEV_VENV=0
  echo "== provisioning a build venv from a clean checkout"
  [ -x "$VENV/bin/pip" ] || python3 -m venv "$VENV"
  "$VENV/bin/pip" install --quiet --disable-pip-version-check cryptography zeroconf qrcode
fi
PIP="$( [ "$USE_DEV_VENV" = 1 ] && echo "$ROOT/.venv/bin/pip" || echo "$VENV/bin/pip" )"
PY="$( [ "$USE_DEV_VENV" = 1 ] && echo "$ROOT/.venv/bin/python" || echo "$VENV/bin/python" )"

verify_sha256() {
  local file="$1" expected="$2" label="$3"
  local measured
  measured="$(sha256sum "$file" | cut -d' ' -f1)"
  if [ "$measured" != "$expected" ]; then
    echo "$label checksum mismatch (pinned $expected, measured $measured)" >&2
    exit 1
  fi
  echo "$label checksum verified: $measured"
}

fetch_verified() {
  local url="$1" dest="$2" expected="$3" label="$4"
  local tmp measured
  tmp="$(mktemp)"
  curl -fL --retry 2 --max-time 180 -o "$tmp" "$url"
  measured="$(sha256sum "$tmp" | cut -d' ' -f1)"
  if [ "$measured" != "$expected" ]; then
    echo "$label checksum mismatch (pinned $expected, measured $measured)" >&2
    rm -f "$tmp"
    exit 1
  fi
  mv "$tmp" "$dest"
  echo "$label checksum verified: $measured"
}

TOOLS="$ROOT/.toolchain/appimage"
mkdir -p "$TOOLS"
if [ ! -f "$TOOLS/appimagetool.AppImage" ]; then
  echo "== provisioning pinned appimagetool ($APPIMAGETOOL_TAG)"
  fetch_verified "$APPIMAGETOOL_URL" "$TOOLS/appimagetool.AppImage" "$APPIMAGETOOL_SHA256" "appimagetool"
fi
# Verify the cached archive every time. A pre-extracted AppRun from an older download is not proof
# that the pinned tool is the one being used.
verify_sha256 "$TOOLS/appimagetool.AppImage" "$APPIMAGETOOL_SHA256" "appimagetool"
if [ ! -x "$TOOL" ]; then
  chmod +x "$TOOLS/appimagetool.AppImage"
  rm -rf "$TOOLS/squashfs-root"
  (cd "$TOOLS" && ./appimagetool.AppImage --appimage-extract >/dev/null 2>&1)
  test -x "$TOOL" || { echo "appimagetool extraction failed" >&2; exit 1; }
fi

rm -rf "$WORK"
mkdir -p "$APPDIR/usr/bin" "$BUNDLE/site-packages" "$APPDIR/usr/share/applications" \
         "$APPDIR/usr/share/icons/hicolor/scalable/apps"

echo "== staging pinned CPython ($CPYTHON_NAME)"
CPYTHON_DIR="$ROOT/.toolchain/cpython"
mkdir -p "$CPYTHON_DIR"
if [ ! -f "$CPYTHON_DIR/$CPYTHON_NAME" ]; then
  fetch_verified "$CPYTHON_URL" "$CPYTHON_DIR/$CPYTHON_NAME" "$CPYTHON_SHA256" "cpython"
else
  verify_sha256 "$CPYTHON_DIR/$CPYTHON_NAME" "$CPYTHON_SHA256" "cpython"
fi
rm -rf "$CPYTHON_DIR/python"
tar -xzf "$CPYTHON_DIR/$CPYTHON_NAME" -C "$CPYTHON_DIR"
PYTHON_BIN="$(readlink -f "$CPYTHON_DIR/python/bin/python$PY_VER")"
is_elf "$PYTHON_BIN" || {
  echo "pinned python$PY_VER at $PYTHON_BIN is not an ELF executable" >&2
  exit 1
}
cp "$PYTHON_BIN" "$APPDIR/usr/bin/python$PY_VER"
mkdir -p "$APPDIR/usr/lib"
cp -a "$CPYTHON_DIR/python/lib/libpython$PY_VER.so"* "$APPDIR/usr/lib/"
test -e "$APPDIR/usr/lib/libpython$PY_VER.so.1.0" || {
  echo "libpython$PY_VER not found in the pinned CPython archive" >&2
  exit 1
}
cp -a "$CPYTHON_DIR/python/lib/python$PY_VER/." "$BUNDLE/"
rm -rf "$BUNDLE/site-packages" "$BUNDLE/dist-packages" "$BUNDLE/lib2to3" "$BUNDLE/test"
mkdir -p "$BUNDLE/site-packages"

echo "== installing runtime dependencies into the image (PySide6 $PYSIDE)"
"$PIP" install --quiet --disable-pip-version-check \
  --target "$BUNDLE/site-packages" \
  "cryptography>=42" "zeroconf>=0.132" "qrcode>=7.4" "PySide6-Essentials==$PYSIDE"

echo "== staging the application"
cp -r daemon/continuityd "$BUNDLE/site-packages/continuityd"
cp -r desktop/qml "$APPDIR/qml"
cp desktop/qml_launcher.py "$APPDIR/qml_launcher.py"
cp LICENSE "$APPDIR/LICENSE"
[ -f NOTICE.md ] && cp NOTICE.md "$APPDIR/NOTICE.md" || true

cat > "$APPDIR/appenv.sh" <<'SH'
HERE="$(dirname "$(readlink -f "$0")")"
export PYTHONHOME="$HERE/usr"
export PYTHONPATH="$HERE/usr/lib/python3.12:$HERE/usr/lib/python3.12/site-packages"
export LD_LIBRARY_PATH="$HERE/usr/lib:$HERE/usr/lib/python3.12/site-packages/PySide6/Qt/lib"
export QT_PLUGIN_PATH="$HERE/usr/lib/python3.12/site-packages/PySide6/Qt/plugins"
export QT_QPA_PLATFORM_PLUGIN_PATH="$HERE/usr/lib/python3.12/site-packages/PySide6/Qt/plugins/platforms"
export QML2_IMPORT_PATH="$HERE/usr/lib/python3.12/site-packages/PySide6/Qt/qml"
export QML_IMPORT_PATH="$QML2_IMPORT_PATH"
SH

cat > "$APPDIR/AppRun" <<'SH'
#!/bin/sh
HERE="$(dirname "$(readlink -f "$0")")"
. "$HERE/appenv.sh"
case "${1:-}" in
  --self-test)
    exec "$HERE/usr/bin/python3.12" -c \
      'import PySide6.QtQml, cryptography, zeroconf, qrcode; from continuityd.config import api_config_path; print("self-test ok:", api_config_path())'
    ;;
  daemon)
    shift
    exec "$HERE/usr/bin/python3.12" -c 'import sys; from continuityd.cli import main; sys.exit(main())' "$@"
    ;;
  *)
    exec "$HERE/usr/bin/python3.12" "$HERE/qml_launcher.py" "$@"
    ;;
esac
SH
chmod 0755 "$APPDIR/AppRun"

"$PY" - "$APPDIR/usr/share/icons/hicolor/scalable/apps/continuity.svg" <<'PY'
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
cp "$APPDIR/usr/share/icons/hicolor/scalable/apps/continuity.svg" "$APPDIR/continuity.svg"
cp "$APPDIR/continuity.svg" "$APPDIR/.DirIcon"

cat > "$APPDIR/continuity.desktop" <<'DESKTOP'
[Desktop Entry]
Type=Application
Name=Continuity
Comment=Clipboard, files and notifications between this desktop and your phone
Exec=AppRun
Icon=continuity
Categories=Network;FileTransfer;
Terminal=false
X-AppImage-Version=0.1.0
DESKTOP

if ! command -v desktop-file-validate >/dev/null 2>&1; then
  echo "desktop-file-validate is not installed." >&2
  echo "Install desktop-file-utils before building the AppImage." >&2
  exit 1
fi
desktop-file-validate "$APPDIR/continuity.desktop"

chmod -R a+rX "$APPDIR"
chmod a+rx "$APPDIR/AppRun"

echo "== clean-room checks on the image contents"
for f in "$APPDIR"/usr/bin/*; do
  is_elf "$f" || { echo "non-ELF file in usr/bin: $f" >&2; exit 1; }
done
if grep -rIl -e "/opt/freestyle" -e "/home/" -e "/root/" \
     "$APPDIR/AppRun" "$APPDIR/appenv.sh" "$APPDIR/usr/bin" 2>/dev/null | grep -q .; then
  echo "host-specific absolute paths found in the launcher files" >&2
  exit 1
fi

echo "== self-test inside the image"
QT_QPA_PLATFORM=offscreen "$APPDIR/AppRun" --self-test

if [ ! -x "$TOOL" ]; then
  echo "appimagetool is not extracted at $TOOL" >&2
  exit 1
fi

mkdir -p "$DIST"
rm -f "$OUT"
echo "== building AppImage"
ARCH=x86_64 "$TOOL" --no-appstream "$APPDIR" "$OUT"
test -s "$OUT" || { echo "appimagetool produced no AppImage" >&2; exit 1; }
chmod 0755 "$OUT"

# The interpreter's GLIBC symbols are not the image floor. Scan every bundled ELF and refuse to
# produce an artifact that needs a newer glibc than the documented value.
python3 scripts/check-appimage-glibc.py "$OUT" --floor "$GLIBC_FLOOR"

echo "appimage: $OUT ($(stat -c%s "$OUT") bytes), glibc floor $GLIBC_FLOOR"
