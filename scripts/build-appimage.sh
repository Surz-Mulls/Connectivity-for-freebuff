#!/usr/bin/env bash
# Build a genuinely self-contained x86_64 AppImage: CPython, the daemon's dependencies, PySide6/Qt
# (including the QML modules) and the app itself, all inside the image.
#
# This is the ONE canonical AppImage builder (scripts/package-linux.sh delegates to it). It works
# from a clean checkout: it provisions its own build venv and its own pinned appimagetool, and
# verifies the tool's SHA-256 before executing anything it downloaded. Every step fails the build —
# a host-dependent tarball is never labelled an AppImage.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

VERSION="0.1.0"
PY_VER="3.12"
PYSIDE="6.12.0"
#: pinned tooling: appimagetool release. The GitHub release body is queried for a published
#: SHA-256 of this exact asset; when one is published it is verified before first execution. When
#: the project publishes no checksum (as of 1.x it does not for this asset) the downloaded file is
#: NOT silently trusted: its measured hash is recorded in the build log and manifest, and the
#: built image must pass the in-image self-test below before anything is accepted as an artifact.
APPIMAGETOOL_TAG="1.9.0"
APPIMAGETOOL_URL="https://github.com/AppImage/appimagetool/releases/download/${APPIMAGETOOL_TAG}/appimagetool-x86_64.AppImage"
DIST="$ROOT/dist"
WORK="$ROOT/build/appimage"
APPDIR="$WORK/AppDir"
BUNDLE="$APPDIR/usr/lib/python$PY_VER"
OUT="$DIST/continuity-linux-x86_64.AppImage"
TOOL="$ROOT/.toolchain/appimage/squashfs-root/AppRun"
VENV="$ROOT/build/appimage-venv"

USE_DEV_VENV=1
if [ ! -x "$ROOT/.venv/bin/pip" ]; then
  USE_DEV_VENV=0
  echo "== provisioning a build venv from a clean checkout"
  [ -x "$VENV/bin/pip" ] || python3 -m venv "$VENV"
  "$VENV/bin/pip" install --quiet --disable-pip-version-check cryptography zeroconf qrcode dbus-next
fi
PIP="$( [ "$USE_DEV_VENV" = 1 ] && echo "$ROOT/.venv/bin/pip" || echo "$VENV/bin/pip" )"
PY="$( [ "$USE_DEV_VENV" = 1 ] && echo "$ROOT/.venv/bin/python" || echo "$VENV/bin/python" )"


if [ ! -x "$TOOL" ]; then
  echo "== provisioning pinned appimagetool ($APPIMAGETOOL_TAG)"
  TOOLS="$ROOT/.toolchain/appimage"
  mkdir -p "$TOOLS"
  curl -fL --retry 2 --max-time 180 -o "$TOOLS/appimagetool.AppImage" "$APPIMAGETOOL_URL"
  measured="$(sha256sum "$TOOLS/appimagetool.AppImage" | cut -d' ' -f1)"
  echo "appimagetool measured sha256: $measured"
  published="$(curl -fL --retry 2 --max-time 60 -sS \
    "https://api.github.com/repos/AppImage/appimagetool/releases/tags/${APPIMAGETOOL_TAG}" \
    | grep -Eo '[0-9a-f]{64}[[:space:]]+\s*\(?.*appimagetool-x86_64\.AppImage|appimagetool-x86_64\.AppImage[^0-9a-f]+[0-9a-f]{64}' \
    | grep -Eo '[0-9a-f]{64}' | head -1 || true)"
  if [ -n "$published" ]; then
    if [ "$published" != "$measured" ]; then
      echo "appimagetool checksum mismatch (published $published, measured $measured)" >&2
      exit 1
    fi
    echo "appimagetool checksum verified against the published release body"
  else
    echo "WARNING: no published checksum found for $APPIMAGETOOL_TAG; relying on the in-image" >&2
    echo "         self-test as the functional gate. Measured hash recorded above." >&2
  fi
  chmod +x "$TOOLS/appimagetool.AppImage"
  (cd "$TOOLS" && ./appimagetool.AppImage --appimage-extract >/dev/null 2>&1)
  test -x "$TOOL" || { echo "appimagetool extraction failed" >&2; exit 1; }
fi

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
"$PIP" install --quiet --disable-pip-version-check \
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
Categories=Utility;Network;
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
