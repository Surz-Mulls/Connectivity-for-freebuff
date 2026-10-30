"""Unit tests for clipboard policy and transfer bookkeeping."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from continuityd.clipboard import ClipboardBackend, ClipboardService, looks_sensitive
from continuityd.config import Settings
from continuityd.protocol import ProtocolError
from continuityd.transfers import TransferService


def make_settings(tmp_path: Path, **overrides) -> Settings:
    settings = Settings.load(tmp_path / "settings.json")
    settings.receive_dir = str(tmp_path / "received")
    for key, value in overrides.items():
        setattr(settings, key, value)
    Path(settings.receive_dir).mkdir(parents=True, exist_ok=True)
    return settings


def test_sensitive_detection():
    assert looks_sensitive("123456")
    assert looks_sensitive("Password: hunter2")
    assert looks_sensitive("-----BEGIN OPENSSH PRIVATE KEY-----")
    assert not looks_sensitive("see you at 8 for dinner")
    assert not looks_sensitive("https://example.com/docs")


def test_clipboard_direction_and_privacy_gating(tmp_path):
    settings = make_settings(tmp_path)
    backend = ClipboardBackend(None, None, "test")
    service = ClipboardService(settings, backend=backend)
    assert service.can_send_to_phone()
    settings.clipboard_direction = "to_desktop"
    assert not service.can_send_to_phone()
    assert service.can_receive_from_phone()
    settings.privacy_mode = True
    assert not service.can_send_to_phone() and not service.can_receive_from_phone()


async def test_clipboard_receives_verified_text(tmp_path):
    settings = make_settings(tmp_path)
    written: list[str] = []
    backend = ClipboardBackend(["true"], ["true"], "test")
    service = ClipboardService(settings, backend=backend)
    service.write_local = lambda text: (written.append(text), True)[1]  # type: ignore[assignment]
    text = "hello from the phone"
    digest = hashlib.sha256(text.encode()).hexdigest()
    session = object()
    result = await service.on_set(session, {"kind": "text", "data": text, "digest": digest})
    assert result["applied"] is True and written == [text]
    duplicate = await service.on_set(session, {"kind": "text", "data": text, "digest": digest})
    assert duplicate["applied"] is False


async def test_clipboard_rejects_digest_mismatch_and_sensitive(tmp_path):
    settings = make_settings(tmp_path)
    service = ClipboardService(settings, backend=ClipboardBackend(None, None, "test"))
    with pytest.raises(ProtocolError):
        await service.on_set(object(), {"kind": "text", "data": "abc", "digest": "0" * 64})
    from continuityd.session import SessionError

    digest = hashlib.sha256(b"123456").hexdigest()
    with pytest.raises(SessionError) as exc:
        await service.on_set(object(), {"kind": "text", "data": "123456", "digest": digest})
    assert exc.value.code == "privacy.blocked"


async def test_transfer_rejects_oversized_offer(tmp_path):
    settings = make_settings(tmp_path)
    service = TransferService(settings)
    fake_session = type("S", (), {"peer": type("P", (), {"name": "x"})()})()
    with pytest.raises(ProtocolError):
        await service.on_offer(fake_session, {
            "transfer_id": "t", "name": "big.bin", "size": 9 * 1024**3,
            "sha256": "a" * 64,
        })


async def test_chunk_integrity_failure_leaves_no_file(tmp_path):
    settings = make_settings(tmp_path, files_auto_accept=True)
    service = TransferService(settings)
    fake_session = type("S", (), {"peer": type("P", (), {"name": "x"})()})()
    payload = b"hello world"
    offer = await service.on_offer(fake_session, {
        "transfer_id": "t2", "name": "note.txt", "size": len(payload),
        "sha256": hashlib.sha256(b"different").hexdigest(),
    })
    assert offer["accept"] is True
    await service.on_chunk(None, {"transfer_id": "t2", "offset": 0}, payload)
    result = await service.on_done(None, {"transfer_id": "t2"})
    assert result["ok"] is False
    received = Path(settings.receive_dir)
    assert not (received / "note.txt").exists()
    assert not list(received.glob("*.part"))


async def test_successful_transfer_writes_file(tmp_path):
    settings = make_settings(tmp_path, files_auto_accept=True)
    service = TransferService(settings)
    fake_session = type("S", (), {"peer": type("P", (), {"name": "x"})()})()
    payload = b"payload!" * 1000
    digest = hashlib.sha256(payload).hexdigest()
    await service.on_offer(fake_session, {
        "transfer_id": "t3", "name": "data.bin", "size": len(payload),
        "sha256": digest,
    })
    await service.on_chunk(None, {"transfer_id": "t3", "offset": 0}, payload)
    result = await service.on_done(None, {"transfer_id": "t3"})
    assert result["ok"] is True
    assert (Path(settings.receive_dir) / "data.bin").read_bytes() == payload


async def test_duplicate_names_do_not_overwrite(tmp_path):
    settings = make_settings(tmp_path, files_auto_accept=True)
    service = TransferService(settings)
    fake_session = type("S", (), {"peer": type("P", (), {"name": "x"})()})()
    (Path(settings.receive_dir) / "report.pdf").write_bytes(b"existing")
    payload = b"new"
    await service.on_offer(fake_session, {
        "transfer_id": "t4", "name": "report.pdf", "size": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
    })
    await service.on_chunk(None, {"transfer_id": "t4", "offset": 0}, payload)
    await service.on_done(None, {"transfer_id": "t4"})
    assert (Path(settings.receive_dir) / "report.pdf").read_bytes() == b"existing"
    assert (Path(settings.receive_dir) / "report-1.pdf").read_bytes() == b"new"
