#!/usr/bin/env bash
# A corrupted appimagetool download must fail the builder before the file is executed.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
tmp="$(mktemp -d)"
created_venv=0
moved_tool=0
cleanup() {
  if [ "$created_venv" = 1 ]; then
    rm -rf "$ROOT/.venv"
  fi
  if [ "$moved_tool" = 1 ]; then
    rm -rf "$ROOT/.toolchain/appimage"
    if [ -d "$tmp/saved-appimage" ]; then
      mkdir -p "$ROOT/.toolchain"
      mv "$tmp/saved-appimage" "$ROOT/.toolchain/appimage"
    fi
  else
    rm -rf "$ROOT/.toolchain/appimage"
  fi
  rm -rf "$tmp"
}
trap cleanup EXIT

if [ -e "$ROOT/.toolchain/appimage" ]; then
  mv "$ROOT/.toolchain/appimage" "$tmp/saved-appimage"
  moved_tool=1
fi
if [ ! -x "$ROOT/.venv/bin/pip" ]; then
  mkdir -p "$ROOT/.venv/bin"
  printf '#!/bin/sh\nexit 0\n' > "$ROOT/.venv/bin/pip"
  printf '#!/bin/sh\nexit 0\n' > "$ROOT/.venv/bin/python"
  chmod 0755 "$ROOT/.venv/bin/pip" "$ROOT/.venv/bin/python"
  created_venv=1
fi

mkdir -p "$tmp/bin"
cat > "$tmp/bin/curl" <<'EOF'
#!/bin/sh
out=""
prev=""
for arg in "$@"; do
  if [ "$prev" = "-o" ]; then
    out="$arg"
  fi
  prev="$arg"
done
if [ -z "$out" ]; then
  echo "fake curl: no -o path" >&2
  exit 1
fi
printf '#!/bin/sh\necho TAMPERED_APPIMAGETOOL_RAN\nexit 99\n' > "$out"
chmod 0755 "$out"
exit 0
EOF
chmod 0755 "$tmp/bin/curl"

set +e
PATH="$tmp/bin:${PATH}" bash "$ROOT/scripts/build-appimage.sh" >"$tmp/log" 2>&1
rc=$?
set -e
if [ "$rc" -eq 0 ]; then
  echo "builder accepted a tampered appimagetool" >&2
  cat "$tmp/log" >&2
  exit 1
fi
if ! grep -q "appimagetool checksum mismatch" "$tmp/log"; then
  echo "builder failed ($rc) without a checksum mismatch:" >&2
  cat "$tmp/log" >&2
  exit 1
fi
if grep -q "TAMPERED_APPIMAGETOOL_RAN" "$tmp/log"; then
  echo "tampered appimagetool was executed" >&2
  exit 1
fi
echo "pinned appimagetool checksum rejected a tampered download (exit $rc)"
