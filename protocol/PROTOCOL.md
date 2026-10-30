# Continuity wire protocol v1

This document is normative for the daemon, the Android client, the desktop UI, the Quickshell
module and the contract tests. It is versioned: breaking changes bump `v`.

## 1. Roles and trust model

* Both peers present a **self-signed ECDSA P-256 certificate** generated on first run. The
  certificate SHA-256 fingerprint *is* the device identity.
* TCP + **TLS 1.3** provides confidentiality. TLS is deliberately *not* used for peer
  authentication: self-signed certificates cannot be chain-verified, so authenticity is established
  at the application layer by (a) an exact fingerprint match against the trust store and (b) a
  signature over both nonces proving possession of the certificate key. This is the SSH host-key
  model and it is the only part of the handshake that decides whether a peer is trusted.
* First-time pairing additionally derives a **short authentication string (SAS)** from both
  fingerprints and both nonces. Pairing completes only when the human confirms the same 6-digit code
  and 4 emoji on both devices, which defeats a man-in-the-middle at pairing time.
* LAN presence is never authorization. An untrusted peer may only send `pair.*` messages and is
  disconnected after 60 s.

## 2. Framing

```
+------------------+----------+------------------+
| length (4 bytes) | type (1) | payload (length) |
+------------------+----------+------------------+
```

* `length` is big-endian, counts payload bytes only, maximum `1048576` (1 MiB). Larger frames are
  rejected **before** allocation.
* type `0x01` = JSON envelope (UTF-8), type `0x02` = opaque binary (file chunks only).
* A truncated header or payload is a fatal frame error; a zero-byte read before a header is a clean
  close.

## 3. Envelope

```json
{ "v": 1, "id": "<uuid4>", "type": "clipboard.set", "reply_to": "<uuid4|null>", "ts": "<iso8601>", "body": { } }
```

`v`, `id`, `type`, `body` are mandatory. Unknown types are rejected with `error.unsupported`.
Requests carry an `id`; responses set `reply_to` to the request id. Both sides may initiate
requests. Every request has a 30 s deadline; `file.*` allows 10 min per chunk and is cancellable.

## 4. Handshake

1. TCP connect, TLS 1.3 handshake (the server certificate is *not* validated by TLS).
2. Server → `hello.challenge`:
   `{proto, nonce, device:{id,name,platform,app_version,caps:[...]}, cert:<b64 DER>}`
3. Client → `hello`:
   `{proto, nonce, device:{...}, cert:<b64 DER>, sig:<b64 ECDSA(SHA-256, client_nonce || server_nonce)>}`
4. Server verifies the client signature with the key in `cert`, computes both fingerprints, and:
   * fingerprint in the trust store and not revoked → `hello.ok` with
     `{trusted:true, device, cert, sig:ECDSA(server_nonce || client_nonce)}`;
   * unknown → `hello.ok` with `{trusted:false, sas:{digits,emoji}, ...}` and the connection enters
     pairing-only mode;
   * revoked or mismatched → `error` with code `identity.revoked` / `identity.mismatch`, then close.
5. The client verifies the server signature and the server fingerprint the same way and compares the
   SAS locally. Any difference aborts the session.

## 5. Pairing

* `pair.confirm` `{sas_digits, sas_emoji}` — each side sends the SAS it displayed after the human
  approved. The peer must agree, otherwise `error.pairing.mismatch`.
* On success both sides append the peer fingerprint to their trust store (`paired_at`, `name`,
  `device_id`) and the connection is promoted to trusted.
* `pair.reject` cancels. `trust.revoke` (trusted peers only) removes the pin on both sides.

## 6. Capabilities

Each device advertises a subset of

```
clipboard.read  clipboard.write  clipboard.images  files.send  files.receive
notifications.mirror  notifications.reply  notifications.dismiss  media.state  media.control
handoff.send  handoff.open  camera.capture  find.ring  find.ping  status.battery
sync.folders  screen.mirror  dex.session  phone.contacts  phone.dial  sms.read  sms.send
```

A message is only accepted if the **sender** advertised the matching capability *and* the receiver's
local privacy settings allow the feature. A capability is a ceiling, never a grant.

## 7. Messages

