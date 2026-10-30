# Local API schema (`continuity.state/1` + IPC commands)

Every UI — the Qt/QML app, the Quickshell module, the CLI — reads the same daemon state. No UI keeps
its own copy of connection state. This document is versioned with the daemon.

## 1. Transports

| Surface | Path | Access control |
|---|---|---|
| Unix socket (canonical) | `$XDG_RUNTIME_DIR/continuity/ipc.sock` | mode 0600 + `SO_PEERCRED` same-UID check |
| Loopback HTTP bridge | `http://127.0.0.1:<ephemeral>` | `Authorization: Bearer <token>`; token in `$XDG_RUNTIME_DIR/continuity/http.token` (0600) |
| CLI | `continuityctl …` | connects to the socket as the same user |

The HTTP bridge exists because a pure-QML application cannot open Unix sockets. Both surfaces call
the same allowlisted `handle_command`, so they cannot drift. The HTTP listener binds `127.0.0.1`
only and refuses every request without the bearer token.

## 2. Socket protocol

Server → client, one JSON object per line:

```json
{"event":"hello","data":{ …snapshot… }}
{"event":"result","command":"status","data":{"ok":true,"result":{…}}}
{"event":"device.connected","data":{…},"ts":"…"}     // after {"cmd":"events"}
```

Client → server, one JSON object per line: `{"cmd":"<name>", …fields}`.

## 3. HTTP

```
GET  /api/status          -> snapshot (same object as the socket)
GET  /api/qr              -> {uri, fingerprint, host, port, qr_svg}
POST /api/command         -> {"ok":true,"result":…} | {"ok":false,"code":…,"message":…}
```

All responses are `Cache-Control: no-store`. Errors use the protocol error codes.

## 4. Commands

| Command | Fields | Result |
|---|---|---|
| `status` | — | snapshot |
| `devices` | — | device list |
| `pair.begin` | — | `{uri, fingerprint, host, port, name, qr_svg}` |
| `pair.connect` | `host`, `port`, `fingerprint?` | `{fingerprint, trusted, device}` |
| `pair.discover` | `timeout?` | `{peers:[…]}` |
| `pair.approve` | `fingerprint`, `accept` | `{resolved}` |
| `trust.list` | — | peers with `revoked`, `paired_at` |
| `trust.revoke` | `fingerprint` | `{revoked}` |
| `clipboard.push` | `fingerprint` | protocol reply |
| `clipboard.pull` | — | `{text_length}` (never returns the text over IPC by default) |
| `file.send` | `fingerprint`, `path` | transfer record |
| `file.accept` | `transfer_id`, `accept` | `{resolved}` |
| `handoff.send` | `fingerprint`, `url` | `{accepted}` |
| `find.ring` | `fingerprint`, `duration_s` | `{ok}` |
| `find.ping` | `fingerprint` | `{ok, rtt_ms}` |
| `privacy.set` | `privacy_mode?`, `clipboard_direction?`, `paused_features?` | privacy snapshot |
| `settings.get` / `settings.set` | `settings{…}` | settings (allowlisted keys only) |
| `diagnostics.run` | — | `{report, paths}` (writes sanitized JSON + Markdown) |
| `dex.probe` / `dex.start` / `dex.stop` / `dex.status` | `mode?`, `package?` | capability report / session |
| `notifications.list` | — | mirrored items |
| `notifications.reply` | `fingerprint`, `key`, `text` | protocol reply |
| `events` | — | switches the connection to the event stream |
| `shutdown` | — | stops the daemon |

`settings.set` accepts only: `clipboard_allow_sensitive`, `clipboard_images`,
`notifications_enabled`, `notifications_include_sensitive`, `files_auto_accept`, `adb_enabled`,
`discovery_enabled`, `verification_code_handoff`, `log_level`. Anything else is
`protocol.unsupported` — in particular privileged integrations cannot be enabled by a remote or
untrusted call.

## 5. Snapshot

```json
{
  "schema": "continuity.state/1",
  "updated": "ISO-8601",
  "daemon": {"version":"0.1.0","state":"running","port":47820,"uptime_s":12.4,
             "device":{"id":"…","name":"…","fingerprint":"64-hex"},
             "capabilities":["…"],"last_error":""},
  "privacy": {"privacy_mode":false,"clipboard_direction":"both",
              "clipboard_allow_sensitive":false,"paused_features":[],
              "notifications_enabled":true,"notifications_include_sensitive":false,
              "files_enabled":true,"files_auto_accept":false,
              "adb_enabled":false,"shizuku_enabled":false},
  "devices": [{"fingerprint":"…","id":"…","name":"…","platform":"android",
               "caps":["…"],"state":"connected|unpaired|disconnected|revoked",
               "address":"ip:port","last_seen":"…","battery":{"level":87,"charging":false},
               "network":"wifi","app_version":"0.1.0","rtt_ms":4.2}],
  "trusted": [{"fingerprint":"…","device_id":"…","name":"…","paired_at":"…","revoked":false}],
  "transfers": [{"id":"…","direction":"send|receive","name":"…","size":0,
                 "transferred":0,"state":"pending|active|done|failed|cancelled",
                 "error":"","peer":"…","path":"…","progress":0.0}],
  "clipboard": {"backend":"wayland|unavailable","available":true,
                "direction":"both","last_result":"idle"},
  "notifications": [{"key":"…","app":"…","title":"…","text":"…","actions":[],
                     "sensitive":false,"replyable":false,"dismissed":false}],
  "dex": {"enabled":false,"session":null,"paths":{"adb":null,"scrcpy":null}},
  "metrics": {"connections_total":0,"messages_in":0,"messages_out":0,
              "bytes_in":0,"bytes_out":0},
  "pairing": {"pending":[{"fingerprint":"…","sas":null}]}
}
```

Battery, `rtt_ms` and notification text are `null`/empty when unknown — the UI must render
"unavailable", never a fabricated value.

## 6. Events

`daemon.started`, `daemon.stopped`, `device.connected`, `device.pairing_required`,
`device.disconnected`, `device.status`, `pairing.request`, `pairing.timeout`, `trust.revoked`,
`clipboard.updated`, `clipboard.blocked`, `clipboard.cleared`, `transfer.request`,
`transfer.started`, `transfer.progress`, `transfer.done`, `transfer.failed`,
`transfer.cancelled`, `notification.posted`, `notification.dismissed`, `handoff.received`,
`find.ring`, `find.ping`, `media.state`, `privacy.changed`, `dex.session`,
`discovery.results`, `diagnostics.ready`.

Events carry `{event, data, ts}`. Consumers must treat them as hints and reconcile with
`status`; they are not a durable log.

## 7. Contract tests

`daemon/tests/test_ipc.py` covers the socket round-trip, the HTTP auth rejection, a command
round-trip, the settings allowlist and the snapshot shape. They run without a phone.
