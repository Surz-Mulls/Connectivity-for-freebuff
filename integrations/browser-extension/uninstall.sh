#!/usr/bin/env bash
# Remove the native-messaging host manifests (Chromium and Firefox/Zen) and helper. Leaves the
# unpacked extension alone (remove it from the browser yourself).
set -euo pipefail
HOST_NAME="dev.continuity.handoff"
for target in \
  "$HOME/.config/google-chrome/NativeMessagingHosts" \
  "$HOME/.config/chromium/NativeMessagingHosts" \
  "$HOME/.config/vivaldi/NativeMessagingHosts" \
  "$HOME/.config/BraveSoftware/Brave-Browser/NativeMessagingHosts"; do
  rm -f "$target/$HOST_NAME.json"
done
rm -f "$HOME/.mozilla/native-messaging-hosts/$HOST_NAME.json"
rm -rf "$HOME/.local/share/continuity/native-host"
echo "removed native-messaging host"
