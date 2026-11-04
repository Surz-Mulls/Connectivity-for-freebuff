# Validation report — v0.1.0-test.2 candidate (continuation pass, MASTER_AGENT_PROMPT_v7.1)

Repo `Surz-Mulls/Connectivity-for-freebuff`, branch **`FreeBuff`** only; `main` untouched. The
published `v0.1.0-test.1` release and its tag `8b13133…` are unchanged; nothing in this pass was
pushed, tagged or published — the candidate awaits explicit user approval (§ 7.15).

## 1. Measured results

| Area | Result | Evidence |
|---|---|---|
| Python daemon suite | **95 passed** | `cd daemon && ../.venv/bin/python -m pytest -q` (82 previous + 7 reconnect + 7 new policy tests) |
| Kotlin/JVM unit tests | **ok (exit 0, quiet)** incl. 5 new `ReconnectPolicyTest` tests | `./gradlew :app:testDebugUnitTest` |
| Android debug build | **passed** | `./gradlew :app:assembleDebug` (exit 0) |
| AppImage in-image self-test | **passed** | `QT_QPA_PLATFORM=offscreen dist/… .AppImage --appimage-extract-and-run --self-test` |
| Internal checksum check | **passed** | `sha256sum -c SHA256SUMS` in `dist/` |
| CI workflow | **not run** | updated to single canonical pipeline; first run must happen on GitHub |
| Android instrumentation / device journeys B01–B07 | **blocked** | no phone, no emulator in this environment |
| QML/Quickshell/Dolphin on live desktop | **blocked** | no Hyprland/Qt display session |
| Arch makepkg build + install test | **blocked** | no distrobox/podman, docker socket is `root:docker 660`, sudo exists but is prohibited here |
| KDE Connect remote-input baseline (§0.4) | **blocked** | no compositor/user session; required evidence cannot be produced in this VM |

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

## 3. Artifacts (this pass, local only — NOT published)

| Asset | Size (B) | SHA-256 |
|---|---|---|
| `continuity-android-debug.apk` | 29,304,123 | `3c4f37cf0f2f71f535cf832237f519ddd547b325c161a61f63f539528ad48406` |
| `continuity-linux-x86_64.AppImage` | 98,195,960 | `c20e6bb45becc2cd7001392d4df0e50f0295c629b3f23571e462ee771f3528b0` |
| `continuity-linux-x86_64.pkg.tar.zst` | 159,978 | `03b79cdc60eb8ce1fa67031222a3cba6825df12d0d8e228bf9935342bd4c1701` |
| `continuity-linux-x86_64-portable.tar.zst` | 161,044 | `7cd3e845ef2363becaa933a1516b2c545d72b5206e8ef7a2cac850c404ae6e41` |

## 4. Known remaining gaps (honest)

* Android instrumentation/device journeys, DeX sessions, notification RemoteInput end-to-end:
  device required.
* Desktop GUI/QML/panel/Dolphin/browser on a real compositor: user session required.
* Arch package is PKGBUILD-layout-assembled only; real `makepkg` (distrobox) still needed.
* CI has not executed the updated pipeline yet.
* §0.4 KDE Connect baseline: cannot be reproduced without the user's laptop session; the input
  mechanism choice therefore remains blocked, not decided.
