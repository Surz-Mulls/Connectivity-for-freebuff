# Build environment and local build evidence (2026-11-16)

This is the machine-readable companion to the release report. Everything here was executed in the
unprivileged cloud workspace on branch `Grok` at commit `36bac524dec0532db2fff83f29ad6fc0e53e6632`
plus the release-pass edits. Commands and exit codes are for *this* workspace; CI is the builder of
the published assets.

## Host

| | |
|---|---|
| OS | Ubuntu 24.04.5 LTS, x86_64 |
| User | unprivileged (`uid=258619419`, no root, `no_new_privs`) |
| `sudo` | unavailable: `The "no new privileges" flag is set` |
| Python | 3.12.3 (`.venv` at the repo root) |
| JDK | Eclipse Temurin `21.0.13+9` (`.toolchain/jdk`) |
| Gradle | `8.11.1` (`.toolchain/gradle-8.11.1`) |
| Android SDK | `platforms;android-35`, `build-tools;35.0.0`, `platform-tools` |
| ShellCheck | 0.10.0 |
| `desktop-file-validate` | 0.28 |
| GNU readelf | 2.42 |
| `file` | 5.45 |
| Docker client | 29.1.3, **server unreachable**: `permission denied ... /var/run/docker.sock` |
| podman / distrobox | not installed; cannot install without root |

Pinned downloads (verified before use):

| Artifact | SHA-256 |
|---|---|
| `appimagetool-x86_64.AppImage` 1.9.0 (12632352 B) | `46fdd785094c7f6e545b61afcfb0f3d98d8eab243f644b4b17698c01d06083d1` |
| `cpython-3.12.16+20261110-...-install_only.tar.gz` (68163679 B) | `c2f87d4b4e8db3abddb0f116c6ccfc503d0cbdbb9ee8faacddad1b679ec12e99` |
| Temurin JDK `21.0.13+9` (207858352 B) | `d7f5d5cf865a2902b70ff549b97586a7d3f234e016f041ab447ea740c7d66d1c` |
| Android command-line tools build 11076708, contents 12.0 (153607504 B) | `2d2d50857e4eb553af5a6dc3ad507a17adf43d115264b1afc116f95c92e5e258` |
| Gradle 8.11.1 distribution | `f397b287023acdba1e9f6fc5ea72d22dd63669d59ed4a289a29b1a76eee151c6` |

A stale pre-pin `appimagetool` extraction was present in `.toolchain/appimage` at the start of this
pass. The original builder trusted an existing extracted `AppRun`; it now verifies the cached
archive every run. The stale file was replaced with the pinned download, extracted again, and every
Linux artifact below was rebuilt with it. This is why the local AppImage hash differs from earlier
runs in this workspace.

## Commands executed

| # | Command | Exit | Result |
|---|---|---|---|
| 1 | `.venv/bin/python -m pytest daemon/tests -q` | 0 | **97 passed** |
| 2 | `bash scripts/build-android.sh` | 0 | 22 JVM tests (0 failures), `lintDebug` success, `assembleDebug` success; APK `4bac97855aa84a6f63700e4ecac0de12905d3932815839ff333cad0ec7e2f235` (29,304,243 B), debug-signed |
| 3 | `bash scripts/package-linux.sh` | 0 | AppImage `af9fe4240c74cfd533d88dcbf971b52acc838472fb1af41fe17d953c7e0fc0f4` (136,681,976 B); portable `b4d38478e3a0f88ce8ba90e6cba8a79a3ae7eecdf18adc3f28f1c30645241ee8` (161,343 B, single top-level directory); manual layout archive `a5cc2d80366b44204cd8ee1cf684ea1c21896d042184c1c3c56001660c1e17f9` (160,200 B, **not makepkg**) |
| 4 | `python3 scripts/check-appimage-glibc.py dist/continuity-linux-x86_64.AppImage --floor 2.34` (also invoked by the builder) | 0 | **glibc 2.34** across 312 ELF files; worst file `PySide6/Qt/lib/libQt6Core.so.6` |
| 5 | `QT_QPA_PLATFORM=offscreen HOME=/tmp/cont-home-2 dist/continuity-linux-x86_64.AppImage --appimage-extract-and-run --self-test` | 0 | `self-test ok` on the final `af9fe…` build |
| 6 | same AppImage copied to `/tmp/Continuity Path 2/Continuity.AppImage` and run with `--appimage-extract-and-run --self-test` | 0 | `self-test ok` (path with spaces) |
| 7 | `python3 scripts/validate-desktop-entries.py` | 0 | application and KDE service entries valid |
| 8 | `desktop-file-validate packaging/continuity.desktop` | 0 | clean |
| 9 | `bash scripts/tests/test_build_arch_distrobox.sh` | 0 | mocked wrapper tests, 0 failed (29 assertions) |
| 10 | `python3 scripts/tests/test_browser_extension_install.py` | 0 | deterministic ID `pocpmobopjgeddenbhlieogenkjfldjn`, no placeholder |
| 11 | `shellcheck -x -S warning` on bootstrap/build/package/verify/wrapper/test scripts and both extension scripts | 0 | clean |
| 12 | `bash scripts/verify-arch-package.sh dist/continuity-linux-x86_64.pkg.tar.zst` | 1 | **expected refusal**: that file is the manual layout archive, not a makepkg package |
| 13 | `docker info` | 1 | `permission denied` on `/var/run/docker.sock` |
| 14 | `command -v podman`, `command -v distrobox` | 1 | not installed; no root to add them |
| 15 | `bash scripts/bootstrap-toolchain.sh` | 0 | cached JDK `d7f5…` and cmdline-tools `177e…` verified; `sdkmanager` exit 0; Gradle reused |

## What is deliberately missing locally

* **Real `makepkg` / `pacman -U`.** It needs an Arch container. Docker is unusable for this user and
  podman/distrobox cannot be installed without root. The `arch-makepkg` CI job is the real build and
  install evidence; this workspace contributes only the mocked wrapper tests and the metadata
  verifier refusal above.
* **FUSE-mounted AppImage launch.** `/dev/fuse` is not available; `--appimage-extract-and-run` is the
  local execution mode. CI exercises both FUSE and extract-and-run.
* **Clean-machine glibc compatibility.** The local floor scan is an environment check; the
  `appimage-images` CI job runs the artifact on `ubuntu:22.04` and `archlinux:latest`.
* **Device, Hyprland, Quickshell and Dolphin journeys.** No phone, compositor or KDE session. Those
  remain `implemented-unverified`/`blocked` and are listed in `docs/USER_VALIDATION.md`.

## Android compatibility correction found by this pass

`ContinuityTile.onClick()` called `TileService.startActivityAndCollapse(PendingIntent)`, which is
API 34+, while the app's `minSdk` is 33. `lintDebug` failed with `NewApi`. The Intent overload is
deprecated and throws for targets 34+, so API 33 now uses `startActivity(intent)` and API 34+ keeps
the PendingIntent call. Lint, unit tests and `assembleDebug` all pass after the change.
