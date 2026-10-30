# Install, build, permissions and uninstall

## Build host used for this delivery

Ubuntu 24.04.5 LTS, x86_64, 2 vCPU, 3 GB RAM, unprivileged container (**no root, no sudo**). JDK 21
and the Android SDK were installed into `.toolchain/` (gitignored). No Qt 6, `scrcpy`, `adb` or
`kdeconnect` could be installed from distro packages here; see `docs/implementation-validation.md`.

## Desktop: daemon + CLI

```bash
python3 -m venv .venv
.venv/bin/pip install -e "daemon[dev]"
.venv/bin/continuityd run          # foreground; Ctrl+C stops it
```

State and secrets live in the user's XDG directories, never in the repository:

| Path | Contents | Mode |
|---|---|---|
| `~/.config/continuity/identity/` | device certificate + private key | 0700 / key 0600 |
| `~/.config/continuity/trusted-peers.json` | pinned peer fingerprints | 0600 |
| `~/.config/continuity/settings.json` | privacy and feature settings | 0600 |
| `$XDG_RUNTIME_DIR/continuity/ipc.sock` | local API socket | 0600 |
| `$XDG_RUNTIME_DIR/continuity/http.token` | loopback bridge port + bearer token | 0600 |
| `~/.local/share/continuity/received/` | received files (0600) | 0700 |

Run it as a user service if you like (do **not** run as root):

```ini
# ~/.config/systemd/user/continuity.service
[Unit]
Description=Continuity daemon
After=graphical-session.target
[Service]
ExecStart=%h/.venv/bin/continuityd run
Restart=on-failure
[Install]
WantedBy=default.target
```

`systemctl --user enable --now continuity` is optional and not installed by any script.

## Desktop: Qt 6 QML UI

The UI is pure QML and binds to the daemon's loopback bridge. Arch packages (pacman itself needs
your approval — nothing here installs them for you):

```
sudo pacman -S --needed qt6-declarative qt6-base
```

Then:

```bash
desktop/run-continuity.sh          # reads the 0600 token, launches qml6/qml
```

KDE Frameworks/Kirigami are **not** required; the QML uses Qt Quick Controls only, so it also runs
under `pyside6-qml` if you prefer. The build host verified the QML sources only by inspection — see
the matrix.

## Desktop: Quickshell (optional, unverified)

```bash
# review integrations/quickshell/README.md first; integration is a single include line you add
```

Nothing under `~/.config/quickshell` is modified by any script in this repo.

## Desktop: Dolphin

```bash
integrations/dolphin/install.sh          # copies a service menu into ~/.local/share/kio/servicemenus
integrations/dolphin/uninstall.sh        # removes exactly that file
```

## Desktop: Chromium/Vivaldi tab handoff

```bash
integrations/browser-extension/install.sh   # registers the native-messaging host + prints the unpacked-extension path
```

Load the printed directory via `chrome://extensions` → *Load unpacked*. The host binary is a small
Python script that calls `continuityctl handoff <fingerprint> <url>`; it accepts only `http(s)`.

## Android: build the APK

```bash
./scripts/build-android.sh
```

The script reuses `.toolchain/jdk` and `.toolchain/sdk`, installing (into `.toolchain/` only) the
command-line tools, `platforms;android-35` and `build-tools;35.0.0` when missing, then runs
`gradle :app:assembleDebug` and copies `app-debug.apk` + a SHA-256 file into `artifacts/android/`.

Manual equivalent:

```bash
export JAVA_HOME="$PWD/.toolchain/jdk" ANDROID_HOME="$PWD/.toolchain/sdk"
cd android && ../.toolchain/gradle-8.11.1/bin/gradle :app:assembleDebug
```

The debug APK is **debug-signed**; it is not a production release. Release signing requires your own
keystore (`keystore.properties`, gitignored) — no key is created or committed here.

Install:

```bash
adb install -r artifacts/android/app-debug.apk
```

## Android permissions and onboarding

| Permission / setting | Why | When |
|---|---|---|
| `INTERNET`, `ACCESS_NETWORK_STATE`, `ACCESS_WIFI_STATE` | LAN TLS connection, connection state | first launch |
| `FOREGROUND_SERVICE` + `FOREGROUND_SERVICE_CONNECTED_DEVICE` | keep the paired connection alive; **not** `dataSync` | start service |
| `POST_NOTIFICATIONS` | foreground service notice + mirrored "open link" notifications | Android 13+ prompt |
| `READ_MEDIA_IMAGES` | only when you share photos through the share sheet | on action |
| Notification access (`NotificationListenerService`) | mirror notifications and reply via the app's own RemoteInput | you enable it in Settings |
| "Allow restricted settings" | required for sideloaded builds before notification access can be granted | Android 13+/HyperOS |
| `RECEIVE_SENSITIVE_NOTIFICATIONS` app-op | Android 15 redacts sensitive notifications; **optional and never automated** | you decide, via `adb shell appops set dev.continuity.app RECEIVE_SENSITIVE_NOTIFICATIONS allow` |
| HyperOS: Autostart = on, battery = "No restrictions" | keep the service alive on Xiaomi ROMs | verify on the device |
| USB debugging (+ Xiaomi "USB debugging (Security settings)" + reboot) | **only** for DeX Workspace (scrcpy), not for Continuity features | opt-in |

Continuity never enables developer settings, never grants permissions through ADB/Shizuku, and never
runs `chmod 666 /dev/uinput`. On a Xiaomi device, scrcpy input may additionally need the security
debugging toggle and a reboot — the app tells you, it does not toggle it.

## Firewall

One TCP listener on port **47820** (or the first free port; the actual port is in `status`). Keep it
LAN-only. Example nftables advice (you apply it):

```
nft add rule inet filter input tcp dport 47820 ip saddr 192.168.0.0/16 accept
nft add rule inet filter input tcp dport 47820 drop
```

No other ports are opened. The loopback HTTP bridge binds `127.0.0.1` only.

## Uninstall / cleanup

```bash
systemctl --user disable --now continuity 2>/dev/null || true
rm -rf ~/.config/continuity ~/.local/share/continuity "$XDG_RUNTIME_DIR/continuity"
integrations/dolphin/uninstall.sh
integrations/browser-extension/uninstall.sh
adb uninstall dev.continuity.app
```

Removing the daemon's config directory deletes the device identity and every pinned peer; the phone
must then re-pair.

## Distrobox (Arch desktop component)

If your host is not Arch, a user-owned Arch distrobox is a reasonable way to get Qt 6 and `scrcpy`
for testing the *desktop* side. It does not reproduce a Hyprland/Quickshell session, GPU video,
PipeWire devices or USB/Bluetooth access. Nothing in this repo requires it.
