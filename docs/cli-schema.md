# CLI and IPC JSON schema (v1)

`continuityctl` is the documented command surface. All IPC-backed commands share one envelope on
the wire; everything above it is a stable JSON contract. This file is normative for consumers
(Quickshell panel, Dolphin service menu, browser native host, diagnostics scripts).

## Exit codes (must reflect failure)

| Exit | Meaning |
|------|---------|
| `0`  | command succeeded (`ok: true`) |
| `1`  | daemon answered a structured `{ok: false}` error (also for `--json`, which prints the error envelope so scripts can read `code`/`message`) |
| `2`  | no daemon reachable / transport failure / usage error (argparse) |

The Dolphin service menu and the browser native host rely on exit codes: a failed send must never
be reported as success.

## Wire envelope (IPC socket, internal)

```json
{"event": "result", "command": "<cmd>", "data": {"ok": true, "result": {…}}}
```

Errors:

```json
{"ok": false, "code": "<error-code>", "message": "<sanitised message>"}
```

`--json` output is the **unwrapped result** (`data.result`) on success, or the error object
(`{"ok": false, "code": …, "message": …}`) on failure, so `status --json` really has top-level
`devices`. Human output prints the same unwrapped result.

## `continuityctl status --json` → state document `continuity.state/1`

Top-level keys: `schema`, `updated`, `daemon` (`{version, state, port, uptime_s, device,
capabilities, last_error}`), `privacy`, `devices`, `trusted`, `transfers`, `pending_transfers`,
`reconnects`, `clipboard`, `notifications`, `dex`, `metrics`, `pairing`.

* `devices[]`: `{fingerprint, id, name, platform, caps[], state, address, last_seen, battery,
  network, app_version, rtt_ms}`; `state` is one of `connected | disconnected | unpaired | revoked`.
* `pending_transfers[]` (approval offers, not yet in `transfers`): `{transfer_id, id, name, size,
  peer, peer_fingerprint, expires_in_s}`. The desktop UI's Accept/Decline buttons call
  `file.accept` with `transfer_id`.
* `pairing.pending[]`: `{fingerprint, sas: {digits, emoji[]} | null, device}` — `sas` carries the
  digits to compare when a pairing request is live (never `null` while one is pending).
* `reconnects[]` (automatic reconnect state per peer we have an address for): `{fingerprint, name,
  state: idle|backoff|connecting|offline, attempt, last_error, next_delay_s, target}`. `target` is
  `null` for inbound-only sessions: those peers are honestly not auto-reconnected, never guessed.

## `continuityctl paths --json` (separate schema, no envelope)

Top-level fields only:

```json
{"runtime_dir": "…", "ipc": "…/ipc.sock", "api_config": "…/http.token"}
```

Shell launchers must use this command (or `continuityd paths --json`) instead of reconstructing
XDG paths; `api_config` is the only safe way to hand the UI the daemon port/token file path.

## Command results

* `devices` → list as `devices[]` above.
* `pair.begin` → `{uri, fingerprint, host, port, name, qr_svg}`.
* `pair.connect` → `{fingerprint, trusted, device}`.
* `pair.approve` → `{resolved: true}` (error `protocol.unsupported` when nothing was pending).
* `file.send` → transfer record `{id, direction, name, size, transferred, state, error, peer,
  path, progress}`.
* `file.accept` → `{resolved: true}` (error `protocol.unsupported` when the offer is gone — the
  UI must treat both outcomes as "resolved, refresh").
* `clipboard.push` → phone reply body `{digest, applied, reason}`.
* `handoff.send` → phone reply body `{accepted, url}`.
* `find.ring` → `{ok: true}`; `find.ping` → `{ok: true, rtt_ms}`.
* `privacy.set` → the privacy sub-object of the state document.
* `dex.probe` → probe report incl. `capabilities` (booleans are conditioned on actual flags,
  device state and transport, not on binaries being installed) and `notes[]`.
* `dex.start` → `{ok, session, serial}`; requires `serial` when several ADB devices are
  authorized (`--serial` on the CLI).
* `shutdown` → `{stopping: true}`; the daemon process then stops and removes its runtime files.

## CLI examples

```console
$ continuityctl devices --json          # exit 0
[…]

$ continuityctl send-file abc "missing.bin" --json   # exit 1
{
  "ok": false,
  "code": "auth.required",
  "message": "device is not connected"
}

$ continuityctl status --json           # exit 2 when the daemon is down
error: daemon is not running (no socket at …)
```
