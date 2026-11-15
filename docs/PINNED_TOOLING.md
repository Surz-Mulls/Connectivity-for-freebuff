# Pinned AppImage build tools

Measured in this workspace on 2026-11-15. The builder refuses a file whose SHA-256
does not match, and it does that before `chmod +x` or execution.

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
recorded on 2026-11-07.

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
was built for. It is not a promise about PySide6's Qt libraries; those come from
the manylinux wheels pip downloads on the builder.
