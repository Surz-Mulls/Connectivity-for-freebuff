# Verification report — v4 prompt vs. the real repositories

Date checked: 2026-10-28. Method: shallow `git clone` of every repo into a sandbox, then reading
LICENSE files, manifests, source layout and docs. Exact commits are in `REPO_SHAS.tsv`
(reproduce with `scripts/clone-research.sh`).

**What was and was not done.** Cloned and read: yes (14 repos). Built or run anything: **no**.
The sandbox could not reach the Android SDK download host, and has no phone, no Hyprland session and no
GPU, so every statement below is about *source and documentation*, not runtime behaviour.

## 1. Result in one paragraph

All 13 repository URLs in v4 resolve and the licence claims for Linux Link (GPL-3.0), Misael-art
android-dex (MIT), Shrey113 Android-Dex (proprietary), Shevery (Apache-2.0), scrcpy (Apache-2.0) and
LocalSend (Apache-2.0) are correct. The Misael-art architecture description and the Shevery module
format are correct. The scrcpy Xiaomi "USB debugging (Security settings)" note is correct and also needs a reboot.
Five things in or around v4 needed correcting; they are fixed in `MASTER_AGENT_PROMPT_v5.md`.

## 2. Repository table

| # | Repo | Pinned | Licence (verified from file) | Stack (verified) | Notes that change decisions |
|---|---|---|---|---|---|
| 1 | ArvinKavaskov/linux-link | 2297252 | GPL-3.0 (Cargo: GPL-3.0-or-later) | Rust daemon `linkd` v5.4.0 (tokio, quinn QUIC, rustls, bluer, mdns-sd, zbus, ksni tray, egui windows, evdev); Android Kotlin + Compose, minSdk 33 / targetSdk 35 | Pins peer cert SHA-256 after QR pairing, mTLS 1.3. UDP 47100 (QUIC) + 47101 (discovery). Hyprland second screen = `hyprctl output create headless` + `wf-recorder` + uinput. Tray is a StatusNotifierItem (Waybar `tray`). **No Quickshell code anywhere.** Author tested on Zorin + Honor only. |
| 2 | zoir-dev/vortex | 31995f2 | GPL-3.0 | Rust daemon (tokio, bluer, zbus) + **Tauri 2 / Vue 3** GUI; Android Kotlin + Compose, minSdk 29; protobuf + Noise | Beta. README says live-tested on **one** device pair (Redmi 9 MIUI + Ubuntu GNOME). Second screen is GNOME-only and view-only; Universal Control needs the Wayland InputCapture portal (tested GNOME 45+, Hyprland "untested"). GUI stack conflicts with the required Qt/QML, so reference only. |
| 3 | KDE/kdeconnect-kde | a19267a | Files carry `GPL-2.0-only OR GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL` | C++/Qt/KF; plugins incl. `virtualmonitor`, `shareinputdevices`, `digitizer`, `presenter`, `sftp`, `telephony`, `sms`, `remotecommands` | The dual licence lets you combine it with GPL-3.0-only code. `remotecommands`/`runcommand` are arbitrary-command features, which v4 forbids: do not port. |
| 4 | KDE/kdeconnect-android | d407078 | GPL-2.0-only OR 3.0-only (COPYING + LICENSES/) | Kotlin, Gradle 9.6.0, **compileSdk/targetSdk 37**, minSdk 23, JVM target 11 | compileSdk 37 means SDK platform 37 must exist in `sdkmanager --list`; check before promising a build. |
| 5 | shrimqy/Sefirah | 6db524a | GPL-3.0 | **C#/.NET** (Sefirah.csproj), Windows-first | README: "Support for linux is limited". Not a Linux parity source. |
| 6 | shrimqy/Sefirah-Android | 6596ffc | GPL-3.0 | Kotlin, Gradle 9.7.0, AGP 9.3.1 | README documents Android 15 sensitive-notification redaction and the fix `adb shell appops set <pkg> RECEIVE_SENSITIVE_NOTIFICATIONS allow` (verified text). Needs "Allow restricted settings". |
| 7 | THARUN-BART/linlink | e53fe15 | MIT | Flutter app (+ web/desktop dirs) and a Rust `linux-companion` | **Different project from Linux Link.** Claims calling with PC mic/speaker over TCP: a README claim; Android restricts call-audio capture for normal apps, so inspect `CallService` before trusting it. |
| 8 | manjeetdeswal/Use-As-Server | 9cfb651 | **No LICENSE file in repo.** README badge says MIT. | Python single-file servers (Linux: 2,088 lines): customtkinter, websockets, pyautogui, pyperclip, mss, opencv, pyaudio, pystray; shells out to **xdotool** | Not copyable until the author adds a LICENSE. Input/screen code is **X11-oriented, so it will not drive Hyprland natively** (needs XWayland at best). Its Linux guide tells users to `chmod 666 /dev/uinput`, which is unsafe: do not copy. The Android client is on Play Store only; its source is not in the repo. |
| 9 | HmnDev-Tech/shevery | 53d875f | Apache-2.0 (README: all code files) | Kotlin + Shizuku, Next.js site | `docs/adb-modules-api.md`: module = ZIP with `module.prop` at root, optional `action.sh`, `service.sh`, `webui/`. "Not a root overlay system." Matches v4. |
| 10 | Genymobile/scrcpy | a60891a | Apache-2.0 | C + Java server; **v5.0.1** | `--new-display[=WxH/dpi]`, `--flex-display`/`-x`, `--start-app`, `--no-vd-system-decorations`, `--no-vd-destroy-content`, `--keep-active`, camera source (`--video-source=camera`), `--v4l2-sink`, `--otg`, uhid/aoa keyboard+mouse, `--gamepad`. Drag & drop pushes files to /sdcard/Download. |
| 11 | localsend/localsend | cfd6991 | Apache-2.0 | Flutter app + Rust core/server | Default port 53317, multicast group 224.0.0.167 (verified in constants). UX/protocol reference. |
| 12 | Misael-art/android-dex | 8c95010 | MIT | `android-dex-ui` (PySide6/Qt Quick), `android-dex-kit` (bash + scrcpy + adb, systemd, udev), `android-dex-flash` (fastboot/heimdall/Magisk) | JSON-RPC daemon on a 0600 socket (README). Kit needs scrcpy ≥ 3.0 for `--new-display`, else falls back to mirror. Capability probing reads `enable_freeform_support` and `force_desktop_mode_on_external_displays`. Has a `xiaomi.env` profile. README is Portuguese. Keep `android-dex-flash` out of the product. |
| 13 | Shrey113/Android-Dex | 2deb812 | **Proprietary** (LICENSE text) | Flutter + Kotlin, closed source | Repo holds docs/website only. Feature/UX reference only: no copying, no redistribution. |
| 14 | Martichou/rquickshare *(added by this audit)* | 378d8ae | GPL-3.0 | Rust | Quick Share/Nearby Share for Linux. **Last upstream commit 2025-06-16**; active forks exist (alanjds, Fero). Known issue: Android drops its mDNS advertisement; workaround is a Bluetooth advert. |

