#!/usr/bin/env bash
# Launch the QML desktop client against a running daemon.
# Only the *path* of the 0600 runtime token file is passed to QML, never the bearer token itself:
# command lines are visible in /proc/<pid>/cmdline to other local users, file permissions are not.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNTIME="${XDG_RUNTIME_DIR:-/tmp}/continuity"
TOKEN_FILE="$RUNTIME/http.token"

if [ ! -r "$TOKEN_FILE" ]; then
  echo "No daemon token at $TOKEN_FILE. Start the daemon first: continuityd run" >&2
  exit 1
fi

for candidate in qml6 qml /usr/lib/qt6/bin/qml pyside6-qml; do
  if command -v "$candidate" >/dev/null 2>&1; then
    exec "$candidate" "$HERE/qml/Main.qml" -- --api-config="$TOKEN_FILE"
  fi
done

cat >&2 <<'MSG'
No Qt 6 QML runtime found. Install one of:
  Arch:      sudo pacman -S qt6-declarative
  Debian:    sudo apt install qml6-module-qtquick-controls qml6-module-qtquick-layouts
  anywhere:  pip install PySide6-Essentials && use pyside6-qml
The daemon, CLI and Quickshell module work without it.
MSG
exit 1
