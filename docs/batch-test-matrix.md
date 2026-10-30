# Batch-test matrix

Reproduce the automated rows with:

```bash
cd daemon && ../.venv/bin/python -m pytest -q
.venv/bin/python scripts/generate-theme.py --check
./scripts/build-android.sh
```

"Actual result" is what happened **in this environment** (Ubuntu 24.04 cloud VM, no phone, no
Hyprland, no Qt). Hardware rows are marked blocked/not verified, never pass.

## A. Automated (executed here)

| ID | Test | Procedure | Expected | Actual | Status |
|---|---|---|---|---|---|
| A01 | Framing | `pytest test_core.py` | round-trip, reject >1 MiB/unknown/truncated | 63/63 pass | **pass** |
| A02 | Identity persistence | temp dir twice | same fingerprint, key 0600 | pass | **pass** |
| A03 | Signature tamper | sign, flip data | verify false | pass | **pass** |
| A04 | SAS symmetry | derive both sides | identical, changes with any input | pass | **pass** |
| A05 | Trust store | add/revoke/reload | persists, revoked not trusted | pass | **pass** |
| A06 | Envelope validation | malformed envelopes | typed protocol errors | pass | **pass** |
| A07 | Path safety | 13 hostile names | all rejected | pass | **pass** |
| A08 | URL handoff safety | `file:`, `javascript:`, `intent:` | rejected | pass | **pass** |
| A09 | TLS pairing round-trip | two identities over loopback TLS 1.3 | both pin, SAS shown, trusted reconnect | pass | **pass** |
| A10 | Declined pairing | approver false | no trust on either side | pass | **pass** |
| A11 | Pin mismatch | wrong expected fingerprint | handshake refused, no trust | pass | **pass** |
| A12 | Revoked identity | revoke then connect | connection refused | pass | **pass** |
| A13 | File round-trip | send 110 KiB over TLS | bytes identical at receiver | pass | **pass** |
| A14 | Integrity failure | wrong sha256 | file not published, temp removed | pass | **pass** |
| A15 | Duplicate names | existing `report.pdf` | new file becomes `report-1.pdf` | pass | **pass** |
| A16 | Clipboard policy | directions + privacy mode | send/receive gates correct | pass | **pass** |
| A17 | Clipboard sensitive | `123456` | `privacy.blocked` | pass | **pass** |
| A18 | Capability ceiling | peer without `files.send` | `capability.denied` | pass | **pass** |
| A19 | Unpaired peer scope | untrusted session, file offer | `auth.required` | pass | **pass** |
| A20 | IPC socket | request `status` | snapshot `continuity.state/1` | pass | **pass** |
| A21 | IPC allowlist | `root.shell`, privileged setting | `protocol.unsupported` | pass | **pass** |
| A22 | HTTP bridge auth | no token / wrong token | 401 | pass | **pass** |
| A23 | HTTP command | `privacy.set` | state changes, 200 | pass | **pass** |
| A24 | Diagnostics sections | run | required check ids present, Android `blocked` | pass | **pass** |
| A25 | Diagnostics redaction | run + serialise | home path absent, JSON+MD written | pass | **pass** |
| A26 | Theme drift | `generate-theme.py --check` | no drift | pass | **pass** |
| A27 | Android build | `gradle :app:assembleDebug` | APK produced, debug-signed | see `docs/implementation-validation.md` | **pass/fail recorded there** |

## B. Requires the phone (blocked here)

| ID | Journey | Preconditions | Procedure | Expected | Status |
|---|---|---|---|---|---|
| B01 | Pair once | Android app installed, same LAN | scan/link from desktop, compare SAS on both | both pin; desktop shows connected | blocked — no device |
| B02 | Reconnect | B01 done | restart app / toggle Wi-Fi | manual reconnect succeeds; states honest | blocked |
| B03 | Send file → phone | B01 | share sheet → Continuity | file in Downloads/Continuity, checksum ok | blocked |
| B04 | Receive file ← phone | B01 | `continuityctl send-file` | file in daemon receive dir | blocked |
| B05 | Clipboard → phone | B01 | copy desktop text, push | text on phone clipboard | blocked |
| B06 | Clipboard ← phone | B01 | Quick Settings / app action | text on desktop clipboard | blocked |
| B07 | Notification mirror + reply | notification access granted | receive message, reply from desktop | reply delivered by the app's RemoteInput | blocked |
| B08 | Handoff URL | B01 | browser extension "send tab" | phone notification opens URL after confirmation | blocked |
| B09 | Ring phone | B01 | `continuityctl ring` | phone rings ≤10 s then stops | blocked |
| B10 | Sensitive notification redaction | Android 15 | mirror OTP notification | content hidden unless app-op granted | blocked |
| B11 | HyperOS autostart/battery | device | set Autostart on, battery unrestricted | service survives | blocked |
| B12 | Share target appears | B01 | share a photo | Continuity in share sheet | blocked |

## C. Requires DeX tooling/device (blocked here)

| ID | Capability | Procedure | Expected | Status |
|---|---|---|---|---|
| C01 | adb device detection | `adb devices -l` with phone authorized | serial + `device` state | blocked — no adb/scrcpy |
| C02 | scrcpy capability probe | `scrcpy --help` | `--new-display` support recorded | blocked |
| C03 | Virtual display session | `continuityctl dex start --mode virtual_display` | window opens, stop cleans up | blocked |
| C04 | Independent app windows | `dex start --app <pkg>` | per-app window; else explicit refusal | blocked |
| C05 | Native desktop mode | — | reported unavailable on Android 15 | not implemented |

## D. Compositor/shell (blocked here)

| ID | Item | Procedure | Expected | Status |
|---|---|---|---|---|
| D01 | Desktop QML UI launches | `desktop/run-continuity.sh` | window renders live snapshot | blocked — no Qt runtime on host |
| D02 | Quickshell panel | include module in shell | status + battery + privacy toggle | blocked — no Quickshell |
| D03 | Dolphin menu | install service menu, right-click file | sends to phone | blocked — no Dolphin session |
| D04 | KDE Connect remote input baseline | prompt §0.4 procedure | evidence table filled | blocked — see `baseline-remote-input.md` |
| D05 | Universal Control | portal InputCapture test | input crosses displays | blocked — depends on D04 evidence |
