# Claude Research Patch Notes — Continuity + Android-Dex (v4 → v5; carried into v6)

**Purpose:** Handoff notes for Freebuff, the implementation agent. Claude's contribution in this pack was source/repository research, feature-gap analysis, and specification updates. It was not intended to produce a built application. The verification report explicitly says that no builds or live device tests were run in its research environment.

## Files this summary is derived from

- `continuity-pack/README.md`
- `continuity-pack/FEATURE_GAP_ANALYSIS.md`
- `continuity-pack/VERIFICATION_REPORT.md`
- `continuity-pack/REPO_SHAS.tsv`
- `continuity-pack/MASTER_AGENT_PROMPT_v5.md`

The full reports remain in this bundle and take precedence for details. This summary is not a replacement for them.

## Patch notes

### Research provenance and workflow

- Pinned the upstream revisions inspected in `REPO_SHAS.tsv`; preserve repo URLs and commit IDs in engineering notes.
- Clarified that source inspection is not build/runtime evidence. The research pack did not build the app, run APK compilation, use a physical Mi 12, or test a live Hyprland/Quickshell session.
- Added `PROGRESS.md` and `STATUS.json` monitoring, module-level commits, an explicit approval-gated action list, and a full diagnostics/reporting requirement.
- Added an early real-build requirement for the implementation agent, with full build logs and honest handling of unavailable SDK downloads.

### Architecture and repository corrections

- **Linux Link ≠ LinLink.** They are different repositories; do not conflate them.
- **Sefirah desktop is Windows-first C#/.NET** with limited Linux support; Sefirah-Android is a separate Kotlin project.
- **Vortex is GPL-3.0, Rust + Tauri/Vue on desktop**, Android Kotlin/Compose, beta and tested by its README on a limited setup. Its Hyprland InputCapture and second-screen claims are not established on the target system.
- **No reference project contains Quickshell integration.** v5 adds an explicit D-Bus + JSON-lines Unix socket contract and requires the Quickshell module to consume real backend state.
- **Use-As-Server must not be copied:** the repository has no LICENSE file, its Linux desktop/input assumptions are X11-oriented, its Android client source is not in the repo, and its `chmod 666 /dev/uinput` advice is unsafe.
- **Misael-art/android-dex** (MIT according to the repository license) is the main open-source DeX/workspace implementation reference: PySide6/Qt Quick UI, local JSON-RPC daemon with a mode-0600 socket, and Bash toolkit using scrcpy/ADB, supervisor/systemd/udev and OEM profiles including Xiaomi.
- **Shrey113/Android-Dex is proprietary** according to its LICENSE; use public docs/UX as a reference only. Do not copy or redistribute its code.
- Do not merge Misael-art's separate `android-dex-flash` fastboot/Heimdall/Magisk subsystem into the normal continuity runtime.
- **Shevery modules** are ZIPs with a root `module.prop` plus optional `action.sh`, `service.sh` and `webui/`, invoked through Shizuku. They are not root overlays or a generic plugin API to embed uncritically. Keep optional, permission-gated and independently revocable.
- Preserve license notices and track reused files/dependencies. GPL and proprietary boundaries must be resolved before reuse or distribution.

### Apple-parity features added after the v4 audit

- Android Direct Share target so the laptop appears in the native share sheet.
- Vivaldi/Chromium extension using native messaging for browser-tab handoff.
- QR pairing plus short-code/emoji authentication confirmation.
- Click-through from ongoing Quickshell items to the corresponding app in an authorized scrcpy virtual display, with a phone-side fallback.
- Optional Quick Share interoperability investigation via RQuickShare/maintained fork; the app's own authenticated transport stays primary.
- Opt-in verification-code handoff with auto-clear, with the necessary notification/SMS permission trade-offs made explicit.
- Optional Phone panel for recents/contacts/dial actions where Android roles and permissions support it; do not promise carrier/system-only functionality such as Call Screening, Hold Assist or visual voicemail.
- Universal Control exploration using KDE Connect `shareinputdevices` or a portal/InputCapture approach, explicitly testing Hyprland rather than assuming it works.
- Drawing-tablet and presenter/media remote references.
- Bluetooth audio handoff and Wi-Fi Direct investigated only if hardware/stack support makes them useful.
- Optional shared local notes/to-dos in the content shelf.
- Existing camera/document scan, recent photos, screen mirroring/control, hotspot assistance, find/ring, Android Quick Settings, privacy dashboard and diagnostics remain in scope.

### Android 15 / Xiaomi HyperOS caveats

- Android 15 sensitive notification redaction is documented in Sefirah-Android's README; the report notes the `RECEIVE_SENSITIVE_NOTIFICATIONS` app-op as an explicit optional step. It must never be auto-applied without approval.
- Sideloaded builds may need “Allow restricted settings” before notification access or accessibility is enabled; include onboarding guidance.
- Re-verify current foreground-service types and Android 15 `dataSync` time limits; don't use `dataSync` for the persistent connection without a verified basis.
- MediaProjection requires user consent per session and the correct foreground-service handling; verify against current Android docs.
- Verify HyperOS Autostart and battery “No restrictions” on the physical phone. scrcpy input can require Xiaomi “USB debugging (Security settings)” plus a reboot; don't toggle it automatically.
- Android 16 QPR3 connected-display desktop windowing must not be assumed on an Android 15 Mi 12.
- scrcpy ≥3.0 is needed for `--new-display` in the referenced Android-Dex kit path; independently-app windows, virtual display and basic full-screen mirroring must be reported as separate capabilities.

### Build, tests, and UX

- Build APKs from Linux with the project Gradle Wrapper, compatible JDK, Android SDK platform and build-tools; add NDK/CMake only if required. `android-tools`/`adb` is not the APK compiler.
- Inspect the product's own `compileSdk`, AGP and Gradle settings. Do not inherit KDE Connect's `compileSdk 37`, and do not silently lower compileSdk because a platform package is unavailable.
- Use `design/tokens.json` as the canonical Catppuccin Mocha (dark) + Latte (light) token source, and `design/ui-concept.html` as a final polish reference. They are design references, not implementation proof.
- Implement “Run Full Diagnostics” in the testing UI and a CLI, export sanitized JSON and readable Markdown, and produce a per-feature batch-test matrix.
- Keep two primary modes: Apple-like Continuity and Android-Dex/DeX Workspace. DeX remains first-class; a single screen mirror does not count as independent-app-window support, though it may be a real fallback on the target phone.
- Continue with a feature-complete integrated test build, then run a separate final UI polish pass.

## What Freebuff should do with these notes

1. Read the full research reports before architectural changes.
2. Inspect the actual target product workspace and its Git state; do not mistake this research pack for product source code.
3. Reproduce and log the first real build early.
4. Use source references when resolving specific dependency/licensing/API questions instead of rerunning the entire audit.
5. Implement and test the full product, exporting APK and desktop artifacts where possible.
6. Keep runtime/device-only tests marked unverified until actually tested on the Mi 12 and the target Hyprland/Quickshell system.
