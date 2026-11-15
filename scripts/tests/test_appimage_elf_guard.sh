#!/usr/bin/env bash
# Proves scripts/build-appimage.sh refuses a python3.12 that is a shell wrapper.
# This is not an AppImage build and does not execute appimagetool.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
tmp="$(mktemp -d)"
created_tool=0
created_venv=0
cleanup() {
  rm -rf "$tmp"
  if [ "$created_tool" = 1 ]; then
    rm -rf "$ROOT/.toolchain/appimage"
  fi
  if [ "$created_venv" = 1 ]; then
    rm -rf "$ROOT/.venv"
  fi
  rm -rf "$ROOT/build/appimage"
}
trap cleanup EXIT

mkdir -p "$tmp/bin"
cat > "$tmp/bin/python3.12" <<'EOF'
#!/bin/sh
exec /opt/freestyle/python/bin/python3 "$@"
EOF
chmod 0755 "$tmp/bin/python3.12"

tool="$ROOT/.toolchain/appimage/squashfs-root/AppRun"
if [ ! -e "$tool" ]; then
  mkdir -p "$(dirname "$tool")"
  printf '#!/bin/sh\nexit 0\n' > "$tool"
  chmod 0755 "$tool"
  created_tool=1
fi
if [ ! -x "$ROOT/.venv/bin/pip" ]; then
  mkdir -p "$ROOT/.venv/bin"
  printf '#!/bin/sh\nexit 0\n' > "$ROOT/.venv/bin/pip"
  printf '#!/bin/sh\nexit 0\n' > "$ROOT/.venv/bin/python"
  chmod 0755 "$ROOT/.venv/bin/pip" "$ROOT/.venv/bin/python"
  created_venv=1
fi

set +e
PATH="$tmp/bin:${PATH}" bash "$ROOT/scripts/build-appimage.sh" >"$tmp/log" 2>&1
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
