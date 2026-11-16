# User validation — what only you can run

The automated gates cover Linux packaging, Python/Kotlin tests, the AppImage, the makepkg metadata
and a `pacman -U` install in a container. They do **not** cover the phone, Hyprland, Quickshell,
Dolphin or a real Arch desktop. This page is the checklist for those rows. Record each result and
send back the files named at the end.

Use the assets from the same release; do not mix versions. Start with `sha256sum -c SHA256SUMS`.

## 1. Install the Android APK (Mi 12, HyperOS)

```sh
adb install -r continuity-android-debug.apk
```

On the phone:

1. Open **Continuity**. Grant the notification permission when asked.
2. HyperOS may block notification access for a sideloaded app:
   **Settings → Apps → Continuity → Allow restricted settings**, then
   **Settings → Notifications → Notification access → Continuity**.
3. Set **Autostart** on and battery saver to **No restrictions** for Continuity.
4. Do not enable USB debugging for normal Continuity features; it is only for the optional DeX
   Workspace mode.

Expected: the app opens without a crash and shows a connection screen. Send back a screenshot and
`adb shell dumpsys package dev.continuity.app | grep versionName`.

## 2. Pair once (B01)

On the laptop, from the unpacked portable tree or an installed package:

```sh
continuityd run
# second terminal
continuityctl pair begin
```

The command prints the host/port, a QR/SVG, a 6-digit code and four emoji. On the phone, enter the
host/port or scan the QR, compare the code and emoji **on both screens**, then approve on both.

Expected: both sides show the same code/emoji; pairing is refused if they differ; after approval
`continuityctl devices --json` contains one trusted device. Send back `continuityctl status --json`
and a photo of both confirmation screens (redact fingerprints if you prefer).

## 3. Journeys B01–B07

| ID | Step | Expected result |
|---|---|---|
| B01 | Pair once, as above | one pinned device; no re-pair prompt on reconnect |
| B02 | Toggle Wi-Fi off/on, then sleep the laptop and wake it | the app reconnects with bounded backoff; `status` shows `idle/backoff/connecting/offline` honestly, then connected |
| B03 | Send a file from phone to laptop | laptop shows the sender, filename and size; **Accept** writes it under `~/.local/share/continuity/received/`; the SHA-256 matches |
| B04 | Send a file from laptop to phone (`continuityctl file send <fingerprint> <path>`) | phone asks before writing; decline leaves no file; accept writes one file |
| B05 | Copy text on laptop, push clipboard to phone | phone clipboard contains exactly the text; sensitive/disabled settings are respected |
| B06 | Copy text on phone, send to laptop | laptop clipboard contains exactly the text; no background clipboard read on Android 15 |
| B07 | Trigger a notification on the phone while connected | laptop mirrors it; reply and dismiss actions work; redacted content is not reconstructed |

For each journey record: start time, phone state, laptop state, result, and the last 100 lines of
`continuityd` output. For a failure, also send `continuityctl diagnostics` (it writes a sanitized
JSON/Markdown report path).

## 4. Reconnect after Wi-Fi toggle and sleep/wake

1. Connect, confirm `continuityctl status --json` says connected.
2. Toggle phone Wi-Fi off for 10 seconds, then on.
3. Close the laptop lid for 30 seconds, then wake it.
4. Watch `continuityctl status --json` and the app for two minutes.

Expected: reconnect attempts are bounded and visible; revoked peers are never silently re-linked;
the final state is connected or an explicit offline state, never a false "connected". Send the
status snapshots taken immediately after each step.

## 5. QML window, Quickshell and Dolphin (Hyprland)

```sh
desktop/run-continuity.sh          # QML client
# Quickshell: add the include line documented in integrations/quickshell/README.md
integrations/dolphin/install.sh    # then open Dolphin
```

Expected:

* the QML window opens on Hyprland, shows the daemon state and does not crash when the daemon stops;
* the Quickshell panel shows connection/status values from the same API;
* Dolphin's **Continuity → Send to phone** action appears for a selected file and hands the path to
  the helper without shell interpolation.

Send a screen recording or screenshots, `hyprctl version`, `qs --version` (or the Quickshell
version), and the exact error text if an action fails.

## 6. AppImage from a path with spaces, and pacman install

```sh
mkdir -p "$HOME/Continuity Test"
cp continuity-linux-x86_64.AppImage "$HOME/Continuity Test/Continuity.AppImage"
chmod +x "$HOME/Continuity Test/Continuity.AppImage"
QT_QPA_PLATFORM=offscreen "$HOME/Continuity Test/Continuity.AppImage" --appimage-extract-and-run --self-test
"$HOME/Continuity Test/Continuity.AppImage" daemon run
```

Expected: the self-test prints `self-test ok`; the daemon starts; the UI starts in a second terminal.
This is the specific Arch + spaces path the automated Ubuntu job cannot prove.

For the Arch package:

```sh
sudo pacman -U continuity-0.1.0.test3-1-x86_64.pkg.tar.zst
continuityd --help
continuityctl paths --json
```

Expected: `pacman` reports the package as installed; both commands exit 0; `pacman -Ql continuity`
lists `/usr/bin/continuityd`, `/usr/lib/continuity/qml/Main.qml` and the desktop entry. Send
`pacman -Q continuity`, the install transcript and `continuityctl paths --json`.

## 7. KDE Connect remote-input baseline (§0.4)

The failure could not be reproduced in the cloud workspace. On the real laptop:

1. Install KDE Connect on the phone and desktop; pair.
2. Enable **Remote input** and try pointer/keyboard input from the phone.
3. Record whether input works, the KDE Connect versions, the session type (`echo $XDG_SESSION_TYPE`),
   and any error from `journalctl --user -u kdeconnectd` around the attempt.

Expected/recorded: either input works (then the baseline is not reproduced) or it fails with a
specific error. Send the versions, session type and journal excerpt; this row stays **blocked**
until then.

## 8. What to send back

* `continuityctl status --json` before/after each journey.
* `continuityctl diagnostics` output path or file.
* `adb logcat -d -s Continuity:*` after an Android failure.
* The release tag and `sha256sum -c SHA256SUMS` result.
* Phone model/ROM build, laptop GPU/compositor versions, and exact commands.

Do not send private clipboard contents or files; redact them. These results are the only way the
hardware rows move from `implemented-unverified` to `implemented-and-tested`.
