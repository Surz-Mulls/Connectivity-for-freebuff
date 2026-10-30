# Feature matrix — what is real in this build

Status vocabulary, used strictly:

* **implemented-and-tested** — code exists *and* an automated test executed here.
* **implemented-unverified** — code exists, compiles, but the path needs the phone/live compositor.
* **blocked** — a specific external limitation prevents it; the reason is stated.
* **not-implemented** — deliberately absent in this build; the app returns an explicit error.

Nothing below is marked passing because it compiled.

## Foundation, identity and pairing

| Feature | Status | Evidence / note |
|---|---|---|
| Device identity (self-signed ECDSA P-256, 0600 key) | implemented-and-tested | `test_core.py::test_identity_*`, `test_session.py` |
| TLS 1.3 confidentiality + pinned-fingerprint authentication + nonce signatures | implemented-and-tested | `test_session.py` pairing/pin/revoke tests |
| SAS pairing (6 digits + 4 emoji, HKDF over both fingerprints + both nonces) | implemented-and-tested | `test_core.py::test_sas_*`, pairing round-trip test |
| QR payload + SVG generation | implemented-and-tested | `test_ipc.py::test_qr_payload_contains_fingerprint` |
| Pairing declined / SAS mismatch refused | implemented-and-tested | `test_declined_pairing_*`, `sas_matches` tests |
| Trust revocation refused at handshake | implemented-and-tested | `test_revoked_identity_cannot_connect` |
| Capability ceiling per message | implemented-and-tested | `test_capability_is_enforced` |
| Untrusted peer limited to pairing messages | implemented-and-tested | `test_untrusted_peer_is_limited_to_pairing` |
| mDNS discovery | implemented-unverified | zeroconf code path; no second host here |
| Automatic reconnect/backoff after link loss | **not-implemented** | manual reconnect only; documented limitation |
| Android pairing UI + pinned connect | implemented-unverified | APK builds; needs device |

## Clipboard

| Feature | Status | Evidence / note |
|---|---|---|
| Desktop→phone text sync | implemented-unverified | daemon policy tested; phone side needs device |
| Phone→desktop text sync | implemented-and-tested (daemon side) | digest verification, duplicate suppression, direction gating |
| Background phone clipboard read | **blocked** | Android 15 blocks background clipboard reads; only foreground/Quick Settings/share actions are wired |
| Sensitive content blocked by default | implemented-and-tested | `looks_sensitive` + policy tests |
| Image clipboard | **not-implemented** | capability not advertised |
| Loop suppression | implemented-and-tested | digest `duplicate` test |

## Files, sharing and sync

| Feature | Status | Evidence / note |
|---|---|---|
| Send/receive files, chunked, resumable offset | implemented-and-tested (daemon) | round-trip over real TLS in `test_session.py` |
| SHA-256 + size verification before publish | implemented-and-tested | `test_chunk_integrity_failure_leaves_no_file` |
| Path safety / traversal / reserved names | implemented-and-tested | `sanitize_filename` + transfer tests |
| No silent overwrite (numeric suffix) | implemented-and-tested | `test_duplicate_names_do_not_overwrite` |
| Android share-sheet target (Direct Share intent) | implemented-unverified | manifest filter + `ACTION_SEND` handler in APK |
| Dolphin "Send to phone" | implemented-unverified | `integrations/dolphin/` |
| Two-way folder sync | **not-implemented** | returns `capability.denied`; conflict design documented only |
| Transfer history UI | implemented-and-tested (daemon snapshot) | `TransfersPage.qml` |

## Notifications, media, calls

| Feature | Status | Evidence / note |
|---|---|---|
| Mirror notifications (dedupe, actions, retention) | implemented-unverified | daemon store + Android listener; no unit test yet |
| Reply through the notification's own RemoteInput | implemented-unverified | `NotificationRelay.reply` |
| Sensitive notification redaction handling | implemented-unverified | honours opt-in; app-op is user-applied, never automated |
| Media metadata/control | **not-implemented** | explicit `capability.denied` |
| Calls / SMS / contacts | **not-implemented** | needs roles we deliberately do not request |
| Verification-code handoff with auto-clear | **not-implemented** | requires SMS permission or sensitive-notification app-op |

