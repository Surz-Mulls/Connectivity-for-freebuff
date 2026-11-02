# Validation report — v0.1.0-test.1

Repository `Surz-Mulls/Connectivity-for-freebuff`, branch **`FreeBuff`** only.
`main` was never checked out, committed to, merged, rebased or pushed by this work; the repository
history records that the two branches have no common ancestor, which is left as it is.

This report replaces the previous one. Test counts below are measured in this run, not copied.

## 1. Measured results

| Area | Result | Command / evidence |
|---|---|---|
| Python daemon suite | **82 passed** | `cd daemon && ../.venv/bin/python -m pytest -q` |
| Kotlin/JVM unit tests | **17 passed** | `./gradlew :app:testDebugUnitTest` |
| Android debug build | **passed** | `./gradlew :app:assembleDebug` |
| Cross-language ECDSA vectors | **passed** | 64 DER/raw vectors shared by both suites + 300 JVM-generated round-trips |
| AppImage in-image self-test | **passed** | `AppRun --self-test` inside the built image (imports PySide6.QtQml, cryptography, zeroconf, qrcode, continuityd) |
| Android lint | **not run in this pass** | requires the full lint task; previous pass reported no blocking errors |
| QML/Quickshell/Dolphin on a live desktop | **blocked** | no Qt 6 display, no Hyprland, no KDE on this host |
| Phone pairing / reconnect / transfer / DeX | **blocked** | no Android device or emulator |
| GitHub Actions | **not run** | workflow committed, no run on this commit yet |
| Arch install / launch / uninstall | **blocked** | no Arch environment, no `makepkg`, no root |

## 2. Critical/high findings fixed in this pass

### 2.1 Protocol documentation vs implementation (high — misleading contract)
`protocol/PROTOCOL.md` described v1 (`v: 1`, nonce-only signatures, no TLS binding) while both
clients implement v2. Rewritten as a normative v2 specification: framing, envelope, the exact
`hello.challenge`/`hello`/`hello.ok` schemas, the length-prefixed transcript
(`continuity/handshake/v2` + NUL, role, both fingerprints, both nonces, observed TLS fingerprint),
the no-downgrade rule, pairing-only state, capabilities, transfer rules, error codes and limits.
`daemon/continuityd/protocol.py` docstring and README counts updated.

### 2.2 Python receiver accepted weak transfer IDs and unbound duplicates (critical)
`on_offer` accepted any non-empty string ≤64 chars, so a traversal-like id could reach a path, and a
known id was resumed without comparing peer, name, size or digest. Now:
canonical lowercase UUID only (`canonical_transfer_id`), bound to the authenticated peer fingerprint,
duplicate offers must match name, size and SHA-256 exactly, cross-peer reuse is `identity.mismatch`,
and a declined id is poisoned for 10 minutes (`capability.denied` on replay).
Tests: `tests/test_transfer_policy.py::test_transfer_ids_must_be_canonical_uuids`,
`::test_duplicate_id_must_match_peer_name_size_and_digest`, `::test_cross_peer_id_reuse_is_rejected`,
`::test_chunk_from_another_peer_is_rejected`.

### 2.3 Rejected/pending offers left state behind (high)
The old path stored the incoming record even when the approver said no. Approval now happens
**before** any staging file, record, transfer or lock is created; a decline, timeout or missing
approver creates nothing and returns `accept: false` with a reason.
Tests: `::test_declined_offer_leaves_nothing_behind_and_cannot_be_replayed`,
`::test_missing_approver_never_accepts`, `::test_approver_timeout_is_a_rejection`.

### 2.4 Concurrency cap and overwrite race (critical — data loss)
`os.replace` silently replaced an existing destination, and the cap was unenforced. Finalisation now
hard-links the staging file into place (`os.link` fails if the destination exists) and retries with
`name-1.ext` under a single finalisation lock; the resolved path is re-checked to be inside the
receive directory. Locks and incoming records are removed on every terminal path.
Tests: `::test_same_name_finishing_together_never_overwrites`,
`::test_destination_appearing_after_offer_is_not_replaced`, `::test_concurrent_transfer_cap_is_enforced`.

### 2.5 Android accepted incoming files without asking (high — privacy)
`acceptOffer` returned `accept: true` as soon as the global file switch was on. It now suspends the
offer on a per-transfer decision: a notification shows sender, filename and size with **Accept** and
**Reject** actions (45 s expiry, then rejected), nothing is written before approval, and a rejection
is remembered for 10 minutes. Auto-accept is a separate opt-in (`files_auto_accept`, default off)
that only applies to an already-pinned trusted device.

