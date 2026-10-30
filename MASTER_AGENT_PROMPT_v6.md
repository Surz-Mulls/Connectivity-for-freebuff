# MASTER AGENT PROMPT v6 — Freebuff Implementation Handoff: Apple-Like Continuity + Android-Dex Workspace

**Version 6 is the implementation handoff for Freebuff. Claude was used as the research agent; the supplied pack is intentionally research-focused and does not claim to have built or run the product. This version preserves the v5 specification and explicitly carries forward Claude’s patch notes, repository corrections, pinned source commits, Apple-parity additions, Android 15/HyperOS findings, Quickshell IPC contract, design references, and cloud-build/diagnostics requirements. Freebuff is expected to IMPLEMENT, BUILD, TEST, DEBUG, and deliver artifacts—not restart the research phase or stop after writing a plan. Treat the evidence documents as source research, not runtime/build evidence. Where this prompt and the supplied v5 research notes conflict, this v6 prompt wins; retain and cite the source notes.**

## 0. Freebuff handoff and Claude research patch notes (read first)

### 0.0 Who does what

- **Claude's role was research.** The supplied pack records upstream source inspection, repository commit SHAs, feature-gap analysis, licence/architecture corrections, design references and implementation guidance. It intentionally did not claim to build or run the application because its research environment lacked the Android SDK download path, physical phone, Hyprland session and GPU.
- **Freebuff's role is implementation.** Do not treat the absence of a build in Claude's research pack as a defect in that pack, and do not spend the session recreating all of its research. Inspect the actual target project/workspace, read this prompt and the bundled reports, implement the product, run the build and tests that the current environment permits, debug failures from actual logs, and export the deliverables.
- If the app's target repository/workspace is already supplied by the user or mounted in the current environment, work in that project and preserve its Git history/changes. The research pack is supporting material, not a substitute for the application source. Do not claim a product repo was cloned unless it actually was.
- The v5 source notes may be copied into `docs/research/` and design references into `design/`, retaining their provenance and inspected commit SHAs. Do not edit historical research reports to make a claim appear verified after the fact; add a dated implementation-validation note instead.
- Re-check specific claims only when the current code, dependency versions, licences, or actual build results make that necessary. The reference SHAs are a reproducible baseline, not an instruction to blindly pin every dependency to an old revision.

### 0.0.1 Claude's research patch notes (v4 → v5, carried into v6)

These are the changes documented by Claude's research pack in `FEATURE_GAP_ANALYSIS.md`, `VERIFICATION_REPORT.md`, `REPO_SHAS.tsv`, and the v5 README. A standalone patch-notes file is also included in this bundle. Apply these corrections; do not silently revert to v4 assumptions:

1. **Evidence and provenance:** source-level verification was made against specific repository commits recorded in `REPO_SHAS.tsv`. It is not runtime validation: the pack explicitly says no builds or device tests were run. Label these facts as source-inspected until Freebuff produces build/test evidence.
2. **Repository corrections:** Linux Link (`ArvinKavaskov/linux-link`) is different from LinLink (`THARUN-BART/linlink`). Sefirah desktop is C#/.NET and Windows-first, with limited Linux support; do not treat it as an established Linux implementation. Vortex is GPL-3.0, Tauri/Vue on desktop, beta, and its Hyprland InputCapture path is untested. No reference project contains Quickshell-specific integration.
3. **Licensing and unsafe references:** Misael-art `android-dex` identifies MIT and is the principal open-source DeX/workspace reference. Shrey113 Android-Dex identifies a proprietary licence and must be used as a feature/UX reference only—not copied or redistributed. `Use-As-Server` has no repository LICENSE file, is X11-oriented on Linux, and its `chmod 666 /dev/uinput` advice is unsafe; do not copy its code or that advice. Keep Misael-art's `android-dex-flash` / fastboot / Heimdall / Magisk maintenance subsystem out of the normal continuity product.
4. **Quickshell contract:** implement a real backend API before the Quickshell UI. The v5 contract calls for session D-Bus `io.continuity.Daemon` at `/io/continuity/Daemon`, plus a 0600 JSON-lines Unix socket at `$XDG_RUNTIME_DIR/continuity/ipc.sock`, with `continuityctl` as a client. The Qt UI, Quickshell module and CLI must consume backend state rather than maintaining conflicting copies.
5. **New Apple-parity / Android-native features:** retain Direct Share target; browser tab handoff via WebExtension/native messaging; QR plus short-code/emoji pairing confirmation; click-through from live status items; optional Quick Share interoperability via RQuickShare or a maintained fork; opt-in verification-code handoff with auto-clear; a phone panel for contacts/recents where Android permissions/roles permit; Universal Control investigation through KDE Connect `shareinputdevices` or a portal-based path; drawing-tablet/presenter mode; Bluetooth audio handoff investigation; optional Wi-Fi Direct investigation; and shared local notes/to-dos if they fit without undermining core work.
6. **Android 15 / HyperOS constraints:** account for sensitive notification redaction; document the opt-in `RECEIVE_SENSITIVE_NOTIFICATIONS` app-op only with user approval; explain “Allow restricted settings” for sideloaded app notification/accessibility permissions; verify current foreground-service rules and avoid using `dataSync` for a persistent connection; require proper per-session MediaProjection consent; verify Xiaomi HyperOS autostart/battery settings on the actual phone; scrcpy input may require “USB debugging (Security settings)” and a reboot. Native desktop windowing/connected-display support documented for Android 16 QPR3 must not be assumed on Android 15; detect capabilities and use scrcpy virtual display where supported.
7. **DeX remains first-class:** probe the real device and `scrcpy` capabilities, including `--new-display`, `--start-app` and `--flex-display`; report independent app windows separately from single-screen mirroring. Never promise a desktop mode the Mi 12/HyperOS path does not expose.
8. **Build/toolchain accuracy:** APK compilation requires a compatible JDK, the repository Gradle Wrapper, Android SDK platform/build-tools, and any project-required NDK/CMake. `android-tools`/`adb` is for device communication, not the APK compiler. Do not inherit `compileSdk 37` from KDE Connect automatically: inspect this product's Gradle/AGP settings and install the exact required SDK platform if available. Never silently lower `compileSdk` because an SDK platform is unavailable.
9. **Batch diagnostics and monitoring:** keep `PROGRESS.md` and `STATUS.json` updated, commit modules independently where possible, implement “Run Full Diagnostics” in the testing UI plus a CLI, export sanitized JSON and readable reports, and build a reproducible per-feature test matrix. Separate build success, unit tests, integration tests and real-device verification.
10. **Explicit approval boundaries:** pause for approval before `sudo`, package installation via pacman/yay/paru, writing under `/etc` or `/usr`, udev/polkit/firewall/system-unit changes, `modprobe`/`insmod`, ADB pairing/install/debug-setting changes, granting permissions via ADB/Shizuku, exposing network services beyond the local subnet, or pushing/publishing changes. Continue ordinary implementation without asking for approval at each stage.
11. **Design handoff:** use `design/tokens.json` as the canonical token source (Catppuccin Mocha dark and Latte light) and `design/ui-concept.html` as a visual direction for the final polish pass. They are references, not proof of a working UI. The testing UI can be utilitarian; the shipped UI must be polished.

### 0.0.2 Required first actions for Freebuff

1. Print the current directory, inspect the actual project source tree and Git status, and locate the supplied research pack.
2. Read `FEATURE_GAP_ANALYSIS.md`, `VERIFICATION_REPORT.md`, `REPO_SHAS.tsv`, `README.md`, `design/tokens.json`, and `design/ui-concept.html` before changing architecture or dependencies.
3. Write a concise initial entry to `PROGRESS.md` and `STATUS.json`; identify the actual build environment and project Gradle/SDK requirements.
4. Run the first baseline build as early as possible and preserve the complete stdout/stderr log. If it fails, fix the actual failure rather than speculating from the research-only environment.
5. Continue through the implementation and feature-complete integration scope below. Do not stop at a plan, report, prototype, or three-feature MVP. Produce whatever real artifacts the current environment can support, and explicitly flag hardware-only tests that need my device.

### 0.1 Bundled files (in the same pack as this prompt)

`PATCH_NOTES_CLAUDE.md` (research changes summarised from Claude’s notes), `REPO_SHAS.tsv` (pinned upstream commits), `scripts/clone-research.sh`, `VERIFICATION_REPORT.md`, `FEATURE_GAP_ANALYSIS.md`, `design/tokens.json` (canonical design tokens, Catppuccin Mocha default plus a light theme) and `design/ui-concept.html` (visual reference for the polish pass). Copy them into the project under `docs/research/` and `design/`. Treat the verification report as a starting point: re-check anything that decides the architecture, because these files were produced from source reading only, with no build and no device.

### 0.2 Monitoring protocol (so I can follow along)

1. Keep `PROGRESS.md` (human-readable, newest entry on top) and `STATUS.json` at the repository root. Update both at the end of every module and at least every 10 minutes while working.
2. `STATUS.json` schema: `{"updated":"<ISO-8601>","stage":"inspect|foundation|features|batch-test|polish|release","module":"<name>","state":"running|waiting-user|blocked|done","last_commit":"<sha>","tests":{"pass":0,"fail":0,"blocked":0,"not_verified":0},"needs_user":["<exact action I must take>"],"notes":"<one line>"}`.
3. One Git commit per module, with a message that names the module and its status (implemented-and-tested / implemented-unverified / blocked). Never squash away a failing module.
4. When you need something from me (a command to run, a toggle on the phone, a password), put it in `needs_user` with the exact steps, set `state` to `waiting-user`, and continue with independent work.

### 0.3 Actions that ALWAYS need my explicit go-ahead

Do not run these without showing me the exact command and waiting: anything with `sudo`; `pacman`/`yay`/`paru` installs; `modprobe`/`insmod`; writing anything under `/etc`, `/usr`, or udev/polkit/firewall/systemd system units; `adb install`, `adb pair`, `adb tcpip`, enabling any Android debugging or developer setting; granting an Android permission through ADB or Shizuku; any network exposure beyond the local subnet; any `git push` or publishing. Never recommend `chmod 666 /dev/uinput` or similar world-writable device nodes: use a udev rule that grants a specific group, and show it to me first.