## Continuity experiences

| Feature | Status | Evidence / note |
|---|---|---|
| URL handoff (desktop→phone, phone→desktop) | implemented-and-tested (validation) / unverified delivery | only http(s); receiver confirmation |
| Browser tab handoff extension | implemented-unverified | MV3 + native-messaging host in `integrations/browser-extension/` |
| Find phone / ring desktop / ping | implemented-unverified | daemon + APK wiring; no device test |
| Device status + battery over the wire | implemented-unverified | `status.battery` capability |
| Phone camera capture / document scan | **not-implemented** | explicit `capability.denied` |
| Recent photos shelf | **not-implemented** | — |
| Phone as webcam/mic | **not-implemented** | needs v4l2loopback/PipeWire and root-adjacent setup |
| Hotspot/tethering assistant | **not-implemented** | — |
| Second screen / Sidecar | **not-implemented** | needs Hyprland headless output + wf-recorder + input injection |
| Universal Control (pointer crossing) | **blocked** | `xdg-desktop-portal-hyprland` InputCapture unverified; see `baseline-remote-input.md` |
| Bluetooth audio handoff / Wi-Fi Direct | **not-implemented** | hardware-dependent investigation only |
| Quick Share interop (RQuickShare) | **not-implemented** | optional adapter, not integrated |

## DeX Workspace (first-class requirement)

| Capability | Status | Evidence / note |
|---|---|---|
| Device/adb/scrcpy discovery + capability probe | implemented-unverified | `dex.probe`; no adb/scrcpy on this host |
| Session supervision (start/stop/exit, argv allowlist, no shell) | implemented-unverified | `dex.start/stop`; package-name validation |
| Virtual display (`--new-display`) | implemented-unverified | requires scrcpy ≥ 3.0, checked at runtime |
| Independent app windows (`--start-app` + `--flex-display`) | implemented-unverified | only offered when the installed scrcpy reports support |
| Native Android desktop mode (Android 16 QPR3) | **not-implemented** | never assumed on Android 15/HyperOS; reported as unavailable |
| Wireless ADB | implemented-unverified | uses existing adb authorization only; never enables debugging |
| Audio forwarding / per-app audio / recording | **not-implemented** | not exposed without on-device verification |

## Shell and system integration

| Feature | Status | Evidence / note |
|---|---|---|
| Unix-socket IPC + loopback HTTP bridge + schema | implemented-and-tested | `test_ipc.py` (auth, commands, snapshot) |
| CLI (`continuityd`, `continuityctl`) | implemented-and-tested (IPC path) | command tests |
| Quickshell panel consuming real backend state | implemented-unverified | `integrations/quickshell/`; no Quickshell here |
| Qt 6/QML desktop UI | implemented-unverified | QML authored; no Qt runtime installed on this host |
| Privacy dashboard (both platforms) | implemented-unverified | daemon tested via IPC; UIs need devices |
| Full diagnostics + JSON/Markdown export + redaction | implemented-and-tested | `test_diagnostics.py` |
| Design tokens → generated QML/Compose + drift check | implemented-and-tested | `scripts/generate-theme.py --check` |
| Shevery/Shizuku modules | **not-implemented** | documented decision: privilege/maintenance cost not justified for core paths |

## Security posture

Tested here: pin mismatch, revoked identity, declined pairing, SAS mismatch, unknown/malformed
frames, oversized frames, truncated frames, unsafe file names, digest mismatch, out-of-order and
oversized chunks, clipboard sensitive-content block, settings allowlist, IPC peer-UID check, HTTP
bearer requirement.

Not tested here (needs real peers/hardware): hostile-peer fuzzing beyond the frame/name cases,
TLS renegotiation, long-running soak, Android permission bypass attempts, malicious notification
payloads.

**Security-relevant defaults:** no root, no telemetry, no cloud, no arbitrary shell, no automatic
unlock, no silent capture, privacy mode off by default but one click away, ADB integration off by
default, sensitive clipboard and notifications off by default.
