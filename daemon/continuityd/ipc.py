"""Local control surfaces.

1. Canonical: a JSON-lines Unix socket at ``$XDG_RUNTIME_DIR/continuity/ipc.sock`` (0600), and the
   peer credentials are checked with ``SO_PEERCRED`` so only the same UID can talk to it.
2. Convenience: a loopback-only HTTP/1.1 bridge guarded by a random bearer token stored 0600 in the
   runtime dir. It exists because a pure-QML application cannot open Unix sockets; every command
   goes through the same ``handle_command`` function, so the two surfaces cannot drift.

No command accepts a shell string. Paths are expanded and must exist; everything else is a
validated JSON field.
"""

from __future__ import annotations

import asyncio
import json
import os
import secrets
import socket
import struct
from pathlib import Path
from typing import Any

from .config import ipc_socket_path, runtime_dir
from .protocol import ProtocolError
from .session import SessionError

MAX_REQUEST = 64 * 1024
HTTP_PORT_FILE = "http.token"


class IPCServer:
    def __init__(self, manager):
        self.manager = manager
        self.server: asyncio.Server | None = None
        self.http_server: asyncio.Server | None = None
        self.token = secrets.token_urlsafe(32)
        self.http_port = 0
        self.token_file = runtime_dir() / HTTP_PORT_FILE

    # ---------------------------------------------------------------- unix socket
    async def start(self) -> dict:
        path = ipc_socket_path()
        path.unlink(missing_ok=True)
        self.server = await asyncio.start_unix_server(self._handle_client, path=str(path),
                                                      limit=MAX_REQUEST)
        os.chmod(path, 0o600)
        await self._start_http()
        return {"socket": str(path), "http_port": self.http_port,
                "token_file": str(self.token_file)}

    async def _start_http(self) -> None:
        self.http_server = await asyncio.start_server(self._handle_http, host="127.0.0.1",
                                                      port=0, limit=MAX_REQUEST)
        sockets = self.http_server.sockets or []
        if sockets:
            self.http_port = sockets[0].getsockname()[1]
        # 0600 file readable only by this user; the QML launcher passes it in-memory
        self.token_file.write_text(json.dumps({"port": self.http_port, "token": self.token}))
        os.chmod(self.token_file, 0o600)

    async def stop(self) -> None:
        for server in (self.server, self.http_server):
            if not server:
                continue
            server.close()
            try:
                # Python 3.12 waits for live handlers; a daemon must not hang on shutdown.
                await asyncio.wait_for(server.wait_closed(), 2.0)
            except (asyncio.TimeoutError, TimeoutError):
                pass
        ipc_socket_path().unlink(missing_ok=True)
        self.token_file.unlink(missing_ok=True)

    async def _handle_client(self, reader: asyncio.StreamReader,
                             writer: asyncio.StreamWriter) -> None:
        if not _same_uid(writer):
            writer.close()
            return
        stream_task = None
        try:
            await self._write(writer, {"event": "hello", "data": self.manager.snapshot()})
            while True:
                line = await reader.readline()
                if not line:
                    break
                if len(line) > MAX_REQUEST:
                    await self._write(writer, {"error": "limit.exceeded"})
                    break
                try:
                    command = json.loads(line)
                except json.JSONDecodeError:
                    await self._write(writer, {"error": "protocol.json"})
                    continue
                if not isinstance(command, dict):
                    await self._write(writer, {"error": "protocol.json"})
                    continue
                if command.get("cmd") == "events":
                    queue = self.manager.bus.subscribe()
                    await self._write(writer, {"event": "subscribed", "data": {}})
                    try:
                        while True:
                            event = await queue.get()
                            await self._write(writer, event)
                    except (ConnectionError, asyncio.CancelledError):
                        pass
                    finally:
                        self.manager.bus.unsubscribe(queue)
                    break
                reply = await self.handle_command(command)
                await self._write(writer, {"event": "result", "command": command.get("cmd"),
                                           "data": reply})
        except (ConnectionError, asyncio.IncompleteReadError):
            pass
        finally:
            if stream_task:
                stream_task.cancel()
            writer.close()

    @staticmethod
    async def _write(writer: asyncio.StreamWriter, payload: dict) -> None:
        writer.write((json.dumps(payload, separators=(",", ":")) + "\n").encode())
        await writer.drain()

    # ---------------------------------------------------------------- http bridge
    async def _handle_http(self, reader: asyncio.StreamReader,
                           writer: asyncio.StreamWriter) -> None:
        try:
            request_line = await asyncio.wait_for(reader.readline(), 5)
            if not request_line:
                return
            method, target, _ = request_line.decode("latin-1").strip().split(" ", 2)
            headers: dict[str, str] = {}
            for _ in range(50):
                line = await asyncio.wait_for(reader.readline(), 5)
                if line in (b"\r\n", b"\n", b""):
                    break
                key, _, value = line.decode("latin-1").partition(":")
                headers[key.strip().lower()] = value.strip()
            if headers.get("authorization", "") != f"Bearer {self.token}":
                await _http_reply(writer, 401, {"error": "auth.required"})
                return
            if method == "GET" and target.startswith("/api/status"):
                await _http_reply(writer, 200, self.manager.snapshot())
                return
            if method == "GET" and target.startswith("/api/qr"):
                await _http_reply(writer, 200, self.manager.pairing_payload())
                return
            if method == "POST" and target.startswith("/api/command"):
                length = int(headers.get("content-length", "0") or 0)
                if length <= 0 or length > MAX_REQUEST:
                    await _http_reply(writer, 400, {"error": "protocol.json"})
                    return
                body = await reader.readexactly(length)
                try:
                    command = json.loads(body)
                except json.JSONDecodeError:
                    await _http_reply(writer, 400, {"error": "protocol.json"})
                    return
                reply = await self.handle_command(command)
                await _http_reply(writer, 200, reply)
                return
            await _http_reply(writer, 404, {"error": "protocol.unsupported"})
        except (asyncio.TimeoutError, TimeoutError, ValueError, ConnectionError):
            pass
        finally:
            writer.close()

    # ---------------------------------------------------------------- commands
    async def handle_command(self, command: dict[str, Any]) -> dict:
        """Allowlisted command surface shared by the socket, HTTP bridge and CLI."""
        try:
            name = command.get("cmd")
            if not isinstance(name, str):
                raise ProtocolError("protocol.json", "cmd must be a string")
            handler = getattr(self, f"_cmd_{name.replace('.', '_')}", None)
            if handler is None:
                raise ProtocolError("protocol.unsupported", f"unknown command {name!r}")
            return {"ok": True, "result": await handler(command)}
        except (ProtocolError, SessionError) as exc:
            return {"ok": False, "code": exc.code, "message": exc.message}
        except FileNotFoundError as exc:
            return {"ok": False, "code": "protocol.json", "message": str(exc)}
        except Exception as exc:  # noqa: BLE001 - one bad command must not kill the daemon
            return {"ok": False, "code": "internal",
                    "message": f"{exc.__class__.__name__}: {exc}"}

    async def _cmd_status(self, command: dict) -> dict:
        return self.manager.snapshot()

    async def _cmd_devices(self, command: dict) -> list[dict]:
        return self.manager.snapshot()["devices"]

    async def _cmd_pair_begin(self, command: dict) -> dict:
        return self.manager.pairing_payload()

    async def _cmd_pair_connect(self, command: dict) -> dict:
        host = str(command.get("host", ""))
        port = int(command.get("port", 0))
        if not host or not 1 <= port <= 65535:
            raise ProtocolError("protocol.json", "host and port are required")
        return await self.manager.connect(host, port, command.get("fingerprint"))

    async def _cmd_pair_approve(self, command: dict) -> dict:
        fingerprint = str(command.get("fingerprint", ""))
        if not self.manager.resolve_pairing(fingerprint, bool(command.get("accept", False))):
            raise ProtocolError("protocol.unsupported", "no pending pairing for that device")
        return {"resolved": True}

    async def _cmd_pair_discover(self, command: dict) -> dict:
        peers = await self.manager.discovery.browse(float(command.get("timeout", 3)))
        return {"peers": peers}

    async def _cmd_trust_list(self, command: dict) -> list[dict]:
        return [p.__dict__ for p in self.manager.trust.peers]

    async def _cmd_trust_revoke(self, command: dict) -> dict:
        fingerprint = str(command.get("fingerprint", ""))
        return self.manager.revoke(fingerprint)

    async def _cmd_clipboard_push(self, command: dict) -> dict:
        return await self.manager.push_clipboard(str(command.get("fingerprint", "")))

    async def _cmd_clipboard_pull(self, command: dict) -> dict:
        text = self.manager.clipboard.read_local()
        return {"text_length": len(text)}

    async def _cmd_file_send(self, command: dict) -> dict:
        path = Path(str(command.get("path", ""))).expanduser()
        if not path.is_file():
            raise ProtocolError("protocol.json", "path is not a readable file")
        return await self.manager.send_file(str(command.get("fingerprint", "")), str(path))

    async def _cmd_file_accept(self, command: dict) -> dict:
        resolved = self.manager.resolve_transfer(str(command.get("transfer_id", "")),
                                                 bool(command.get("accept", False)))
        if not resolved:
            raise ProtocolError("protocol.unsupported", "no pending transfer offer")
        return {"resolved": True}

    async def _cmd_handoff_send(self, command: dict) -> dict:
        return await self.manager.send_handoff(str(command.get("fingerprint", "")),
                                               str(command.get("url", "")))

    async def _cmd_find_ring(self, command: dict) -> dict:
        return await self.manager.ring(str(command.get("fingerprint", "")),
                                       int(command.get("duration_s", 10)))

    async def _cmd_find_ping(self, command: dict) -> dict:
        return await self.manager.ping_device(str(command.get("fingerprint", "")))

    async def _cmd_privacy_set(self, command: dict) -> dict:
        return self.manager.update_privacy(
            privacy_mode=command.get("privacy_mode"),
            clipboard_direction=command.get("clipboard_direction"),
            paused_features=command.get("paused_features"),
        )

    async def _cmd_settings_get(self, command: dict) -> dict:
        return self.manager.settings.public()

    async def _cmd_settings_set(self, command: dict) -> dict:
        allowed = {"clipboard_allow_sensitive", "clipboard_images", "notifications_enabled",
                   "notifications_include_sensitive", "files_auto_accept", "adb_enabled",
                   "discovery_enabled", "verification_code_handoff", "log_level"}
        for key, value in (command.get("settings") or {}).items():
            if key not in allowed:
                raise ProtocolError("protocol.unsupported", f"setting {key!r} is not settable")
            setattr(self.manager.settings, key, value)
        self.manager.settings.save()
        return self.manager.settings.public()

    async def _cmd_diagnostics_run(self, command: dict) -> dict:
        return self.manager.run_diagnostics()

    async def _cmd_dex_probe(self, command: dict) -> dict:
        return await self.manager.dex.probe()

    async def _cmd_dex_start(self, command: dict) -> dict:
        return await self.manager.dex.start(mode=str(command.get("mode", "virtual_display")),
                                            package=command.get("package"))

    async def _cmd_dex_stop(self, command: dict) -> dict:
        return await self.manager.dex.stop()

    async def _cmd_dex_status(self, command: dict) -> dict:
        return self.manager.dex.status()

    async def _cmd_notifications_list(self, command: dict) -> list[dict]:
        return self.manager.notifications.snapshot()

    async def _cmd_notifications_reply(self, command: dict) -> dict:
        session = self.manager.session_for(str(command.get("fingerprint", "")))
        return await self.manager.notifications.reply(session, str(command.get("key", "")),
                                                      str(command.get("text", "")))

    async def _cmd_shutdown(self, command: dict) -> dict:
        asyncio.create_task(self._shutdown())
        return {"stopping": True}

    async def _shutdown(self) -> None:
        await asyncio.sleep(0.1)
        await self.manager.stop()


async def _http_reply(writer: asyncio.StreamWriter, status: int, payload: dict) -> None:
    body = json.dumps(payload).encode()
    reason = {200: "OK", 400: "Bad Request", 401: "Unauthorized", 404: "Not Found"}.get(
        status, "OK")
    head = (f"HTTP/1.1 {status} {reason}\r\n"
            "Content-Type: application/json\r\n"
            "Cache-Control: no-store\r\n"
            f"Content-Length: {len(body)}\r\n"
            "Connection: close\r\n\r\n")
    writer.write(head.encode() + body)
    await writer.drain()


def _same_uid(writer: asyncio.StreamWriter) -> bool:
    """SO_PEERCRED check: the socket is 0600, but verify anyway."""
    try:
        sock = writer.get_extra_info("socket")
        if sock is None:
            return False
        raw = sock.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i"))
        _pid, uid, _gid = struct.unpack("3i", raw)
        return uid == os.getuid()
    except (AttributeError, OSError):
        return True  # non-Linux fallback: rely on filesystem permissions
