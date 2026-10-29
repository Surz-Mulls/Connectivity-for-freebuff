# Feature-gap analysis — what v4 missed, and what v5 adds

Sources used (web, checked 2026-10-28):
- macOS Tahoe 26 Continuity additions (Phone app on Mac, Live Activities in the menu bar that open in iPhone Mirroring when clicked): Apple press release via businesswire.com/news/home/20250609265520/en, and AppleInsider, "macOS 26 Tahoe Phone app greatly improves taking calls on your Mac".
- Android desktop windowing and connected displays (Android 16 QPR3): developer.android.com/blog/posts/android-devices-extend-seamlessly-to-connected-displays.
- Quick Share interop on Linux: github.com/Martichou/rquickshare and the Fero fork.
- Plus the cloned source: KDE Connect plugins, Vortex, Linux Link, LinLink, scrcpy docs.

## 1. Apple experience → status in v4 → what v5 does

| Apple experience | v4 | Gap / v5 action | Priority |
|---|---|---|---|
| AirDrop | Covered (own protocol, LocalSend as UX reference) | Add **Quick Share interop** via RQuickShare/Fero as an optional adapter so the phone's built-in share sheet works with no extra app on the phone. Our own authenticated path stays the default. | P2 |
| (no Apple equivalent; Android-native) | Not covered | **Direct Share target**: the laptop appears by name in Android's share sheet (sharing shortcuts). | P1 |
| Universal Clipboard | Covered | Add auto-expiry for forwarded sensitive text; note scrcpy has its own clipboard sync, so only one manager may own it per session. | P1 |
| Handoff | URL/text only | Add a **Vivaldi/Chromium WebExtension** (native messaging) for "send this tab to phone" and the Android `ACTION_VIEW` receive path. This is real handoff, not just a share sheet. | P1 |
| Continuity Camera (photo/scan) | Covered (N) | No change. | P2 |
| Continuity Camera (webcam/mic) | Covered (G) | Pin the mechanism: scrcpy `--video-source=camera` with `--v4l2-sink` is the lowest-effort route; compare with Linux Link's own webcam path. | P2 |
| iPhone Mirroring | Covered (P) | Add **per-app windows** via scrcpy `--new-display --start-app=<pkg> --flex-display` (one window per app). | P2 |
| **Live Activities click-through (macOS 26)** | Status panel only | **New:** clicking an ongoing item (ride, timer, media, call) in the Quickshell panel opens that app in a mirrored window (needs ADB authorised, otherwise falls back to "open on phone" notification). | P2 |
| **Phone app on Mac (macOS 26)** | Calls: notifications + investigation | **New:** a Phone panel with recents, favourites, contacts and dial-from-desktop where Android permissions allow (call-log and contacts are restricted permissions, opt-in). **Call Screening, Hold Assist and visual voicemail: not feasible** without system/carrier APIs. Marked as such. | P2/P3 |
| Sidecar | Covered (K) | Reference both Linux Link (Hyprland headless output + wf-recorder) and KDE Connect `virtualmonitor`; say plainly which one is tested. | P3 |
| Universal Control | Mentioned as maybe not available | **New:** two real paths exist: KDE Connect `shareinputdevices` and Vortex's InputCapture-portal approach. Need `xdg-desktop-portal-hyprland` InputCapture support, which Vortex lists as untested: the agent must test it. | P3 |
| Drawing tablet / Markup | Sketch only if cheap | KDE Connect `digitizer` plugin and Linux Link's stylus tablet device (pressure/tilt/eraser via uinput) are existing designs. | P3 |
| Instant Hotspot | Covered (R) | No change. | P2 |
| Find My / ring | Covered (S) | No change. | P1 |
| Auto Unlock / proximity | Lock opt-in; unlock off | Keep. Linux Link implements unlock with a polkit rule; v5 still forbids it by default. | P3 |
| AirPods auto-switch | Not covered | **New (investigate):** Bluetooth audio hand-off between laptop and phone (Vortex has "smart audio handoff"). Hardware-dependent. | P3 |
| iPhone notifications on Mac | Covered (E) | Add Android 15 redaction handling (see section 3). | P1 |
| Verification codes autofill | Not covered | **New:** opt-in "SMS code → laptop clipboard, auto-clears" (Vortex does this). On Android 15 it needs either SMS permission or the sensitive-notifications appop, because OTP notifications are redacted for listeners. | P2 |
| Shared notes / reminders | Not covered | **New (optional):** shared Notes/To-dos in the content shelf (Vortex). | P3 |
| Presenter / media remote | Mentioned loosely | KDE Connect `presenter` plugin as the design reference. | P2 |
| Wi-Fi password sharing | Not covered | Skip: sharing credentials conflicts with the "never scrape hotspot passwords" rule. Guided QR via system UI only. | – |
| Apple Pay, iMessage, FaceTime, iCloud Keychain | Excluded | Stay excluded. | – |
| Native desktop mode (DeX) | Covered (first-class) | Clarify: Android 16 QPR3 connected-display desktop windowing is a *different* feature that targets Android 16 devices; on an Android 15 Mi 12 the working route is scrcpy virtual display. Detect, don't assume. | P1 |

## 2. Things v4 tells the agent to do that I would tighten

1. "Do not stop to ask between stages" is fine for build work, but v5 adds an explicit list of actions that **always** need your go-ahead (sudo, pacman/yay, modprobe, udev/polkit rules, firewall changes, `adb install`, enabling any debug setting, anything under `/etc`). v4 only said "authorization" in general terms.
2. v4 asks for the whole feature set in one batch. v5 keeps that, but requires a **STATUS.json heartbeat** and **commit after every module**, so you can watch progress and roll back one module without losing the rest.
3. v4 expects a Qt/QML desktop UI. v5 keeps it, and adds: no reference project ships a Quickshell integration, so the daemon must expose D-Bus + a JSON socket first, and the Quickshell widget is built against that.

## 3. Android 15 notes added to v5 (marked verify-before-relying where not checked in source)

| Topic | Fact | Source / status |
|---|---|---|
| Sensitive notifications | Redacted for listeners from Android 15; fix is `adb shell appops set <pkg> RECEIVE_SENSITIVE_NOTIFICATIONS allow` | Verified in Sefirah-Android README |
| Sideloaded app permissions | "Allow restricted settings" (App info) before notification access / accessibility can be enabled | Verified in Sefirah README |
| Background clipboard | Reads blocked in background | In v4; Linux Link and Sefirah use Shizuku/overlay |
| Foreground service types | Use the correct type per feature; Android 15 added time limits for `dataSync`, so do not use it for the persistent connection | From general knowledge, **verify** on developer.android.com |
| MediaProjection | Per-session consent; Android 14+ requires the `mediaProjection` FGS type | General knowledge, **verify** |
| Xiaomi/HyperOS | Autostart, battery "No restrictions", and **USB debugging (Security settings)** + reboot for scrcpy input | Last item verified in scrcpy FAQ; others are common Xiaomi guidance, **verify on the device** |
| Desktop windowing | Android 16 QPR3 feature, not Android 15 | Verified (Android Developers blog) |
