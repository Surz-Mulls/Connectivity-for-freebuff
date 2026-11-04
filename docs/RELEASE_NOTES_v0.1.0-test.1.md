# Continuity v0.1.0-test.1 — pre-release

Local-first Android ↔ Linux companion. No account, no cloud, no relay: devices find each other on
the LAN, pair by comparing a 6-digit code and four emoji, and pin each other's certificate
fingerprint.

This is a **test pre-release**. Debug-signed Android build, hardware paths untested.

## Download

| Platform | Asset | Notes |
|---|---|---|
| Android 13+ | `continuity-android-debug.apk` | debug-signed; install with `adb install -r` or the file manager |
| Linux (any glibc distro) | `continuity-linux-x86_64.AppImage` | self-contained: bundles CPython 3.12, PySide6/Qt 6 and all dependencies |
| Arch Linux | `continuity-linux-x86_64.pkg.tar.zst` | assembled from `packaging/PKGBUILD`; not `makepkg`-tested |
| Linux (host Python) | `continuity-linux-x86_64-portable.tar.zst` | needs python3.11+, `python-cryptography`, `python-zeroconf`, `python-qrcode`, and a Qt 6 QML runtime for the UI |

Verify with `sha256sum -c SHA256SUMS` after downloading all assets.

## Run the AppImage

```sh
chmod +x continuity-linux-x86_64.AppImage
./continuity-linux-x86_64.AppImage daemon run &  # terminal 1: the daemon
./continuity-linux-x86_64.AppImage              # terminal 2: the Qt/QML client
```

The AppImage needs no project Python or Qt installation. It does need a normal desktop session for
the UI (the xcb platform plugin is bundled but its system libraries are expected on a desktop).

## Arch package

```sh
sudo pacman -U continuity-linux-x86_64.pkg.tar.zst
continuityd run      # daemon
continuity           # UI
```

Dependencies: `python`, `python-cryptography`, `python-zeroconf`, `python-qrcode`,
`python-dbus-next`, `qt6-declarative`.

## Android

Install the APK, open it, grant notification permission, then pair from the desktop:

```sh
continuityd run
continuityctl pair begin          # shows a QR/SVG and the SAS
```

Compare the code and emoji on both screens before confirming. Incoming files always ask for
per-transfer approval by default; auto-accept is a separate opt-in that only applies to a device you
have already pinned.

## Honest limitations

* Automatic reconnect after a network change is **not implemented**; reconnect manually.
* Android 15 restricts background clipboard access: clipboard sync happens from the app, the Quick
  Settings tile or the share sheet, never silently in the background.
* Notification content may be redacted by Android 15; redacted text is not recovered.
* DeX Workspace is supervised on the desktop through authorised `adb`/`scrcpy`; it is not native
  Samsung DeX and no permissions are granted automatically.
* Quickshell, Dolphin and the browser extension are shipped but **unverified** in this build.
* No phone, HyperOS device, Hyprland session or real Arch install was available here. Those paths
  are marked blocked/unverified in `docs/VALIDATION_REPORT.md`.
