#!/usr/bin/env bash
# Remove exactly the files install.sh created. Leaves everything else untouched.
set -euo pipefail
rm -f "$HOME/.local/share/kio/servicemenus/continuity-send.desktop"
rm -f "$HOME/.local/share/continuity/integrations/continuity-send.sh"
rmdir --ignore-fail-on-non-empty "$HOME/.local/share/continuity/integrations" 2>/dev/null || true
echo "removed Dolphin integration"
