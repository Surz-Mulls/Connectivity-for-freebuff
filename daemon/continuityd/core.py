"""Device manager: state, event bus, pairing approval and feature dispatch.

This is the single source of truth for connection state. The Qt UI, Quickshell module, CLI and
HTTP bridge are all clients of ``snapshot()``; none keeps its own copy.
"""

from __future__ import annotations

import asyncio
import datetime as _dt
import logging
import os
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import __version__
from .clipboard import ClipboardService
from .config import Settings, runtime_dir
from .dex import DexError, DexService
from .diagnostics import DiagnosticsRunner, export as export_report
from .discovery import Discovery
from .identity import Identity
from .notifications import NotificationService
from .protocol import Msg, ProtocolError, now_iso, sanitize_filename, validate_url
from .session import Peer, Session, SessionError, advertised_capabilities, start_server
from .transfers import TransferService
from .trust import TrustStore

log = logging.getLogger("continuityd.core")


class EventBus:
    """In-process fan-out with a short replay buffer for late subscribers."""

    def __init__(self, replay: int = 50):
        self._queues: set[asyncio.Queue] = set()
        self.recent: deque[dict] = deque(maxlen=replay)

    def subscribe(self, maxsize: int = 256) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=maxsize)
        self._queues.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        self._queues.discard(queue)

    def emit(self, event: str, data: dict | None = None) -> None:
        payload = {"event": event, "data": data or {}, "ts": now_iso()}
        self.recent.append(payload)
        for queue in list(self._queues):
            if queue.full():
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            with _suppress():
                queue.put_nowait(payload)


class _suppress:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return True


@dataclass
class Device:
    fingerprint: str
    device_id: str
    name: str
    platform: str = "unknown"
    caps: list[str] = field(default_factory=list)
    state: str = "disconnected"
    address: str = ""
    last_seen: str = field(default_factory=now_iso)
    battery: dict | None = None
    network: str = ""
    app_version: str = ""
    rtt_ms: float | None = None

    def public(self) -> dict:
        return {
            "fingerprint": self.fingerprint, "id": self.device_id, "name": self.name,
            "platform": self.platform, "caps": sorted(self.caps), "state": self.state,
            "address": self.address, "last_seen": self.last_seen, "battery": self.battery,
            "network": self.network, "app_version": self.app_version, "rtt_ms": self.rtt_ms,
        }


