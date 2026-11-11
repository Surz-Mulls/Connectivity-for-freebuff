#!/usr/bin/env bash
# Mocked tests for scripts/build-arch-distrobox.sh.
#
# No real distrobox, podman, pacman, makepkg, sudo or system change happens here: every external
# command is a fake on PATH that logs its arguments. These tests prove the wrapper's contract
# (create-time volume, --no-tty, reuse, missing-mount recovery, no sudoers rule, no root build,
# exit-code propagation, paths with spaces, heredoc execution). Real Distrobox integration is a
# separate, hardware/daemon-dependent check and is recorded as implemented-unverified.
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
SCRIPT="$ROOT/scripts/build-arch-distrobox.sh"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
BIN="$WORK/bin"
LOG="$WORK/calls.log"
STATE="$WORK/state"
PROJ="$WORK/project with spaces"
mkdir -p "$BIN" "$STATE"

FAILS=0
pass() { printf 'PASS %s\n' "$1"; }
fail() { printf 'FAIL %s\n' "$1" >&2; FAILS=$((FAILS + 1)); }

# ------------------------------------------------------------------ fakes
cat > "$BIN/distrobox" <<'FAKE'
#!/usr/bin/env bash
set -uo pipefail
printf 'CALL distrobox %s\n' "$*" >> "$FAKE_LOG"
sub="${1:-}"
[ $# -gt 0 ] && shift
case "$sub" in
  list)
    printf 'ID | NAME | STATUS | IMAGE\n'
    if [ -f "$FAKE_STATE/exists" ]; then
      printf 'abc | %s | Up | fake\n' "$FAKE_BOX"
    fi
    ;;
  create)
    touch "$FAKE_STATE/exists" "$FAKE_STATE/mount_ok"
    ;;
  enter)
    if [ "${1:-}" = "--no-tty" ]; then
      shift
    else
      printf 'ENTER_WITHOUT_NO_TTY\n' >> "$FAKE_LOG"
    fi
    box="${1:-}"
    shift || true
    [ "${1:-}" = "--" ] && shift
    printf 'ENTER box=%s cmd=%s\n' "$box" "${1:-}" >> "$FAKE_LOG"
    if [ "${1:-}" = "test" ]; then
      [ -f "$FAKE_STATE/mount_ok" ] && exit 0 || exit 1
    fi
    if [ "${1:-}" = "env" ]; then
      shift
      while [ $# -gt 0 ] && [[ "$1" == *=* ]]; do
        case "$1" in
          CONTINUITY_SRC=*) export CONTINUITY_SRC="$FAKE_PROJECT" ;;
          *) export "$1" ;;
        esac
        shift
      done
      exec "$@"
    fi
    exec "$@"
    ;;
  rm|stop)
    printf 'DESTRUCTIVE_CONTAINER_CALL\n' >> "$FAKE_LOG"
    ;;
esac
FAKE

cat > "$BIN/podman" <<'FAKE'
#!/usr/bin/env bash
printf 'CALL podman %s\n' "$*" >> "$FAKE_LOG"
FAKE

cat > "$BIN/pacman" <<'FAKE'
#!/usr/bin/env bash
printf 'CALL pacman %s\n' "$*" >> "$FAKE_LOG"
exit "${FAKE_PACMAN_FAIL:-0}"
FAKE

cat > "$BIN/sudo" <<'FAKE'
#!/usr/bin/env bash
printf 'CALL sudo %s\n' "$*" >> "$FAKE_LOG"
exec "$@"
FAKE

cat > "$BIN/makepkg" <<'FAKE'
#!/usr/bin/env bash
printf 'CALL makepkg %s (cwd=%s)\n' "$*" "$PWD" >> "$FAKE_LOG"
if [ "${FAKE_MAKEPKG_FAIL:-0}" != "0" ]; then
  exit "$FAKE_MAKEPKG_FAIL"
