# Release record — v0.1.0-test.3

Published **2026-11-16T09:46:25Z** as a pre-release from branch `Grok`.
[GitHub release](https://github.com/Surz-Mulls/Connectivity-for-freebuff/releases/tag/v0.1.0-test.3).
The tag points at `d9bad85b587f84a1c417815630561fbec2f8a901`; this file is a later docs-only commit,
so the tag remains the verified commit.

## Gates

| Gate | Evidence |
|---|---|
| Exact-commit CI green | [run 43840044190](https://github.com/Surz-Mulls/Connectivity-for-freebuff/actions/runs/43840044190) on `d9bad85`: python, android, linux, arch-makepkg and appimage-images all success |
| Release-candidate build on that commit | [run 43841944574](https://github.com/Surz-Mulls/Connectivity-for-freebuff/actions/runs/43841944574): build success; manifest `commit` = `d9bad85…` |
| Verifier on the candidate | `0 FAIL, 0 WARN` (17 PASS lines) |
| Arch package is makepkg | `continuity-0.1.0.test3-1-x86_64.pkg.tar.zst` with `.PKGINFO`, `.BUILDINFO`, `.MTREE`; `pacman -U` installed it and `verify-arch-install: ok (qml=qml6)` |
| Other base images | `appimage-images` passed on `ubuntu:22.04` and `archlinux:latest`; this is a separate build of the same commit/source, not byte-identical (appimagetool is not reproducible) |
| Notes contain only executed claims | generated from run 43841944574; hardware explicitly marked not device-tested |
| Nothing outside `Grok`/new tag | `main` still `3ee3a9c3a71bb5127e3773a40432bfd0767b94ab`; old tags/releases unchanged |

## Published assets

`SHA256SUMS` is the authoritative list; the same digests are in `BUILD-MANIFEST.json`.
The release has 9 assets (8 listed below plus `SHA256SUMS` itself).

| Asset | Size (B) | SHA-256 |
|---|---:|---|
| `continuity-android-debug.apk` | 29,202,779 | `090297a4aed5779479a66b7762d1b8ef58b83748c86d3829e9a408b15a0605b2` |
| `continuity-linux-x86_64.AppImage` | 136,673,784 | `ba5153b44d7fc9b24370d377d6757fe43bfc0e6cde406bd4b0a14e7d56a5baca` |
| `continuity-0.1.0.test3-1-x86_64.pkg.tar.zst` | 78,300 | `43ab03e787e0443a29d83152c86240955e8417dc7f62a686b245f19d85a97ecd` |
| `continuity-linux-x86_64-portable.tar.zst` | 153,595 | `aad64defbf399fc41433d7c39b8e9bf0268f4075224dff08b033a60f6f113f84` |
| `continuity.desktop` | 208 | `c77eb75d8a3138a4730920fc2271c57b5821f075ce5929f1307fee4193480914` |
| `BUILD-MANIFEST.json` | 1,745 | `077799c47a426b91bc451e3c966286932783d72e477d047ae3599734ee4da16f` |
| `RELEASE_NOTES_v0.1.0-test.3.md` | 3,872 | `7dc38b84fdb52d280994e2adc0a1545a2590c9f3c5e42fd5f42ad6d836a11b03` |
| `VALIDATION_REPORT_v0.1.0-test.3.md` | 3,242 | `584a11aa7c9979bb2dfe81d6ff7faf78fcac7834d8e4e71570b28164b03c7c34` |

## Independent verification

Downloaded the published assets again and ran:

```sh
tools/verify_release.py v0.1.0-test.3
```

Result: **0 FAIL, 0 WARN**, including tag resolution to `d9bad85`, manifest commit match, all
`SHA256SUMS` entries, AppImage extraction/ELF/launcher checks and `AppRun --self-test`, APK v2+
signature, Arch `.PKGINFO/.BUILDINFO/.MTREE`, and the portable archive's single top-level directory.
The release notes and report are also attached as assets.

## Limits

* APK is debug-signed and was not installed on the Mi 12; device journeys B01–B07, reconnect,
  Quickshell, Dolphin and KDE Connect §0.4 are `implemented-unverified`/`blocked`.
* The AppImage was not launched in a full Hyprland desktop session. Its self-test and the
  `ubuntu:22.04`/`archlinux:latest` CI self-tests passed; glibc floor is **2.34**.
* Real Distrobox/podman was unavailable in this unprivileged VM; only the mocked wrapper suite ran.
* `v0.1.0-test.1` and `v0.1.0-test.2` were not modified. Their AppImages are defective and their
  Arch assets are manual layout archives; see `docs/RELEASE_CORRECTIONS.md`.
