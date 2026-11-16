# Release corrections — `v0.1.0-test.1`, `v0.1.0-test.2`, `v0.1.0-test.3`

The two older pre-releases are immutable. Nothing in this pass moved their tags, replaced their
assets, edited their GitHub notes, or published over them. This page records what is wrong with
them, because deleting history would hide the defect.

## Do not use the test.1 or test.2 AppImage

Both published AppImages are **defective**. Their `usr/bin/python3.12` is a shell wrapper that
`exec`s `/opt/freestyle/python/bin/python3` — a path that exists on the build host, not inside the
image. The in-image `--self-test` on the build host could pass because that host Python was present;
on another machine the image is not self-contained. They must not be recommended or installed.

The local `v0.1.0-test.2` build report did record a passing self-test, but that report was measured on
the builder, not on a clean machine. That is exactly the gap the new release process closes: the
`release-candidate` workflow builds the image from a pinned python-build-standalone CPython, verifies
every `usr/bin` entry is ELF, and a separate CI job runs the uploaded bytes on `ubuntu:22.04` and
`archlinux:latest`.

## test.1 manifest/tag mismatch

The `BUILD-MANIFEST.json` attached to `v0.1.0-test.1` says commit `ab4134a`, while the tag
`v0.1.0-test.1` points at `8b1313371caa4b358dc63f34c85fc6cd7c1b1d3b`. A provenance document that does
not name the tag's commit is not usable. `v0.1.0-test.3`'s manifest names the full commit and the
release verifier checks it against the peeled tag ref.

## Old Arch assets are not makepkg packages

The `continuity-linux-x86_64.pkg.tar.zst` assets in test.1 and test.2 were assembled by
`scripts/package-linux.sh` on Ubuntu. They have no `.BUILDINFO` and no `.MTREE`, which `makepkg`
always writes, and they carry `packager = FreeBuff <noreply@codebuff.com>`. They are layout archives,
not installable Arch packages. test.2's own release report says this in section 5.

`v0.1.0-test.3` ships the output of a real `makepkg` run in an Arch container, with `.PKGINFO`,
`.BUILDINFO`, `.MTREE`, a neutral `Continuity maintainers` packager identity, a `pacman -U` install
and the post-install checks. `scripts/verify-arch-package.sh` refuses the manual archive name.

## test.2 glibc claim

The test.2 release body does not claim "any glibc distro", so it does not repeat test.1's specific
wording. Its AppImage is still the same defective wrapper design, and no clean-machine/base-image
test was run. The test.1 notes did say "Linux (any glibc distro)"; a correction banner is now at the
top of `docs/RELEASE_NOTES_v0.1.0-test.1.md`.

The real floor of the new image is **glibc 2.34**, measured across all bundled ELFs. The new builder
fails if a rebuild needs more; the AppImage is tested on Ubuntu 22.04 and current Arch in CI.

## What test.3 replaces

| Old problem | test.3 |
|---|---|
| AppImage wraps a host `/opt/freestyle` Python | pinned relocatable CPython, every `usr/bin` file ELF, no `/opt/freestyle`, `/home/` or `/root/` in launchers |
| self-test only on the builder | self-test in the image, plus `ubuntu:22.04` and `archlinux:latest` CI jobs |
| manual Arch layout archive | genuine `makepkg` package, metadata and `pacman -U` verified |
| manifest/tag mismatch | manifest commit checked against the peeled tag by the verifier |
| ad-hoc release upload | one build artifact, one manifest and `SHA256SUMS` generated after all files exist; publish job downloads the exact bytes and never rebuilds |

## Draft notice for the old GitHub releases (NOT applied)

The user has not authorised editing the old release notes. If they later say "apply notices", the
following text is ready for each old release:

> **Correction (2026-11-16):** this pre-release's AppImage is defective: `usr/bin/python3.12` execs
> `/opt/freestyle/python/bin/python3` from the build host, so the image is not self-contained. Its
> `pkg.tar.zst` asset is a manually assembled layout archive, not a `makepkg` package. Do not use
> these assets. A corrected, CI-built pre-release is available at `v0.1.0-test.3`; see
> `docs/RELEASE_CORRECTIONS.md` in the repository. The tag and assets of this release are unchanged.
