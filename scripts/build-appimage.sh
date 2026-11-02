#!/usr/bin/env bash
# Build a genuinely self-contained x86_64 AppImage: CPython, the daemon's dependencies, PySide6/Qt
# (including the QML modules) and the app itself, all inside the image.
#
# This is deliberately strict: every step fails the build. A host-dependent tarball is never
# labelled an AppImage.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

VERSION="0.1.0"
PY_VER="3.12"
PYSIDE="6.12.0"
DIST="$ROOT/dist"
WORK="$ROOT/build/appimage"
APPDIR="$WORK/AppDir"
BUNDLE="$APPDIR/usr/lib/python$PY_VER"
OUT="$DIST/continuity-linux-x86_64.AppImage"
TOOL="$ROOT/.toolchain/appimage/squashfs-root/AppRun"

rm -rf "$WORK"
mkdir -p "$APPDIR/usr/bin" "$BUNDLE/site-packages" "$APPDIR/usr/share/applications" \
         "$APPDIR/usr/share/icons/hicolor/scalable/apps"

echo "== staging CPython"
PYTHON_BIN="$(readlink -f "$(command -v python$PY_VER)")"
cp "$PYTHON_BIN" "$APPDIR/usr/bin/python$PY_VER"
mkdir -p "$APPDIR/usr/lib"
for lib in /usr/lib/x86_64-linux-gnu/libpython$PY_VER.so.1.0 /usr/lib/libpython$PY_VER.so.1.0 \
           "/usr/lib/x86_64-linux-gnu/libpython$PY_VER.so"; do
  if [ -f "$lib" ]; then cp "$lib" "$APPDIR/usr/lib/"; break; fi
done
test -e "$APPDIR/usr/lib/libpython$PY_VER.so.1.0" || {
  echo "libpython$PY_VER not found; cannot bundle CPython" >&2; exit 1; }
cp -a "/usr/lib/python$PY_VER/." "$BUNDLE/"
rm -rf "$BUNDLE/site-packages" "$BUNDLE/dist-packages" "$BUNDLE/lib2to3" "$BUNDLE/test"
mkdir -p "$BUNDLE/site-packages"

echo "== installing runtime dependencies into the image (PySide6 $PYSIDE)"
"$ROOT/.venv/bin/pip" install --quiet --disable-pip-version-check \
  --target "$BUNDLE/site-packages" \
  "cryptography>=42" "zeroconf>=0.132" "qrcode>=7.4" "dbus-next>=0.2.3" "PySide6-Essentials==$PYSIDE"

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

.venv/bin/python - "$APPDIR/usr/share/icons/hicolor/scalable/apps/continuity.svg" <<'PY'
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
Categories=Utility;Network;
Terminal=false
X-AppImage-Version=0.1.0
DESKTOP

chmod -R a+rX "$APPDIR"
chmod a+rx "$APPDIR/AppRun"

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
echo "appimage: $OUT ($(stat -c%s "$OUT") bytes)"
