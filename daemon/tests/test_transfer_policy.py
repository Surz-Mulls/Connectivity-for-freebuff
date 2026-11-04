"""Hostile-case coverage for the receive side of file transfer.

Every test drives the real ``TransferService``; nothing is mocked except the session object, which
only has to expose the authenticated peer identity the handshake would provide.
"""

from __future__ import annotations

import hashlib
import uuid
from pathlib import Path

import pytest

from continuityd.config import Settings
from continuityd.protocol import ProtocolError
from continuityd.session import SessionError
from continuityd.transfers import MAX_CONCURRENT, TransferService

FPR_A = "a" * 64
FPR_B = "b" * 64


class _Peer:
    def __init__(self, fingerprint: str = FPR_A, name: str = "desktop") -> None:
        self.fingerprint = fingerprint
        self.name = name


class _Session:
    def __init__(self, fingerprint: str = FPR_A, name: str = "desktop") -> None:
        self.peer = _Peer(fingerprint, name)


def _service(tmp_path: Path, **kwargs) -> TransferService:
    approver = kwargs.pop("approver", None)
    return TransferService(Settings(receive_dir=str(tmp_path / "inbox"), **kwargs),
                           approver=approver)


async def _offer(service: TransferService, session: _Session, *, transfer_id: str | None = None,
                 name: str = "note.txt", payload: bytes = b"hello",
                 digest: str | None = None) -> tuple[str, bytes, dict]:
    if transfer_id is None:
        transfer_id = str(uuid.uuid4())
    digest = digest or hashlib.sha256(payload).hexdigest()
    reply = await service.on_offer(session, {
        "transfer_id": transfer_id, "name": name, "size": len(payload), "sha256": digest,
    })
    return transfer_id, payload, reply


async def test_transfer_ids_must_be_canonical_uuids(tmp_path):
    service = _service(tmp_path, files_auto_accept=True)
    session = _Session()
    good = str(uuid.uuid4())
    for hostile in ("", "t", "../escape", good.upper(), "{" + good + "}", good.replace("-", ""),
                    "x" * 64):
        with pytest.raises(ProtocolError) as exc:
            await _offer(service, session, transfer_id=hostile, name="a.txt", payload=b"x")
        assert exc.value.code == "protocol.json"
    assert service.incoming == {}


async def test_duplicate_id_must_match_peer_name_size_and_digest(tmp_path):
    service = _service(tmp_path, files_auto_accept=True)
    session = _Session()
    transfer_id, payload, reply = await _offer(service, session, name="a.txt", payload=b"hello")
    assert reply["accept"] is True

    for changed in (
        {"name": "b.txt", "payload": payload},
        {"name": "a.txt", "payload": b"hello!"},
        {"name": "a.txt", "payload": b"hellp"},
    ):
        with pytest.raises(ProtocolError):
            await _offer(service, session, transfer_id=transfer_id, name=changed["name"],
                         payload=changed["payload"])
    # the original record is untouched
    assert service.incoming[transfer_id]["written"] == 0


async def test_cross_peer_id_reuse_is_rejected(tmp_path):
    service = _service(tmp_path, files_auto_accept=True)
    transfer_id, payload, _ = await _offer(service, _Session(FPR_A), name="a.txt", payload=b"hi")
    await service.on_chunk(_Session(FPR_A), {"transfer_id": transfer_id, "offset": 0}, payload)
    with pytest.raises(SessionError) as exc:
        await _offer(service, _Session(FPR_B), transfer_id=transfer_id, name="a.txt", payload=b"hi")
    assert exc.value.code == "identity.mismatch"


async def test_chunk_from_another_peer_is_rejected(tmp_path):
    service = _service(tmp_path, files_auto_accept=True)
    transfer_id, payload, _ = await _offer(service, _Session(FPR_A))
    with pytest.raises(SessionError) as exc:
        await service.on_chunk(_Session(FPR_B), {"transfer_id": transfer_id, "offset": 0}, payload)
    assert exc.value.code == "identity.mismatch"


async def test_declined_offer_leaves_nothing_behind_and_cannot_be_replayed(tmp_path):
    async def decline(_request: dict) -> bool:
        return False

    service = _service(tmp_path, approver=decline)
    session = _Session()
    transfer_id, payload, reply = await _offer(service, session, name="secret.pdf")
    assert reply["accept"] is False
    assert service.incoming == {}
    assert service.transfers == {}
    assert not list((tmp_path / "inbox").glob("*.part"))
    with pytest.raises(SessionError) as exc:
        await _offer(service, session, transfer_id=transfer_id, name="secret.pdf")
    assert exc.value.code == "capability.denied"