### 0.4 Baseline problem to reproduce before building

My current setup uses stock KDE Connect between the Mi 12 (Android 15, HyperOS) and this Arch laptop, and **phone-to-laptop remote control does not work**. Before designing our input path: reproduce it, record `kdeconnect-cli -l --id-name-only` output, whether the remote-input plugin is enabled on both sides, `journalctl --user -u kdeconnectd` (or the actual unit name) during a test, and which Wayland input mechanism KDE Connect tried (portal/libei, uinput, X11/XWayland). Hypothesis only, not a diagnosis: the Wayland input-injection path on Hyprland. Write the evidence to `docs/baseline-remote-input.md`. Our own input features (touchpad, keyboard, Universal Control, extended-monitor touch) must not depend on the mechanism that failed unless you have shown why it will work here.

## 1. Mission

Build a reliable, privacy-first, local-network ecosystem that makes my Android phone and Linux computer behave like parts of one integrated environment, similar in feel to Apple Continuity. This is a real software engineering task, not a mockup, proposal-only task, or prototype with fake controls. Inspect the workspace and upstreams, implement the application, integrate subsystems, build it, test it, diagnose failures, and deliver usable artifacts.

### Target environment

- **Phone:** Xiaomi Mi 12, targeting Android 15 / HyperOS. Verify the actual device/software when possible; do not assume all OS versions behave identically.
- **Desktop:** Arch Linux, Hyprland Wayland compositor, Quickshell shell, Dolphin file manager.
- **Possible development environment:** a cloud Linux machine, probably Ubuntu but not guaranteed. It may be short-lived or lack physical access to my phone. Detect the actual OS and capabilities before choosing commands.
- **Experience goal:** local-first; secure first-time pairing; automatic, honest reconnection; low idle resource use; feature-complete integrations; polished final GUI on both platforms.

## 2. Highest-priority execution rule: integrated feature-complete testing build

I prefer to find integration problems across a broad set of implemented capabilities in one batch. **Implement all feasible features in this prompt into one integrated testing build.** Do not stop at a deliberately limited MVP of pairing, clipboard and file transfer while leaving major requested features for a later phase. Do not stop after each feature to ask me whether to continue.

This does **not** mean writing one giant untested code dump. Work internally in dependency-aware stages: build and test foundations as you go, keep the feature modules isolated enough to diagnose, and continue implementing the full scope without waiting for approval between routine stages. Present the integrated build and batch-test report when the broad feature set is ready.

### Testing UI versus final UI

- **Testing build:** a basic, utilitarian, diagnostics-focused GUI is acceptable. Prioritize real functionality, observable state, accurate errors, logs, repeatable tests and integration. Do not spend early effort on elaborate animations or cosmetic details.
- **Final product:** must have a polished, coherent and intentional GUI on Android and desktop. After the feature-complete build is testable, run a separate UI/UX polish pass and re-test the primary journeys.

### No fake completeness

- A screen, button, mock response, TODO, hard-coded demo, or placeholder is not a completed feature.
- Do not silently replace difficult functionality with a stub.
- If an OS restriction prevents full support, implement capability detection, permission/onboarding flow, safe fallback and clear explanation.
- Mark each feature accurately: **implemented and tested**, **implemented but unverified**, **blocked by a specific limitation**, or **not implemented**.
- Do not sacrifice security or data integrity for a successful demo.
- Continue autonomously through routine decisions. Ask only when a genuine user choice, credential, physical action, or authorization is required.

## 3. Preserve the established architecture

First inspect the whole workspace, existing project instructions, source tree, manifests, build files, tests, design docs, dependencies and Git status. Do not overwrite existing work or silently swap the established stack.

Default architecture contract:

- **Android:** Kotlin + Jetpack Compose.
- **Desktop:** Qt 6 + QML, using suitable KDE Frameworks/Kirigami integration where it fits.
- **Design:** a canonical shared, version-controlled token source; generate or map platform-specific values rather than forcing both toolkits to share runtime code.
- **Backend:** clearly separated service/protocol layer for networking, state and sensitive operations.
- **Linux integration:** native Wayland-compatible behavior, with explicit Hyprland and Quickshell support.
- **Testing:** reproducible build commands, automated tests where practical, structured logs, a full diagnostic action and a batch-test report.

Treat these as the intended choices, not an invitation to substitute Tauri/Vue, Flutter, Electron or another stack because an upstream reference uses it. If the existing repository already has a conflicting explicit choice, report it and preserve the existing project unless there is a concrete blocker. Explain evidence and consequences before any fundamental change.

Reuse mature, compatible libraries and upstream patterns instead of unnecessarily reimplementing discovery, pairing, cryptography, transfers or desktop integration. Do not mix incompatible source code blindly.

## 4. Upstream repository research

Claude has already inspected the listed upstreams at the SHAs in `REPO_SHAS.tsv`; read `VERIFICATION_REPORT.md` and `FEATURE_GAP_ANALYSIS.md` first. **Do not repeat the full research phase before starting implementation.** Use the notes as a baseline and revisit only the specific upstream source needed to resolve a concrete code, API, dependency, licence or build issue. You may re-clone a relevant reference repo if needed, but keep it separate from the product workspace. Record what was actually inspected and never claim a clone, build or test occurred unless it actually did.

### Primary references

1. Linux Link — https://github.com/ArvinKavaskov/linux-link
2. Vortex — https://github.com/zoir-dev/vortex
3. KDE Connect desktop — https://github.com/KDE/kdeconnect-kde
4. KDE Connect Android — https://github.com/KDE/kdeconnect-android
5. Sefirah desktop — https://github.com/shrimqy/Sefirah
6. Sefirah Android — https://github.com/shrimqy/Sefirah-Android

### Additional references

7. LinLink — https://github.com/THARUN-BART/linlink
8. Use-As-Server — https://github.com/manjeetdeswal/Use-As-Server (**feature checklist only**: no LICENSE file in the repository although the README badge says MIT; Linux server is X11-oriented (xdotool/pyautogui/mss); its Android client is closed and on Google Play; do not copy its code or its `chmod 666 /dev/uinput` advice)
9. Shevery — https://github.com/HmnDev-Tech/shevery
10. scrcpy — https://github.com/Genymobile/scrcpy (screen mirroring/control, audio/video forwarding and webcam integration reference; inspect upstream requirements and license).
11. LocalSend — https://github.com/localsend/localsend (local-network sharing UX, discovery and transfer workflow reference; inspect protocol, security and license before considering any reuse).
12. Misael-art Android-Dex — https://github.com/Misael-art/android-dex (especially `android-dex-kit` and `android-dex-ui`; a Linux DeX-like workspace based on Qt/QML, a local daemon, scrcpy/ADB, USB/Wi-Fi sessions, device diagnostics and reconnect supervision).
13. Shrey113 Android-Dex — https://github.com/Shrey113/Android-Dex and release notes at https://github.com/Shrey113/Android-Dex/releases (feature reference for a DeX-like desktop workflow, multi-app windows where supported, ADB/device management, audio/media, keyboard/mouse control and reconnection; inspect current release details and license).
14. RQuickShare — https://github.com/Martichou/rquickshare (GPL-3.0, Rust; Quick Share/Nearby Share for Linux; last upstream commit 2025-06-16, so also look at maintained forks such as Fero) — reference/optional adapter for AirDrop-like sharing with the phone's built-in share sheet.
15. KDE Connect plugin set to study specifically: `virtualmonitor`, `shareinputdevices`/`shareinputdevicesremote`, `digitizer`, `presenter`, `sftp`, `telephony`/`sms`/`mmtelephony`, `findmyphone`/`findthisdevice`. **Do not port `remotecommands`/`runcommand`** (arbitrary command execution is forbidden by this prompt).
16. Android Developers — desktop windowing and connected displays (Android 16 QPR3): https://developer.android.com/blog/posts/android-devices-extend-seamlessly-to-connected-displays — to understand what native desktop mode is and which devices have it. The Mi 12 on Android 15 should not be assumed to have it.

For each relevant repository, inspect actual source and documentation: implemented features, component boundaries, protocol, build process, platform assumptions, dependencies, test coverage, limitations, security model and license. Do not rely only on README claims or screenshots.

### Specific research tasks

- **Linux Link:** examine its Rust daemon, Kotlin Android application, device identity and pairing, certificate verification/pinning, discovery and reconnection, clipboard, files, notifications, audio/video and desktop integration. Verify how its Hyprland support works and distinguish Waybar assumptions from Quickshell needs.
- **Vortex:** inspect pairing, transport, protocol/schema, daemon/UI boundary, reconnect flow, Android permissions and ADB-related functionality. Extract useful patterns without silently changing our required stack.
- **KDE Connect:** examine established device discovery, pairing, plugin architecture, file transfer, clipboard and notification handling.
- **Sefirah and other candidates:** compare feature coverage, protocol and existing implementations; adopt only what is compatible and justified.
- **Misael-art Android-Dex:** inspect the `android-dex-kit`, `android-dex-ui` and any relevant daemon interfaces. The README describes a Qt Quick/PySide6 UI, an allowlisted local JSON-RPC service, a no-root scrcpy/ADB kit, automatic DeX-versus-mirror selection, USB/Wi-Fi connection and recovery, device diagnostics and systemd integration. Verify these claims in source and current releases. The repo declares MIT licensing; verify the actual LICENSE and preserve required notices if code is reused. Do not change our chosen Android Kotlin/Compose + desktop Qt 6/QML stack just because the reference UI uses PySide6.
- **Shrey113 Android-Dex:** inspect its latest README/releases/docs for user-facing capabilities and compatibility. Its README describes it as closed-source/proprietary; treat it as a feature/behavior reference only. Do not copy its source, reverse engineer private components, package its binary as our own, or redistribute/repackage it without written authorization. Its release history and public website are evidence of advertised features, not proof that a feature works on our device.
- **Shevery:** inspect its ADB Modules guide and API/implementation. Determine whether modules can provide an optional development/diagnostic path or safely fill a specific Android privilege gap. Do not assume its module runner is a generic plugin interface for our app.

