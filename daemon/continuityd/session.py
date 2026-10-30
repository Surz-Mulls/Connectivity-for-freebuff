"""TLS transport + authenticated peer session.

Two layers, deliberately separate:

* TLS 1.3 gives confidentiality only. Self-signed certificates cannot be chain-verified, so the
  handshake below authenticates the peer by pinned fingerprint plus a signature over both nonces
  (SSH host-key model).
* Everything after the handshake is authorized per message by capability and by local privacy
  settings. An unpaired peer can only exchange ``pair.*`` messages.
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import json
import logging
import ssl
from dataclasses import dataclass, field
from pathlib import Path
from typing import Awaitable, Callable

from . import PROTOCOL_VERSION, __version__
from .config import Settings
from .frames import TYPE_BLOB, TYPE_JSON, FrameError, read_frame, write_frame, write_json
from .identity import Identity, fingerprint_of_der
from .protocol import (
    PAIRING_ONLY,
    REQUIRED_CAPS,
    Msg,
    ProtocolError,
    error_body,
    make,
    parse,
    validate_device,
)
from .sas import derive_sas, sas_matches, verify_signature
from .trust import TrustStore

log = logging.getLogger("continuityd.session")

HANDSHAKE_TIMEOUT = 15.0
PAIRING_TIMEOUT = 120.0
IDLE_TIMEOUT = 180.0
MAX_CONNECTIONS = 8

MessageHandler = Callable[["Session", dict], Awaitable[dict | None]]
BlobHandler = Callable[["Session", dict, bytes], Awaitable[None]]


class SessionError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


def _unb64(value: str, limit: int = 64 * 1024) -> bytes:
    if not isinstance(value, str):
        raise SessionError("protocol.json", "expected base64 string")
    try:
        raw = base64.b64decode(value.encode(), validate=True)
    except Exception as exc:  # noqa: BLE001 - any decode failure is a protocol error
        raise SessionError("protocol.json", "invalid base64") from exc
    if len(raw) > limit:
        raise SessionError("limit.exceeded", "base64 field too large")
    return raw


@dataclass
class Peer:
    device: dict
    cert_der: bytes
    fingerprint: str
    trusted: bool
    sas: dict | None = None

    @property
    def caps(self) -> set[str]:
        return set(self.device.get("caps", []))

    @property
    def name(self) -> str:
        return self.device.get("name") or self.device.get("id", "peer")

    def describe(self) -> dict:
        return {
            "id": self.device.get("id"),
            "name": self.name,
            "platform": self.device.get("platform"),
            "app_version": self.device.get("app_version"),
            "fingerprint": self.fingerprint,
            "trusted": self.trusted,
            "caps": sorted(self.caps),
        }


@dataclass
class Session:
    identity: Identity
    trust: TrustStore
    settings: Settings
    handler: MessageHandler | None = None
    blob_handler: BlobHandler | None = None
    initiator: bool = False
    expected_fingerprint: str | None = None
    #: async callback (peer) -> bool; wired to the UI/IPC in the daemon, auto-approve in tests
    pair_approver: Callable[["Peer"], Awaitable[bool]] | None = None
    capabilities: list[str] = field(default_factory=list)
    reader: asyncio.StreamReader | None = None
    writer: asyncio.StreamWriter | None = None
    peer: Peer | None = None
    buffer: bytes = b""
    closed: bool = False
    failure: "SessionError | None" = None
    _pending: dict[str, asyncio.Future] = field(default_factory=dict)
    _tasks: set[asyncio.Task] = field(default_factory=set)
    bytes_in: int = 0
    bytes_out: int = 0

    # ------------------------------------------------------------------ properties
    @property
    def trusted(self) -> bool:
        return bool(self.peer and self.peer.trusted)

    # ------------------------------------------------------------------ entry points
    async def run(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        self.reader, self.writer = reader, writer
        try:
            async with asyncio.timeout(HANDSHAKE_TIMEOUT):
                if self.initiator:
                    await self._client_handshake()
                else:
                    await self._server_handshake()
            await self._loop()
        except SessionError as exc:
            self.failure = exc
            await self._send_error(exc.code, exc.message)
        except (FrameError, ProtocolError) as exc:
            self.failure = SessionError(getattr(exc, "code", "protocol.frame"), str(exc))
            await self._send_error(self.failure.code, str(exc))
        except (asyncio.TimeoutError, TimeoutError):
            await self._send_error("internal", "session timed out")
        except (ConnectionError, ssl.SSLError, OSError) as exc:
            log.debug("connection ended: %s", exc)
        finally:
            await self.close()

    async def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        for future in self._pending.values():
            if not future.done():
                future.cancel()
        self._pending.clear()
        for task in list(self._tasks):
            task.cancel()
        if self.writer:
            with contextlib.suppress(Exception):
                self.writer.close()
                await self.writer.wait_closed()

    # ------------------------------------------------------------------ handshake
    async def _server_handshake(self) -> None:
        assert self.reader and self.writer
        server_nonce = self.identity.nonce()
        await write_json(self.writer, make(Msg.HELLO_CHALLENGE, {
            "proto": PROTOCOL_VERSION,
            "nonce": _b64(server_nonce),
            "device": self.identity.info("linux", self.capabilities),
            "cert": _b64(self.identity.cert_der),
        }))
        msg = await self._read_json(HANDSHAKE_TIMEOUT)
        if msg["type"] != Msg.HELLO:
            raise SessionError("protocol.unsupported", "expected hello")
        body = msg["body"]
        if int(body.get("proto", 0)) != PROTOCOL_VERSION:
            raise SessionError("protocol.version", "peer protocol version mismatch")
        client_nonce = _unb64(body["nonce"], 64)
        cert_der = _unb64(body["cert"])
        signature = _unb64(body["sig"], 128)
        if not verify_signature(cert_der, client_nonce + server_nonce, signature):
            raise SessionError("identity.mismatch", "client signature invalid")
        device = validate_device(body["device"])
        fingerprint = fingerprint_of_der(cert_der)
        entry = self.trust.get(fingerprint)
        if entry and entry.revoked:
            raise SessionError("identity.revoked", "this device was revoked")
        trusted = bool(entry and not entry.revoked)
        sas = None if trusted else derive_sas(fingerprint, self.identity.fingerprint,
                                             client_nonce, server_nonce)
        self.peer = Peer(device=device, cert_der=cert_der, fingerprint=fingerprint,
                         trusted=trusted, sas=sas)
        await write_json(self.writer, make(Msg.HELLO_OK, {
            "trusted": trusted,
            "device": self.identity.info("linux", self.capabilities),
            "cert": _b64(self.identity.cert_der),
            "sig": _b64(self.identity.sign(server_nonce + client_nonce)),
            "sas": sas,
        }))
        if not trusted:
            await self._server_pair()

    async def _server_pair(self) -> None:
        assert self.reader and self.writer and self.peer and self.peer.sas
        approved = True
        if self.pair_approver is not None:
            try:
                approved = await asyncio.wait_for(self.pair_approver(self.peer), PAIRING_TIMEOUT)
            except (asyncio.TimeoutError, TimeoutError):
                approved = False
        if not approved:
            await self._send_error("pairing.timeout", "pairing was not approved")
            raise SessionError("pairing.timeout", "pairing was not approved")
        msg = await self._read_json(PAIRING_TIMEOUT)
        if msg["type"] == Msg.PAIR_REJECT:
            raise SessionError("pairing.timeout", "peer rejected pairing")
        if msg["type"] != Msg.PAIR_CONFIRM:
            raise SessionError("protocol.unsupported", "expected pair.confirm")
        if not sas_matches(self.peer.sas, msg["body"].get("sas_digits"),
                           msg["body"].get("sas_emoji")):
            raise SessionError("pairing.mismatch", "confirmation code did not match")
        self.trust.add(self.peer.fingerprint, self.peer.device.get("id", ""),
                       self.peer.name, self.peer.device.get("platform", "unknown"))
        self.peer.trusted = True
        await write_json(self.writer, make(Msg.PAIR_CONFIRM, {
            "sas_digits": self.peer.sas["digits"],
            "sas_emoji": self.peer.sas["emoji"],
            "role": "server",
        }))
        log.info("paired with %s (%s)", self.peer.name, self.peer.fingerprint[:12])

    async def _client_handshake(self) -> None:
        assert self.reader and self.writer
        challenge = await self._read_json(HANDSHAKE_TIMEOUT)
        if challenge["type"] != Msg.HELLO_CHALLENGE:
            raise SessionError("protocol.unsupported", "expected hello.challenge")
        body = challenge["body"]
        if int(body.get("proto", 0)) != PROTOCOL_VERSION:
            raise SessionError("protocol.version", "peer protocol version mismatch")
        server_nonce = _unb64(body["nonce"], 64)
        server_cert = _unb64(body["cert"])
        server_fingerprint = fingerprint_of_der(server_cert)
        if self.expected_fingerprint and server_fingerprint != self.expected_fingerprint:
            raise SessionError("identity.mismatch", "peer certificate does not match the pin")
        server_device = validate_device(body["device"])
        client_nonce = self.identity.nonce()
        await write_json(self.writer, make(Msg.HELLO, {
            "proto": PROTOCOL_VERSION,
            "nonce": _b64(client_nonce),
            "device": self.identity.info("linux", self.capabilities),
            "cert": _b64(self.identity.cert_der),
            "sig": _b64(self.identity.sign(client_nonce + server_nonce)),
        }))
        ok = await self._read_json(HANDSHAKE_TIMEOUT)
        if ok["type"] == Msg.ERROR:
            code = ok["body"].get("code", "internal")
            raise SessionError(code, ok["body"].get("message", "peer rejected the session"))
        if ok["type"] != Msg.HELLO_OK:
            raise SessionError("protocol.unsupported", "expected hello.ok")
        if not verify_signature(server_cert, server_nonce + client_nonce,
                                _unb64(ok["body"]["sig"], 128)):
            raise SessionError("identity.mismatch", "server signature invalid")
        sas = derive_sas(self.identity.fingerprint, server_fingerprint, client_nonce, server_nonce)
        trusted = self.trust.is_trusted(server_fingerprint)
        if bool(ok["body"].get("trusted")) != trusted:
            raise SessionError("identity.mismatch", "trust state disagrees with the local store")
        if trusted and ok["body"].get("sas"):
            # a trusted peer must never re-open pairing
            raise SessionError("protocol.json", "unexpected pairing data for a trusted peer")
        self.peer = Peer(device=server_device, cert_der=server_cert,
                         fingerprint=server_fingerprint, trusted=trusted, sas=sas)
        if trusted:
            return
        await self._client_pair(sas)

    async def _client_pair(self, sas: dict) -> None:
        assert self.reader and self.writer and self.peer
        approved = True
        if self.pair_approver is not None:
            try:
                approved = await asyncio.wait_for(self.pair_approver(self.peer), PAIRING_TIMEOUT)
            except (asyncio.TimeoutError, TimeoutError):
                approved = False
        if not approved:
            await write_json(self.writer, make(Msg.PAIR_REJECT, {"reason": "declined"}))
            raise SessionError("pairing.timeout", "pairing was declined")
        await write_json(self.writer, make(Msg.PAIR_CONFIRM, {
            "sas_digits": sas["digits"], "sas_emoji": sas["emoji"], "role": "client",
        }))
        msg = await self._read_json(PAIRING_TIMEOUT)
        if msg["type"] == Msg.ERROR:
            raise SessionError(msg["body"].get("code", "internal"),
                               msg["body"].get("message", "pairing failed"))
        if msg["type"] != Msg.PAIR_CONFIRM:
            raise SessionError("protocol.unsupported", "expected pair.confirm")
        if not sas_matches(sas, msg["body"].get("sas_digits"), msg["body"].get("sas_emoji")):
            raise SessionError("pairing.mismatch", "confirmation code did not match")
        self.trust.add(self.peer.fingerprint, self.peer.device.get("id", ""),
                       self.peer.name, self.peer.device.get("platform", "unknown"))
        self.peer.trusted = True
        log.info("paired with %s (%s)", self.peer.name, self.peer.fingerprint[:12])

    # ------------------------------------------------------------------ io
    async def _read_json(self, timeout: float) -> dict:
        assert self.reader
        frame = await asyncio.wait_for(read_frame(self.reader), timeout)
        if frame is None:
            raise SessionError("internal", "peer closed the connection")
        frame_type, payload = frame
        if frame_type != TYPE_JSON:
            raise SessionError("protocol.frame", "expected a JSON frame")
        self.bytes_in += len(payload)
        return parse(payload)

    async def _send_error(self, code: str, message: str) -> None:
        if not self.writer or self.closed:
            return
        with contextlib.suppress(Exception):
            await write_json(self.writer, make(Msg.ERROR, error_body(code, message)))

    def authorize(self, msg_type: str) -> None:
        if not self.peer:
            raise SessionError("auth.required", "no peer")
        if not self.peer.trusted and msg_type not in PAIRING_ONLY:
            raise SessionError("auth.required", "pairing has not been completed")
        required = REQUIRED_CAPS.get(msg_type)
        if required and required not in self.peer.caps:
            raise SessionError("capability.denied",
                               f"peer did not advertise {required}")

    async def send(self, msg_type: str, body: dict | None = None) -> str:
        assert self.writer and self.peer
        self.authorize(msg_type)
        envelope = make(msg_type, body)
        await write_json(self.writer, envelope)
        return envelope["id"]

    async def request(self, msg_type: str, body: dict | None = None,
                      timeout: float = 30.0) -> dict:
        assert self.writer
        envelope = make(msg_type, body)
        future: asyncio.Future = asyncio.get_running_loop().create_future()
        self._pending[envelope["id"]] = future
        try:
            await write_json(self.writer, envelope)
            return await asyncio.wait_for(future, timeout)
        finally:
            self._pending.pop(envelope["id"], None)

    async def send_blob(self, header: dict, data: bytes) -> None:
        assert self.writer
        encoded = json.dumps(header, separators=(",", ":")).encode()
        payload = len(encoded).to_bytes(4, "big") + encoded + data
        await write_frame(self.writer, TYPE_BLOB, payload)
        self.bytes_out += len(data)

    # ------------------------------------------------------------------ loop
    async def _loop(self) -> None:
        assert self.reader
        while not self.closed:
            try:
                frame = await asyncio.wait_for(read_frame(self.reader), IDLE_TIMEOUT)
            except (asyncio.TimeoutError, TimeoutError):
                raise SessionError("internal", "idle timeout") from None
            except FrameError:
                raise
            if frame is None:
                return
            frame_type, payload = frame
            if frame_type == TYPE_JSON:
                msg = parse(payload)
                self.bytes_in += len(payload)
                if msg["reply_to"]:
                    future = self._pending.get(msg["reply_to"])
                    if future and not future.done():
                        future.set_result(msg)
                        continue
                self._spawn(self._handle(msg))
            else:
                header, data = decode_blob(payload)
                if not self.peer or not self.peer.trusted:
                    raise SessionError("auth.required", "not paired")
                if self.blob_handler:
                    await self.blob_handler(self, header, data)
                else:
                    raise SessionError("capability.denied", "binary frames are not accepted")

    def _spawn(self, coro) -> None:
        task = asyncio.create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _handle(self, msg: dict) -> None:
        assert self.writer
        try:
            self.authorize(msg["type"])
            if msg["type"] == Msg.PING:
                await write_json(self.writer, make(Msg.PONG, {"ts": msg["ts"]},
                                                  reply_to=msg["id"]))
                return
            if msg["type"] == Msg.BYE:
                self.closed = True
                return
            if self.handler is None:
                raise SessionError("protocol.unsupported", "no handler for this message")
            reply_body = await self.handler(self, msg)
            if reply_body is not None:
                await write_json(self.writer, make(_reply_type(msg["type"]), reply_body,
                                                  reply_to=msg["id"]))
        except ProtocolError as exc:
            await self._send_error(exc.code, exc.message)
        except SessionError as exc:
            await self._send_error(exc.code, exc.message)
        except Exception as exc:  # noqa: BLE001 - never let one message kill the session
            log.exception("handler failed for %s", msg["type"])
            await self._send_error("internal", f"handler failed: {exc.__class__.__name__}")


def _reply_type(msg_type: str) -> str:
    mapping = {
        Msg.CLIPBOARD_SET: Msg.CLIPBOARD_ACK,
        Msg.FILE_OFFER: Msg.FILE_ACCEPT,
        Msg.FILE_DONE: Msg.FILE_RESULT,
        Msg.HANDOFF_URL: Msg.HANDOFF_RESULT,
        Msg.STATUS_REQUEST: Msg.STATUS,
        Msg.DEX_PROBE: Msg.DEX_SESSION,
        Msg.PAIR_CONFIRM: Msg.PAIR_CONFIRM,
    }
    return mapping.get(msg_type, msg_type)


# ---------------------------------------------------------------------- blob framing
def decode_blob(payload: bytes) -> tuple[dict, bytes]:
    if len(payload) < 4:
        raise SessionError("protocol.frame", "blob frame too short")
    header_len = int.from_bytes(payload[:4], "big")
    if header_len == 0 or header_len > 64 * 1024 or 4 + header_len > len(payload):
        raise SessionError("protocol.frame", "invalid blob header length")
    try:
        header = json.loads(payload[4:4 + header_len].decode())
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SessionError("protocol.json", "invalid blob header") from exc
    if not isinstance(header, dict):
        raise SessionError("protocol.json", "blob header must be an object")
    return header, payload[4 + header_len:]


# ---------------------------------------------------------------------- TLS contexts
def server_context(identity: Identity) -> ssl.SSLContext:
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_3
    ctx.load_cert_chain(Path(identity.directory) / "device-cert.pem",
                        Path(identity.directory) / "device-key.pem")
    return ctx


def client_context() -> ssl.SSLContext:
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_3
    # Peer authentication happens above TLS: see module docstring.
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


async def start_server(handler: Callable[[asyncio.StreamReader, asyncio.StreamWriter], Awaitable[None]],
                       identity: Identity, host: str = "0.0.0.0", port: int | None = None
                       ) -> asyncio.Server:
    return await asyncio.start_server(handler, host=host, port=port or 0,
                                      ssl=server_context(identity), limit=1 << 20)


async def connect(host: str, port: int) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
    return await asyncio.open_connection(host, port, ssl=client_context(), limit=1 << 20)


def advertised_capabilities(settings: Settings) -> list[str]:
    caps = ["status.battery", "find.ring", "find.ping", "handoff.send", "handoff.open"]
    if settings.clipboard_enabled and settings.clipboard_direction != "off":
        caps += ["clipboard.read", "clipboard.write"]
        if settings.clipboard_images:
            caps.append("clipboard.images")
    if settings.files_enabled:
        caps += ["files.send", "files.receive"]
    if settings.notifications_enabled:
        caps += ["notifications.mirror", "notifications.dismiss", "notifications.reply"]
    if settings.sync_folders:
        caps.append("sync.folders")
    caps += ["media.state", "media.control", "camera.capture", "dex.session"]
    if settings.adb_enabled:
        caps.append("dex.session")
    return sorted(set(caps))


__all__ = ["Session", "SessionError", "Peer", "server_context", "client_context",
           "start_server", "connect", "decode_blob", "advertised_capabilities",
           "PROTOCOL_VERSION", "__version__"]
