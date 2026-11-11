# PROGRESS — Continuity (Freebuff implementation of MASTER_AGENT_PROMPT_v6)

Newest entry on top. One entry per module. Status vocabulary: **implemented-and-tested**,
**implemented-unverified**, **blocked**, **not-implemented**.

---

## 2026-11-09 — Grok review fixes (release still untouched)

Branch `Grok` is cut from `FreeBuff` `36c46a3efc09e828b320b576f6176cecdf098916`.
`main`, `FreeBuff`, and the published `v0.1.0-test.2` release are not modified.

- Python: `python -m pytest daemon/tests -q` from the repo root and
  `python -m pytest -q` from `daemon/` both passed **95** tests
  (2026-11-09, local CPython 3.12). `python -m continuityd.cli --help` and
  `continuityd --help` both succeeded. This is not a GitHub Actions result.
- Linux CI installs `desktop-file-utils`, `file`, `curl`, `ca-certificates`,
  `libfuse2t64` and `zstd` explicitly. Application `.desktop` files are validated
  with `desktop-file-validate`. A missing tool fails the build. The Dolphin file
  stays a KDE `Type=Service` template; desktop-file-utils rejects that type, so
  it is checked as a template rather than claimed to pass the freedesktop validator.
- Distrobox remains optional. The project mount is set only on `distrobox create`.
  `distrobox enter` is not passed `--volume`. An existing container without the
  mount is not deleted; the script prints recovery steps and exits.
- `packaging/PKGBUILD` stays pinned to the `v0.1.0-test.2` tag archive and its
  measured SHA-256. Candidate builds use `scripts/prepare-candidate-pkgbuild.sh`,
  which `git archive`s `HEAD` and refuses a recipe that still points at the tag.
- makepkg itself was **not** executed in this environment (no Docker, no Distrobox,
  privilege drop blocked). The `arch-makepkg` CI job is what has to prove it.
- Device journeys stay **implemented-unverified** or **blocked**. Nothing here was
  run on a Mi 12, HyperOS, Hyprland, Quickshell, Dolphin, or an Arch desktop.

## 2026-11-08 — post-release repair (branch `Grok`, release not mutated)

v0.1.0-test.2 **is published** (2026-11-05T06:20:42Z, tag `8db808a7c70513f545f1eb8656579911ce4c59b1`).
The previous `STATUS.json` still said it was unpublished; that file was wrong, not the release.

- CI on the tag was red: `python -m pytest daemon/tests` could not import `tests.test_transfer_policy`
  (pytest importlib mode from the repo root), and the linux job died because `desktop-file-validate`
  was not installed. Both are fixed on `Grok`. Tests were not deleted or weakened.
- Published asset ledger (re-downloaded, `sha256sum`, matches GitHub digests and `SHA256SUMS`):
  APK `3c4f37cf…8406` (same as the old report), AppImage `91de5e55…75f4`, manual Arch archive
  `8b4248b2…24cd`, portable `57a89e3e…269c`. The Linux mismatch is a publish-time rebuild
  (`builddate` 2026-11-05T06:19:30Z), not a corrupt APK. The published `.pkg.tar.zst` is **not**
  makepkg output (no `.BUILDINFO` / `.MTREE`).
- `packaging/PKGBUILD` now sources the v0.1.0-test.2 tag archive with sha256
  `aa817ab138cca16efecb15f59def0cfe59845fad852c0e989b015f69ed1e3698`.
  `scripts/build-arch-distrobox.sh` bind-mounts the repo at `/mnt/continuity-src`, always installs
  the build packages, and treats verify failures as fatal. CI job `arch-makepkg` runs `makepkg`
  in a clean `archlinux` container. The manual archive from `scripts/package-linux.sh` stays a
  separate artifact.
- Hardware, recorded only at the level of evidence:
  - B01–B07: **implemented-unverified**, device runs **blocked** (no Mi 12 / HyperOS here).
  - Wi-Fi reconnect and sleep/wake: **implemented-unverified** (policy unit tests only).
  - Notification reply and dismissal: **implemented-unverified**.
  - Quickshell and Dolphin on Hyprland: **implemented-unverified**, live session **blocked**.
  - AppImage on Arch from a path with spaces: **not run on Arch**.
  - KDE Connect remote-input baseline: **blocked**.
  - DeX journeys: **implemented-unverified**; native desktop mode on Android 15: **not-implemented**.
- No tag, no release asset, and no edit to `main` or the existing release.

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

## Shipped — v0.1.0-test.2
Published https://github.com/Surz-Mulls/Connectivity-for-freebuff/releases/tag/v0.1.0-test.2
(prerelease, tag at `8db808a`). Assets uploaded: debug APK, AppImage, Arch `.tar.zst`, portable
`.tar.zst`, `SHA256SUMS`, `BUILD-MANIFEST.json`, validation report. **Every asset was re-downloaded
from the release URL and its SHA-256 was re-verified.** `main` and `v0.1.0-test.1` untouched.
