"""Notification mirroring and reply routing.

The desktop never invents notification content. It stores what the phone sent, deduplicates by
notification key, emits events for the UI, and forwards a reply only for an action the phone
advertised as reply-capable. Sensitive bodies are dropped unless the user opted in.

Desktop delivery uses ``notify-send`` when present; the daemon never blocks on it.
"""

from __future__ import annotations

import asyncio
import shutil
import subprocess
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Callable

from .config import Settings
from .protocol import Msg, ProtocolError
from .session import Session, SessionError

MAX_BODY = 4096
MAX_STORED = 200


@dataclass
class MirrorNotification:
    key: str
    app: str
    title: str
    text: str = ""
    actions: list[dict] = field(default_factory=list)
    sensitive: bool = False
    received: float = field(default_factory=time.time)
    dismissed: bool = False

    def public(self) -> dict:
        return {
            "key": self.key, "app": self.app, "title": self.title, "text": self.text,
            "actions": self.actions, "sensitive": self.sensitive,
            "received": self.received, "dismissed": self.dismissed,
            "replyable": any(a.get("reply") for a in self.actions),
        }


class NotificationService:
    def __init__(self, settings: Settings, emit: Callable[[str, dict], None] | None = None):
        self.settings = settings
        self.emit = emit or (lambda event, data: None)
        self.items: "OrderedDict[str, MirrorNotification]" = OrderedDict()
        self.notify_send = shutil.which("notify-send")
        self.desktop_bridge = bool(self.notify_send)

    # ---------------------------------------------------------------- inbound
    async def on_post(self, session: Session, body: dict) -> dict:
        if not self.settings.notifications_enabled:
            raise SessionError("privacy.blocked", "notification mirroring is disabled")
        key = str(body.get("key", ""))[:256]
        if not key:
            raise ProtocolError("protocol.json", "notification key required")
        sensitive = bool(body.get("sensitive"))
        if sensitive and not self.settings.notifications_include_sensitive:
            stored = MirrorNotification(key=key, app="redacted", title="Sensitive notification",
                                        text="Content hidden by your privacy settings",
                                        sensitive=True)
        else:
            stored = MirrorNotification(
                key=key,
                app=str(body.get("app", ""))[:64],
                title=str(body.get("title", ""))[:256],
                text=str(body.get("text", ""))[:MAX_BODY],
                actions=[a for a in body.get("actions", []) if isinstance(a, dict)][:6],
                sensitive=sensitive,
            )
        existing = self.items.get(key)
        self.items[key] = stored
        self.items.move_to_end(key)
        while len(self.items) > MAX_STORED:
            self.items.popitem(last=False)
        self.emit("notification.posted", stored.public())
        if not existing:
            self._desktop_notify(stored)
        return {"key": key, "accepted": True, "replyable": stored.public()["replyable"]}

    async def on_dismiss(self, session: Session, body: dict) -> dict:
        key = str(body.get("key", ""))
        item = self.items.get(key)
        if item and not item.dismissed:
            item.dismissed = True
            self.emit("notification.dismissed", {"key": key})
            return {"key": key, "dismissed": True}
        return {"key": key, "dismissed": False}

    # ---------------------------------------------------------------- outbound
    async def reply(self, session: Session, key: str, text: str) -> dict:
        item = self.items.get(key)
        if not item or item.dismissed:
            raise SessionError("protocol.unsupported", "unknown or dismissed notification")
        action = next((a for a in item.actions if a.get("reply")), None)
        if not action:
            raise SessionError("capability.denied", "this notification has no reply action")
        if not text.strip():
            raise ProtocolError("protocol.json", "empty reply")
        return await session.request(Msg.NOTIFY_ACTION, {
            "key": key, "action_id": action.get("id", "reply"), "reply_text": text[:4096],
        })

    async def dismiss(self, session: Session, key: str) -> dict:
        return await session.request(Msg.NOTIFY_ACTION, {"key": key, "action_id": "dismiss"})

    # ---------------------------------------------------------------- helpers
    def _desktop_notify(self, item: MirrorNotification) -> None:
        if not self.notify_send:
            return
        argv = [self.notify_send, "--app-name", "Continuity", f"{item.app}: {item.title}"]
        if item.text:
            argv.append(item.text[:512])
        try:
            asyncio.get_running_loop().run_in_executor(
                None, lambda: subprocess.run(argv, check=False, timeout=3,
                                             capture_output=True))
        except (OSError, subprocess.SubprocessError, RuntimeError):
            pass

    def trim(self) -> int:
        """Drop notifications older than the configured retention."""
        cutoff = time.time() - max(1, self.settings.notifications_retention_days) * 86400
        stale = [k for k, v in self.items.items() if v.received < cutoff]
        for key in stale:
            self.items.pop(key, None)
        return len(stale)

    def snapshot(self) -> list[dict]:
        return [item.public() for item in self.items.values() if not item.dismissed]
