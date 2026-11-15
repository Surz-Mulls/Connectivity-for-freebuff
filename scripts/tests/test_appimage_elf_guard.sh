#!/usr/bin/env bash
# The builder must refuse a python3.12 that is a shell wrapper.
# Production builds do not set CONTINUITY_APPIMAGE_PYTHON_OVERRIDE; they unpack the pinned
# CPython archive and apply the same ELF check to that binary. This hook only lets CI prove
# the rejection without downloading CPython.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

cat > "$tmp/python3.12" <<'EOF'
#!/bin/sh
exec /opt/freestyle/python/bin/python3 "$@"
EOF
chmod 0755 "$tmp/python3.12"

set +e
CONTINUITY_APPIMAGE_PYTHON_OVERRIDE="$tmp/python3.12" \
  bash "$ROOT/scripts/build-appimage.sh" >"$tmp/log" 2>&1
rc=$?
set -e
if [ "$rc" -eq 0 ]; then
  echo "builder accepted a non-ELF python3.12" >&2
  cat "$tmp/log" >&2
  exit 1
fi
if ! grep -q "not an ELF executable" "$tmp/log"; then
  echo "builder failed ($rc) without the ELF message:" >&2
  cat "$tmp/log" >&2
  exit 1
fi
if grep -q "freestyle/python/bin/python3: not found" "$tmp/log"; then
  echo "the wrapper was executed; the guard ran too late" >&2
  exit 1
fi
echo "elf-guard rejected a non-ELF python3.12 (exit $rc)"