class DeviceManager:
    def __init__(self, settings: Settings, identity: Identity, trust: TrustStore,
                 *, emit=None):
        self.settings = settings
        self.identity = identity
        self.trust = trust
        self.bus = EventBus()
        self.emit = self.bus.emit
        self.capabilities = advertised_capabilities(settings)
        self.clipboard = ClipboardService(settings, self.emit)
        self.notifications = NotificationService(settings, self.emit)
        self.transfers = TransferService(settings, self.emit, approver=self._approve_transfer)
        self.dex = DexService(settings, self.emit)
        self.discovery = Discovery(identity, settings, self.emit)
        self.diagnostics = DiagnosticsRunner(settings=settings, identity=identity, manager=self)
        self.sessions: dict[str, Session] = {}
        self.devices: dict[str, Device] = {}
        self.server: asyncio.Server | None = None
        self.port = settings.port
        self.host = "0.0.0.0"
        self.started_at = time.time()
        self._pairing_requests: dict[str, asyncio.Future] = {}
        self._pending_transfers: dict[str, asyncio.Future] = {}
        self.last_error = ""
        self.recent_failures: deque[dict] = deque(maxlen=20)
        self.metrics = {"connections_total": 0, "messages_in": 0, "messages_out": 0,
                        "bytes_in": 0, "bytes_out": 0}

    # ---------------------------------------------------------------- lifecycle
    async def start(self) -> None:
        self.server = await start_server(self._on_connection, self.identity,
                                         host=self.host, port=self.settings.port)
        sockets = self.server.sockets or []
        if sockets:
            self.port = sockets[0].getsockname()[1]
        self.settings.port = self.port
        try:
            self.settings.save()
        except OSError as exc:
            log.warning("could not persist settings: %s", exc)
        await self.discovery.start(self.port)
        self.emit("daemon.started", {"port": self.port, "fingerprint": self.identity.fingerprint})

    async def stop(self) -> None:
        for session in list(self.sessions.values()):
            await session.close()
        self.sessions.clear()
        if self.server:
            self.server.close()
            await self.server.wait_closed()
        await self.discovery.stop()
        await self.dex.stop()
        self.emit("daemon.stopped", {})

    # ---------------------------------------------------------------- connections
    async def _on_connection(self, reader: asyncio.StreamReader,
                             writer: asyncio.StreamWriter) -> None:
        if len(self.sessions) >= 8:
            writer.close()
            return
        session = Session(identity=self.identity, trust=self.trust, settings=self.settings,
                          handler=self.dispatch, blob_handler=self._on_blob,
                          capabilities=self.capabilities, pair_approver=self._approve_pairing)
        await self._run_session(session, reader, writer)

    async def _run_session(self, session: Session, reader, writer) -> None:
        # StreamWriter.get_extra_info() is synchronous. Awaiting it raised TypeError on every
        # inbound connection, aborting the session before a single frame was read.
        peer = writer.get_extra_info("peername") if writer else None
        address = f"{peer[0]}:{peer[1]}" if peer else ""
        task = asyncio.create_task(session.run(reader, writer))
        self.metrics["connections_total"] += 1
        try:
            for _ in range(300):
                if session.peer is not None or session.closed:
                    break
                await asyncio.sleep(0.01)
            if session.peer:
                self._register(session, address, connected=session.trusted)
            await task
        finally:
            self._unregister(session)
            self.metrics["bytes_in"] += session.bytes_in
            self.metrics["bytes_out"] += session.bytes_out

    def _register(self, session: Session, address: str, *, connected: bool) -> None:
        assert session.peer
        peer = session.peer
        existing = self.devices.get(peer.fingerprint)
        device = Device(
            fingerprint=peer.fingerprint, device_id=peer.device.get("id", ""),
            name=peer.name, platform=peer.device.get("platform", "unknown"),
            caps=sorted(peer.caps), state="connected" if connected else "unpaired",
            address=address, app_version=peer.device.get("app_version", ""),
            battery=existing.battery if existing else None,
        )
        self.devices[peer.fingerprint] = device
        self.sessions[peer.fingerprint] = session
        self.emit("device.connected" if connected else "device.pairing_required",
                  device.public())

    def _unregister(self, session: Session) -> None:
        if session.peer:
            device = self.devices.get(session.peer.fingerprint)
            if device:
                device.state = "disconnected"
                device.last_seen = now_iso()
                self.sessions.pop(session.peer.fingerprint, None)
                self.emit("device.disconnected", device.public())
            if session.failure:
                self.last_error = f"{session.failure.code}: {session.failure.message}"
                self.recent_failures.append({"code": session.failure.code,
                                             "message": session.failure.message,
                                             "ts": now_iso()})

    async def connect(self, host: str, port: int, expected_fingerprint: str | None = None,
                      timeout: float = 15.0) -> dict:
        from .session import connect as tls_connect

        reader, writer = await tls_connect(host, port)
        session = Session(identity=self.identity, trust=self.trust, settings=self.settings,
                          handler=self.dispatch, blob_handler=self._on_blob,
                          capabilities=self.capabilities, initiator=True,
                          expected_fingerprint=expected_fingerprint,
                          pair_approver=self._approve_pairing)
        task = asyncio.create_task(session.run(reader, writer))
        for _ in range(int(timeout / 0.01)):
            if session.peer is not None or session.closed:
                break
            await asyncio.sleep(0.01)
        if session.peer is None:
            await asyncio.gather(task, return_exceptions=True)
            raise SessionError(session.failure.code if session.failure else "internal",
                               session.failure.message if session.failure else "handshake failed")
        self._register(session, f"{host}:{port}", connected=session.trusted)
        # keep the connection alive in the background
        asyncio.create_task(self._supervise(session, task))
        return {"fingerprint": session.peer.fingerprint, "trusted": session.trusted,
                "device": session.peer.describe()}

    async def _supervise(self, session: Session, task: asyncio.Task) -> None:
        try:
            await task
        finally:
            self._unregister(session)

    # ---------------------------------------------------------------- approvals
    async def _approve_pairing(self, peer: Peer) -> bool:
        """Ask the user through the UI; deny by default if nobody answers in 60 s."""
        assert peer.sas
        fingerprint = peer.fingerprint
        request = {
            "fingerprint": fingerprint,
            "device": peer.describe(),
            "sas": peer.sas,
        }
        future: asyncio.Future = asyncio.get_running_loop().create_future()
        self._pairing_requests[fingerprint] = future
        self.emit("pairing.request", request)
        try:
            return bool(await asyncio.wait_for(future, 60))
        except (asyncio.TimeoutError, TimeoutError):
            self.emit("pairing.timeout", request)
            return False
        finally:
            self._pairing_requests.pop(fingerprint, None)

    def resolve_pairing(self, fingerprint: str, accept: bool) -> bool:
        future = self._pairing_requests.get(fingerprint)
        if not future or future.done():
            return False
        future.set_result(accept)
        return True

    async def _approve_transfer(self, info: dict) -> bool:
        if self.settings.files_auto_accept:
            return True
        future: asyncio.Future = asyncio.get_running_loop().create_future()
        self._pending_transfers[info["transfer_id"]] = future
        self.emit("transfer.request", info)
        try:
            return bool(await asyncio.wait_for(future, 60))
        except (asyncio.TimeoutError, TimeoutError):
            return False
        finally:
            self._pending_transfers.pop(info["transfer_id"], None)

    def resolve_transfer(self, transfer_id: str, accept: bool) -> bool:
        future = self._pending_transfers.get(transfer_id)
        if not future or future.done():
            return False
        future.set_result(accept)
        return True

    # ---------------------------------------------------------------- dispatch
    async def dispatch(self, session: Session, msg: dict) -> dict | None:
        self.metrics["messages_in"] += 1
        msg_type, body = msg["type"], msg["body"]
        if msg_type == Msg.CLIPBOARD_SET:
            return await self.clipboard.on_set(session, body)
        if msg_type == Msg.FILE_OFFER:
            return await self.transfers.on_offer(session, body)
        if msg_type == Msg.FILE_DONE:
            return await self.transfers.on_done(session, body)
        if msg_type == Msg.NOTIFY_POST:
            return await self.notifications.on_post(session, body)
        if msg_type == Msg.NOTIFY_DISMISS:
            return await self.notifications.on_dismiss(session, body)
        if msg_type == Msg.HANDOFF_URL:
            url = validate_url(str(body.get("url", "")))
            self.emit("handoff.received", {"url": url, "title": str(body.get("title", ""))[:200],
                                           "from": session.peer.name if session.peer else ""})
            return {"accepted": True, "url": url}
        if msg_type == Msg.FIND_RING:
            self.emit("find.ring", {"from": session.peer.name if session.peer else ""})
            return {"ok": True}
        if msg_type == Msg.FIND_PING:
            self.emit("find.ping", {"from": session.peer.name if session.peer else ""})
            return {"ok": True}
        if msg_type == Msg.STATUS:
            self._update_status(session, body)
            return None
        if msg_type == Msg.STATUS_REQUEST:
            return {"battery": {"level": None, "charging": None}, "network": "unknown",
                    "app_version": __version__, "foreground": True}
        if msg_type == Msg.MEDIA_STATE:
            self.emit("media.state", dict(body))
            return None
        if msg_type == Msg.MEDIA_COMMAND:
            raise SessionError("capability.denied",
                               "media command bridges to the phone from the engine, "
                               "not from the desktop daemon")
        if msg_type == Msg.PRIVACY_SET:
            raise SessionError("privacy.blocked",
                               "privacy is local-only; a peer cannot change this device's policy")
        if msg_type == Msg.DEX_PROBE:
            return await self.dex.probe()
        if msg_type == Msg.SYNC_MANIFEST or msg_type == Msg.SYNC_PLAN:
            raise SessionError("capability.denied",
                               "folder sync is not implemented in this build")
        raise SessionError("protocol.unsupported", f"no handler for {msg_type}")

    async def _on_blob(self, session: Session, header: dict, data: bytes) -> None:
        if header.get("type") != Msg.FILE_CHUNK:
            raise ProtocolError("protocol.unsupported", "unexpected binary frame")
        await self.transfers.on_chunk(session, header, data)

    def _update_status(self, session: Session, body: dict) -> None:
        if not session.peer:
            return
        device = self.devices.get(session.peer.fingerprint)
        if not device:
            return
        battery = body.get("battery")
        if isinstance(battery, dict):
            level = battery.get("level")
            device.battery = {"level": level if isinstance(level, int) else None,
                              "charging": bool(battery.get("charging"))}
        device.network = str(body.get("network", ""))[:32]
        device.last_seen = now_iso()
        self.emit("device.status", device.public())

    # ---------------------------------------------------------------- actions
    def session_for(self, fingerprint: str) -> Session:
        session = self.sessions.get(fingerprint)
        if not session or not session.trusted:
            raise SessionError("auth.required", "device is not connected")
        return session

    async def push_clipboard(self, fingerprint: str) -> dict:
        return await self.clipboard.push_local(self.session_for(fingerprint))

    async def send_file(self, fingerprint: str, path: str) -> dict:
        transfer = await self.transfers.send_file(self.session_for(fingerprint), Path(path))
        return transfer.public()

    async def send_handoff(self, fingerprint: str, url: str) -> dict:
        url = validate_url(url)
        reply = await self.session_for(fingerprint).request(Msg.HANDOFF_URL, {"url": url})
        return reply["body"]

    async def ring(self, fingerprint: str, duration_s: int = 10) -> dict:
        duration = max(1, min(int(duration_s), 30))
        reply = await self.session_for(fingerprint).request(Msg.FIND_RING,
                                                            {"duration_s": duration})
        return reply["body"]

    async def ping_device(self, fingerprint: str) -> dict:
        session = self.session_for(fingerprint)
        started = time.monotonic()
        await session.request(Msg.PING, {"ts": now_iso()}, timeout=5)
        rtt = (time.monotonic() - started) * 1000
        device = self.devices.get(fingerprint)
        if device:
            device.rtt_ms = round(rtt, 1)
        return {"ok": True, "rtt_ms": round(rtt, 1)}

    def revoke(self, fingerprint: str) -> dict:
        session = self.sessions.pop(fingerprint, None)
        revoked = self.trust.revoke(fingerprint)
        device = self.devices.get(fingerprint)
        if device:
            device.state = "revoked"
        if session:
            asyncio.create_task(session.close())
        self.emit("trust.revoked", {"fingerprint": fingerprint, "revoked": revoked})
        return {"revoked": revoked}

    def update_privacy(self, *, privacy_mode: bool | None = None,
                       clipboard_direction: str | None = None,
                       paused_features: list[str] | None = None) -> dict:
        if privacy_mode is not None:
            self.settings.privacy_mode = bool(privacy_mode)
        if clipboard_direction:
            if clipboard_direction not in ("off", "to_phone", "to_desktop", "both"):
                raise ProtocolError("protocol.json", "invalid clipboard direction")
            self.settings.clipboard_direction = clipboard_direction
        if paused_features is not None:
            self.settings.paused_features = [str(f)[:32] for f in paused_features][:32]
        self.settings.save()
        self.clipboard.status["direction"] = self.settings.clipboard_direction
        snapshot = self.snapshot()["privacy"]
        self.emit("privacy.changed", snapshot)
        return snapshot

    # ---------------------------------------------------------------- pairing helpers
    def pairing_payload(self) -> dict:
        host = self.discovery._local_ip() if hasattr(self.discovery, "_local_ip") else "127.0.0.1"
        uri = (f"continuity://pair?fpr={self.identity.fingerprint}&host={host}"
               f"&port={self.port}&name={self.identity.name}")
        result = {"uri": uri, "fingerprint": self.identity.fingerprint, "host": host,
                  "port": self.port, "name": self.identity.name, "qr_svg": None}
        try:
            import qrcode
            import qrcode.image.svg

            image = qrcode.make(uri, image_factory=qrcode.image.svg.SvgPathImage)
            path = runtime_dir() / "pair-qr.svg"
            image.save(str(path))
            os.chmod(path, 0o600)
            result["qr_svg"] = str(path)
        except Exception as exc:  # noqa: BLE001 - QR is a convenience
            log.debug("QR generation failed: %s", exc)
        return result

    # ---------------------------------------------------------------- reporting
    def snapshot(self) -> dict:
        now = now_iso()
        privacy = {
            "privacy_mode": self.settings.privacy_mode,
            "clipboard_direction": self.settings.clipboard_direction,
            "clipboard_allow_sensitive": self.settings.clipboard_allow_sensitive,
            "paused_features": list(self.settings.paused_features),
            "notifications_enabled": self.settings.notifications_enabled,
            "notifications_include_sensitive": self.settings.notifications_include_sensitive,
            "files_enabled": self.settings.files_enabled,
            "files_auto_accept": self.settings.files_auto_accept,
            "adb_enabled": self.settings.adb_enabled,
            "shizuku_enabled": self.settings.shizuku_enabled,
        }
        return {
            "schema": "continuity.state/1",
            "updated": now,
            "daemon": {
                "version": __version__, "state": "running", "port": self.port,
                "uptime_s": round(time.time() - self.started_at, 1),
                "device": {"id": self.identity.device_id, "name": self.identity.name,
                           "fingerprint": self.identity.fingerprint},
                "capabilities": self.capabilities, "last_error": self.last_error,
            },
            "privacy": privacy,
            "devices": [d.public() for d in self.devices.values()],
            "trusted": [p.__dict__ for p in self.trust.active()],
            "transfers": [t.public() for t in self.transfers.transfers.values()],
            "clipboard": dict(self.clipboard.status),
            "notifications": self.notifications.snapshot(),
            "dex": self.dex.status(),
            "metrics": dict(self.metrics),
            "pairing": {"pending": [
                {"fingerprint": f, "sas": None} for f in self._pairing_requests
            ]},
        }

    # ---------------------------------------------------------------- diagnostics
    def run_diagnostics(self, out_dir: Path | None = None) -> dict:
        report = self.diagnostics.run()
        paths = export_report(report, out_dir or (Path(__file__).resolve().parents[2]
                                                  / "artifacts" / "reports"))
        self.emit("diagnostics.ready", {"report": report.to_dict(), "paths": paths})
        return {"report": report.to_dict(), "paths": paths}


def iso_now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat()