Check licenses before copying or linking implementation code. Linux Link identifies itself as GPL-3.0. Shevery describes its code as Apache-2.0 while also crediting upstream projects; inspect the precise files and inherited licensing before reuse. Verify each other dependency's license as well. Document attribution and distribution implications.

Do not let research become a substitute for implementation. Once enough evidence supports the architecture, proceed.

### Independent feature-parity research: model the experience, not Apple's proprietary internals

I want this to feel as close as realistically possible to Apple Continuity while remaining a local-first Android/Linux product. Independently compare our feature set with Apple's published Continuity features, plus useful patterns from KDE Connect, Microsoft Phone Link, scrcpy and LocalSend. Inspect actual documentation/source for current constraints rather than copying feature names. Use these references as an audit checklist:

- Apple Support — Continuity features and requirements: https://support.apple.com/en-au/108046
- Apple — macOS Continuity: https://www.apple.com/in/macos/continuity/
- KDE Connect features and documentation: https://apps.kde.org/kdeconnect/ and https://github.com/KDE/kdeconnect-kde
- Microsoft Phone Link capabilities: https://support.microsoft.com/en-us/topic/phone-link-requirements-and-setup
- Android Companion Device pairing/background behavior: https://developer.android.com/develop/connectivity/bluetooth/companion-device-pairing
- Android clipboard security restrictions: https://developer.android.com/privacy-and-security/risks/secure-clipboard-handling
- Android Quick Settings tiles: https://developer.android.com/develop/ui/views/quicksettings-tiles
- Android call API boundaries: https://developer.android.com/develop/connectivity/telecom/dialer-app
- scrcpy: https://github.com/Genymobile/scrcpy
- LocalSend: https://github.com/localsend/localsend

Map each relevant Apple feature to one of: **implement natively**, **implement with an explicit optional integration/permission**, **provide a guided partial equivalent**, or **not feasible without unsupported/proprietary capabilities**. Record the rationale, dependencies, privacy impact and test plan. Do not impersonate Apple services or pretend to provide iMessage, FaceTime, iCloud, Apple Pay, Apple Account authentication, Apple's proprietary device APIs or universal operating-system privileges. Make the user experience analogous, not falsely identical.

The audit must explicitly evaluate these experiences:

| Apple-like experience | Linux/Android target behavior | Practicality and guardrails |
|---|---|---|
| AirDrop | Nearby trusted-device send/receive for files, folders, URLs, images and text, with progress, confirmation and transfer resume where possible | Core feature; local, authenticated and encrypted; use LocalSend as a UX/protocol comparison, not an automatic dependency |
| Universal Clipboard | Fast clipboard handoff across devices, including supported text and images; optional file/URI handoff where practical | Core, with Android background restrictions and sensitive-clipboard controls treated honestly |
| Handoff | “Continue on phone/PC” for URLs and shared content, with extension points for apps that explicitly integrate | Implement real share/intent integration; do not claim arbitrary application state can be resumed |
| Continuity Camera | From the desktop, request the phone camera to take a photo or scan a document and send the result to the chosen desktop destination | High-value addition; require explicit phone confirmation/camera permission; add preview, crop/perspective correction and retake |
| iPhone Mirroring | Optional window for live Android screen mirroring and, when authorized/supported, keyboard/mouse control | Evaluate integration with the real scrcpy project before reimplementing; ADB/debugging required for many modes, and Xiaomi may require an extra “USB debugging (Security Settings)” option |
| Continuity Camera as webcam/mic | Make the phone selectable as a Linux webcam/microphone | Requires real camera/audio pipeline and virtual-device lifecycle; don't confuse camera capture/scan with webcam streaming |
| Sidecar / Universal Control | Tablet as a real extended monitor where possible; phone as touchpad, keyboard, media or presentation remote; optional desktop-to-phone control through a supported mirror/control path | Split second-monitor output from input control; distinguish these from a universal pointer crossing displays, which may not be available cross-platform |
| Calls and text forwarding | Show call state, relevant notification actions and message replies; investigate supported SMS/MMS and call audio integration separately | Feature support is permission/API/role/device dependent. RCS and third-party messaging contents generally cannot be assumed accessible. Do not claim full call answering/audio until verified on the actual phone and Linux stack |
| Instant Hotspot | Help desktop connect when the phone's hotspot is the available network; explain/take the user to the right phone settings; support USB tethering as a transport option if useful | Android may restrict programmatic hotspot control. Do not silently enable tethering, extract credentials or bypass system UI |
| Find My / proximity | Ring or alert the phone from the desktop; ping the desktop from phone; show last-seen/presence; optional proximity lock | Local discovery can support this; location tracking is not required. Lock is opt-in; automatic unlock stays disabled by default |
| Ongoing status / Live Activities | Quickshell panel and desktop notifications for connection, active transfer, media, phone battery and actionable status; Android notification/Quick Settings controls for common actions | Must be driven by live backend state and remain useful without keeping the full GUI open |
| Continuity sketch / capture | Start a phone capture/scan from the desktop and receive a preview or annotated image; optionally send selected screenshots or text | Prioritize camera/document capture; add sketch/markup only if it fits the supported pipeline |
| Android-Dex / DeX workspace | Use the connected Android device as a desktop-style environment from Linux, including supported native desktop mode or app windows, keyboard/mouse input, media/audio and device/session control | This is a separate required product mode, not just a single scrcpy mirror. Test the Xiaomi/HyperOS capability path and provide honest fallback behavior; only implement independent app windows when the actual Android/device/scrcpy pipeline supports them |

Current Android documentation establishes that Companion Device Manager can assist initial discovery/pairing and certain background starts, but does not itself create a connection or enable continuous scanning. Android also restricts background clipboard reads. Account for these constraints in the architecture instead of assuming Apple-like privileges exist. The official scrcpy project already supplies mature Android mirroring/control features on Linux; evaluate wrapping/launching it as an optional first integration, respecting its license and explicit debugging authorization.

### Feature priority for implementation planning

Use this priority to sequence dependencies and testing, **not as permission to silently omit lower-priority features**. Continue toward one feature-complete integrated testing build.

- **P1 — seamless foundation:** trusted pairing/reconnect, encrypted file and clipboard transfer, notification actions/replies, URL/text handoff, device status, find/ring action, Android quick controls, Quickshell status/actions, diagnostics and privacy controls.
- **P2 — high-value Continuity experiences:** desktop-triggered camera/photo/document scan, recent-photo sharing, screen-mirroring integration, incoming-call awareness, messaging bridge investigation, media/volume, optional phone-as-webcam/mic, hotspot/tethering assistance, richer drag-and-drop/share flows.
- **P3 — advanced/hardware-specific:** real extended monitor and pen/touch input, robust two-way folder sync, full call-audio relay, proximity lock, DND sync, advanced automation/extensions.

Attempt every item. Where a capability is intrinsically blocked by OS restrictions, lack of hardware, required role changes or unavailable hardware in the cloud, implement its safe fallback or integration boundary and record it as blocked/unverified rather than presenting a fake control.

## 4A. Verified upstream facts (pinned commits; re-verify at those SHAs before relying on them)

These were read from local clones on 2026-10-28; nothing was built or run. See `VERIFICATION_REPORT.md` for the full table.

| Repo | Licence | Stack / key facts that affect design |
|---|---|---|
| Linux Link (ArvinKavaskov) | GPL-3.0 | Rust daemon `linkd` (QUIC via quinn, mTLS 1.3 with pinned SHA-256 fingerprints, BLE + mDNS discovery, zbus, evdev); Android Kotlin + Compose, minSdk 33. UDP 47100 (QUIC) and 47101 (discovery). Hyprland second screen uses `hyprctl output create headless` + `wf-recorder` + uinput. Tray is a StatusNotifierItem (Waybar-style). **No Quickshell support.** |
| Vortex | GPL-3.0 | Beta, live-tested on one device pair (GNOME). Rust daemon + **Tauri/Vue** GUI (not our stack). Protobuf + Noise, BLE signalling. Has emoji-SAS pairing, SMS-code-to-clipboard, shared notes/to-dos, audio hand-off, call banner/SMS/contacts, Universal Control (experimental, Wayland InputCapture portal; Hyprland untested), second screen GNOME-only and view-only. |
| KDE Connect (desktop + Android) | `GPL-2.0-only OR GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL` | Android: Kotlin, Gradle 9.6.0, **compileSdk/targetSdk 37**, minSdk 23. Mature plugin architecture; has `virtualmonitor`, `shareinputdevices`, `digitizer`. |
| Sefirah / Sefirah-Android | GPL-3.0 | Desktop is **C#/.NET, Windows-first** ("Linux support is limited"). Android: Kotlin, Gradle 9.7.0, AGP 9.3.1. Documents the Android 15 sensitive-notification fix (`appops set <pkg> RECEIVE_SENSITIVE_NOTIFICATIONS allow`) and "Allow restricted settings". |
| LinLink (THARUN-BART) | MIT | Flutter app + Rust `linux-companion`. **A different project from Linux Link.** Claims calls via PC mic/speaker: unverified; Android restricts call-audio capture for ordinary apps, so inspect before believing it. |
| Use-As-Server | **no LICENSE file** | See reference 8. Checklist only. |
| Shevery | Apache-2.0 | Module = ZIP with `module.prop`, optional `action.sh`, `service.sh`, `webui/`; Shizuku-backed; not a root overlay. |
| scrcpy v5.0.1 | Apache-2.0 | `--new-display[=WxH/dpi]`, `--flex-display`, `--start-app`, `--keep-active`, `--no-vd-system-decorations`, `--video-source=camera`, `--v4l2-sink`, `--otg`, uhid/aoa input, `--gamepad`. FAQ: Xiaomi needs "USB debugging (Security settings)" for input, plus a reboot. Drag-and-drop pushes files to /sdcard/Download. |
| LocalSend | Apache-2.0 | Default port 53317, multicast 224.0.0.167. |
| Misael-art android-dex | MIT | `android-dex-ui` (PySide6/Qt Quick) → `android-dexd` (JSON-RPC, 0600 socket) → `android-dex-kit` (bash, scrcpy+adb, supervisor, systemd, udev, per-OEM profiles incl. xiaomi). Needs scrcpy ≥ 3.0 for `--new-display`, otherwise it falls back to mirroring. Probes `enable_freeform_support` and `force_desktop_mode_on_external_displays`. `android-dex-flash` (fastboot/heimdall/Magisk) stays excluded. |
| Shrey113 Android-Dex | **Proprietary** | Closed source; behaviour/UX reference only. |
| RQuickShare | GPL-3.0 | Quick Share for Linux; Android may drop its mDNS advert, workaround is a Bluetooth advertisement; upstream stalled since 2025-06. |

