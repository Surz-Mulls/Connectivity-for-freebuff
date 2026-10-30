# Continuity

A local-first, privacy-first bridge between an **Android phone (Android 15 / HyperOS)** and a
**Linux desktop (Hyprland + Quickshell)**: trusted pairing, clipboard, files, notifications,
handoff, find/ring, a live status API for Quickshell — plus a first-class **DeX Workspace** mode.

There is **no cloud account, no relay, no telemetry**. Everything runs on the LAN with pinned
device identities, and every UI is a client of one daemon API.

This repository is the implementation of `MASTER_AGENT_PROMPT_v6.md` (the handoff prompt is kept at
the repository root). The research pack that the prompt references is preserved unmodified in
[`docs/research/`](docs/research/README.md), with upstream commit SHAs in `docs/research/REPO_SHAS.tsv`.

---

## What is here

| Component | Path | Status |
|---|---|---|
| Daemon (protocol, pairing, clipboard, files, notifications, diagnostics, DeX supervision) | `daemon/` | implemented, 63 automated tests passing |
| Wire protocol specification v1 | `protocol/PROTOCOL.md` | normative |
| Local IPC: Unix socket + loopback HTTP bridge, schema | `daemon/continuityd/ipc.py`, `docs/ipc-schema.md` | implemented + tested |
| CLI (`continuityd`, `continuityctl`) | `daemon/continuityd/cli.py` | implemented |
| Desktop UI (Qt 6 / QML) | `desktop/qml/` | QML sources; runtime not installed on the build host |
| Quickshell status panel | `integrations/quickshell/` | sample module, unverified on a live shell |
| Android app (Kotlin + Compose) | `android/` | built to a debug APK (see `artifacts/`) |
| Browser tab handoff (Chromium/Vivaldi MV3 + native host) | `integrations/browser-extension/` | implemented |
| Dolphin "Send to phone" service menu | `integrations/dolphin/` | implemented |
| Design tokens + generators (QML + Compose) | `design/tokens.json`, `scripts/generate-theme.py` | implemented, drift-checked |

Full per-feature status, including what is blocked and why: **[`docs/feature-matrix.md`](docs/feature-matrix.md)**.
Test matrix: **[`docs/batch-test-matrix.md`](docs/batch-test-matrix.md)**.

## Quick start (desktop)

```bash
python3 -m venv .venv
.venv/bin/pip install -e daemon[dev]        # cryptography, zeroconf, qrcode, dbus-next
.venv/bin/continuityd run                   # foreground daemon; writes IPC socket + state
```

In another terminal:

```bash
.venv/bin/continuityctl status              # full state snapshot
.venv/bin/continuityctl pair begin          # pairing URI + QR SVG path
.venv/bin/continuityctl devices
.venv/bin/continuityctl diagnostics         # sanitized JSON + Markdown report
.venv/bin/continuityctl dex probe           # scrcpy/adb capability report
```

Launch the Qt UI (needs a Qt 6 QML runtime — see `docs/install.md`):

```bash
desktop/run-continuity.sh
```

## Quick start (Android)

```bash
cd android && ./gradlew :app:assembleDebug     # or use the toolchain script below
adb install -r app/build/outputs/apk/debug/app-debug.apk
```

Then: open the app → **Connection** → enter the host/port shown by `continuityctl pair begin`
(the QR payload contains the desktop fingerprint) → both devices must show the same **6 digits and
4 symbols** → approve on both sides. Pairing is refused unless both confirmations match.

Android permissions the app asks for, and what each is for, are listed in
[`docs/install.md`](docs/install.md). Notification access and "Allow restricted settings" are
user-initiated; the app never toggles developer settings or app-ops through ADB.

## Security model (short version)

* Each device generates a **self-signed ECDSA P-256 certificate** on first run; its SHA-256
  fingerprint *is* the identity.
* TCP + **TLS 1.3** gives confidentiality. Peer authentication is a **pinned fingerprint** plus an
  ECDSA signature over both nonces — the SSH host-key model. A self-signed certificate cannot be
  chain-verified, so TLS alone could never establish trust.
* First pairing additionally derives a **SAS** (6 digits + 4 emoji) from both fingerprints and both
  fresh nonces. Both humans must confirm the same code.
* Unpaired peers may only exchange `pair.*` and are disconnected after 60 s. Capabilities are a
  ceiling, privacy settings are the grant. A peer can never change this device's privacy policy.
* No arbitrary shell execution, no unauthenticated ADB, no world-writable device nodes, no silent
  camera/mic/screen activation. DeX is opt-in and drives allowlisted `scrcpy`/`adb` argv only.

Details: `protocol/PROTOCOL.md` §1, §6, §9 and `docs/feature-matrix.md` (security section).

## Repository layout

```
daemon/       Python 3.11+ backend (asyncio, TLS, mDNS, IPC, diagnostics, DeX supervision)
protocol/     normative wire protocol
desktop/      Qt 6 / QML client (+ generated Theme.qml)
android/      Kotlin + Jetpack Compose client (+ generated Theme.kt)
design/       canonical tokens (Catppuccin Mocha/Latte) + concept reference
integrations/ Quickshell module, browser extension, Dolphin service menu
scripts/      theme generation, environment/build helpers
docs/         research provenance, feature matrix, test matrix, IPC schema, install guide
artifacts/    built APK, checksums, diagnostics reports, build logs
```

## Building

```bash
# daemon tests
cd daemon && ../.venv/bin/python -m pytest -q

# theme drift check
.venv/bin/python scripts/generate-theme.py --check

# Android APK (unprivileged toolchain, no root needed)
./scripts/build-android.sh
```

`scripts/build-android.sh` downloads a JDK 21 and the Android command-line tools into
`.toolchain/` (gitignored) if they are missing, then runs the Gradle build and copies the APK plus a
SHA-256 checksum into `artifacts/android/`. It never touches system directories and never writes a
signing key.

## Known limitations (honest)

* Everything phone-side and compositor-side is **unverified on the target hardware**: the cloud
  build host has no Mi 12, no Hyprland session and no Quickshell. Those rows are marked
  `not_verified` / `blocked` in `docs/feature-matrix.md`, never "passing".
* The desktop QML UI was authored here but **not executed** in this environment (no Qt 6 package
  installable without root). The daemon, CLI, IPC and Android build were executed.
* Folder sync, camera capture/scan, media control, call/SMS bridging and second-screen output are
  specified in the prompt but **not implemented in this build**; each returns an explicit error
  rather than a fake control. See the matrix for the exact state and the reason.
* KDE Connect's remote-input failure (`§0.4` of the prompt) could not be reproduced here; the
  evidence-collection procedure is in `docs/baseline-remote-input.md` and is marked blocked.

## Licence

GPL-3.0-only for this repository. Third-party components, their licences and the upstream projects
that informed the design are listed in [`NOTICE.md`](NOTICE.md). No code was copied from
proprietary or unlicensed projects.