## 3. Corrections

1. **Use-As-Server was listed without caveats.** It has no LICENSE file, is X11-only on Linux, and its Android app is closed. Use it as a feature checklist only.
2. **"Linux Link" and "LinLink" are two different projects.** v4's URL (ArvinKavaskov/linux-link) is the right Linux Link. LinLink is THARUN-BART/linlink. An earlier chat message of mine blurred them. Sorry about that; the table above is the corrected picture.
3. **Sefirah is not a Linux solution.** The desktop side is Windows-first C#. Only Sefirah-Android is reusable on your phone side. An earlier chat message of mine implied Sefirah gave you Linux SFTP mounting. That was wrong.
4. **Nobody supports Quickshell.** Every reference uses a StatusNotifierItem tray or GNOME extension. The Quickshell panel is new work, so v5 makes the daemon expose a documented D-Bus API plus a JSON socket.
5. **Vortex's "feature-complete" is the author's claim,** tested on one pair on GNOME. v5 does not count its Hyprland paths as proven.

## 4. Still unverified (needs your phone/laptop)

- Everything at runtime: pairing, reconnect, clipboard, notification replies, scrcpy `--new-display` on the Mi 12, Hyprland headless output, v4l2loopback, PipeWire virtual devices.
- Whether HyperOS on your Mi 12 honours scrcpy virtual displays with `--start-app`.
- Whether Quick Share on HyperOS (or Xiaomi's own sharing) is visible to RQuickShare.
- Android 15 foreground-service timeout details and MediaProjection rules: stated from general knowledge in v5, flagged "verify on developer.android.com".
- Native Android desktop windowing (connected displays reached general availability in Android 16 QPR3 per Android Developers). Not expected on an Android 15 Mi 12; v5 detects it rather than assuming.
