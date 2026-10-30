"""Clipboard sync with direction gating, loop suppression and sensitive-content policy.

Honest about Android: Android 15 blocks background clipboard *reads*, so phone→desktop automatic
sync is only advertised when the phone client can actually read (foreground/Quick Settings/share).
The desktop never invents content: if no real clipboard tool is present it reports the capability
as unavailable instead of pretending.
"""

from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
from dataclasses import dataclass
from typing import Callable

from .config import Settings
from .protocol import Msg, ProtocolError
from .session import Session, SessionError

MAX_TEXT_BYTES = 1 << 20
MAX_IMAGE_BYTES = 8 << 20

OTP_RE = re.compile(r"\b(?:[A-Z0-9]{4}[- ]?){1,2}[A-Z0-9]{2,6}\b")
SENSITIVE_HINTS = ("password", "passwd", "secret", "private key", "api key", "recovery code",
                   "-----begin", "2fa", "one-time code", "verification code")


def digest_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def looks_sensitive(text: str) -> bool:
    """Conservative heuristic used to *block by default*, never to justify forwarding."""
    lowered = text.lower()
    if any(hint in lowered for hint in SENSITIVE_HINTS):
        return True
    # 6-8 digit standalone codes are the classic OTP shape
    if re.fullmatch(r"\s*\d{6,8}\s*", text):
        return True
    return bool(OTP_RE.fullmatch(text.strip()) and len(text.strip()) <= 12)


@dataclass
class ClipboardBackend:
    read_cmd: list[str] | None
    write_cmd: list[str] | None
    name: str

    @property
    def available(self) -> bool:
        return bool(self.read_cmd or self.write_cmd)


def detect_backend() -> ClipboardBackend:
    """Pick the first real clipboard tool on this session; never shell out through a string."""
    if shutil.which("wl-paste") and shutil.which("wl-copy"):
        return ClipboardBackend(["wl-paste", "--no-newline"], ["wl-copy"], "wayland")
    if shutil.which("xclip"):
        return ClipboardBackend(["xclip", "-selection", "clipboard", "-o"],
                                ["xclip", "-selection", "clipboard", "-i"], "x11")
    return ClipboardBackend(None, None, "unavailable")


class ClipboardService:
    def __init__(self, settings: Settings, emit: Callable[[str, dict], None] | None = None,
                 backend: ClipboardBackend | None = None):
        self.settings = settings
        self.emit = emit or (lambda event, data: None)
        self.backend = backend or detect_backend()
        self.last_digest = ""
        self.last_text = ""
        self.status = {
            "backend": self.backend.name,
            "available": self.backend.available,
            "direction": settings.clipboard_direction,
            "last_result": "idle",
        }

    # ---------------------------------------------------------------- policy
    def can_send_to_phone(self) -> bool:
        return (self.settings.clipboard_enabled
                and self.settings.privacy_mode is False
                and self.settings.clipboard_direction in ("both", "to_phone"))

    def can_receive_from_phone(self) -> bool:
        return (self.settings.clipboard_enabled
                and self.settings.privacy_mode is False
                and self.settings.clipboard_direction in ("both", "to_desktop"))

    # ---------------------------------------------------------------- local clipboard
    def read_local(self) -> str:
        if not self.backend.read_cmd:
            raise SessionError("capability.denied", "no clipboard tool available on this desktop")
        try:
            result = subprocess.run(self.backend.read_cmd, capture_output=True, timeout=5,
                                    check=False)
        except (OSError, subprocess.SubprocessError) as exc:
            raise SessionError("internal", f"clipboard read failed: {exc}") from exc
        if result.returncode != 0:
            return ""
        return result.stdout.decode("utf-8", "replace")[:MAX_TEXT_BYTES]

    def write_local(self, text: str) -> bool:
        if not self.backend.write_cmd:
            return False
        try:
            subprocess.run(self.backend.write_cmd, input=text.encode(), timeout=5,
                           check=False, capture_output=True)
            return True
        except (OSError, subprocess.SubprocessError):
            return False

    # ---------------------------------------------------------------- remote
    async def push_local(self, session: Session) -> dict:
        if not self.can_send_to_phone():
            raise SessionError("privacy.blocked", "clipboard sending is disabled")
        text = self.read_local()
        if not text:
            raise SessionError("capability.denied", "local clipboard is empty or unavailable")
        if looks_sensitive(text) and not self.settings.clipboard_allow_sensitive:
            raise SessionError("privacy.blocked",
                               "clipboard content looks sensitive; enable sensitive sharing first")
        return await session.request(Msg.CLIPBOARD_SET, {
            "kind": "text", "data": text, "digest": digest_text(text),
            "sensitive": looks_sensitive(text),
        })

    async def on_set(self, session: Session, body: dict) -> dict:
        if not self.can_receive_from_phone():
            raise SessionError("privacy.blocked", "clipboard receiving is disabled")
        kind = body.get("kind")
        if kind != "text":
            raise SessionError("capability.denied", "only text clipboard sync is implemented")
        text = body.get("data")
        if not isinstance(text, str):
            raise ProtocolError("protocol.json", "clipboard data must be a string")
        if len(text.encode()) > MAX_TEXT_BYTES:
            raise ProtocolError("limit.exceeded", "clipboard text too large")
        digest = str(body.get("digest", ""))
        if digest != digest_text(text):
            raise ProtocolError("protocol.json", "clipboard digest mismatch")
        if digest == self.last_digest:
            return {"digest": digest, "applied": False, "reason": "duplicate"}
        sensitive = bool(body.get("sensitive")) or looks_sensitive(text)
        if sensitive and not self.settings.clipboard_allow_sensitive:
            self.status["last_result"] = "blocked-sensitive"
            self.emit("clipboard.blocked", {"reason": "sensitive content", "digest": digest})
            raise SessionError("privacy.blocked", "sensitive clipboard content is blocked")
        applied = self.write_local(text)
        self.last_digest = digest
        self.last_text = text
        self.status["last_result"] = "applied" if applied else "received-no-backend"
        self.emit("clipboard.updated", {"digest": digest, "source": "phone",
                                        "sensitive": sensitive, "applied": applied,
                                        "preview": text[:120]})
        return {"digest": digest, "applied": applied,
                "reason": "" if applied else "no clipboard tool on this desktop"}

    def clear_local(self) -> bool:
        """Auto-clear after a sensitive handoff; never leaves the text in our own state."""
        cleared = self.write_local("")
        self.last_text = ""
        self.status["last_result"] = "cleared"
        self.emit("clipboard.cleared", {})
        return cleared