### Corrections to carry forward

1. Do not use Use-As-Server code. Its Linux input and screen capture assume X11; Hyprland is Wayland.
2. Linux Link ≠ LinLink. Sefirah's desktop half is Windows-first and gives no Linux parity.
3. No reference supports Quickshell. Section 4B-Q defines the contract we build instead.
4. "Feature-complete" claims in READMEs are not evidence. Your own tests are.
5. Native Android desktop mode (Android 16 QPR3) is not assumed on the Mi 12. The working DeX-like path to implement and test is a scrcpy virtual display (`--new-display`, `--start-app`, `--flex-display`).

### Combined-work licence rule

If any GPL-3.0-only file is included, the combined work is GPL-3.0-only (KDE Connect's dual-licensed files are compatible with that choice). MIT and Apache-2.0 code may be included with notices preserved. Do not include code with no licence (Use-As-Server) or a proprietary licence (Shrey113). Keep a `NOTICE.md` listing every upstream, commit, licence and what was reused.

## 4B. Additional features found by the v5 research (implement or record an evidence-based blocker)

Same rules as Section 2: real implementations, honest status, safe fallbacks. Priorities follow Section 4's scheme.

- **4B-1 Direct Share target (P1).** The laptop appears by name in Android's share sheet (sharing shortcuts), one tap to send.
- **4B-2 Browser handoff extension (P1).** A Vivaldi/Chromium WebExtension with native messaging: "Send this tab to phone". Phone side opens the URL through a confirmation screen showing exactly what will open. Reverse direction: phone share sheet → laptop browser.
- **4B-3 Short-code pairing confirmation (P1).** In addition to QR, show a short authentication string (emoji or digits) derived from both keys on both devices; pairing completes only when I confirm they match.
- **4B-4 Live-item click-through (P2).** Ongoing items in the Quickshell panel (media, timer, ride/delivery notification, call) open the originating app in a mirrored window via `scrcpy --new-display --start-app=<package>` when ADB is authorised, else fall back to a phone-side "open this" notification. Never launch apps I did not click.
- **4B-5 Quick Share interop (P2).** Optional adapter (RQuickShare or a maintained fork) so the phone's built-in Quick Share can send to/receive from the laptop with no companion app. Capability-detect it, run it as a separate unprivileged process, and test on HyperOS because Android may drop its mDNS advertisement. Our own authenticated transfer stays the default.
- **4B-6 Verification-code handoff (P2, opt-in).** A fresh code arriving on the phone is placed on the laptop clipboard and auto-cleared after a short timeout. On Android 15 this needs either an SMS permission or the sensitive-notifications appop, because OTP notifications are redacted for notification listeners. Explain the trade-off in the permission screen.
- **4B-7 Phone panel (P2/P3).** Recents, favourites, contacts and dial-from-desktop where Android permissions allow (call log and contacts are restricted permissions: opt-in, minimal). Visual voicemail, Call Screening and Hold Assist are **not feasible** without system/carrier APIs: list them as such in the parity audit.
- **4B-8 Universal Control (P3).** Cursor and keyboard crossing from laptop to phone. Study KDE Connect `shareinputdevices` and Vortex's approach. Requires Wayland input capture through `xdg-desktop-portal-hyprland`; test whether it exists on this machine before designing anything.
- **4B-9 Drawing tablet and presenter remote (P3 / P2).** Phone or tablet as pressure-sensitive tablet (study KDE `digitizer`, Linux Link's stylus device) and as a slide/media remote (KDE `presenter`).
- **4B-10 Bluetooth audio hand-off (P3, investigate).** Move headphones between laptop and phone (Vortex has a version). Hardware-dependent: record exactly what works with my headphones.
- **4B-11 Wi-Fi Direct fast path (P3, investigate).** Only if the Linux side (wpa_supplicant P2P) and Android permissions make it practical; otherwise USB tethering is the high-speed fallback.
- **4B-12 Shared notes/to-dos (P3, optional).** Small local-only list in the content shelf; skip if it threatens the core schedule.

### 4B-Q Daemon contract for Quickshell (required; supersedes loose wording in Section 5.M)

1. The backend daemon exposes (a) a session D-Bus service `io.continuity.Daemon` with object `/io/continuity/Daemon` and interfaces for Devices, Transfers, Clipboard, Dex, Privacy and Diagnostics, with change signals; and (b) a JSON-lines Unix socket at `$XDG_RUNTIME_DIR/continuity/ipc.sock` (mode 0600, same UID only) that streams state events and accepts a small allowlisted command set. Provide `continuityctl` as a CLI over the same API.
2. Every UI (Qt/QML app, Quickshell widget, CLI) is a client of this API. No UI may hold its own copy of connection state.
3. Ship a sample Quickshell module under `integrations/quickshell/` that reads the socket or D-Bus and shows device state, battery, transfer progress, clipboard actions, quick-send, privacy-mode toggle and errors. Use whatever I/O primitives the **installed** Quickshell version documents; check its docs and do not guess API names. It must be installable and removable without touching my existing Quickshell config (an include line I add myself).
4. Document the schema (`docs/ipc-schema.md`) and version it. Add contract tests that run without a phone, using a fake peer.

## 5. Full feature scope

Implement the following as a coherent ecosystem sharing a stable device identity, pairing model, protocol, settings model and accurate connection state.

### Non-negotiable: preserve Android-Dex as a first-class capability

This product has **two distinct but integrated experiences**: (1) Apple-like phone/PC Continuity, and (2) an **Android-Dex / DeX Workspace** that lets me use/control my Android device from the Linux desktop. Do not let the Continuity features replace, remove, downgrade or turn DeX functionality into a mere optional “screen mirror” button. If the current workspace already has Android-Dex code or a DeX-related feature, inspect and preserve it before refactoring. If it is not yet present, implement the best real version the target device can support.

Keep these modes integrated through shared device management, status, safe ADB/scrcpy supervision, file/clipboard paths and diagnostics, but do not make ADB debugging a prerequisite for ordinary Continuity features. DeX mode may require its own explicit USB/Wireless Debugging authorization. A failure in one mode must not break the other.


### A. Discovery, pairing and reconnection

- Discover compatible devices on the local network.
- Provide explicit first-time pairing, preferably QR-based or another authenticated out-of-band mechanism.
- Verify the peer's identity; persist trust securely; permit explicit revocation.
- Show accurate states such as discovering, pairing, connected, reconnecting, unavailable, permission required and error.
- Reconnect after reboot, sleep/wake, Wi-Fi/address changes and temporary disconnection where the OS allows it.
- Support multiple paired devices where practical.
- Avoid unnecessary polling and background activity.
- Never trust a device solely because it is on the same LAN.
- UI state must derive from actual backend state, not a hard-coded boolean.

### B. Clipboard

- Linux-to-Android text clipboard sync.
- Android-to-Linux sync to the extent supported by OS version and background/foreground rules.
- Clearly expose direction, active mode and last result.
- Handle duplicate events/loops, Unicode, large values, stale state and reconnects.
- Provide manual push/pull fallback.
- Support images only if the entire implementation path is real and tested.
- Do not keep clipboard history unless explicitly requested and configurable.
- Avoid forwarding sensitive clipboard content without the user enabling that behavior.
- Investigate Android restrictions honestly. If reliable automatic background phone-to-PC clipboard requires Shizuku, a user-authorized overlay, foreground action or other elevated capability, explain the trade-off and implement a safe fallback. Never claim an impermissible background API works.

### C. Files and sharing

- Transfer files both directions.
- Support multi-file selection, Android share intents, progress and cancellation.
- Provide a native-feeling desktop “Send to phone” action and Dolphin integration where practical.
- Support timeouts, retries, interruptions, duplicate names and clear destination choice.
- Verify transfer integrity (for example, checksum and size).
- Prevent path traversal, unsafe filenames and silent overwrites.
- Keep transfers encrypted and local.
- Make optional transfer history transparent and configurable.

### D. Folder synchronization

- Support a user-selected sync folder and optional explicitly selected additional folders.
- Implement two-way sync where safe; use efficient file watching when available.
- Handle additions, edits, renames, deletions, offline periods and reconnects.
- Detect conflicts and expose deterministic resolution; do not blindly overwrite differing/newer files.
- Protect against symlink/path traversal and access outside approved roots.
- Explain permissions and make current sync state/errors visible.
- Test conflict and deletion semantics before calling sync complete.

### E. Notification mirroring and replies

- Mirror notifications after the user enables Android notification access.
- Preserve identity; handle updates and dismissal sync without duplicate storms.
- Support replies only when the real Android notification exposes a supported reply action.
- Accurately represent unsupported actions and outcomes.
- Make sensitive notification content configurable; minimize retained content.
- A textbox or generic dismissal is not equivalent to a functioning notification reply.

### F. Media, volume and audio

- Display real media metadata and playback state where exposed.
- Implement supported playback controls in both directions.
- Synchronize volume only through appropriate APIs.
- Detect unsupported/unavailable sessions honestly.
- Investigate phone-as-PC microphone/speaker and supported phone-audio-to-PC routing.
- Use appropriate Linux audio integration such as PipeWire where applicable.
- Respect Android playback-capture restrictions and apps that prohibit capture.
- Do not report audio streaming as successful until the path has been tested.

### G. Webcam and microphone

- Support using the phone as a webcam and audio input when technically feasible.
- Integrate with supported Linux virtual-device facilities.
- Make activation, state, teardown and cleanup reliable.
- Show an explicit active indicator; never activate camera/microphone silently.
- Explain one-time dependencies/permission setup.
- Avoid root where possible. Explain and obtain authorization for any necessary system-level setup.

### H. Handoff

- Send a URL from one device to another and open it with a safe handler.
- Implement other handoff types only if genuinely supported.
- Validate incoming URLs and handle unsupported schemes safely.
- Show the receiving user what will be opened; do not execute arbitrary commands received from the network.

### I. Status

- Show connection, last-seen, capabilities, permission and service state.
- Show battery data when exposed by the OS.
- Attribute battery and status to the correct device when multiple devices are connected.

### J. Do Not Disturb and proximity

- Investigate DND synchronization where permitted.
- Implement proximity locking only when reliable and explicitly enabled.
- Automatic unlocking is a distinct security-sensitive feature: design, threat-model and opt in separately. Never weaken authentication to imitate Apple behavior.

### K. Tablet as an extended monitor

Investigate a real extended-desktop feature, not merely video mirroring. Where feasible implement virtual monitor create/teardown, video streaming, dimensions/orientation, pointer/touch, keyboard and stylus support, plus reconnects. Use compositor-specific capability detection. For Hyprland/Sway or other Wayland environments, test the real output/input path. Do not imply all Wayland compositors offer identical APIs. If hardware or cloud access prevents testing, mark it unverified.

### L. Remote input and automation

- Investigate supported keyboard, touchpad and input-control features.
- Treat ADB and privileged automation as optional sensitive capabilities, never a universal prerequisite for ordinary continuity features.
- Keep them disabled until explicitly configured; require authorization for device/actions; use least privilege; no root requirement for routine use.
- Never automatically enable Android debugging, bypass OS security, or execute arbitrary network-provided shell commands.
- Document setup and threat model. Keep core features working without ADB/Shizuku wherever Android permits.

### M. Hyprland and Quickshell integration

The target shell is **Quickshell**, not Waybar. Expose a documented local IPC or D-Bus API that Quickshell can consume. Provide a sample Quickshell widget/integration using actual backend state. At minimum expose device status, battery when available, transfer progress, clipboard actions, quick send actions, pairing/service status, and useful errors. Do not build the feature model around Waybar-specific assumptions. Integrate with Dolphin where practical and do not overwrite my desktop configuration wholesale.

Do not build the feature model around Waybar-specific assumptions. Integrate with Dolphin where practical and do not overwrite my desktop configuration wholesale.

### N. Desktop-triggered camera capture and document scanning

- Add a desktop action such as **“Take photo / scan document with phone”**. The computer should send a request to the paired phone; the phone must show a clear consent/foreground camera UI before opening the camera.
- On the phone, support capture, preview, retake and return/cancel. For document scans, investigate edge detection, crop, perspective correction and contrast cleanup; do not claim scanner-quality results without testing.
- Return the selected image/PDF over the authenticated local connection to a user-selected desktop destination or, where supported, the requesting app. Provide a real save/insert flow rather than only opening a file chooser after the fact.
- Show progress/errors; handle rotated images, large files, disconnects and cancelled capture. Never activate the camera silently. Keep capture/scan as a separate feature from webcam streaming.

### O. Recent photos and a shared local content shelf

- Provide an optional, privacy-conscious way to browse selected/recent photos on the phone from desktop and send selected items to either device. Use scoped URI/MediaStore access and only request the relevant media permission when needed.
- Create a small **local-only recent activity/content shelf** for sent/received items, URLs and handoff actions with timestamps and transfer status. Make retention configurable and provide clear-history controls. Avoid storing full clipboard text or notification bodies by default.
- Support drag-and-drop and copy/share actions where the platform APIs allow them. Make the destination and whether an operation copies, moves or shares explicit.

### P. Optional Android screen mirroring and control integration

- Investigate and prefer reuse/integration of the official **scrcpy** project: https://github.com/Genymobile/scrcpy. Consider an app action that starts/stops a managed scrcpy session and reports its status, instead of duplicating its video/input/audio stack without need.
- Support a documented USB or TCP/IP workflow where available, with explicit enabling/authorization of Android debugging and clear active-session status. Keep mirroring independent of ordinary continuity features; users who do not enable debugging must still have the core app.
- Consider clipboard, audio forwarding, camera-as-webcam and virtual-display modes only after checking the current upstream capabilities, licenses, target device and exact prerequisites. Do not embed or redistribute scrcpy binaries without license compliance and source/version disclosure.
- Xiaomi devices may require a distinct USB debugging security setting for input injection. Detect/document this requirement where confirmed; never attempt to bypass device confirmation or silently enable debugging.

### Q. Calls, text messages and contact continuity

Investigate a staged communications bridge, inspired by Apple call/text forwarding and Windows Phone Link, without claiming unsupported iMessage/RCS integration.

- At minimum, show accurate incoming/ongoing call notifications where an available Android signal exposes them, and offer only actual available notification actions. Prevent sensitive call content from leaking to an untrusted desktop.
- Investigate SMS/MMS read/send/reply only through a documented, supported route with clear permissions, role requirements and distribution implications. Android SMS/call permissions and APIs can require default-handler roles or carry policy restrictions; do not silently request that the app become the default dialer or SMS application.
- Treat RCS and private content in third-party messaging apps as unsupported unless the app/system exposes a supported API or user-visible notification action. Never scrape private app databases or bypass Android security.
- Investigate native call answer/reject/control separately from audio routing. Prove whether the specific Mi 12/HyperOS + Linux audio stack supports a real calling path, such as a separately configured Bluetooth hands-free route. Receiving a notification is not equivalent to answering a call, and answering a call is not equivalent to relaying call audio. Report each capability separately.
- Optional contact lookup must be opt-in and minimal. Prefer launching a system-supported `tel:` or `sms:` action where a full call/messaging bridge is unavailable.

### R. Hotspot and connectivity assistant

- Help the desktop recover connectivity when the phone is the available internet/network path. Detect relevant connection state where feasible and explain options in clear language.
- Provide one-click instructions/open-settings affordances for enabling the phone hotspot, and connect to a previously configured hotspot through NetworkManager only after explicit user action. Never scrape hotspot passwords or silently enable tethering.
- Evaluate USB tethering as a useful, local/private high-bandwidth transport for file transfers or screen streaming. Detect the resulting network interface where possible and use the same authenticated application identity/protocol without requiring internet access.
- Treat BLE as a discovery/presence path unless the selected protocol proves it is suitable for data. Implement a transport abstraction so Wi-Fi LAN, USB tethering or other explicitly supported routes can share the same trust model.

### S. Find device, presence and proximity helpers

- Add **Ring phone / Find my phone** from desktop and **Ping desktop / Find computer** from Android. Use a user-visible sound/vibration/notification on the target where OS APIs permit it. Do not require GPS/location tracking for LAN-based ringing.
- Show per-device online/nearby/last-seen state and whether the signal came from a real authenticated connection, BLE proximity or a stale cache. Distinguish “nearby” from “connected.”
- Proximity-based screen locking can be an explicit opt-in. Never implement automatic unlock by default and never weaken OS lock/authentication controls.

### T. Android Quick Settings tile and companion controls

- Provide an Android Quick Settings tile where supported for quick access to connection state and a small set of safe actions such as pause/resume clipboard sync, open the app or trigger a user-approved share workflow. Respect lock-screen state and Android TileService lifecycle semantics.
- Use an ongoing notification/foreground service only when genuinely required by Android and permitted; keep it low-noise, informative and honest about the current connection. Do not keep a service alive merely to fake a persistent “connected” indicator.
- Provide desktop keyboard shortcuts and Quickshell quick actions, with user-visible enablement and conflict-safe installation/removal. Sensitive operations should require unlocking/confirmation where appropriate.

### U. Safe context-aware automation and extension boundaries

- Consider a small declarative rules engine for local events, such as “notify me when a paired device reconnects,” “pause clipboard sync in privacy mode,” “ask before accepting files,” or “show the camera-capture action when requested.” Rules must be visible, explainable, editable and off until enabled.
- Do not implement unrestricted remote shell execution or a general arbitrary-script plugin runner. Network-originated events must not trigger destructive/system-changing commands.
- If Shevery module compatibility or a separate diagnostic module is pursued, keep it optional, manually invoked or tightly policy-gated, audited and independently revocable as described in the dedicated Shevery section. Prefer the app's own allowlisted diagnostic API for normal operation.

### V. Privacy dashboard and safe defaults

- Add one place on both platforms for per-feature toggles, paired-device trust/revocation, clipboard direction and sensitive-content behavior, notification categories, folder grants, recent-item retention, camera/microphone activity and optional ADB/Shizuku integrations.
- Provide an easy pause/privacy mode that temporarily stops clipboard sync and sensitive forwarding without deleting pairing. Make clear which capabilities are paused and whether existing transfers continue.
- Mark active camera/mic/desktop-control sessions visibly; provide a fast stop action. Keep the privacy dashboard synchronized with real backend state.
- Never make “remember me” or auto-reconnect silently grant a new permission or extend a device's privileges.

### Android-Dex / DeX Workspace (required, not a stretch goal)

Implement a clearly visible **“DeX Workspace” / “Android Desktop”** entry in the Linux application. This must provide a working DeX-like session on the target Xiaomi Mi 12 / HyperOS device to the greatest extent its actual Android build supports. Treat this as a first-class product capability alongside Continuity.

Research and implement, in order of safety and capability:

1. **Device manager:** detect USB-connected and authorized wireless-ADB devices; show model/alias, connection transport and state; support selecting among multiple devices; explain how to authorize a new computer; support device disconnect/reconnect without restarting the full application. Never bypass Android's debugging confirmation.
2. **Automatic workspace mode selection:** probe whether the connected device supports a real Android/OEM desktop-mode or virtual-display workflow. Attempt a real DeX-like/windowed mode only when the detected capability and required APIs support it. Fall back promptly and explicitly to supported screen mirroring/control if native desktop mode cannot be used. Show the chosen mode and why. Do not mislabel ordinary full-screen screen mirroring as native DeX.
3. **App/workspace launching:** where supported by the actual device/API/toolchain, allow opening and managing Android apps in desktop-like resizable windows, with correct keyboard/mouse input, focus, window sizing and switching. Evaluate the supported scrcpy/AOSP/OEM virtual-display and multi-window paths. A single full-screen mirrored display does not count as independent per-app windows. If independent app windows are unavailable on the target HyperOS build, expose the best tested fallback and mark the limitation clearly rather than faking it.
4. **Session engine:** supervise scrcpy/ADB or the validated equivalent as child processes through a narrow backend API; handle startup readiness, authorization, unexpected exit, transport changes, retries/backoff, stop/cleanup and session restoration. Never construct shell commands from untrusted UI/network strings; use allowlisted executables/arguments and safe subprocess APIs.
5. **USB and Wi-Fi:** support USB and user-authorized wireless debugging when available. Provide a guided pairing flow for Android Wireless Debugging, safe saved-device selection and recovery after IP changes. Do not expose unauthenticated ADB over the LAN or leave debugging enabled silently. Explain when using USB tethering is useful and distinct from ADB-over-Wi-Fi.
6. **Desktop-grade interaction:** provide keyboard/mouse control when authorized; investigate shortcuts, copy/paste, rotation/resolution/DPI, screen-off behavior, multi-device switching and game-controller input where the actual tools/device permit them. Add only controls with a real backend implementation.
7. **Audio/media and device tools:** integrate compatible media controls, audio forwarding, notification state, screenshot/screen-record controls and a recent-files/downloads surface only where there is a working supported implementation. Keep continuity notification/media features shared where possible so duplicate managers do not fight over the same device. Treat per-app audio as a separate capability that must be proven on-device, not assumed.
8. **UI/UX:** the testing build may use a functional session dashboard with device selector, mode, screen/session preview, connection status, logs and start/stop/reconnect controls. In the final UI, polish this into a cohesive workspace with a window/app launcher or session organizer where the backend supports it. Do not sacrifice reliable controls for visual effects.
9. **Shared services:** reuse the same secure file-transfer/clipboard/content layer as Continuity when appropriate, but keep privileged ADB session control isolated from the local Continuity protocol. Explain which operations require ADB and which do not.
10. **Capabilities and fallback:** maintain an explicit capability matrix for the actual target phone: native desktop mode, virtual display, single-screen mirroring, independent app windows, keyboard/mouse injection, audio forwarding, screen off, clipboard, screenshot, recording and wireless reconnection. Every capability must be marked implemented/tested, partial, blocked, or not verified.

### Android-Dex upstream reuse and licensing boundaries

- Use Misael-art's `android-dex-kit` and `android-dex-ui` as the main open-source implementation reference because their documented Qt/QML + daemon + allowlisted toolkit boundary aligns with the desired desktop stack. Inspect the actual current source, LICENSE, dependency licenses, architecture contract, tests and target limitations before deciding whether to integrate code or only patterns. Keep required MIT attribution/notices if code is copied.
- Use Shrey113 Android-Dex's public release notes/docs only as a feature checklist and UX reference unless its maintainer gives written authorization to reuse/redistribute its proprietary software. Do not include its prebuilt downloads in our artifacts or pretend its features are open source.
- Prefer the official `scrcpy` upstream for screen mirroring/input/audio paths where feasible; respect its current license and keep its version and installation provenance documented. Do not reimplement its mature video path without a reason.
- Do not merge the separate `android-dex-flash` / bootloader / firmware-writing subsystem into the continuity or DeX runtime by default. These operations can brick a device and are outside ordinary DeX use. If the existing workspace includes such maintenance tools, preserve them as a separate, explicitly optional, fail-closed project/component; do not invoke them in diagnostics or normal setup. Do not add unlock/flash/root features as part of the default product merely because the repository includes a separate toolkit.

## 6. Shevery ADB Modules: optional, carefully bounded exploration

Shevery documents ZIP-based ADB Modules stored in its private storage and executed through its active Shizuku server. Its module format includes `module.prop`, user-triggered `action.sh`, optional policy-gated `service.sh`, optional local WebUI, enable/disable state and last-run logs. Its docs describe safe/custom/full modes, background-action gates, path/size/output limits and timeouts. It is not a generic module system to drop directly into this project, nor is it Magisk/KSU systemless module compatibility.

Investigate these uses:

1. **Diagnostic helper:** if useful and safe, create an optional module or equivalent narrowly scoped diagnostic workflow that collects Android OS/build identifiers, app/service state, granted relevant permissions, connectivity results and capability signals for the batch-test report. Redact tokens, private identifiers where unnecessary, personal notifications, clipboard contents and secrets.
2. **Advanced optional actions:** identify any specific Android API limitation that a Shizuku-backed action can safely address. Document the exact added capability, required server mode, permissions and failure behavior.
3. **Setup/testing assistance:** consider a user-triggered test helper only when it has a clear purpose and can be audited. Keep ordinary pairing, transfer, notifications and other core paths independent of it.
4. **Module compatibility decision:** determine whether this project should merely document compatibility with Shevery/Shizuku, provide a small optional adapter to the Shizuku API, or publish its own isolated module package. Choose based on actual source/API inspection, not assumptions.

Mandatory safety rules:

- Do not make Shevery or Shizuku a dependency for core functionality.
- Do not require root; distinguish ADB-shell privileges from root privileges.
- Never run downloaded modules silently, auto-trust a module, or enable background script execution by default.
- Do not implement an unrestricted arbitrary-script runner merely for convenience.
- If modules are used, inspect source and checksum before installation; show the exact operations and require user confirmation; sandbox/limit paths, input size, runtime, output and network access; log results without leaking secrets; make revocation/removal clear.
- Do not require a GitHub personal access token simply to run the core app.
- Do not copy Shevery's implementation without checking exact-file licensing and attribution.
- If the benefits do not outweigh the privilege and maintenance risks, document that conclusion and leave the core design independent.

## 7. Security and privacy

Security is a core acceptance requirement, not a later enhancement.

### Identity and transport

- Local network by default; no mandatory cloud account, relay, cloud storage or telemetry.
- Use an established secure transport and authenticated peer identities.
- Use correctly verified mutual TLS with pinned certificate fingerprints, or another well-reviewed mechanism suitable for the stack.
- Prevent silent identity replacement; define trust renewal/re-pairing.
- Authenticate sensitive protocol operations; consider replay resistance, malformed messages, timeouts and malicious peers.
- Bound frame/message sizes, file sizes, queues and concurrent operations.
- Validate all incoming data and avoid unnecessary listeners/network exposure.
- LAN presence is not authorization.

### Sensitive operations

- No root requirement for routine features.
- No silent permission escalation, camera/mic/screen activation, arbitrary remote shell or destructive sync.
- No automatic unlock without a separately reviewed, opt-in design.
- Request only permissions needed for enabled features.
- Revoke trust and clean up resources when a device is removed.
- Never log credentials, private keys or unnecessary sensitive user content.
- Do not add analytics/telemetry.

### Security tests

Review pairing, certificate persistence, reconnect authentication, authorization, path handling, permissions, shutdown and trust revocation. Test untrusted peers, changed identities, malformed/oversized messages, interrupted transfers, transfer tampering, duplicate requests and unsafe paths where feasible. A README claim is not proof of security; document tested versus unverified areas.

## 8. Cloud build environment: detect, build, package and export APK

Assume development may occur on a cloud Linux VM/container rather than my own Arch installation. The OS may be Ubuntu/Debian, Arch, or something else. **Detect the actual environment first** (`/etc/os-release`, architecture, available RAM/disk, Java, Git, network, container runtime and permissions). Do not assume Ubuntu, and do not assume the cloud can access my physical phone or run a real Wayland desktop.

### Android APK build is mandatory where the environment permits

**Implementation-agent requirement:** run the first real build early, not after all features are written. Use the project’s existing Gradle Wrapper and actual configured JDK/AGP/SDK requirements; save the complete command and build log. Then rebuild after each major integration and once at the end. If the cloud environment cannot reach Android SDK repositories, report the exact failed URL/command and continue with all offline/static tests possible—do not claim an APK was produced.

Build the Android APK from Linux using the project’s Gradle wrapper and Android SDK command-line toolchain. Do not confuse the `android-tools` OS package / Android Platform Tools (`adb`, `fastboot`) with the Android SDK build toolchain: `adb` is for device communication/install/logs, while APK compilation requires Gradle plus a compatible JDK, Android SDK platform, build-tools, and any project-required NDK/CMake packages.

- Inspect `gradlew`, Gradle plugin version, Java requirements, `compileSdk`, `targetSdk`, `minSdk`, NDK/CMake requirements and flavors before installing versions.
- Prefer the repository Gradle wrapper; do not use an arbitrary system Gradle version unless the wrapper genuinely cannot work.
- Install Android SDK command-line tools from the official source, configure `ANDROID_HOME` or `ANDROID_SDK_ROOT` consistently with the project, and use `sdkmanager` or the currently recommended official CLI to install the exact required `platforms;android-XX`, `build-tools;XX`, `platform-tools`, and other required packages.
- Accept SDK licenses through the documented noninteractive mechanism when allowed.
- Use Java compatible with the Gradle wrapper and Android Gradle Plugin. Do not blindly install the newest JDK if the project requires another version.
- Build the debug/testing APK with the correct Gradle task, typically `./gradlew assembleDebug` from the Android project root. If the Android Gradle project is a subproject or has named flavors, inspect available tasks and invoke the exact appropriate task.
- Also run tests/lint that are feasible; report build output and failures honestly.
- Locate the resulting APK under the appropriate `build/outputs/apk/` path, verify it exists and is non-empty, inspect it with `apkanalyzer` if available, and verify its signature with `apksigner` when possible.
- Copy artifacts into a predictable `artifacts/android/` directory with clear version/build metadata. Provide SHA-256 checksums and an artifact manifest.
- Preserve logs and a concise build report. Never claim APK success without checking the actual output.

Use `adb` to install the APK, capture logcat and gather connected-device information only if a suitable device/emulator is accessible and authorized. If the cloud host cannot see the phone, still compile the APK, export it and give exact manual-install/testing instructions. Do not claim real-device tests in that case.

### Toolchain facts from the upstream projects (check again at build time)

| Project | Gradle wrapper | compileSdk / targetSdk | Other |
|---|---|---|---|
| kdeconnect-android | 9.6.0 | 37 / 37 (minSdk 23) | Kotlin 2.4.x; JVM target 11 |
| Sefirah-Android | 9.7.0 | read `build-logic` | AGP 9.3.x, Kotlin 2.3.x |
| linux-link/android | 9.6.1 | 35 / 35 (minSdk 33) | Compose, JVM 17 |
| vortex/android | 8.13 | 36 / 36 (minSdk 29) | AGP 8.13.x, JVM 17 |

Use a JDK that satisfies the strictest wrapper and AGP in the project you are actually building (17 is the usual floor for current AGP; read the AGP compatibility table instead of guessing). If `sdkmanager --list` does not offer the platform the project requires (for example `platforms;android-37`), report that and stop on that module: **do not silently lower `compileSdk`**.

Desktop: Rust (`rustup`, stable; the `linkd` crate uses edition 2021 and tokio/quinn/rustls/bluer/zbus). Qt 6 and KDE Frameworks 6 development packages for the QML app. Runtime tools used by features: `scrcpy` (≥ 3.0 for `--new-display`, current release preferred), `android-tools`, `ffmpeg`, `v4l2loopback-dkms` + matching kernel headers, `pipewire-pulse`, `wf-recorder` (Hyprland screen capture), `sshfs` or GVfs. Verify every package name with `pacman -Ss`/`pacman -Si` and print install commands for my approval (Section 0.3).

### Ubuntu/Debian path

If the host is Ubuntu/Debian, install only the required packages using that system's package manager. Typically this includes Git, a compatible JDK, unzip/zip, and dependencies required by the project; install the Android SDK command-line tools separately from the official Android developer source. Do not assume `apt install android-tools` alone can build an APK.

### Arch path and Distrobox fallback

If the host is Arch Linux, use pacman for appropriate OS dependencies and the same official Android SDK/Gradle process. If the cloud host is Ubuntu/Debian but Arch-specific packaging or dependencies are needed for the **desktop component**, check whether Podman/Docker and Distrobox are available and permitted. If so, create a user-owned Arch Distrobox container to build/package the Arch desktop component with `pacman`/AUR only where justified. Explain any need for host setup and do not use privileged container settings without authorization.

Distrobox is a userland compatibility/container workflow, not a full VM. Do not claim it reproduces a real Hyprland + Quickshell Wayland session, PipeWire hardware, webcam devices or Android USB/Bluetooth access automatically. Build in the container where useful, but mark compositor, hardware, camera/microphone, Bluetooth discovery and physical-phone integration as unverified if the cloud environment lacks those facilities.

### Reproducibility and artifact handling

- Prefer a repeatable script such as `scripts/build-android.sh` and, if useful, `scripts/build-desktop-arch.sh` with clear prerequisites, error handling and version detection.
- Do not hard-code a single cloud provider or home directory.
- Do not put signing keys, passwords, GitHub tokens or secrets into the repository, logs or build artifacts.
- Debug APK is appropriate for testing and should be identified as debug-signed. Do not treat it as a production release.
- For release signing, require a user-provided protected keystore or CI secret; never create, upload or expose a real release key without authorization.
- Export APK, checksums, build/test report, relevant logs and exact install commands in a predictable directory.

## 9. Full diagnostics action and batch-test report — required

Implement a **“Run Full Diagnostics”** action in the testing GUI and a corresponding CLI command or script (for example `continuity-diagnostics`). This is an explicit deliverable, not a suggestion.

The diagnostics action must run all safe, relevant checks and produce a unified report that I can hand to an AI agent to debug multiple failures at once.

### Required diagnostic sections

1. **Environment:** OS/distro, kernel, architecture, session type, Wayland/compositor and Quickshell versions when detectable; application versions and Git commit.
2. **Build:** Java/JDK, Gradle wrapper, Android Gradle Plugin/SDK versions, SDK licenses/status, build outputs and test/lint status.
3. **Desktop integration:** daemon/service state, IPC/D-Bus reachability, dependencies, permissions, Quickshell connectivity, Dolphin action availability and relevant optional packages.
4. **Android:** OS/build identifiers only as needed, app version, SDK compatibility, granted/denied relevant permissions, background/battery restriction status where available, and service state.
5. **Discovery and transport:** interface availability, supported discovery mechanisms, listener/port status, last discovery/connect attempts, pairing/trust-store health and sanitized connection errors.
6. **Feature capability matrix:** clipboard direction/mode, file transfer, folder sync, recent photos/content shelf, camera capture/document scan, notification access/reply support, call state/SMS/audio path (each separately), media sessions, audio, webcam, hotspot/tethering assistance, Continuity screen mirroring, Android-Dex workspace mode (native desktop/virtual display/single mirror/independent app windows as separate capabilities), ADB device/authorization state, USB/Wi-Fi reconnect, keyboard/mouse control, screenshot/recording, per-app audio status, find-device/presence, Android Quick Settings tile, DND, handoff, second-screen/input, privacy mode and optional Shevery/Shizuku adapter status.
7. **Resource behavior:** safe snapshot of CPU/memory usage, active process counts, idle-loop warnings, active transfers/queues and relevant timeouts.
8. **Security posture:** trust state, peer identity verification state, certificate validity/fingerprint status without private keys, unexpected listeners, unsafe configuration checks, permission boundaries and optional privileged capability state.
9. **Recent failures:** sanitized recent error messages, correlation IDs, test IDs, error codes and timestamps; include small relevant log excerpts rather than unbounded logs.
10. **Suggested next actions:** actionable remediation tied to failed checks, without declaring a root cause unless evidence supports it.

### Diagnostic behavior and privacy

- Display live progress and individual pass/fail/warn/blocked/not-tested results.
- Never change firewall rules, permissions, trust, system services or privileged settings automatically as a side effect of diagnostics.
- Any repair action must be separate, explain its effect, and require confirmation where it changes system/security state.
- Redact clipboard content, notification bodies, file contents and paths that unnecessarily reveal private data, tokens, passwords, private keys, wireless credentials, serial numbers and unrelated identifiers.
- Never collect a full arbitrary environment dump. Use an allowlist of relevant fields.
- Cap log sizes and execution time, and make cancellation safe.
- Export both machine-readable JSON and a human-readable Markdown or text report into an explicit output location. Show that location in the UI and provide a one-click “Copy sanitized summary” action.
- Include report schema/version, app version, commit and generated timestamp. State which checks could not run because the device, permissions, or required tools were unavailable.
- Diagnostics must not require Shevery/Shizuku to run core checks. A separately selected optional privileged diagnostic may add more data only after explicit authorization.

### Batch-test matrix

For every feature, create a reproducible matrix with:

| Field | Requirement |
|---|---|
| Feature/test ID | Stable unique identifier |
| Platform | Android, Linux, both, cloud-only or hardware-dependent |
| Preconditions | Permissions, dependencies, device or setup |
| Procedure | Concrete repeatable steps |
| Expected result | Observable outcome |
| Actual result | Evidence-based outcome |
| Status | Pass, fail, blocked, skipped or not verified |
| Evidence | Sanitized logs, test output or observation |
| Follow-up | Root cause, fix or next experiment |

The “Run Full Diagnostics” action should include the applicable automated checks and link or map results to this test matrix. It must not label a feature as passed solely because compilation succeeded.

## 10. Test journeys and full integration

These five real-device journeys are minimum acceptance tests, not the whole test plan:

1. **Pair once:** pair the phone and computer, explicitly approve trust and establish an authenticated connection.
2. **Reconnect:** interrupt/restart components or network where practical, recover connection and verify accurate UI updates.
3. **Transfer a file:** transfer a real file both directions where supported, show progress and verify its contents/checksum.
4. **Clipboard handoff:** copy content on one device, use the supported path, verify it on the other; demonstrate permission requirements/manual fallback.
5. **Notification reply:** mirror a real notification and send a reply through an actual supported Android notification action.

Also test:

- simultaneous clipboard/file activity;
- interrupted transfers and duplicate names;
- Wi-Fi/IP changes and sleep/wake;
- sync edits, deletes, offline conflicts and conflict resolution;
- notification updates/dismissals and duplicate suppression;
- multiple devices if supported;
- media/audio/video device start-stop lifecycle;
- revoke/re-pair and changed identity;
- Quickshell state updates and backend reconnect;
- safe failure of an optional feature without breaking core features;
- missing/denied permissions;
- diagnostics action, JSON/Markdown export, redaction and cancellation;
- desktop-triggered phone camera capture/document scan and user cancellation;
- Android Quick Settings tile state/action behavior;
- scrcpy integration session start/stop and authorization failures if implemented;
- Android-Dex workspace launch, supported mode detection, correct native-mode-versus-mirror labeling, ADB authorization, USB and wireless reconnection, device selection, keyboard/mouse control, resize/focus, multi-window capability (if available), audio/media paths, screenshot/recording controls and complete process cleanup;
- phone ring/desktop ping and distinction between BLE-nearby and authenticated-connected states;
- hotspot-assistant user confirmation and USB-tether transport if implemented;
- optional communications checks with SMS, calls, replies and call audio reported as separate capabilities.

Cloud builds can verify compilation and many automated tests, but they cannot by themselves prove behavior on the actual Xiaomi phone or a live Hyprland/Quickshell session. Clearly separate unit-tested, integration-tested, emulator-tested, real-device-tested and not-verified results.

## 11. Development sequence (continue without approval at each stage)

### Stage 1 — Inspect

- Check workspace, instructions and Git status.
- Detect the actual host OS, network, disk/RAM, Java, SDK, container runtime and available test devices.
- Research relevant upstream sources and licenses.
- Record architecture, dependencies, risks and implementation plan.

### Stage 2 — Foundation

- Implement protocol and backend boundaries.
- Establish identity, discovery, pairing, trust storage and lifecycle.
- Set up the Android and desktop build environments.
- Establish reliable logs/errors, diagnostic data model, test harness and shared design tokens.
- Compile and test the foundation.

### Stage 3 — Feature-complete implementation

Continue through all required feature groups in dependency-aware order. Integrate files, folder sync, notifications, audio/video, handoff, input/second-screen investigation, desktop actions, Quickshell and optional Shevery/Shizuku path. Do not stop at the first three core capabilities. Keep modules independent enough for failures to be isolated.

### Stage 4 — Integrated batch testing

Build the integrated testing version. Run automated tests, diagnostics and the broad feature matrix. Prioritize common roots for failures, fix and re-run relevant checks. Do not ask me to approve ordinary feature-to-feature transitions.

### Stage 5 — GUI polish

Once the test build is testable, refine both GUIs: coherent light/dark design, typography, spacing, icons, accessibility, responsive states, onboarding, permission explanations, errors and the Quickshell experience. Hide developer clutter from the regular UI but retain accessible diagnostics. Re-test the primary user journeys after UI changes.

### Stage 6 — Release candidate

Build and verify artifacts where the environment supports it. Deliver APK, desktop build/package where possible, checksums, test matrix, diagnostic report, install/uninstall instructions and known limitations.

## 12. UX and design requirements

### Testing UI

At minimum show actual device/connection states, permissions/capabilities, transfer queue and progress, clipboard status, notification/reply status, sync conflicts, media/virtual-device state, errors and diagnostic actions. Use clear labels and error states. Keep controls functional and avoid unsafe actions by accident.

### Final GUI

The final product must have a deliberately designed, consistent UI on Android and desktop. Include sensible visual hierarchy, spacing, typography, icons, light/dark modes, keyboard accessibility where suitable, responsive layouts, real empty/loading/error/permission/disconnected states, pairing flow, functional controls and honest connection status. Establish canonical tokens for color, typography, spacing, radii and control sizes, then generate/map values into Compose and QML/Kirigami. Do not let dynamic Material You colors override a chosen product identity by accident. The product should feel unified while respecting each platform's conventions.

## 13. Performance and robustness

- Minimize idle CPU, battery and unnecessary wakeups.
- Avoid busy loops and needless filesystem rescans.
- Use bounded queues and cancellation-aware operations.
- Do not block UI threads.
- Clean up sockets, child processes, virtual devices and temporary files.
- Prevent duplicate transfers, reconnect storms and notification floods.
- Make error recovery deterministic where feasible.
- Isolate optional components so one unsupported feature does not break the rest.
- Measure idle and active resource use instead of merely claiming efficiency.

## 14. Installation and documentation

Provide:

- exact Linux and Android build/install commands;
- prerequisites and version requirements;
- reproducible build scripts;
- cloud build instructions and artifact locations;
- service start/stop and status commands;
- pairing and Android permission steps;
- firewall needs if any;
- Quickshell example/configuration and Dolphin integration;
- optional system setup, with explanation before privileged modifications;
- full-diagnostics command, report schema and output location;
- batch-test matrix and known limitations;
- safe uninstall and cleanup instructions;
- licenses and third-party attributions.

Do not overwrite my Hyprland, Quickshell or Dolphin configuration wholesale. Make integrations reversible. Do not run destructive commands against unknown files or change system-wide settings without explanation and authorization.

## 15. Git and delivery discipline

Preserve existing history, branch and working-tree changes. Do not discard modifications, force-push or commit secrets. Use clear commits where practical; test before calling a checkpoint stable. Do not stop for approval between routine milestones. Do not claim any commit, clone, build, installation, push or test occurred unless it actually did.

## 16. Definition of done

The feature-complete testing delivery is ready when:

1. Android and desktop projects build where the environment allows.
2. The integrated backend and frontends communicate over the real protocol.
3. Feasible required features have real implementations, not mock controls or TODO-only screens.
4. The five required demonstration journeys have reproducible tests and honest status.
5. Every continuity-parity item in the independent audit has an implementation, a safe partial equivalent or a documented evidence-based blocker.
6. Every other feature has a test result or a specific blocker.
7. Pairing, identity, security boundaries and trust revocation have been tested as far as the environment allows.
8. HyperOS, Android, Wayland, Hyprland and Quickshell limitations are accurately documented.
9. The full-diagnostics GUI action and CLI, sanitized JSON + human-readable report, and complete batch-test matrix are delivered.
10. The debug APK is built, signature-checked where possible, checksummed, and exported to a known artifact directory when Android builds are available.
11. The test build can be installed and tested with no undocumented assumptions.
12. The final UI polish pass is completed before claiming the final product is ready.
13. Android-Dex/DeX Workspace remains a visible, working first-class mode with device selection, session supervision, accurate mode/capability reporting, supported interaction controls and a real fallback when native DeX is unavailable. A mere single-screen mirror does not satisfy the independent-app-window requirement, although it may be reported as the tested fallback when the target device cannot support more.

Do not call the project finished merely because it compiles. Do not hold back the feature-complete testing build for cosmetic perfection. The release is not complete until both GUIs are polished and the main journeys are reliable.

## 17. Required final report

At completion, give me:

1. Implemented features and their status.
2. Features that passed end-to-end tests; failures and unverified capabilities.
3. Which upstream repos were actually cloned versus remotely inspected, plus relevant commit SHAs and licenses.
4. Build/install commands for Android and desktop.
5. Path to the APK, desktop artifacts, checksums and build manifest.
6. Path to the batch-test matrix and full-diagnostics JSON/Markdown report.
7. How to run diagnostics and the entire batch-test suite.
8. Feature-parity audit: which Apple-inspired capabilities were implemented, partially implemented, blocked or intentionally unsupported, with links/evidence.
9. How to pair devices and enable required Android permissions.
10. Known blockers, security/licensing concerns and target-device limitations.
11. Actual Git branch/commits and current working-tree status.
12. The highest-value next debugging tasks based on the observed evidence.

**Primary objective:** deliver one integrated, feature-complete test build so I can hunt down many errors in a batch. Preserve and implement both the Apple-like Continuity feature set and the Android-Dex/DeX Workspace mode. Make the system observable and easy to debug, build/export the APK from a cloud Linux environment where possible, use Distrobox/Arch only when helpful for desktop-specific work, keep Shevery modules optional and permission-gated, and then polish the final cross-platform GUI without compromising functionality, privacy, security or honest reporting.

## 18. Android 15 / HyperOS notes (apply while implementing; verify items marked V on developer.android.com or on the device)

- Sensitive notifications are redacted for listeners on Android 15. Documented fix: `adb shell appops set <package> RECEIVE_SENSITIVE_NOTIFICATIONS allow` (verified text in Sefirah-Android). Offer it as an explicit, optional step I run; never auto-run.
- Sideloaded builds need "Allow restricted settings" (App info) before notification access or accessibility can be turned on. Put this in onboarding.
- Pick the correct foreground-service type per feature. **V:** Android 15 added time limits for `dataSync` services; do not use it for the persistent connection. Prefer companion-device presence and `connectedDevice` where applicable.
- **V:** Screen capture needs per-session user consent and the matching foreground-service type; design for the user stopping it from the system UI.
- Background clipboard reads stay blocked; use the foreground/Quick Settings/share paths from Section 5.B, with Shizuku or overlay as explicit opt-ins.
- Xiaomi/HyperOS: set Autostart on and battery to "No restrictions" for the app (**V** on the device); for scrcpy input, enable "USB debugging (Security settings)" and reboot (verified in scrcpy's FAQ). Never bypass the confirmation dialogs.
- Native desktop windowing/connected displays belong to Android 16 QPR3 and later devices. Detect, do not assume, on this phone. The working path is the scrcpy virtual display.

## 19. Design system and UI reference

- `design/tokens.json` is the canonical source: Catppuccin Mocha by default (dark) with a Latte (light) theme, state colours, radii, spacing, type scale. Generate `Theme.qml` and Compose theme files from it with a script, and add a test that fails if the generated files drift from the tokens.
- Dynamic Material You colours are off by default. Status is never colour-only (icon + label). Camera/mic/screen/desktop-control activity uses the `camera_mic_active` colour plus a persistent indicator and a one-click stop.
- `design/ui-concept.html` shows the intended layout language: a compact Quickshell status popup, the desktop app's Devices/Transfers/DeX/Privacy sections, and the Android home, share and privacy screens. It is a visual reference for the Stage 5 polish pass, not a spec to copy pixel for pixel. The testing build can stay utilitarian.



## 20. v6 handoff note

This prompt is intended for the implementation agent (currently Freebuff), following Claude's research pass. Treat the supplied `PATCH_NOTES_CLAUDE.md`, `FEATURE_GAP_ANALYSIS.md`, `VERIFICATION_REPORT.md`, `REPO_SHAS.tsv`, and design assets as the research handoff. Do not ask Claude to build, and do not treat the research pack's explicit lack of builds/device tests as a failed task. The implementation task now is to inspect the real product workspace, reproduce the actual baseline build, implement the complete product, run available tests, export real artifacts, and clearly identify tests that require the physical Mi 12 or the target Hyprland/Quickshell session.
