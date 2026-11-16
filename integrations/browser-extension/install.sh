#!/usr/bin/env bash
# Register the native-messaging host for Chromium-family browsers (user scope only).
# Idempotent: safe to re-run after native host updates (manifest syntax verified with bash -n in CI).
#
# The extension ID is not guessed and not left as a placeholder. manifest.json pins a public key;
# Chromium derives the extension ID from SHA-256 of that key. The same derivation is applied here
# so allowed_origins always names the ID Chromium will assign to this unpacked extension.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOST_NAME="dev.continuity.handoff"
HOST_DIR="$HOME/.local/share/continuity/native-host"
HOST_SCRIPT="$HOST_DIR/continuity_native.py"
WRAPPER="$HOST_DIR/continuity-native-host"
MANIFEST="$HERE/manifest.json"

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

echo "native host installed in $written browser profile(s): $WRAPPER"
echo "extension directory: $HERE"
echo "pinned extension ID: $EXTENSION_ID"
echo
echo "1. chrome://extensions -> Developer mode -> Load unpacked -> $HERE"
echo "2. the native-messaging manifests already allow chrome-extension://$EXTENSION_ID/"
echo "3. reload the extension. The host is refused unless the ID matches."
echo
echo "Uninstall: $HERE/uninstall.sh"
