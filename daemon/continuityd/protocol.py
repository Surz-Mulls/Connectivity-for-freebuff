"""Envelope + message validation for protocol v1.

Validation is deliberately strict and cheap: a malformed or oversized frame must be rejected
before any handler sees it.
"""

from __future__ import annotations

import datetime as _dt
import json
import re
import uuid
from typing import Any

from . import PROTOCOL_VERSION

MAX_BODY_BYTES = 1 << 20
UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


class Msg:
    HELLO_CHALLENGE = "hello.challenge"
    HELLO = "hello"
    HELLO_OK = "hello.ok"
    PAIR_CONFIRM = "pair.confirm"
    PAIR_REJECT = "pair.reject"
    TRUST_REVOKE = "trust.revoke"
    PING = "ping"
    PONG = "pong"
    CLIPBOARD_SET = "clipboard.set"
    CLIPBOARD_ACK = "clipboard.ack"
    FILE_OFFER = "file.offer"
    FILE_ACCEPT = "file.accept"
    FILE_REJECT = "file.reject"
    FILE_CHUNK = "file.chunk"
    FILE_DONE = "file.done"
    FILE_RESULT = "file.result"
    NOTIFY_POST = "notify.post"
    NOTIFY_DISMISS = "notify.dismiss"
    NOTIFY_ACTION = "notify.action"
    MEDIA_STATE = "media.state"
    MEDIA_COMMAND = "media.command"
    HANDOFF_URL = "handoff.url"
    HANDOFF_RESULT = "handoff.result"
    FIND_RING = "find.ring"
    FIND_PING = "find.ping"
    STATUS = "status"
    STATUS_REQUEST = "status.request"
    PRIVACY_SET = "privacy.set"
    SYNC_MANIFEST = "sync.manifest"
    SYNC_PLAN = "sync.plan"
    SYNC_RESULT = "sync.result"
    CAMERA_REQUEST = "camera.request"
    CAMERA_RESULT = "camera.result"
    DEX_PROBE = "dex.probe"
    DEX_SESSION = "dex.session"
    ERROR = "error"
    BYE = "bye"


PAIRING_ONLY = frozenset({Msg.PAIR_CONFIRM, Msg.PAIR_REJECT, Msg.PING, Msg.PONG,
                          Msg.ERROR, Msg.BYE})

#: capability required of the *sender* for each message type
REQUIRED_CAPS: dict[str, str] = {
    Msg.CLIPBOARD_SET: "clipboard.write",
    Msg.FILE_OFFER: "files.send",
    Msg.FILE_ACCEPT: "files.receive",
    Msg.FILE_DONE: "files.send",
    Msg.NOTIFY_POST: "notifications.mirror",
    Msg.NOTIFY_DISMISS: "notifications.mirror",
    Msg.NOTIFY_ACTION: "notifications.reply",
    Msg.MEDIA_STATE: "media.state",
    Msg.MEDIA_COMMAND: "media.control",
    Msg.HANDOFF_URL: "handoff.send",
    Msg.FIND_RING: "find.ring",
    Msg.FIND_PING: "find.ping",
    Msg.STATUS: "status.battery",
    Msg.SYNC_MANIFEST: "sync.folders",
    Msg.SYNC_PLAN: "sync.folders",
    Msg.CAMERA_REQUEST: "camera.capture",
    Msg.CAMERA_RESULT: "camera.capture",
    Msg.DEX_PROBE: "dex.session",
    Msg.DEX_SESSION: "dex.session",
}

CAPABILITIES = frozenset({
    "clipboard.read", "clipboard.write", "clipboard.images", "files.send", "files.receive",
    "notifications.mirror", "notifications.reply", "notifications.dismiss",
    "media.state", "media.control", "handoff.send", "handoff.open", "camera.capture",
    "find.ring", "find.ping", "status.battery", "sync.folders", "screen.mirror",
    "dex.session", "phone.contacts", "phone.dial", "sms.read", "sms.send",
})

ERROR_CODES = frozenset({
    "protocol.version", "protocol.frame", "protocol.json", "protocol.unsupported",
    "auth.required", "identity.revoked", "identity.mismatch", "pairing.mismatch",
    "pairing.timeout", "capability.denied", "privacy.blocked", "path.unsafe",
    "transfer.integrity", "transfer.cancelled", "limit.exceeded", "internal",
})

REQUIRED_BODY: dict[str, tuple[str, ...]] = {
    Msg.HELLO_CHALLENGE: ("proto", "nonce", "device", "cert"),
    Msg.HELLO: ("proto", "nonce", "device", "cert", "sig"),
    Msg.HELLO_OK: ("trusted", "device", "cert", "sig"),
    Msg.PAIR_CONFIRM: ("sas_digits", "sas_emoji"),
    Msg.CLIPBOARD_SET: ("kind", "data", "digest"),
    Msg.CLIPBOARD_ACK: ("digest",),
    Msg.FILE_OFFER: ("transfer_id", "name", "size", "sha256"),
    Msg.FILE_ACCEPT: ("transfer_id", "offset"),
    Msg.FILE_REJECT: ("transfer_id", "reason"),
    Msg.FILE_DONE: ("transfer_id",),
    Msg.FILE_RESULT: ("transfer_id", "ok"),
    Msg.NOTIFY_POST: ("key", "app", "title"),
    Msg.NOTIFY_DISMISS: ("key",),
    Msg.NOTIFY_ACTION: ("key", "action_id"),
    Msg.MEDIA_STATE: ("app", "playing"),
    Msg.MEDIA_COMMAND: ("command",),
    Msg.HANDOFF_URL: ("url",),
    Msg.HANDOFF_RESULT: ("accepted",),
    Msg.STATUS: ("battery",),
    Msg.SYNC_MANIFEST: ("folder", "entries"),
    Msg.SYNC_PLAN: ("folder", "ops"),
    Msg.SYNC_RESULT: ("folder",),
    Msg.CAMERA_REQUEST: ("request_id", "mode"),
    Msg.CAMERA_RESULT: ("request_id", "ok"),
    Msg.DEX_SESSION: ("action",),
    Msg.ERROR: ("code", "message"),
}

