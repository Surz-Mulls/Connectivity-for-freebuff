#!/usr/bin/env bash
# Launch the QML desktop client against a running daemon.
#
# Two rules matter here:
#  1. the bearer token never appears in argv (readable via /proc/<pid>/cmdline by other users);
#     QML receives only the path of the 0600 config file;
#  2. the path comes from the daemon itself (`continuityd paths`), never from a second
#     reconstruction of XDG rules in shell. The old `${XDG_RUNTIME_DIR:-/tmp}` fallback could point
#     the UI at a different directory than the daemon writes to.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

api_config_path() {
  if command -v continuityd >/dev/null 2>&1; then
    continuityd paths --json 2>/dev/null \
      | python3 -c 'import json,sys; print(json.load(sys.stdin)["api_config"])' && return 0
  fi
  local lib
  for lib in "$HERE/lib" "$HERE/../daemon"; do
    if [ -d "$lib/continuityd" ]; then
      PYTHONPATH="$lib${PYTHONPATH:+:$PYTHONPATH}" python3 -c \
        'from continuityd.config import api_config_path; print(api_config_path())' && return 0
    fi
  done
  return 1
}

if ! TOKEN_FILE="$(api_config_path)"; then
  echo "Cannot determine the daemon's API config path. Install or run continuityd, then retry." >&2
  exit 1
fi

if [ ! -r "$TOKEN_FILE" ]; then
  echo "The daemon is not running: no readable config at $TOKEN_FILE" >&2
  echo "Start it first: continuityd run" >&2
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
