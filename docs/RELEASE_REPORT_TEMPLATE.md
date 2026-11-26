# Validation report — @TAG@

Candidate `@TAG@`, built from commit `@COMMIT@` on branch `Grok` by release-candidate run
[`@RUN_ID@`](@RUN_URL@) on @DATE@.

## Release assets

Built once by the `build` job; the `publish` job downloads those exact bytes and does not rebuild.
`SHA256SUMS` is generated after all assets exist.

@ASSET_TABLE@

## Checks executed by this workflow

| Check | Result / evidence |
|---|---|
| Python daemon suite | executed in the build job (`python -m pytest daemon/tests -q`) |
| Android JVM tests | executed in the build job (`:app:testDebugUnitTest`); the job log is the count |
| Android lint | executed in the build job (`:app:lintDebug`) |
| Android debug APK | built by `:app:assembleDebug`; debug-signed; APK v2+ signature verified by the release verifier |
| Linux packaging | `scripts/package-linux.sh`: AppImage, portable archive, desktop entry |
| AppImage self-test | in-image `AppRun --self-test`, plus extraction/ELF/launcher checks by the verifier |
| Whole-image runtime floors | measured across every bundled ELF; documented floors glibc **@GLIBC@**, GLIBCXX **3.4.29**, CXXABI **1.3.13**, OpenSSL 3.0.0 if present; builder fails above any |
| Desktop entries | application entry via `desktop-file-validate` and the project validator; KDE service via the project validator |
| Arch package | genuine `makepkg` build in an `archlinux:latest` container, metadata verified, `pacman -U` installed, post-install checks run |
| Release verifier | `tools/verify_release.py --local ... --expect-commit @COMMIT@` (this job) |

Base-image compatibility is a separate `ci` job (`appimage-images`) that runs the uploaded AppImage
on `ubuntu:22.04` and `archlinux:latest`. Branch CI on this commit: @CI_RUN_TEXT@.

## Hardware and clean-machine limits

No Mi 12 / HyperOS, Hyprland, Quickshell, Dolphin or KDE Connect session was available to the
builder. The APK is not device-tested; the AppImage is not launched on a full desktop session; the
Arch package is installed in a container, not on the target laptop. Those rows remain
`implemented-unverified`/`blocked`. The user steps are in `docs/USER_VALIDATION.md`.

## Old releases

`v0.1.0-test.1`, `v0.1.0-test.2` and every earlier published tag, including `v0.1.0-test.3` when this
tag is newer, are untouched. The test.1 and test.2 AppImages are defective (they exec a
build-host `/opt/freestyle` interpreter) and their Arch assets are manual layout archives. This
release does not modify, replace or re-tag them. See `docs/RELEASE_CORRECTIONS.md`.
