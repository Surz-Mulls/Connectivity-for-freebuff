# Implementation validation (dated, evidence-based)

This file is the implementation-side counterpart to the research pack in `docs/research/`. The
research reports there were produced from source reading only and are **not** edited here; this is a
separate, dated record of what the builder actually did.

## 2026-10-29/30 — cloud build host

Environment: Ubuntu 24.04.5 LTS, kernel 6.1 (container), x86_64, 2 vCPU, 3 GB RAM, 10 GB free,
**unprivileged** (`no_new_privs`; `sudo` cannot run). Python 3.12.3, Node 24.21, gcc 13. No JDK,
Gradle, Qt 6, Rust, `adb`, `scrcpy` or `kdeconnect` preinstalled.

### Executed

| Check | Command | Result |
|---|---|---|
| Daemon test suite | `cd daemon && ../.venv/bin/python -m pytest -q` | **63 passed** |
| Theme generation | `.venv/bin/python scripts/generate-theme.py` | generated `desktop/qml/Theme.qml` + Android `ui/Theme.kt` |
| Theme drift | `scripts/generate-theme.py --check` | no drift |
| Android toolchain | JDK 21 + cmdline-tools + `platforms;android-35` + `build-tools;35.0.0` in `.toolchain/` | installed without root |
| Android APK | `gradle :app:assembleDebug` | see the result recorded in `artifacts/` and the final report |

### Not executed (and why)

| Check | Blocker |
|---|---|
| Real device pairing/reconnect/clipboard/files/notifications | no Mi 12, no ADB access from the cloud host |
| DeX / scrcpy sessions | `adb` and `scrcpy` are not installable without root; no device |
| Qt 6 QML runtime | no Qt 6 packages installable without root (PySide6 exists only as a dev fallback) |
| Quickshell module | no Hyprland/Quickshell session |
| Dolphin service menu | no KDE/Dolphin session |
| KDE Connect remote-input baseline | needs the real laptop + phone; procedure in `docs/baseline-remote-input.md` |
| PipeWire/v4l2loopback webcam path | not implemented in this build; would need kernel modules (root) |

### Corrections made against the research pack while building

* **Backend language.** The prompt mandates Qt 6/QML for the desktop UI and Kotlin/Compose for
  Android but does not mandate a Rust daemon. Linux Link's Rust daemon cannot be built here (no Rust,
  no root) and would have produced zero runnable evidence. The daemon is Python 3.11+ (asyncio,
  stdlib `ssl` with TLS 1.3, `cryptography`). The protocol contract from prompt §4B-Q is unchanged,
  and the CLI, QML UI and Quickshell module all consume the same documented API.
* **TLS authentication.** Self-signed certificates cannot be chain-verified, so Python's TLS layer
  is used for confidentiality only. Peer authenticity is a pinned fingerprint plus an ECDSA signature
  over both nonces (`protocol/PROTOCOL.md` §1, §4). This is deliberately documented rather than
  presented as mutual TLS.
* **Discovery** uses `_continuity._tcp` and is advisory; trust always comes from the pin.
* **Scope honesty.** Features that could not be implemented truthfully (folder sync, camera capture,
  media control, call/SMS bridge, webcam, second screen, Quick Share, Shevery modules) return explicit
  errors and are marked `not-implemented` in `docs/feature-matrix.md` instead of receiving stub
  controls.
