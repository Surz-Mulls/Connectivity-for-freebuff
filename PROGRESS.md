# PROGRESS — Continuity (Freebuff implementation of MASTER_AGENT_PROMPT_v6)

Newest entry on top. One entry per module. Status vocabulary: **implemented-and-tested**,
**implemented-unverified**, **blocked**, **not-implemented**.

---

## 2026-11-04 — continuation pass (v0.1.0-test.2 candidate, NOT published)

- **Automatic reconnect implemented** (§A): desktop `DeviceManager` bounded-backoff loop with
  jitter/reset/offline honesty + `ReconnectPolicy`/`ReconnectState` (tests in `test_reconnect.py`);
  Android side `ReconnectPolicy.kt` + schedule/reset/cancel in `ContinuityService` (5 JVM tests).
- Phase-0 §1 audit fixed: notification relay actually wired (`notify.action` reply/dismiss,
  secret-visibility redaction, own-package skip), `staging.setReadable(false,false)` removed,
  peer-validated-before-destructive finalisation, Android/Python pre-approval reservations, cap
  incl. pending, required `file.done` digest, per-transfer lock around finalisation, staging
  startup/shutdown cleanup, fail-closed `_same_uid`, constant-time token compare, real daemon
  shutdown path, CLI exit codes + unwrapped `--json` schema (docs/cli-schema.md), DeX honest
  capabilities + explicit serial choice, measured Android network/foreground/clipboard result,
  single canonical AppImage pipeline (fatal on failure, clean-checkout venv, pinned tool,
  measured-hash record), stale v1 labels fixed, fresh APK + 3 Linux assets rebuilt (see
  docs/VALIDATION_REPORT_v0.1.0-test.2.md for sizes/SHAs).
- **Distrobox/makepkg and device tests stay blocked** in this environment (no distrobox/podman,
  docker socket root-only, no phone/compositor); exact user steps in STATUS.json `needs_user`.
- Repeat test counts measured this pass: **Python 95 passed**, Android JVM tests ok (incl. new
  reconnect tests), `assembleDebug` ok, AppImage in-image self-test ok, `sha256sum -c` ok.
- CI not yet run; **nothing pushed, tagged or released** — awaiting approval for
  `v0.1.0-test.2`.

## 2026-10-31 — published

- Pre-release `v0.1.0-test.1` published at the tagged commit with APK, AppImage, Arch and
  portable archives, `SHA256SUMS`, `BUILD-MANIFEST.json` and `VALIDATION_REPORT.md`.
  Downloaded again from GitHub and verified: all four checksums OK, `prerelease=true`, `draft=false`.

## 2026-10-31 — v0.1.0-test.1 correction pass

- Protocol doc rewritten as normative v2 (TLS-bound transcript, no downgrade).
- Python receiver: canonical UUIDs, peer binding, metadata-verified resume, 4-transfer cap,
  hard-link no-clobber finalisation, no state left by rejected offers — `test_transfer_policy.py`.
- Android: per-transfer Accept/Reject notification (45 s), peer-bound `Incoming`, no-clobber
  finalisation, `files_auto_accept` opt-in default off.
- Token path now comes from `continuityd paths`; no `/tmp` fallback in the launcher.
- Packaging no longer needs a developer `.venv`; real self-contained AppImage (CPython + PySide6/Qt)
  with an in-image self-test; maintained `packaging/PKGBUILD`.
- Measured again: 82 Python tests, 17 JVM tests, APK + three Linux assets built.

## 2026-10-31 — audit pass (prompt v2)

- Re-scanned the tree at `59360a9`. Findings A–K reproduced in the current source.
- P0: removed `setReadable(false, false)` (C) and replaced the fixed-offset DER parser with a
  structural codec (D). 64 shared vectors + 17 JVM tests.
- P1: protocol v2 transcript with TLS-certificate binding, envelope version enforcement, real
  inbound + relay tests (A/B); Android transfer hardening (E); bearer token out of argv, 0600
  diagnostics, private runtime dir (G); Dolphin exec without a shell (H); `READ_MEDIA_IMAGES`
  removed (F); tracked bootstrap script, Gradle wrapper with checksum, LICENSE (J).