### 2.6 Android transfers were not peer-bound (high)
`Incoming` now stores the senders fingerprint; chunk and finalisation handlers reject a different
session with `identity.mismatch`, and finalisation retries on `FileAlreadyExistsException` instead of
replacing an existing file.

### 2.7 Launcher rebuilt the token path instead of asking the daemon (high)
`desktop/run-continuity.sh` used `${XDG_RUNTIME_DIR:-/tmp}/continuity/http.token`, which could point
at a different directory than the daemon writes and reintroduced `/tmp`. The daemon now exposes
`api_config_path()` and `continuityd paths --json`; the launcher asks for it (falling back to the
package's own `config` module), passes only the **path** to QML, and fails with a useful message when
the daemon is absent.

### 2.8 Packaging assumed a developer `.venv` (high — clean CI failure)
`scripts/package-linux.sh` called `.venv/bin/python` unconditionally. It now uses
`${PYTHON:-python3}` and creates a build-only venv for `zstandard` when the host lacks it; no
untracked developer state is required.

### 2.9 AppImage was broken and host-dependent (high — deliverable)
The old script copied only `AppRun` out of the extracted tool, which cannot work (exit 127), and the
result would have required a host Qt/Python. `scripts/build-appimage.sh` now builds a real AppDir
containing CPython 3.12, `cryptography`, `zeroconf`, `qrcode`, `dbus-next`, **PySide6-Essentials
6.12.0 with its Qt 6/QML modules**, the daemon and the QML client, runs an in-image self-test, and
invokes appimagetool from its complete extracted directory. Any failure aborts the build; there is no
"success" message for a missing artifact.

### 2.10 Arch metadata (medium)
A maintained `packaging/PKGBUILD` is committed with the complete dependency set (`python`,
`python-cryptography`, `python-zeroconf`, `python-qrcode`, `python-dbus-next`, `qt6-declarative`;
`python-pyside6` as an alternative runtime). The uploaded `.pkg.tar.zst` is assembled from that
layout on Ubuntu and is **not** `makepkg`-tested or install-tested; the manifest says so.

### 2.11 Inconsistent counts (medium)
README and `docs/implementation-validation.md` claimed 63 tests; they now state the measured 82 and
identify the protocol version. `STATUS.json`, `PROGRESS.md`, the manifest and these notes all point
at one build.

## 3. Release assets (built from this commit)

| File | Size | SHA-256 |
|---|---|---|
| `continuity-android-debug.apk` | 29,286,743 | `ce0989b1279a2c10042dabb9ed1477ac7aff81d95db1970a4ebccb109e061640` |
| `continuity-linux-x86_64.AppImage` | 98,171,384 | `dcacae7ee32700068e9bc84c508accb7407c3cd96269caa04d14738ffdec18b7` |
| `continuity-linux-x86_64.pkg.tar.zst` | 140,757 | `453cee850dc76c62fc1b0776a5ebadcca681e468bd68b26f17dca4cb8f7f40fa` |
| `continuity-linux-x86_64-portable.tar.zst` | 141,875 | `70015178a0a2be3b4347732724a49f1177466196a6b249948766f1f5f9c29fba` |

Android: package `dev.continuity.app`, versionName `0.1.0`, versionCode `1`, minSdk 33,
targetSdk 35, compileSdk 35, **debug-signed with the AGP debug keystore — not a production or Play
release**. No device test was possible.

The AppImage bundles its runtime and needs no project Python or Qt installation. It was not launched
on a clean machine or with a GUI here (no display server), so desktop integration, xcb platform
plugin loading and the QML window remain **unverified**; only the in-image import self-test passed.

## 4. Not done, deliberately

1. **Automatic reconnect with backoff** (core gap named in the brief) is still **not implemented**;
   reconnect is manual.
2. Notification relay behaviour under Android 15 redaction, DeX/scrcpy supervision, Quickshell
   module, Dolphin multi-file action and the browser extension allowlist are **unverified** here.
3. mDNS still advertises the full fingerprint.
4. Arch package is not `makepkg`/install tested; CI has not run on this commit.

## 5. Reconciliation with the external patch

No `patches/freebuff-fixes.patch`, `reference/`, `repro/` or `VERIFICATION_OF_FINDINGS.md` was
provided in this workspace. Every fix here was implemented from the written findings and verified by
the tests named above; the external patch was not applied and no such claim is made.
