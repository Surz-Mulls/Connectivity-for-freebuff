# Pinned build tools

Measured in this workspace on 2026-11-15 and 2026-11-16. Every builder refuses a file
whose SHA-256 does not match, and does that before unpacking, `chmod +x` or execution.

## Eclipse Temurin JDK

`scripts/bootstrap-toolchain.sh` installs this under `.toolchain/jdk` without root.

| | |
|---|---|
| Version | `21.0.13+9` (LTS) |
| URL | `https://github.com/adoptium/temurin21-binaries/releases/download/jdk-21.0.13%2B9/OpenJDK21U-jdk_x64_linux_hotspot_21.0.13_9.tar.gz` |
| Size | 207858352 bytes |
| SHA-256 | `d7f5d5cf865a2902b70ff549b97586a7d3f234e016f041ab447ea740c7d66d1c` |
| Provenance | Upstream `OpenJDK21U-jdk_x64_linux_hotspot_21.0.13_9.tar.gz.sha256.txt` matches the measured digest (2026-11-16). |

## Android command-line tools

| | |
|---|---|
| Build | `11076708`, contents `Pkg.Revision=12.0` |
| URL | `https://dl.google.com/android/repository/commandlinetools-linux-11076708_latest.zip` |
| Size | 153607504 bytes |
| SHA-256 | `2d2d50857e4eb553af5a6dc3ad507a17adf43d115264b1afc116f95c92e5e258` |
| Provenance | Measured from `dl.google.com` on 2026-11-16; CI independently measured the same digest. The previous cached zip (10.0, 138733165 bytes) had digest `177e20e…`; Google rotated the `_latest` artifact, and the pinned build failed closed until this value was updated. |

## Gradle

| | |
|---|---|
| Version | `8.11.1` |
| URL | `https://services.gradle.org/distributions/gradle-8.11.1-bin.zip` |
| SHA-256 | `f397b287023acdba1e9f6fc5ea72d22dd63669d59ed4a289a29b1a76eee151c6` |
| Provenance | Matches the upstream `.sha256` file, which the bootstrap script fetches and compares as well. |

## appimagetool

| | |
|---|---|
| Tag | `1.9.0` |
| URL | `https://github.com/AppImage/appimagetool/releases/download/1.9.0/appimagetool-x86_64.AppImage` |
| Size | 12632352 bytes |
| SHA-256 | `46fdd785094c7f6e545b61afcfb0f3d98d8eab243f644b4b17698c01d06083d1` |
| Measured | 2026-11-15T12:05:56Z, `sha256sum` of a fresh download |

The GitHub release body does not publish a checksum for this asset. The tag is
`1.9.0`; the file is a continuous build. The hash above is what this repo pins.
A second download the same day matched it. It also matches the hash a reviewer
recorded on 2026-11-07. The builder verifies the cached archive on every run; on
2026-11-16 a stale pre-pin extraction was detected this way and replaced.

## CPython

Host `python3.12` is not copied into the image. The published AppImages did that
and sometimes copied a shell wrapper whose `exec` path exists only on the build
machine.

| | |
|---|---|
| Project | astral-sh/python-build-standalone |
| Release | `20261110` |
| File | `cpython-3.12.16+20261110-x86_64-unknown-linux-gnu-install_only.tar.gz` |
| URL | `https://github.com/astral-sh/python-build-standalone/releases/download/20261110/cpython-3.12.16+20261110-x86_64-unknown-linux-gnu-install_only.tar.gz` |
| Size | 68163679 bytes |
| SHA-256 | `c2f87d4b4e8db3abddb0f116c6ccfc503d0cbdbb9ee8faacddad1b679ec12e99` |

The SHA-256 matches the `SHA256SUMS` file in that GitHub release. The unpacked
`python/bin/python3.12` is an ELF binary. `GLIBC_` symbols in that binary and in
`libpython3.12.so.1.0` stop at **2.17**. That is the minimum glibc this interpreter
was built for. It is *not* the image floor: PySide6's Qt libraries need newer symbols.

## Whole-image glibc floor

Measured on 2026-11-16 by `scripts/check-appimage-glibc.py` over **312 ELF files** in
the built AppImage: the highest required symbol is **`GLIBC_2.34`**, set by
`usr/lib/python3.12/site-packages/PySide6/Qt/lib/libQt6Core.so.6`. The documented
floor in `scripts/build-appimage.sh` is `2.34`; the builder fails if any rebuild
needs a higher version. Supported baseline: Ubuntu 22.04+, Debian 12+, current Arch.
This is an environment test, not a clean-machine test; CI runs the same AppImage on
`ubuntu:22.04` and `archlinux:latest` in the `appimage-images` job.
