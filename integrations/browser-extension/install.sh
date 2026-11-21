#!/usr/bin/env bash
# Register the native-messaging host for Chromium-family browsers and Firefox/Zen (user scope).
# Idempotent: safe to re-run after native host updates (manifest syntax verified with bash -n in CI).
#
# Chromium: manifest.json pins a public key; Chromium derives the extension ID from SHA-256 of that
# key. The same derivation is applied here so allowed_origins names the ID Chromium will assign.
# Firefox/Zen: the ID is the declared browser_specific_settings.gecko.id, and Firefox requires the
# native host manifest to use allowed_extensions instead of allowed_origins. The Chromium key
# derivation is deliberately not reused for the Firefox manifest.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOST_NAME="dev.continuity.handoff"
HOST_DIR="$HOME/.local/share/continuity/native-host"
HOST_SCRIPT="$HOST_DIR/continuity_native.py"
WRAPPER="$HOST_DIR/continuity-native-host"
MANIFEST="$HERE/manifest.json"
FIREFOX_DIR="$HOME/.mozilla/native-messaging-hosts"

command -v python3 >/dev/null 2>&1 || {
  echo "python3 is required to derive the pinned extension ID." >&2
  exit 1
}

EXTENSION_ID="$(
  python3 - "$MANIFEST" <<'PY'
import base64
import hashlib
import json
import sys

path = sys.argv[1]
try:
    manifest = json.loads(open(path, encoding="utf-8").read())
except (OSError, json.JSONDecodeError) as exc:
    raise SystemExit(f"cannot read {path}: {exc}")
key = str(manifest.get("key", "")).strip()
if not key:
    raise SystemExit("manifest.json has no pinned extension key")
try:
    der = base64.b64decode(key, validate=True)
except ValueError as exc:
    raise SystemExit(f"manifest.json key is not valid base64: {exc}")
digest = hashlib.sha256(der).hexdigest()[:32]
# Chromium maps each hex nibble 0-f to a-p.
print("".join(chr(ord("a") + int(nibble, 16)) for nibble in digest))
PY
)"

case "$EXTENSION_ID" in
  [a-p][a-p][a-p][a-p]*) ;;
  *)
    echo "derived extension ID is not a 32-character Chromium ID: $EXTENSION_ID" >&2
    exit 1
    ;;
esac

GECKO_ID="$(
  python3 - "$MANIFEST" <<'PY'
import json
import sys

path = sys.argv[1]
try:
    manifest = json.loads(open(path, encoding="utf-8").read())
except (OSError, json.JSONDecodeError) as exc:
    raise SystemExit(f"cannot read {path}: {exc}")
gecko_id = str(
    manifest.get("browser_specific_settings", {}).get("gecko", {}).get("id", "")
).strip()
if not gecko_id or "@" not in gecko_id:
    raise SystemExit("manifest.json has no pinned browser_specific_settings.gecko.id")
print(gecko_id)
PY
)"

mkdir -p "$HOST_DIR"
install -m 0755 "$HERE/native-host/continuity_native.py" "$HOST_SCRIPT"

# Chrome requires the manifest to name an executable; use a tiny wrapper so the shebang works
# even when the script is not directly executable on this filesystem.
{
  printf '#!/usr/bin/env bash\n'
  printf 'exec python3 %q "$@"\n' "$HOST_SCRIPT"
} > "$WRAPPER"
chmod 0755 "$WRAPPER"

targets=(
  "$HOME/.config/google-chrome/NativeMessagingHosts"
  "$HOME/.config/chromium/NativeMessagingHosts"
  "$HOME/.config/vivaldi/NativeMessagingHosts"
  "$HOME/.config/BraveSoftware/Brave-Browser/NativeMessagingHosts"
)

written=0
for target in "${targets[@]}"; do
  mkdir -p "$target"
  python3 - "$target/$HOST_NAME.json" "$HOST_NAME" "$WRAPPER" "$EXTENSION_ID" <<'PY'
import json
import sys

path, name, wrapper, extension_id = sys.argv[1:]
payload = {
    "name": name,
    "description": "Continuity tab handoff",
    "path": wrapper,
    "type": "stdio",
    "allowed_origins": [f"chrome-extension://{extension_id}/"],
}
with open(path, "w", encoding="utf-8") as fh:
    json.dump(payload, fh, indent=2)
    fh.write("\n")
PY
  written=$((written + 1))
done

# Firefox/Zen speaks the same stdio protocol but uses a different allow-list key and the declared
# Gecko ID. Never put the Chromium key-derived ID in this manifest.
mkdir -p "$FIREFOX_DIR"
python3 - "$FIREFOX_DIR/$HOST_NAME.json" "$HOST_NAME" "$WRAPPER" "$GECKO_ID" <<'PY'
import json
import sys

path, name, wrapper, gecko_id = sys.argv[1:]
payload = {
    "name": name,
    "description": "Continuity tab handoff",
    "path": wrapper,
    "type": "stdio",
    "allowed_extensions": [gecko_id],
}
with open(path, "w", encoding="utf-8") as fh:
    json.dump(payload, fh, indent=2)
    fh.write("\n")
PY

echo "native host installed: $WRAPPER"
echo "Chromium-family manifests: $written profile(s); extension ID: $EXTENSION_ID"
echo "Firefox/Zen manifest: $FIREFOX_DIR/$HOST_NAME.json; allowed extension: $GECKO_ID"
echo "extension directory: $HERE"
echo
echo "Chromium: chrome://extensions -> Developer mode -> Load unpacked -> $HERE"
echo "Firefox/Zen: about:debugging#/runtime/this-firefox -> This Firefox ->"
echo "  Load Temporary Add-on -> select $HERE/manifest.json"
echo "Chromium reloads the extension to pick up this host; the host is refused unless the ID matches."
echo
echo "Uninstall: $HERE/uninstall.sh"
