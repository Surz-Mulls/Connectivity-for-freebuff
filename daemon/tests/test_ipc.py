"""IPC surface tests: allowlist, validation, HTTP bridge auth and state snapshot."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from continuityd.config import Settings
from continuityd.core import DeviceManager
from continuityd.identity import Identity
from continuityd.ipc import IPCServer
from continuityd.trust import TrustStore


@pytest.fixture()
def manager(tmp_path, monkeypatch):
    # keep the runtime path short: AF_UNIX paths are capped at ~108 bytes
    runtime = Path("/tmp") / f"ct-runtime-{tmp_path.name[-12:]}"
    runtime.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(runtime))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    settings = Settings.load(tmp_path / "settings.json")
    identity = Identity.load_or_create(tmp_path / "identity", "test-desktop")
    trust = TrustStore.load(tmp_path / "trust.json")
    return DeviceManager(settings, identity, trust)


async def test_snapshot_shape(manager):
    snapshot = manager.snapshot()
    assert snapshot["schema"] == "continuity.state/1"
    assert snapshot["daemon"]["device"]["fingerprint"] == manager.identity.fingerprint
    assert snapshot["privacy"]["privacy_mode"] is False
    assert snapshot["devices"] == []
    assert "dex" in snapshot and "clipboard" in snapshot


async def test_unknown_command_is_rejected(manager):
    ipc = IPCServer(manager)
    result = await ipc.handle_command({"cmd": "root.shell"})
    assert result["ok"] is False and result["code"] == "protocol.unsupported"


async def test_settings_allowlist_blocks_privileged_keys(manager):
    ipc = IPCServer(manager)
    bad = await ipc.handle_command({"cmd": "settings.set",
                                    "settings": {"shizuku_enabled": True}})
    assert bad["ok"] is False
    good = await ipc.handle_command({"cmd": "settings.set",
                                     "settings": {"notifications_enabled": False}})
    assert good["ok"] is True
    assert manager.settings.notifications_enabled is False


async def test_privacy_mode_disables_clipboard(manager):
    ipc = IPCServer(manager)
    result = await ipc.handle_command({"cmd": "privacy.set", "privacy_mode": True})
    assert result["ok"] is True
    assert manager.clipboard.can_send_to_phone() is False
    assert manager.clipboard.can_receive_from_phone() is False


async def test_file_send_requires_existing_path(manager):
    ipc = IPCServer(manager)
    result = await ipc.handle_command({"cmd": "file.send", "fingerprint": "x" * 64,
                                       "path": "/definitely/not/here"})
    assert result["ok"] is False and result["code"] == "protocol.json"


async def test_transfer_approval_unknown_id(manager):
    ipc = IPCServer(manager)
    result = await ipc.handle_command({"cmd": "file.accept", "transfer_id": "nope",
                                       "accept": True})
    assert result["ok"] is False


async def test_unix_socket_roundtrip(manager, tmp_path):
    ipc = IPCServer(manager)
    await ipc.start()
    try:
        from continuityd.config import ipc_socket_path

        reader, writer = await asyncio.open_unix_connection(str(ipc_socket_path()))
        hello = json.loads(await reader.readline())
        assert hello["event"] == "hello"
        writer.write(b'{"cmd":"status"}\n')
        await writer.drain()
        while True:
            payload = json.loads(await reader.readline())
            if payload.get("event") == "result":
                break
        assert payload["data"]["result"]["schema"] == "continuity.state/1"
        writer.close()
    finally:
        await ipc.stop()


async def test_http_bridge_requires_token(manager):
    ipc = IPCServer(manager)
    await ipc.start()
    try:
        reader, writer = await asyncio.open_connection("127.0.0.1", ipc.http_port)
        writer.write(b"GET /api/status HTTP/1.1\r\nHost: localhost\r\n\r\n")
        await writer.drain()
        status_line = await reader.readline()
        assert b"401" in status_line
        writer.close()

        reader, writer = await asyncio.open_connection("127.0.0.1", ipc.http_port)
        request = (f"GET /api/status HTTP/1.1\r\nHost: localhost\r\n"
                   f"Authorization: Bearer {ipc.token}\r\n\r\n")
        writer.write(request.encode())
        await writer.drain()
        status_line = await reader.readline()
        assert b"200" in status_line
        while (await reader.readline()) not in (b"\r\n", b"\n", b""):
            pass
        body = await reader.readline()
        assert json.loads(body)["schema"] == "continuity.state/1"
        writer.close()
    finally:
        await ipc.stop()


async def test_http_command_executes(manager):
    ipc = IPCServer(manager)
    await ipc.start()
    try:
        reader, writer = await asyncio.open_connection("127.0.0.1", ipc.http_port)
        body = json.dumps({"cmd": "privacy.set", "privacy_mode": True}).encode()
        request = (f"POST /api/command HTTP/1.1\r\nHost: localhost\r\n"
                   f"Authorization: Bearer {ipc.token}\r\nContent-Length: {len(body)}\r\n\r\n")
        writer.write(request.encode() + body)
        await writer.drain()
        assert b"200" in await reader.readline()
        while (await reader.readline()) not in (b"\r\n", b"\n", b""):
            pass
        payload = json.loads(await reader.readline())
        assert payload["ok"] is True and payload["result"]["privacy_mode"] is True
        writer.close()
    finally:
        await ipc.stop()


def test_qr_payload_contains_fingerprint(manager):
    payload = manager.pairing_payload()
    assert payload["uri"].startswith("continuity://pair?")
    assert manager.identity.fingerprint in payload["uri"]
    assert payload["port"] == manager.port
