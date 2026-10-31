# Validation report — v0.1.0 audit fix pass

Branch `FreeBuff`, repository `Surz-Mulls/Connectivity-for-freebuff`.
Audit start commit: `59360a9` (matches the commit named in the audit prompt). `main` was never
checked out, committed to or pushed.

## 1. What was verified, and how

| Area | Result | Evidence |
|---|---|---|
| Python daemon test suite | **passed** — 70 tests | `daemon/tests`, incl. 7 new binding tests |
| Real inbound connection (finding A) | **passed** | `test_binding.py::test_daemon_accepts_real_inbound_connection` |
| Protocol v2 downgrade rejection | **passed** | `test_binding.py::test_v1_envelope_is_rejected_without_downgrade` |
| TLS certificate binding | **passed** | `test_hello_claiming_a_different_tls_certificate_is_rejected`, `test_client_aborts_when_a_relay_terminates_tls` |
| Android JVM unit tests | **passed** — 17 tests | `./gradlew :app:testDebugUnitTest` |
| ECDSA DER↔raw codec | **passed** — 64 shared vectors + 300 generated signatures | `EcdsaCodecTest`, `daemon/tests/vectors/ecdsa_vectors.json` |
| Identity persistence across restart (finding C) | **passed** | `IdentityPersistenceTest` |
| Transfer id/path/digest/size policy | **passed** | `TransferPolicyTest` |
| APK build | **passed** | `dist/continuity-android-debug.apk` |
| Portable archive | **built** (inspect only) | `dist/continuity-linux-x86_64-portable.tar.zst` |
| Arch package | **built** (inspect only) | `dist/continuity-linux-x86_64.pkg.tar.zst` |
| AppImage | **failed** | `artifacts/logs/appimage.log` |
| QML UI / Quickshell / Dolphin service menu | **unverified** | no Qt 6 runtime, no KDE, no Hyprland on this host |
| Phone pairing, reconnect, transfer, DeX | **blocked** | no Android device or emulator |
| GitHub Actions | **not run** | workflow added, cannot execute without a GitHub API token |

## 2. P0 findings and fixes

### C — identity key unreadable after first start (critical)
`Identity.loadOrCreate` called `setReadable(false, false)` on the key, certificate and metadata.
That clears the **owner's** read bit as well, so the next process start failed with
`Permission denied`. Removed: `filesDir/identity` is already inaccessible to other apps. Regression
test creates an identity, discards the object, reloads it from disk and verifies a signature.

### D — ECDSA DER conversion threw for every real signature (critical)
The old `derToRaw` used fixed offsets (`der[3]`, `der[5]`), which are length bytes in real signatures.
Replaced with `EcdsaCodec`, a structural SEQUENCE/INTEGER parser that handles short and long form
lengths, sign padding, minimal-length enforcement, trailing bytes and truncation, and rejects scalars
outside `1..n-1`. 64 committed DER/raw vectors are shared with the Python suite; 300 signatures
generated on the JVM are round-tripped. The old code was reproduced as failing before the fix
(`scripts/generate-ecdsa-vectors.py` vectors are exactly the cases it mishandled).

### A — every inbound connection aborted (high)
`core.py` awaited `StreamWriter.get_extra_info()`, which is synchronous: `TypeError` before any frame.
Fixed, with a real server test instead of a mocked helper.

### B — handshake not bound to the TLS channel (high)
Protocol v2 transcript: domain label + length-prefixed version, role, both certificate fingerprints,
both nonces and the TLS certificate the signer actually observed. The client requires the TLS peer
certificate to equal the in-band identity; the server requires the client's `tls` field to name the
server certificate. A TLS-terminating relay therefore fails even though it forwards the real
in-band certificate — proven by a relay test that stands up its own TLS server and pipes bytes to the
real daemon. Android enforces `v == 2` on the handshake and every envelope; there is no fallback.

## 3. P1 findings

* **E — Android transfers.** Transfer ids must be canonical UUIDs; names are reduced to safe
  basenames; digests must be 64 hex characters; size is capped at 8 GiB; data is streamed to
  `.name.<uuid>.part` in bounded chunks, never `readBytes()`; size and digest are recomputed before
  an atomic `ATOMIC_MOVE`; collisions get a deterministic suffix; receiving no longer depends on the
  clipboard setting (`Store.filesEnabled` added).
