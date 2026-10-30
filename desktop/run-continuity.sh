#!/usr/bin/env bash
# Launch the QML desktop client against a running daemon.
# The bearer token is read from the 0600 runtime file and passed as an argument; it is never
# written into the repository or into a log.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNTIME="${XDG_RUNTIME_DIR:-/tmp}/continuity"
TOKEN_FILE="$RUNTIME/http.token"

if [ ! -r "$TOKEN_FILE" ]; then
  echo "No daemon token at $TOKEN_FILE. Start the daemon first: continuityd run" >&2
  exit 1
fi

read -r PORT TOKEN < <(python3 - "$TOKEN_FILE" <<'PY'
import json, sys
data = json.load(open(sys.argv[1]))
print(data["port"], data["token"])
PY
)

for candidate in qml6 qml /usr/lib/qt6/bin/qml pyside6-qml; do
  if command -v "$candidate" >/dev/null 2>&1; then
    exec "$candidate" "$HERE/qml/Main.qml" -- --api-port="$PORT" --api-token="$TOKEN"
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