fi
: > continuity-0.1.0.test2-1-x86_64.pkg.tar.zst
FAKE
chmod +x "$BIN"/*

mkfixture() {
  rm -rf "$PROJ"
  mkdir -p "$PROJ/scripts" "$PROJ/packaging"
  cp "$SCRIPT" "$PROJ/scripts/build-arch-distrobox.sh"
  printf 'pkgname=continuity\n' > "$PROJ/packaging/PKGBUILD"
  cat > "$PROJ/scripts/prepare-candidate-pkgbuild.sh" <<'STUB'
#!/usr/bin/env bash
set -euo pipefail
mkdir -p "$1"
cat > "$1/PKGBUILD" <<'PKG'
_srcdir_name="continuity-candidate"
source=("continuity-candidate.tar.gz")
sha256sums=('0000000000000000000000000000000000000000000000000000000000000000')
PKG
STUB
  cat > "$PROJ/scripts/verify-arch-package.sh" <<'STUB'
#!/usr/bin/env bash
printf 'CALL verify-arch-package %s\n' "$*" >> "$FAKE_LOG"
STUB
  cat > "$PROJ/scripts/verify-arch-install.sh" <<'STUB'
#!/usr/bin/env bash
printf 'CALL verify-arch-install\n' >> "$FAKE_LOG"
STUB
  chmod +x "$PROJ/scripts/"*.sh
}

reset_state() {
  : > "$LOG"
  rm -rf "$STATE"
  mkdir -p "$STATE"
  rm -rf "$PROJ/dist"
}

run_wrapper() {
  local extra_path="${1:-$BIN}"
  FAKE_LOG="$LOG" FAKE_STATE="$STATE" FAKE_BOX=arch-build FAKE_PROJECT="$PROJ" \
    PATH="$extra_path:$BIN:$PATH" \
    bash "$PROJ/scripts/build-arch-distrobox.sh" > "$WORK/out" 2>&1
}

assert_rc() { [ "$1" -eq "$2" ] && pass "$3" || fail "$3 (rc=$1, wanted $2)"; }
assert_log() { grep -q -- "$1" "$LOG" && pass "$2" || fail "$2 (log lacks: $1)"; }
assert_no_log() { grep -q -- "$1" "$LOG" && fail "$2 (log has: $1)" || pass "$2"; }
assert_out() { grep -q -- "$1" "$WORK/out" && pass "$2" || fail "$2 (output lacks: $1)"; }

# ------------------------------------------------------------------ tests
mkfixture

if bash -n "$SCRIPT"; then pass "wrapper parses (bash -n)"; else fail "wrapper parses"; fi

if grep -q 'NOPASSWD' "$SCRIPT" || grep -q '/etc/sudoers' "$SCRIPT"; then
  fail "no persistent passwordless-sudo rule"
else
  pass "no persistent passwordless-sudo rule"
fi
if grep -q 'useradd' "$SCRIPT"; then fail "no builder user is created"; else pass "no builder user is created"; fi
if grep -q 'pacman -Syu' "$SCRIPT"; then pass "uses pacman -Syu"; else fail "uses pacman -Syu"; fi
if grep -v '^[[:space:]]*#' "$SCRIPT" | grep -qE 'pacman -Sy([^u]|$)'; then
  fail "no partial pacman -Sy"
else
  pass "no partial pacman -Sy"
fi
if grep -nE '^[[:space:]]*distrobox enter' "$SCRIPT" | grep -v -- '--no-tty' >/dev/null; then
  fail "every distrobox enter uses --no-tty"
else
  pass "every distrobox enter uses --no-tty"
fi
if grep -nE '^[[:space:]]*distrobox enter' "$SCRIPT" | grep -- '--volume' >/dev/null; then
  fail "no --volume is passed to distrobox enter"
else
  pass "no --volume is passed to distrobox enter"
fi

# fresh container: create with the right volume, then build
reset_state
run_wrapper
assert_rc $? 0 "fresh container: wrapper succeeds"
assert_log "distrobox create" "fresh container: create is called"
assert_log "--volume $PROJ:/mnt/continuity-src:rw" "fresh container: create uses the exact mount (path with spaces)"
assert_log "CALL makepkg" "fresh container: makepkg runs through the heredoc"
assert_log "CALL verify-arch-package" "fresh container: package metadata verified"
assert_log "CALL verify-arch-install" "fresh container: install verified"
assert_log "pacman -Syu" "fresh container: full package upgrade"
if [ -f "$PROJ/dist/makepkg/continuity-0.1.0.test2-1-x86_64.pkg.tar.zst" ]; then
  pass "fresh container: package copied to dist/makepkg"
else
  fail "fresh container: package copied to dist/makepkg"
fi
if grep -q 'ENTER_WITHOUT_NO_TTY' "$LOG"; then fail "fresh container: no enter without --no-tty"; else
  pass "fresh container: no enter without --no-tty"
fi

# reuse: existing container with a correct mount is not recreated
reset_state
touch "$STATE/exists" "$STATE/mount_ok"
run_wrapper
assert_rc $? 0 "existing container: wrapper succeeds"
assert_no_log "distrobox create" "existing container: not recreated"
assert_no_log "DESTRUCTIVE_CONTAINER_CALL" "existing container: never stopped or removed"

# missing mount: fail with recovery, do not delete the container
reset_state
touch "$STATE/exists"
run_wrapper
assert_rc $? 1 "missing mount: wrapper fails"
assert_out "distrobox rm" "missing mount: recovery instructions shown"
assert_no_log "distrobox create" "missing mount: container not recreated"
assert_no_log "DESTRUCTIVE_CONTAINER_CALL" "missing mount: container not removed"
assert_no_log "CALL makepkg" "missing mount: build not attempted"

# root refusal: fail clearly, never build
reset_state
mkdir -p "$WORK/rootbin"
cat > "$WORK/rootbin/id" <<'FAKE'
#!/usr/bin/env bash
if [ "${1:-}" = "-u" ]; then echo 0; exit 0; fi
exec /usr/bin/id "$@"
FAKE
chmod +x "$WORK/rootbin/id"
touch "$STATE/exists" "$STATE/mount_ok"
run_wrapper "$WORK/rootbin"
assert_rc $? 1 "root: build refused"
assert_out "refusing to build as root" "root: clear refusal message"
assert_no_log "CALL makepkg" "root: makepkg not executed"
rm -rf "$WORK/rootbin"

# exit-code propagation: a failing makepkg fails the wrapper with the same status
reset_state
touch "$STATE/exists" "$STATE/mount_ok"
export FAKE_MAKEPKG_FAIL=3
run_wrapper
assert_rc $? 3 "failing makepkg: status propagates"
unset FAKE_MAKEPKG_FAIL
assert_out "distrobox build failed (exit 3)" "failing makepkg: failure reported"

printf '\n%s test(s) failed\n' "$FAILS"
[ "$FAILS" -eq 0 ]