| Type | Direction | Body | Notes |
|---|---|---|---|
| `hello.challenge` | S→C | `proto, nonce, device, cert` | always first |
| `hello` | C→S | `proto, nonce, device, cert, sig` | |
| `hello.ok` | S→C | `trusted, device, cert, sig, sas?` | |
| `pair.confirm` | both | `sas_digits, sas_emoji` | pairing-only mode |
| `pair.reject` | both | `reason?` | |
| `trust.revoke` | both | `fingerprint` | trusted only |
| `ping` / `pong` | both | `ts` | liveness, 25 s idle → `ping` |
| `clipboard.set` | both | `kind:"text"\|"image", data, digest, sensitive` | sensitive requires opt-in |
| `clipboard.ack` | both | `digest, applied` | loop suppression via `digest` |
| `file.offer` | both | `transfer_id, name, size, sha256, mime` | name sanitised, no paths |
| `file.accept` | both | `transfer_id, offset` | `offset` enables resume |
| `file.reject` | both | `transfer_id, reason` | |
| `file.chunk` | both | **binary frame**: JSON header + payload | 256 KiB chunks |
| `file.done` | both | `transfer_id` | receiver verifies size + SHA-256 |
| `file.result` | both | `transfer_id, ok, sha256?, error?` | |
| `notify.post` | phone→desktop | `key, app, title, text, actions:[{id,title,reply?}], sensitive` | dedup by `key` |
| `notify.dismiss` | phone→desktop | `key` | |
| `notify.action` | desktop→phone | `key, action_id, reply_text?` | only advertised actions |
| `media.state` | phone→desktop | `app, title, artist, playing, position_ms, can_seek` | |
| `media.command` | desktop→phone | `command:"play\|pause\|next\|prev"` | allowlist only |
| `handoff.url` | both | `url, title?` | receiver shows the exact URL before opening |
| `handoff.result` | both | `accepted, reason?` | |
| `find.ring` | desktop→phone | `duration_s (<=30)` | phone plays an alarm |
| `find.ping` | both | `ts` | desktop shows a notification |
| `status` | both | `battery{level,charging}, network, app_version, foreground` | |
| `status.request` | both | `{}` | |
| `privacy.set` | both | `privacy_mode, clipboard_direction, pause_features:[...]` | immediate |
| `sync.manifest` | both | `folder, entries:[{path,size,mtime_ns,sha256?}], root_id` | |
| `sync.plan` | both | `folder, ops:[{op:"push\|pull\|delete\|conflict", path, ...}]` | |
| `sync.result` | both | `folder, applied, conflicts, errors` | |
| `camera.request` | desktop→phone | `request_id, mode:"photo"\|"scan"` | phone shows consent UI |
| `camera.result` | phone→desktop | `request_id, ok, file{name,size,sha256}` | image transferred separately |
| `dex.probe` | desktop→phone | `{}` | ADB/scrcpy capability report |
| `dex.session` | desktop→phone | `action:"start\|stop", mode, package?` | desktop-local supervision |
| `error` | both | `code, message` | codes are stable strings |
| `bye` | both | `reason?` | graceful close |

## 8. Error codes

`protocol.version`, `protocol.frame`, `protocol.json`, `protocol.unsupported`, `auth.required`,
`identity.revoked`, `identity.mismatch`, `pairing.mismatch`, `pairing.timeout`,
`capability.denied`, `privacy.blocked`, `path.unsafe`, `transfer.integrity`, `transfer.cancelled`,
`limit.exceeded`, `internal`.

## 9. Limits (enforced, not advisory)

| Limit | Value |
|---|---|
| frame payload | 1 MiB |
| clipboard text | 1 MiB (UTF-8), images 8 MiB |
| file size | 8 GiB |
| file name | 255 bytes, no `/`, `\`, `..`, NUL, control chars, reserved device names |
| concurrent transfers | 4 |
| concurrent connections | 8 |
| notification body kept | 4 KiB, retention 7 days (configurable) |
| pairing attempts | 5 per 10 min per source |
| unauthenticated connection lifetime | 60 s |

## 10. Why not reuse a reference protocol

KDE Connect, Linux Link and Vortex each pair a different desktop stack with their own transport
(Rust/QUIC, protobuf/Noise). None exposes a Quickshell-consumable state API, and the research pack
records that no reference ships Quickshell integration. A small documented JSON protocol plus a
separate local IPC surface keeps the daemon, Qt UI, Quickshell module, CLI and Android client on one
contract. LocalSend is used as a UX comparison only; its protocol is not reused.
