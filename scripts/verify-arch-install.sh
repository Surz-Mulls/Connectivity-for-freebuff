#!/usr/bin/env bash
# Post-install checks for a package produced by packaging/PKGBUILD via makepkg.
# Any failure is fatal. This script does not accept the manually assembled
# dist/continuity-linux-x86_64.pkg.tar.zst layout archive.
set -euo pipefail

need() {
  command -v "$1" >/dev/null 2>&1 || { echo "missing command: $1" >&2; exit 1; }
}

need continuityd
need continuityctl
need continuity
test -x /usr/lib/continuity/run-continuity.sh
test -f /usr/share/applications/continuity.desktop
test -f /usr/lib/continuity/qml/Main.qml
test -d /usr/lib/continuity/continuityd

continuityd --help >/dev/null
continuityctl paths --json | python3 -c \
  'import json,sys; d=json.load(sys.stdin); assert {"api_config","runtime_dir","ipc"} <= d.keys()'

pacman -Q python python-cryptography python-zeroconf python-qrcode python-dbus-next qt6-declarative >/dev/null

qml_bin=""
for c in qml6 qml /usr/lib/qt6/bin/qml; do
  if command -v "$c" >/dev/null 2>&1 || [ -x "$c" ]; then
    qml_bin="$c"
    break
  fi
done
if [ -z "$qml_bin" ]; then
  echo "qt6-declarative did not provide a qml runtime" >&2
  exit 1
fi

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
cat > "$tmp/depcheck.qml" <<'QML'
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window
QtObject { Component.onCompleted: Qt.quit() }
QML
QT_QPA_PLATFORM=offscreen "$qml_bin" "$tmp/depcheck.qml"

spaced="$tmp/path with spaces"
mkdir -p "$spaced"
ln -s /usr/bin/continuity "$spaced/continuity"
set +e
msg="$("$spaced/continuity" 2>&1)"
rc=$?
set -e
if [ "$rc" -eq 0 ]; then
  echo "continuity exited 0 without a daemon" >&2
  exit 1
fi
printf '%s\n' "$msg" | grep -q "daemon is not running"

echo "verify-arch-install: ok (makepkg package, qml=$qml_bin)"
