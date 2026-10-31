#!/usr/bin/env bash
# Install the Dolphin "Send to phone" service menu for the current user only.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_DIR="$HOME/.local/share/kio/servicemenus"
SUPPORT_DIR="$HOME/.local/share/continuity/integrations"

mkdir -p "$TARGET_DIR" "$SUPPORT_DIR"
install -m 0755 "$HERE/continuity-send.sh" "$SUPPORT_DIR/continuity-send.sh"
# Substitute the absolute helper path instead of executing through `sh -c`, which is unsafe for
# filenames containing quotes, `$()` or `;`.
escaped="$(printf '%s' "$SUPPORT_DIR/continuity-send.sh" | sed 's/[&|\\]/\\&/g')"
sed "s|@HELPER@|$escaped|g" "$HERE/continuity-send.desktop" > "$TARGET_DIR/continuity-send.desktop"
chmod 0644 "$TARGET_DIR/continuity-send.desktop"

echo "installed: $TARGET_DIR/continuity-send.desktop"
echo "helper:    $SUPPORT_DIR/continuity-send.sh"
echo "If 'continuityctl' is not on PATH, set CONTINUITYCTL in your environment or symlink it into ~/.local/bin."
echo "Remove with: $HERE/uninstall.sh"