ALL_TYPES = frozenset(v for k, v in vars(Msg).items() if not k.startswith("_"))


class ProtocolError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


def make(msg_type: str, body: dict | None = None, *, reply_to: str | None = None,
         msg_id: str | None = None) -> dict:
    if msg_type not in ALL_TYPES:
        raise ProtocolError("protocol.unsupported", f"unknown message type {msg_type}")
    return {
        "v": PROTOCOL_VERSION,
        "id": msg_id or str(uuid.uuid4()),
        "type": msg_type,
        "reply_to": reply_to,
        "ts": now_iso(),
        "body": body or {},
    }


def error_body(code: str, message: str) -> dict:
    return {"code": code if code in ERROR_CODES else "internal", "message": message[:512]}


def validate_device(info: Any) -> dict:
    if not isinstance(info, dict):
        raise ProtocolError("protocol.json", "device must be an object")
    device_id = info.get("id")
    if not isinstance(device_id, str) or not 1 <= len(device_id) <= 128:
        raise ProtocolError("protocol.json", "device.id invalid")
    name = info.get("name", "")
    if not isinstance(name, str) or len(name) > 128:
        raise ProtocolError("protocol.json", "device.name invalid")
    caps = info.get("caps", [])
    if not isinstance(caps, list) or any(not isinstance(c, str) for c in caps):
        raise ProtocolError("protocol.json", "device.caps invalid")
    unknown = set(caps) - CAPABILITIES
    if unknown:
        raise ProtocolError("protocol.json", f"unknown capabilities: {sorted(unknown)[:4]}")
    return {
        "id": device_id,
        "name": name,
        "platform": str(info.get("platform", "unknown"))[:32],
        "app_version": str(info.get("app_version", ""))[:32],
        "proto": int(info.get("proto", PROTOCOL_VERSION)),
        "caps": sorted(set(caps)),
    }


def parse(raw: bytes) -> dict:
    """Validate one JSON envelope. Raises :class:`ProtocolError` on any violation."""
    if len(raw) > MAX_BODY_BYTES:
        raise ProtocolError("limit.exceeded", "envelope too large")
    try:
        obj = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProtocolError("protocol.json", f"invalid JSON: {exc}") from exc
    if not isinstance(obj, dict):
        raise ProtocolError("protocol.json", "envelope must be an object")
    if obj.get("v") != PROTOCOL_VERSION:
        raise ProtocolError("protocol.version", f"unsupported protocol version {obj.get('v')!r}")
    msg_type = obj.get("type")
    if not isinstance(msg_type, str) or msg_type not in ALL_TYPES:
        raise ProtocolError("protocol.unsupported", f"unknown message type {msg_type!r}")
    msg_id = obj.get("id")
    if not isinstance(msg_id, str) or not UUID_RE.match(msg_id):
        raise ProtocolError("protocol.json", "invalid message id")
    body = obj.get("body", {})
    if not isinstance(body, dict):
        raise ProtocolError("protocol.json", "body must be an object")
    for key in REQUIRED_BODY.get(msg_type, ()):
        if key not in body:
            raise ProtocolError("protocol.json", f"{msg_type} missing body.{key}")
    return {
        "v": PROTOCOL_VERSION,
        "id": msg_id,
        "type": msg_type,
        "reply_to": obj.get("reply_to"),
        "ts": obj.get("ts") or now_iso(),
        "body": body,
    }


def validate_url(url: str) -> str:
    """Only http(s) may be opened on the peer; anything else is refused.

    Handoff is explicitly *not* a command channel, so file:, javascript:, intent: and custom
    schemes never reach a shell or an activity launcher.
    """
    from urllib.parse import urlparse

    if not isinstance(url, str) or len(url) > 4096:
        raise ProtocolError("protocol.json", "url too long")
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ProtocolError("protocol.unsupported", f"refusing scheme {parsed.scheme!r}")
    if not parsed.netloc:
        raise ProtocolError("protocol.json", "url has no host")
    return url


RESERVED_NAMES = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)),
                  *(f"lpt{i}" for i in range(1, 10))}


def sanitize_filename(name: str) -> str:
    """Reject rather than repair: a hostile name is a security event, not a formatting issue."""
    if not isinstance(name, str) or not name:
        raise ProtocolError("path.unsafe", "empty file name")
    if len(name.encode()) > 255:
        raise ProtocolError("path.unsafe", "file name too long")
    if any(ch in name for ch in ("/", "\\", "\x00")) or name in (".", ".."):
        raise ProtocolError("path.unsafe", "path separators are not allowed")
    if any(ord(ch) < 32 for ch in name):
        raise ProtocolError("path.unsafe", "control characters are not allowed")
    if name.startswith("."):
        raise ProtocolError("path.unsafe", "hidden file names are not accepted from peers")
    if name.split(".")[0].lower() in RESERVED_NAMES:
        raise ProtocolError("path.unsafe", "reserved device name")
    return name
