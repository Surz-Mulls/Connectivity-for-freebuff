#!/usr/bin/env bash
# Dolphin service-menu helper: send the selected files to the first paired phone.
# Uses only the allowlisted CLI; never builds a shell string from file names.
set -euo pipefail

CLI="${CONTINUITYCTL:-continuityctl}"

status_json="$("$CLI" status --json 2>/dev/null)" || {
  echo "Continuity: daemon is not running" >&2
  exit 1
}

fingerprint="$(printf '%s' "$status_json" | python3 -c '
import json, sys
state = json.load(sys.stdin)
devices = [d for d in state.get("devices", []) if d.get("state") == "connected"]
print(devices[0]["fingerprint"] if devices else "")
')"

if [ -z "$fingerprint" ]; then
  echo "Continuity: no connected phone. Pair one first (continuityctl pair begin)." >&2
  exit 2
fi

failed=0
for path in "$@"; do
  if ! "$CLI" send-file "$fingerprint" "$path" >/dev/null; then
    echo "Continuity: failed to send $(basename "$path")" >&2
    failed=1
  fi
done

if [ "$failed" -eq 0 ]; then
  notify-send --app-name Continuity "Sent to phone" "$# file(s)" 2>/dev/null || true
fi
exit "$failed"
