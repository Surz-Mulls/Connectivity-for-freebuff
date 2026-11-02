# Continuity wire protocol v2

Normative for the daemon, the Android client and the contract tests. Breaking changes increment the
envelope version; there is no negotiation and no downgrade path — a v1 peer is disconnected.

## 1. Roles and trust model

* Both peers present a **self-signed ECDSA P-256 certificate** generated on first run. The
  certificate SHA-256 fingerprint *is* the device identity.
* TCP + **TLS 1.3** provides confidentiality. TLS is deliberately *not* used for chain
  authentication: self-signed certificates cannot be verified against a CA, so authenticity is
  established at the application layer by (a) an exact fingerprint match against the trust store
  and (b) a signature over a transcript that includes **the certificate each side actually saw on
  the TLS connection**. This is the SSH host-key model plus channel binding.
* First-time pairing additionally derives a **short authentication string (SAS)** from both
  fingerprints and both nonces. Pairing completes only when the human confirms the same 6-digit
  code and 4 emoji on both devices.
* LAN presence is never authorization. An untrusted peer may only exchange `pair.*` messages and is
  disconnected after 60 s.
* The trust store is keyed by fingerprint. Revocation takes effect on the next handshake; a revoked
  device receives `identity.revoked` and the connection is closed.

## 2. Framing

```
+------------------+----------+------------------+
| length (4 bytes) | type (1) | payload (length) |
+------------------+----------+------------------+
```

* `length` is big-endian and counts payload bytes only; the maximum is `1048576` (1 MiB). A larger
  length is rejected **before** any buffer is allocated.
* type `0x01` = JSON envelope (UTF-8), `0x02` = opaque binary (file chunks only).
* A truncated header or payload is a fatal frame error; a zero-byte read before a header is a clean
  close.
* Binary chunk payload limit is `262144` bytes (256 KiB) plus the JSON header.

## 3. Envelope

```json
{ "v": 2, "id": "<uuid4>", "type": "clipboard.set", "reply_to": "<uuid4|null>",
  "ts": "<iso8601>", "body": { } }
```

`v`, `id`, `type`, `body` are mandatory. `v` must equal `2`; any other value is answered with
`error protocol.version` and the connection is closed. Unknown types are answered with
`protocol.unsupported`. Requests carry an `id`; responses set `reply_to` to the request id. Both
sides may initiate requests. Every request has a 30 s deadline; `file.*` allows 10 min per chunk and
is cancellable.

## 4. Handshake

1. TCP connect, TLS 1.3 handshake. The client does not CA-validate the server certificate; it
   records the SHA-256 fingerprint of the certificate presented on the wire (`tls_observed`).
2. Server → `hello.challenge`

   ```json
   { "proto": 2, "nonce": "<b64 32 bytes>",
     "device": { "id": "…", "name": "…", "platform": "linux", "app_version": "0.1.0",
                 "caps": ["clipboard.read", "clipboard.write", "files.send", "files.receive",
                          "notifications.post", "handoff.url", "find.ring", "status"] },
     "cert": "<b64 DER>" }
   ```

3. Client → `hello`

   ```json
   { "proto": 2, "nonce": "<b64 32 bytes>", "device": { … },
     "cert": "<b64 DER>",
     "tls": "<sha256 hex of the server certificate it saw on TLS>",
     "sig": "<b64 ECDSA-P256/SHA-256 over transcript(role=\"client\", …)>" }
   ```

4. Server checks, in order: `proto == 2`; the client certificate parses; `body.tls` equals **its
   own** fingerprint (a TLS-terminating relay reports its own certificate here and fails); the
   client signature verifies over the transcript built from the *received* certificate, both
   nonces and the reported TLS fingerprint; the device record is valid. It then answers
   `hello.ok`:

   ```json
   { "trusted": true, "device": { … }, "cert": "<b64 DER>", "tls": "<own fingerprint>",
     "sig": "<b64 over transcript(role=\"server\", …)>", "sas": null }
   ```

   For an unknown device `trusted` is `false`, `sas` is `{ "digits": "123456",
   "emoji": ["🦊","🌊","🔧","🌙"] }`, and the session enters pairing-only mode.

5. The client verifies the server signature over its own transcript, requires
   `hello.ok.tls == tls_observed`, and compares the SAS locally. Any mismatch aborts the session.

### 4.1 Transcript and domain separation

```
transcript = LABEL || lp(role) || lp(initiator_fpr) || lp(responder_fpr)
                     || lp(initiator_nonce) || lp(responder_nonce) || lp(tls_fpr)
```

* `LABEL` is the ASCII bytes `continuity/handshake/v2` **including a trailing NUL**.
* `lp(x)` is a 2-byte big-endian length followed by the bytes; this makes field boundaries
  unambiguous, so moving bytes between nonces cannot produce the same transcript.
* `role` is `client` when signed by the initiator and `server` when signed by the responder, so a
  signature cannot be reflected back at its author.
* `initiator_fpr` is the client certificate fingerprint, `responder_fpr` the server's, in that fixed
  order regardless of who is signing.
* `tls_fpr` is the fingerprint of the certificate the **signer** observed on the TLS connection:
  the client reports the server certificate, the server reports its own. The receiver requires this
  value to equal the certificate it presented/was given, which binds the signature to the actual
  channel.