async def test_missing_approver_never_accepts(tmp_path):
    service = _service(tmp_path)
    _, _, reply = await _offer(service, _Session())
    assert reply["accept"] is False
    assert service.incoming == {}


async def test_approver_timeout_is_a_rejection(tmp_path):
    async def never(_request: dict) -> bool:
        import asyncio
        await asyncio.sleep(10)
        return True

    import continuityd.transfers as transfers_module

    original = transfers_module.OFFER_TIMEOUT
    transfers_module.OFFER_TIMEOUT = 0.05
    try:
        service = _service(tmp_path, approver=never)
        _, _, reply = await _offer(service, _Session())
    finally:
        transfers_module.OFFER_TIMEOUT = original
    assert reply["accept"] is False
    assert service.incoming == {}


async def test_unauthenticated_peer_is_rejected(tmp_path):
    service = _service(tmp_path, files_auto_accept=True)
    with pytest.raises(SessionError) as exc:
        await _offer(service, _Session(fingerprint=""))
    assert exc.value.code == "identity.untrusted"


async def test_concurrent_transfer_cap_is_enforced(tmp_path):
    service = _service(tmp_path, files_auto_accept=True)
    session = _Session()
    for _ in range(MAX_CONCURRENT):
        _, _, reply = await _offer(service, session, name="a.txt", payload=b"x")
        assert reply["accept"] is True
    with pytest.raises(ProtocolError) as exc:
        await _offer(service, session, name="a.txt", payload=b"x")
    assert exc.value.code == "limit.exceeded"


async def test_same_name_finishing_together_never_overwrites(tmp_path):
    service = _service(tmp_path, files_auto_accept=True)
    session = _Session()
    first, first_payload, _ = await _offer(service, session, name="note.txt", payload=b"first")
    second, second_payload, _ = await _offer(service, session, name="note.txt", payload=b"second")
    await service.on_chunk(session, {"transfer_id": first, "offset": 0}, first_payload)
    await service.on_chunk(session, {"transfer_id": second, "offset": 0}, second_payload)
    assert (await service.on_done(session, {
        "transfer_id": first, "sha256": hashlib.sha256(first_payload).hexdigest()}))["ok"] is True
    assert (await service.on_done(session, {
        "transfer_id": second, "sha256": hashlib.sha256(second_payload).hexdigest()}))["ok"] is True

    files = sorted(p.name for p in (tmp_path / "inbox").iterdir())
    assert files == ["note-1.txt", "note.txt"]
    assert {p.read_bytes() for p in (tmp_path / "inbox").iterdir()} == {b"first", b"second"}
    assert not list((tmp_path / "inbox").glob("*.part"))
    assert service.incoming == {}
    assert service._locks == {}


async def test_destination_appearing_after_offer_is_not_replaced(tmp_path):
    service = _service(tmp_path, files_auto_accept=True)
    session = _Session()
    transfer_id, payload, _ = await _offer(service, session, name="report.pdf", payload=b"new")
    await service.on_chunk(session, {"transfer_id": transfer_id, "offset": 0}, payload)
    # Someone creates the destination while the transfer is in flight.
    (tmp_path / "inbox" / "report.pdf").write_bytes(b"existing")
    result = await service.on_done(session, {
        "transfer_id": transfer_id, "sha256": hashlib.sha256(payload).hexdigest()})
    assert result["ok"] is True
    assert (tmp_path / "inbox" / "report.pdf").read_bytes() == b"existing"
    assert (tmp_path / "inbox" / "report-1.pdf").read_bytes() == b"new"


async def test_wrong_size_chunk_is_rejected(tmp_path):
    service = _service(tmp_path, files_auto_accept=True)
    session = _Session()
    transfer_id, _, _ = await _offer(service, session, payload=b"small")
    with pytest.raises(ProtocolError):
        await service.on_chunk(session, {"transfer_id": transfer_id, "offset": 0}, b"x" * 64)
    with pytest.raises(ProtocolError):
        await service.on_chunk(session, {"transfer_id": transfer_id, "offset": 1}, b"x")