- Built `dist/continuity-android-debug.apk`; portable and Arch archives built and inspected.
  AppImage failed (no Qt/mksquashfs on this host) — see `artifacts/logs/appimage.log`.
- Pre-release **not** published: no GitHub API token in this environment.

## 2026-10-30T03:40Z — M6 branch pushed

- Branch `FreeBuff` pushed to `Surz-Mulls/Connectivity-for-freebuff` (`2505682`).
- 63 tests passing · theme drift clean · debug APK in `artifacts/android/`.
- Remaining work is hardware/compositor-bound (see `STATUS.json` → `needs_user`).

## 2026-10-30T00:00Z — M5 batch testing, docs and artifacts (in progress)

- **Daemon: 63 automated tests passing** (`pytest -q`): framing limits, identity, signature tamper,
  trust store, SAS symmetry, envelope validation, 13 hostile file names, URL scheme safety, real
  loopback TLS 1.3 pairing, declined pairing, pin mismatch, revoked identity, file round-trip with
  checksum, integrity failure, duplicate-name policy, clipboard policy + sensitive block, capability
  ceiling, untrusted-scope, IPC socket round-trip, IPC allowlist, HTTP bridge 401/200, diagnostics
  sections + redaction/export.
- **IPC**: Unix socket (0600 + `SO_PEERCRED`) and a loopback HTTP bridge guarded by a 0600 bearer
  token; both dispatch through one allowlisted command function. Schema in `docs/ipc-schema.md`.
- **Diagnostics**: `continuityctl diagnostics` writes sanitized JSON + Markdown, marks Android as
  `blocked` (never pass), redacts home paths, and never mutates state.
- **Android**: Kotlin + Compose app (identity, TLS server/client, SAS pairing, clipboard push,
  share target, file receive with SHA-256 verification, notification relay with RemoteInput replies,
  QS tile, privacy + diagnostics screens). APK build executed with the unprivileged toolchain;
  result recorded in `artifacts/`.
- **Desktop**: QML client with Devices/Transfers/DeX/Privacy/Diagnostics, generated `Theme.qml`.
  Not executed here — no Qt 6 installable without root; marked unverified.
- **Docs delivered**: `README.md`, `NOTICE.md`, `docs/feature-matrix.md`,
  `docs/batch-test-matrix.md`, `docs/install.md`, `docs/ipc-schema.md`,
  `docs/implementation-validation.md`, `docs/baseline-remote-input.md`.
- **Still open / needs the real machines**: device journeys B01–B12, DeX C01–C05, Qt/Quickshell
  D01–D05, KDE Connect baseline evidence (§0.4), branch push (credentials).

## 2026-10-29T09:30Z — M0 workspace + environment inspection (done)

- Cloned `Surz-Mulls/Connectivity-for-freebuff` (handoff pack only — **no product source existed**).
- Host: Ubuntu 24.04.5 LTS, x86_64, 2 vCPU, 3 GB RAM, **no root/sudo** (`no_new_privs`), so distro
  packages (Qt 6, scrcpy, android-tools) could not be installed.
- Fetched a user-space JDK 21 + Android cmdline-tools into `.toolchain/` (gitignored) so a real APK
  build was possible.
- Baseline KDE Connect remote-input reproduction is **blocked** (needs the laptop + phone); a
  procedure and evidence template live in `docs/baseline-remote-input.md`.

### Recheck pass (same day, before shipping)
- Re-ran: Python suite (**95 passed**), Android JVM tests (exit 0), `compileall` clean; scripts
  syntax-checked (`bash -n`).
- Found + fixed a real pre-existing bug: `integrations/browser-extension/install.sh` had doubled
  line-continuation backslashes, so the registration script never parsed at all; rewritten with an
  array loop and `bash -n` green.
- Broadened v7.1 audit source re-reads (transfers/integration/refactor layers), added
  `scripts/build-arch-distrobox.sh` (the reproducible user-side distrobox build path; impossible in
  this VM: no distrobox/podman, root-only docker socket, sudo prohibited by the sandbox).
- Cross-checked the `main`-branch (v6 handoff) deliverables against the branch: baseline
  remote-input doc, batch-test matrix, docs/research + design tokens, diagnostics CLI + QML page,
  `paths`/`--json` schema — all present; no missed item.