* The signature is ECDSA P-256 over SHA-256, encoded as raw `r||s`, 64 bytes, base64 in JSON.

`SAS = SHA-256(initiator_fpr || responder_fpr || initiator_nonce || responder_nonce)` reduced to
six decimal digits and four emoji. It is displayed only for an untrusted peer.

## 5. Pairing

Pairing runs only on an untrusted session:

1. Server displays/returns its SAS to the user (CLI, Qt, Quickshell, Android notification).
2. Both humans compare the code and emoji out of band.
3. Client → `pair.confirm { sas_digits }`; server verifies the value it derived.
4. Server → `pair.confirm { sas_digits }`; client verifies the value it derived.
5. On success the client stores the server fingerprint; the server stores the client fingerprint.
   `pair.reject` or a timeout (60 s) closes the connection and stores nothing.

## 6. Capabilities

Each side advertises only what it implements. A request for a capability the peer did not advertise
is answered with `capability.denied`; it is never silently ignored. Current sets:

| Side | Capabilities |
|---|---|
| daemon | `clipboard.read`, `clipboard.write`, `files.send`, `files.receive`, `notifications.post`, `handoff.url`, `find.ring`, `status` |
| Android | `clipboard.read`, `clipboard.write`, `files.send`, `files.receive`, `notifications.post`, `handoff.url`, `find.ring`, `status` |

`media.control`, `camera.capture` and `sync.folders` were advertised in v1 but never implemented;
they are gone. A peer that requests them now gets `capability.denied` rather than a hang.

## 7. Message bodies

| Type | Body | Reply |
|---|---|---|
| `clipboard.set` | `{kind, data, digest, sensitive}` | `clipboard.ack {digest, applied}` |
| `file.offer` | `{transfer_id, name, size, sha256, mime}` | `file.accept {transfer_id, offset, accept, reason?}` |
| `file.chunk` (binary) | header `{type, transfer_id, offset}` + bytes | none |
| `file.done` | `{transfer_id, sha256}` | `file.result {transfer_id, ok, sha256?, path?, error?}` |
| `notify.post` | `{key, app, title, text, priority, actions}` | `notify.ack` |
| `notify.dismiss` | `{key}` | `notify.ack` |
| `handoff.url` | `{url, title}` | `{accepted}` |
| `find.ring` | `{duration_s}` | `{ok}` |
| `status` | `{}` | `{battery, network, app_version, foreground}` |
| `trust.revoke` | `{fingerprint}` | `{revoked}` |
| `ping` / `bye` | `{}` | `pong {ts}` / close |

## 8. Transfer rules

* `transfer_id` is a **canonical lowercase RFC-4122 UUID** on both ends. Anything else (traversal
  strings, uppercase, braces, a bare 32-hex run) is rejected with `protocol.json` before it reaches
  a path or a map key.
* A transfer is bound to the authenticated peer fingerprint. A different trusted device reusing the
  id is rejected with `identity.mismatch`.
* A resumed offer must repeat the same name, size and SHA-256. A mismatch is `protocol.json`; a
  declined id is poisoned for 10 minutes and answers `capability.denied`.
* At most **four** concurrent transfers per peer. Exceeding the cap is `limit.exceeded`.
* Chunks must arrive in order at exactly the expected offset, at most 256 KiB each, and must never
  exceed the offered size. Data is written to a staging file and fsynced by `file.done`.
* `file.done` verifies size and SHA-256, then publishes atomically **without ever replacing an
  existing file**: the destination is hard-linked into place (`os.link` / `ATOMIC_MOVE` without
  replace) and a deterministic `name-1.ext` is used on collision. The resolved destination must
  remain inside the receive directory.
* Receiving requires explicit per-transfer approval by default on both platforms. A declined,
  timed-out or unapproved offer leaves no record, no staging file and no lock behind.

## 9. Errors and limits

| Code | Meaning |
|---|---|
| `protocol.version` | envelope version is not 2 |
| `protocol.frame` | framing/size violation |
| `protocol.json` | malformed JSON, invalid UUID/digest/offset |
| `protocol.unsafe` | unknown transfer or operation out of order |
| `protocol.unsupported` | unknown message type |
| `identity.mismatch` | fingerprint, TLS binding or signature mismatch |
| `identity.revoked` | peer was revoked |
| `capability.denied` | peer asked for something it did not advertise |
| `privacy.blocked` | local policy forbids the operation right now |
| `limit.exceeded` | size, rate or concurrency limit |
| `path.unsafe` | destination escapes the receive directory |
| `internal` | daemon-side failure; the message is user-visible but never contains secrets |

Limits: frame 1 MiB, chunk 256 KiB, file 8 GiB, four concurrent transfers, eight concurrent
connections, five pairing attempts per ten minutes per source address, 30 s request deadline, 60 s
handshake/pairing deadline, 60 s offer approval deadline.

## 10. Compatibility

There is no v1 support. Android rejects any envelope whose `v` is not `2`, and the daemon does the
same, so a mixed-version pair fails closed with `protocol.version` instead of silently using weaker
v1 semantics (nonce-only signatures, no channel binding).
