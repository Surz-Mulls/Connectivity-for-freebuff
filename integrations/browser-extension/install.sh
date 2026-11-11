#!/usr/bin/env bash
# Register the native-messaging host for Chromium-family browsers (user scope only).
# Idempotent: safe to re-run after native host updates (manifest syntax verified with bash -n in CI).
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOST_NAME="dev.continuity.handoff"
HOST_DIR="$HOME/.local/share/continuity/native-host"
HOST_SCRIPT="$HOST_DIR/continuity_native.py"
WRAPPER="$HOST_DIR/continuity-native-host"

mkdir -p "$HOST_DIR"
install -m 0755 "$HERE/native-host/continuity_native.py" "$HOST_SCRIPT"

# Chrome requires the manifest to name an executable; use a tiny wrapper so the shebang works
# even when the script is not directly executable on this filesystem.
cat > "$WRAPPER" <<'WEOF'
#!/usr/bin/env bash
WEOF
# Interpolated values must be written by the quoting-aware expansion below, not inside heredocs.
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
  cat > "$target/$HOST_NAME.json" <<JEOF
{
  "name": "$HOST_NAME",
  "description": "Continuity tab handoff",
  "path": "$WRAPPER",
  "type": "stdio",
  "allowed_origins": ["chrome-extension://REPLACE_WITH_EXTENSION_ID/"]
}
JEOF
  written=$((written + 1))
done

echo "native host installed in $written browser profile(s): $WRAPPER"
echo "extension directory: $HERE"
echo
echo "1. chrome://extensions -> Developer mode -> Load unpacked -> $HERE"
echo "2. copy the extension ID and replace REPLACE_WITH_EXTENSION_ID in:"
echo "   ~/.config/<browser>/NativeMessagingHosts/$HOST_NAME.json"
echo "3. reload the extension. The host is refused unless the ID matches."
echo
echo "Uninstall: $HERE/uninstall.sh"
