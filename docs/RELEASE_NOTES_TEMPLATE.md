# Continuity @TAG@ — verified pre-release

Local-first Android ↔ Linux companion. No account, no cloud relay: devices find each other on the
LAN, pair by comparing a 6-digit code and four emoji, and pin each other's certificate fingerprint.
This is a **test pre-release**: the Android APK is **debug-signed**, and no phone/Hyprland/hardware
journey was run for this build. **Not device-tested.**

Built by GitHub Actions from commit [`@COMMIT_SHORT@`](https://github.com/Surz-Mulls/Connectivity-for-freebuff/commit/@COMMIT@)
on branch `Grok`.

* Release-candidate run: [`@RUN_ID@`](@RUN_URL@)
* Branch CI on the same commit: @CI_RUN_TEXT@

## Download

| Platform | Asset | Notes |
|---|---|---|
| Android 13+ | `continuity-android-debug.apk` | debug-signed; sideload only |
| Linux x86_64 | `continuity-linux-x86_64.AppImage` | bundles CPython 3.12 and PySide6/Qt 6; needs **glibc @GLIBC@+** |
| Arch Linux x86_64 | `@ARCH_ASSET@` | genuine `makepkg` package; install with `sudo pacman -U @ARCH_ASSET@` |
| Linux (host Python) | `continuity-linux-x86_64-portable.tar.zst` | needs Python 3.11+, `python-cryptography`, `python-zeroconf`, `python-qrcode`, and a Qt 6 QML runtime |

Verify every download with `sha256sum -c SHA256SUMS`; provenance is in `BUILD-MANIFEST.json`, which
names the exact tag and commit. The full check record is in `VALIDATION_REPORT_@TAG@.md`.

@ASSET_TABLE@

## Run

```sh
chmod +x continuity-linux-x86_64.AppImage
./continuity-linux-x86_64.AppImage daemon run    # terminal 1
./continuity-linux-x86_64.AppImage               # terminal 2: Qt/QML client
```

The release-candidate AppImage is self-tested by the release verifier. A separate `ci` build of the
same commit is exercised on `ubuntu:22.04` and `archlinux:latest` by the `appimage-images` job;
`appimagetool` is not byte-reproducible, so those are not the same bytes, but they come from the
same source and the same pinned interpreter/tool. The measured whole-image floor is **glibc
@GLIBC@**; older distributions are unsupported.

## Corrections to older releases

The `v0.1.0-test.1` and `v0.1.0-test.2` AppImages are **defective** and must not be used: their
`usr/bin/python3.12` was a wrapper that execs `/opt/freestyle/python/bin/python3` from the build
machine, so they are not self-contained. Their Arch assets are manually assembled layout archives,
not `makepkg` packages. See `docs/RELEASE_CORRECTIONS.md`. Those releases and tags are unchanged;
this release replaces them.

## What is not verified

Automatic reconnect is unit-tested but not device-tested. Pairing, file transfer, clipboard,
notification reply, Wi-Fi/sleep-wake recovery, the QML window, Quickshell, the Dolphin action and
the KDE Connect §0.4 baseline need the Mi 12 and a Hyprland session. The exact steps and what to
send back are in [`docs/USER_VALIDATION.md`](https://github.com/Surz-Mulls/Connectivity-for-freebuff/blob/@COMMIT@/docs/USER_VALIDATION.md).
