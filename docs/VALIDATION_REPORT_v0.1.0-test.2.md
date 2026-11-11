# Validation report — v0.1.0-test.2

Repo `Surz-Mulls/Connectivity-for-freebuff`. The published pre-release is
[v0.1.0-test.2](https://github.com/Surz-Mulls/Connectivity-for-freebuff/releases/tag/v0.1.0-test.2)
(`prerelease=true`, `draft=false`, published `2026-11-05T06:20:42Z`). The tag
`v0.1.0-test.2` points at `8db808a7c70513f545f1eb8656579911ce4c59b1`. `main` and
`v0.1.0-test.1` (`8b1313371caa4b358dc63f34c85fc6cd7c1b1d3b`) were not moved.

This file used to say the candidate was unpublished. That was stale. The release
exists. Section 3 is the earlier local build. Section 5 is the independently
verified ledger of the bytes GitHub is actually serving. They are not the same
Linux artifacts.

## 1. Measured results (local, before the release was assembled)

| Area | Result | Evidence |
|---|---|---|
| Python daemon suite | **95 passed** | `cd daemon && python -m pytest -q` on that pass (82 previous + 7 reconnect + 7 new policy tests). Re-measure on the repair commit separately; do not treat 95 as a CI result. |
| Kotlin/JVM unit tests | **ok** incl. 5 `ReconnectPolicyTest` tests | `./gradlew :app:testDebugUnitTest` |
| Android debug build | **passed** | `./gradlew :app:assembleDebug` |
| AppImage in-image self-test | **passed** for the local AppImage in section 3 | not a statement about the published bytes |
| Internal checksum check | **passed for that local `dist/`** | `sha256sum -c SHA256SUMS` |
| CI on the tag | **failed** | run [41979767326](https://github.com/Surz-Mulls/Connectivity-for-freebuff/actions/runs/41979767326): `android` success, `python` collection error in `test_policy_round2.py`, `linux` missing `desktop-file-validate` |
| Android instrumentation / device journeys B01–B07 | **blocked** | no phone |
| QML/Quickshell/Dolphin on live Hyprland | **blocked** | no compositor session |
| KDE Connect remote-input baseline (§0.4) | **blocked** | procedure only; see `docs/baseline-remote-input.md` |

## 2. Phase-0 audit ledger (findings → fix → test)

Source re-inspection confirmed every §1 finding from the v7.1 scan. All were fixed in this pass
unless marked otherwise.

### Android
| ID | Finding (source) | Root cause | Fix | Test |
|---|---|---|---|---|
| A1 | `NotificationRelay.serviceSession()` returned `null` (NotificationRelay.kt) | relay was never wired to the service's session | accessor `ContinuityService.trustedSession()`; replies larger plumbing: `notify.action` handler added (reply + `cancelNotification` dismiss) | compile + JVM; device test blocked |
| A2 | `staging.setReadable(false,false)` after staging create (ContinuityService.kt) | cleared the owner's read bit — app could not reopen/hash its own staged file (contradicts Identity.kt note) | call removed; app-private storage keeps the file private | JVM build; runtime blocked |
| A3 | `finishTransfer()` removed the record from `incoming` before peer validation | foreign trusted peer could remove/fail another peer's transfer and its failure path deleted the other peer's staging file | peer checked *before* any destructive action under `transferLock`; foreign attempt returns `identity.mismatch` without touching state | code path review; instrumentation blocked |
| A4 | two concurrent copies of one offer both awaited consent | no atomic reservation before the dialog | `pendingOffers.putIfAbsent(id, peerFingerprint)` reservation; duplicate gets `awaiting approval`; foreign owner gets `reserved by another device`; reservation freed on decline/timeout/finalise | JVM build; policy logic mirrored from the Python tests |
| A5 | dispatch table had no `notify.action` | desktop reply/dismiss requests reached `protocol.unsupported` | handler maps `dismiss` → relay cancel, otherwise stable action id reply | compile |
| A6 | `setClipboard()` posted to main thread and returned `true` unconditionally | result never awaited | awaited synchronous `runBlocking(Dispatchers.Main.immediate)` with a 2 s timeout; failure returns `false` and is reported | compile + code review |
| A7 | `batteryStatus()` reported `wifi` / `foreground:true` unmeasured | lies to the peer | measured `ConnectivityManager` transport → `wifi/cellular/bluetooth/ethernet/other/unknown`; foreground from `MainActivity.onResume/onPause` flag | compile |
| A8 | Android reconnect **not implemented** | — | `ReconnectPolicy` (bounded exp. backoff + jitter), scheduled in `scheduleReconnect()` on initiator session closed/connect failure; reset on trusted `onSessionReady`; cancelled in `onDestroy`; revoked peers never re-linked; pinned fingerprint required | `ReconnectPolicyTest` (5 tests) |

### Python daemon
| ID | Finding (source) | Root cause | Fix | Test |
|---|---|---|---|---|
| P1 | `file.done` accepted a missing digest (transfers.py) | `sha256` optional | `_digest()` required + compared against offer | `test_file_done_requires_a_valid_matching_digest` |
| P2 | duplicate offers raced into two dialogs (pre-approval) | reservation happened after approval | `_reservations[(peer,id)]` pre-approval reservation, freed on decline/timeout; cutoff reply for the duplicate | `test_same_id_second_offer…`, `test_shutdown…` |
| P3 | approval-waiting offers didn't count toward caps | cap checked after approval | cap check before approver, per-peer and global | `test_pending_offers_count_toward_the_cap`, `test_global_cap_bounded_across_peers` |
| P4 | `on_done` hashed/finalised outside the per-transfer lock | chunk writes could interleave with finalisation | same lock held across verify+finalise | existing concurrency tests + code path |
| P5 | no staging cleanup on shutdown/restart | orphaned `.part` files | `TransferService.startup_cleanup()` (daemon start) + `shutdown()` (daemon stop); resume documented as in-session only | `test_startup_cleanup_removes_orphaned_part_files`, module docstring |
| P6 | `_same_uid()` failed OPEN on exception (ipc.py) | broad `except → True` | Linux fails closed (False on any verification failure); non-Linux fallback explicit and documented | code review; socket peer-UID test blocked to container-free envs |
| P7 | bearer compare not constant-time (ipc.py) | string `!=` | `hmac.compare_digest` | code review |
| P8 | `shutdown` stopped only the manager; daemon kept waiting (ipc.py/cli.py) | `_cmd_shutdown` called `manager.stop()` directly | `stop_event` handed to the daemon main loop; teardown then closes IPC + manager + removes runtime artifacts | code review; CLI smoke below |
| P9 | CLI always exited 0; `--json` leaked the `{ok,result}` envelope (cli.py) | no exit-code contract | `_dispatch()`: 0 ok / 1 structured error / 2 transport; `--json` prints unwrapped result, errors print the error object | schema doc + integrations updated |
| P10 | DeX `wireless_adb = adb exists`, etc. (dex.py) | binary presence treated as capability | capabilities conditioned on actual flag/device/transport evidence (TCP-serial regex, `--audio` in help, authorized devices) + explicit notes + serial selection (`dex.start --serial`, `multiple devices` → explicit error) | code review; device probe blocked |
| P11 | pending transfers invisible to `snapshot()`; pairing `sas: null` (core.py) | UI polled a list that never contains pending offers | `pending_transfers[]` + full pairing payloads (digits/emoji) in the snapshot | covered indirectly via UI wiring; snapshot test is TODO next pass |
| P12 | stale `protocol v1` labels (README.md, Main.qml) | doc drift | corrected to v2 | grep |

### Reconnection (§A) — desktop side
`DeviceManager` now tracks `ReconnectState` per trusted peer with a known target address
(recorded by `connect()`), schedules a bounded reconnect loop on trusted-session close, resets on
success, cancels on revoke/stop, and reports `idle/backoff/connecting/offline` in the snapshot.
Inbound-only peers with no address are honestly not auto-reconnected. Tests: `test_reconnect.py`
(bounded attempts, revoked peer → no attempt, success reset, no leaking internals).

### Integrations / desktop (§1.K, §1.L)
* `continuity_native.py`: exact-length framing loop, non-object rejection, credential/port URL
  checks, length bounds, `handoff --json` + phone `accepted` must be true, non-zero CLI exit now
  propagates as failure.
* Dolphin script already reads top-level `devices` — now correct because `status --json` prints
  the unwrapped snapshot; exit codes make failures visible.
* Quickshell panel: same underlying fix (documented in its header note).

## 3. Pre-upload local artifacts (NOT the published files)

Measured on the continuation pass, before the 2026-11-05 release assembly. Do not
use these digests to verify a download of the GitHub release.

| Asset | Size (B) | SHA-256 |
|---|---|---|
| `continuity-android-debug.apk` | 29,304,123 | `3c4f37cf0f2f71f535cf832237f519ddd547b325c161a61f63f539528ad48406` |
| `continuity-linux-x86_64.AppImage` | 98,195,960 | `c20e6bb45becc2cd7001392d4df0e50f0295c629b3f23571e462ee771f3528b0` |
| `continuity-linux-x86_64.pkg.tar.zst` | 159,978 | `03b79cdc60eb8ce1fa67031222a3cba6825df12d0d8e228bf9935342bd4c1701` |
| `continuity-linux-x86_64-portable.tar.zst` | 161,044 | `7cd3e845ef2363becaa933a1516b2c545d72b5206e8ef7a2cac850c404ae6e41` |

The APK row matches the published APK. The three Linux rows do not.

## 4. Why the Linux hashes diverged (investigation)

On 2026-11-08 the four release binaries, `SHA256SUMS`, `BUILD-MANIFEST.json` and
the attached validation report were downloaded again and hashed with `sha256sum`.
Those hashes match the GitHub API `digest` field for every asset. `SHA256SUMS`
matches the four binaries. The attached validation report is byte-identical to
the copy that was in git at `36c46a3` and still lists the section 3 digests.

| Asset | Size published vs section 3 | SHA-256 vs section 3 |
|---|---|---|
| APK | 29,304,123 = 29,304,123 | match |
| AppImage | 98,195,960 = 98,195,960 | differ |
| manual Arch archive | 160,021 ≠ 159,978 | differ |
| portable archive | 161,033 ≠ 161,044 | differ |

The published Arch archive is the manual layout from `scripts/package-linux.sh`,
not a makepkg package. Its `.PKGINFO` has `packager = FreeBuff <noreply@codebuff.com>`
and `builddate = 1793859570` (`2026-11-05T06:19:30Z`, six seconds after the tag
commit). It has no `.BUILDINFO` and no `.MTREE`, which makepkg always writes.
The portable archive's tar members share that same mtime. The release
`BUILD-MANIFEST.json` is a separate hand-written document (`built_utc`
`2026-11-05T06:20:09Z`, commit `8db808a7…`) and does not carry per-file hashes.
The release was published at `2026-11-05T06:20:42Z`.

So the APK uploaded is the file section 3 measured. The Linux deliverables were
rebuilt during release assembly. `package-linux.sh` embeds `builddate=$(date +%s)`
and the tar mtimes, and `appimagetool` does not produce a reproducible AppImage,
so a rebuild cannot keep the earlier SHA-256. `SHA256SUMS` was regenerated for
the uploaded files. The validation report was not. Nothing in the existing
release was replaced while recording this.

## 5. Independently verified published asset ledger

Verified `2026-11-08` by downloading each asset from the release and running
`sha256sum`. Machine-readable copy: `docs/published-build-manifest-v0.1.0-test.2.json`.

| Asset | Size (B) | SHA-256 |
|---|---|---|
| `continuity-android-debug.apk` | 29304123 | `3c4f37cf0f2f71f535cf832237f519ddd547b325c161a61f63f539528ad48406` |
| `continuity-linux-x86_64.AppImage` | 98195960 | `91de5e553cceeab78091ac4235e3ea06bf589bc2ef121e60f69ff9a39f8775f4` |
| `continuity-linux-x86_64.pkg.tar.zst` | 160021 | `8b4248b2e4db42a3c30167a1daeabc3f21d8af914b43f673ed85594b29dc24cd` |
| `continuity-linux-x86_64-portable.tar.zst` | 161033 | `57a89e3eb1579c40c61a907685bc84e89b677aa319a1fd34e0d2ba841845269c` |
| `SHA256SUMS` | 403 | `f992c56dc34d970d372c79be4d2923332bd54ffe85a71e0328126ea63e30a1e6` |
| `BUILD-MANIFEST.json` | 763 | `20b1bed0c9ee5267fdf96f1343728a7097b4ac6a832f5840683b8974a2144d12` |
| `VALIDATION_REPORT_v0.1.0-test.2.md` (the asset, not this updated file) | 9228 | `1c14588c39b84e2ef54de1d7b782612fcc4887164105121c06c734693eca74fa` |

`SHA256SUMS` body:

```
3c4f37cf0f2f71f535cf832237f519ddd547b325c161a61f63f539528ad48406  continuity-android-debug.apk
91de5e553cceeab78091ac4235e3ea06bf589bc2ef121e60f69ff9a39f8775f4  continuity-linux-x86_64.AppImage
8b4248b2e4db42a3c30167a1daeabc3f21d8af914b43f673ed85594b29dc24cd  continuity-linux-x86_64.pkg.tar.zst
57a89e3eb1579c40c61a907685bc84e89b677aa319a1fd34e0d2ba841845269c  continuity-linux-x86_64-portable.tar.zst
```

The published Arch asset remains a manual layout archive. A makepkg-built
package is a different file (`packaging/PKGBUILD`, output under `dist/makepkg/`)
and is not part of this release.

Tag-archive checksum used by the PKGBUILD (downloaded twice, both matched):

`aa817ab138cca16efecb15f59def0cfe59845fad852c0e989b015f69ed1e3698`  
`https://github.com/Surz-Mulls/Connectivity-for-freebuff/archive/refs/tags/v0.1.0-test.2.tar.gz`  
root directory `Connectivity-for-freebuff-0.1.0-test.2/`.

## 6. Hardware ledger (repair pass, 2026-11-08)

No Mi 12, HyperOS, Hyprland, Quickshell, Dolphin or KDE Connect session was
available here. None of the rows below are implemented-and-tested on hardware.

| Item | Code | This environment |
|---|---|---|
| B01 Pair once | implemented | **blocked** — no phone |
| B02 Reconnect, including Wi-Fi toggle | implemented (unit-tested policy only) | **blocked** on a real link |
| B03 Send file to phone | implemented | **blocked** |
| B04 Receive file from phone | implemented | **blocked** |
| B05 Clipboard to phone | implemented | **blocked** |
| B06 Clipboard from phone | implemented | **blocked** |
| B07 Notification mirror + reply | implemented (`notify.action` reply and dismiss) | **blocked** — not exercised on HyperOS |
| Wi-Fi reconnect and sleep/wake recovery | implemented-unverified | **blocked** — no device sleep cycle was run |
| Notification reply and dismissal | implemented-unverified | **blocked** end-to-end |
| Quickshell on Hyprland | implemented-unverified (`integrations/quickshell/`) | **blocked** — no shell |
| Dolphin on Hyprland | implemented-unverified (`integrations/dolphin/`) | **blocked** — no Dolphin session |
| AppImage launch on Arch, path with spaces | entry point exists | **not run on Arch**. Ubuntu CI launches the AppImage from a path with spaces; that is not an Arch result |
| KDE Connect remote-input baseline | procedure only | **blocked** — `docs/baseline-remote-input.md` |
| DeX journeys C01–C05 | probe/start code implemented-unverified | **blocked** — no adb, scrcpy or phone. C05 native desktop mode remains **not-implemented** on this Android 15 target |

## 7. Known remaining gaps

* The published release was not modified by the 2026-11-09 Grok fixes either.
  `packaging/PKGBUILD` still pins this tag archive. Candidate CI builds a separate
  recipe from `git archive` of the commit under test
  (`scripts/prepare-candidate-pkgbuild.sh`). That job had not been observed
  green at the time this paragraph was written; do not treat it as a makepkg
  result until the GitHub Actions log says so.
* Device journeys, DeX, notification RemoteInput end-to-end, sleep/wake, and the
  KDE Connect baseline still need the Mi 12 and a Hyprland session.
* CI for the repair branch has to be read from GitHub Actions, not from a local
  pytest run.


## 7. Final FreeBuff takeover pass (2026-11-11)

`origin/Grok` (`9f74b6add78c97f608127c819f6562a4081238f7`) was a strict descendant of
`origin/FreeBuff` (`36c46a3efc09e828b320b576f6176cecdf098916`): it was incorporated by
fast-forward, no history was rewritten, and the `Grok` branch was left untouched. The remaining
repairs were applied on `FreeBuff`.

### CI evidence
| Run | Tested commit | Result |
|---|---|---|
| [42949932184](https://github.com/Surz-Mulls/Connectivity-for-freebuff/actions/runs/42949932184) | `6cbbf4123b0d8e942caf21d8ad6af0ca1d7444ba` | success; first genuine `makepkg` package (`continuity-0.1.0.test2-1-x86_64.pkg.tar.zst`) with `.PKGINFO`, `.BUILDINFO`, `.MTREE` |
| [42950428961](https://github.com/Surz-Mulls/Connectivity-for-freebuff/actions/runs/42950428961) | `9f74b6add78c97f608127c819f6562a4081238f7` | success, all four jobs: python, android, linux, arch-makepkg |
| final FreeBuff run | recorded in `STATUS.json` / `PROGRESS.md` after publication | see those files for the exact run and commit |

### Changes in this pass
| Area | Change | Status |
|---|---|---|
| Distrobox wrapper | `pacman -Syu`, `--no-tty` for every scripted step, create-time volume only, reuse-with-recovery for existing containers, no sudoers rule, root build refused, exit codes propagated | implemented-and-tested (mocked) |
| Wrapper tests | `scripts/tests/test_build_arch_distrobox.sh`, 29 assertions, fakes on PATH, no containers touched | implemented-and-tested |
| Arch package metadata | `scripts/verify-arch-package.sh` requires `.PKGINFO`/`.BUILDINFO`/`.MTREE` and rejects the manual layout archive; wired into CI and Distrobox | implemented-and-tested in CI |
| Desktop entries | `Network;FileTransfer;` replaces the invalid double-main `Utility;Network;`; Dolphin KDE service validated by its own rules | implemented-and-tested |
| GitHub Actions | Node 24 majors (`checkout@v7`, `setup-python@v7`, `setup-java@v6`, `upload-artifact@v7`) | implemented-and-tested in CI |
| ShellCheck | New CI step; fixed a real `printf` format bug in the browser-extension installer | implemented-and-tested |
| Real Distrobox run | Needs distrobox+podman on a real host; unavailable in this VM | implemented-unverified |
| Docker `makepkg` local | Docker socket is root-only here; exercised only by CI | implemented-unverified locally, tested in CI |
| FUSE AppImage launch | `/dev/fuse` absent in this container; extract-and-run self-test passed locally, CI covers FUSE | implemented-unverified locally, tested in CI |