* **G — local API token.** The launcher passed `--api-token=<bearer>` on the QML command line, where
  `/proc/<pid>/cmdline` exposes it to other local users. QML now receives only `--api-config=<0600
  file>` and reads port/token from it. Diagnostics exports changed from `0644` to `0600`. The
  runtime directory no longer falls back to world-writable `/tmp`; it uses a `0700` directory under
  `XDG_STATE_HOME`.
* **H — process execution.** The Dolphin service menu used `Exec=sh -c '… %F'`; it now calls the
  helper directly with `@HELPER@ %F` substituted at install time, so filenames are never parsed by a
  shell. Native-messaging host already used argv arrays and http(s)-only validation.
* **F — permissions.** `READ_MEDIA_IMAGES` removed; files arrive through SAF/content URIs.
* **J — toolchain.** Tracked `scripts/bootstrap-toolchain.sh` (Gradle verified against the published
  SHA-256, pinned in the script), committed Gradle wrapper with `distributionSha256Sum`, LICENSE
  (GPL-3.0), and `scripts/build-android.sh` no longer depends on an untracked bootstrap file.
* **I — not changed.** mDNS still advertises the fingerprint; reducing it to a prefix would break
  the "connect by discovery" flow without a replacement pinning path. Listed as outstanding.
* **K — status files.** Updated in this commit; a file cannot contain its own SHA, so the recorded
  value is the parent commit.

## 4. Reconciliation with the supplied patch

The prompt describes `patches/freebuff-fixes.patch`, `reference/`, `repro/` and
`VERIFICATION_OF_FINDINGS.md`. **Only the audit prompt itself was supplied**; no patch, reference
implementation or reproduction was present in the workspace or the repository. Every fix was
therefore re-implemented from the descriptions and independently verified with the tests above. No
claim is made that the original patch was applied.

## 5. Android artifact

* File: `dist/continuity-android-debug.apk`
* Size / SHA-256: see `dist/continuity-android-debug.apk.sha256` (recorded at build time)
* Package `dev.continuity.app`, versionName `0.1.0`, versionCode `1`
* minSdk 33, targetSdk 35, compileSdk 35
* Debug-signed with the AGP debug keystore — **not** production/release signed
* No device or emulator was available: launch, pairing, reconnect and transfer are **not**
  device-tested.

## 6. Linux artifacts

| Format | File | Built | Inspected | Installed | Launched |
|---|---|---|---|---|---|
| Portable | `dist/continuity-linux-x86_64-portable.tar.zst` | yes | yes (61 entries) | n/a | no — no Qt 6 runtime |
| Arch package | `dist/continuity-linux-x86_64.pkg.tar.zst` | yes | yes (`.PKGINFO`, 64 entries) | no — no pacman/makepkg | no |
| AppImage | not produced | no | — | — | — |

Blockers, stated plainly:

* The host has no root, so `qt6-declarative`, `pacman`/`makepkg` and `squashfs-tools` cannot be
  installed. Nothing was faked: the AppImage was not produced. `appimagetool`'s extracted runtime
  exits 127 (`.../usr/bin/appimagetool: not found`), i.e. the self-extracted helper cannot run in
  this container; the exact output is in `artifacts/logs/appimage.log`.
* Neither Linux archive bundles Qt or CPython. Both declare `qt6-declarative` (or PySide6) and
  Python plus the daemon's wheels as host dependencies. A genuinely self-contained AppImage needs a
  relocatable CPython and Qt, which this environment cannot assemble.
* The Arch package was assembled from the same tree that `packaging/PKGBUILD` installs, but was not
  produced by `makepkg`; treat install testing as **unverified**.

## 7. Not fixed / remaining work

1. mDNS privacy (fingerprint prefix + explicit opt-in) — finding I.
2. Browser extension: `allowed_origins` still needs the real extension id; pin a `key` in the
   manifest so the id is deterministic.
3. Quickshell panel and QML client never executed (no compositor/Qt).
4. Linux packaging needs an environment with root or a container to bundle Qt and build the AppImage.
5. GitHub pre-release not published: the workspace has an SSH key with write access but no GitHub
   API token, and `gh` is not authenticated. See the final report.
