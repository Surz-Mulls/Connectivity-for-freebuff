"""§ policy tests round 2: pre-approval reservation, digest requirements, DeX honesty, IPC."""

from __future__ import annotations

import hashlib
import uuid
from pathlib import Path

import pytest

from continuityd.config import Settings
from continuityd.protocol import ProtocolError
from continuityd.session import SessionError
from continuityd.transfers import MAX_GLOBAL, MAX_PER_PEER, TransferService

from tests.test_transfer_policy import _Session, _offer, _service


@pytest.mark.asyncio
async def test_duplicate_offer_while_awaiting_approval_gets_one_dialog(tmp_path):
    service = _service(tmp_path)
    service.approver = None  # no approval channel: the first offer is declined immediately
    session = _Session()
    transfer_id = str(uuid.uuid4())
    reply = await service.on_offer(session, {
        "transfer_id": transfer_id, "name": "a.txt", "size": 1, "sha256": "b" * 64,
    })
    assert reply["accept"] is False
    # no reservation is left behind after the decline: replaying later re-asks, nothing is stuck
    assert service._reservations == {}


@pytest.mark.asyncio
async def test_same_id_second_offer_gets_awaiting_approval_not_a_second_dialog(tmp_path):
    async def slow_approver(info):
        await asyncio.sleep(0.2)  # first offer is still waiting
        return False

    import asyncio
    service = _service(tmp_path, approver=slow_approver)
    session = _Session()
    transfer_id = str(uuid.uuid4())
    first = asyncio.create_task(service.on_offer(session, {
        "transfer_id": transfer_id, "name": "a.txt", "size": 1, "sha256": "c" * 64,
    }))
    await asyncio.sleep(0.02)
    second = await service.on_offer(session, {
        "transfer_id": transfer_id, "name": "a.txt", "size": 1, "sha256": "c" * 64,
    })
    assert second["accept"] is False
    assert second["reason"] == "awaiting approval"
    assert (await first)["accept"] is False  # declined by the approver
    await asyncio.gather(first, return_exceptions=True)
    assert service._reservations == {}  # teardown leaves nothing behind


@pytest.mark.asyncio
async def test_pending_offers_count_toward_the_cap(tmp_path):
    import asyncio

    started = asyncio.Event()

    async def blocking_approver(info):
        started.set()
        await asyncio.sleep(0.3)
        return False

    service = _service(tmp_path, approver=blocking_approver)
    session = _Session()
    pending = []
    for index in range(MAX_PER_PEER):
        pending.append(asyncio.create_task(service.on_offer(session, {
            "transfer_id": str(uuid.uuid4()), "name": f"f{index}.txt", "size": 1,
            "sha256": "d" * 64,
        })))
        await started.wait()
        started.clear()
    with pytest.raises(ProtocolError) as exc:
        await service.on_offer(session, {
            "transfer_id": str(uuid.uuid4()), "name": "more.txt", "size": 1, "sha256": "d" * 64,
        })
    assert exc.value.code == "limit.exceeded"
    for task in pending:
        task.cancel()
    await asyncio.gather(*pending, return_exceptions=True)


@pytest.mark.asyncio
async def test_file_done_requires_a_valid_matching_digest(tmp_path):
    service = _service(tmp_path, files_auto_accept=True)
    session = _Session()
    transfer_id, payload, _ = await _offer(service, session, name="doc.txt", payload=b"doc")
    await service.on_chunk(session, {"transfer_id": transfer_id, "offset": 0}, payload)

    # missing digest must be rejected outright
    with pytest.raises(ProtocolError) as missing:
        await service.on_done(session, {"transfer_id": transfer_id})
    assert missing.value.code == "protocol.json"

    # an uppercase digest must still be accepted (case-insensitive comparison)
    digest = hashlib.sha256(payload).hexdigest().upper()
    result = await service.on_done(session, {"transfer_id": transfer_id, "sha256": digest})
    assert result["ok"] is True

    # trailing junk / short digests rejected
    service2 = _service(tmp_path / "2", files_auto_accept=True)
    tid2, payload2, _ = await _offer(service2, session, name="doc2.txt", payload=b"doc2")
    await service2.on_chunk(session, {"transfer_id": tid2, "offset": 0}, payload2)
    with pytest.raises(ProtocolError):
        await service2.on_done(session, {"transfer_id": tid2, "sha256": "abc"})
    # a different valid digest fails structurally, not with an exception
    service3 = _service(tmp_path / "3", files_auto_accept=True)
    tid3, payload3, _ = await _offer(service3, session, name="doc3.txt", payload=b"doc3")
    await service3.on_chunk(session, {"transfer_id": tid3, "offset": 0}, payload3)
    mismatch = await service3.on_done(session, {"transfer_id": tid3, "sha256": "e" * 64})
    assert mismatch["ok"] is False


@pytest.mark.asyncio
async def test_shutdown_removes_everything_including_reservations(tmp_path):
    import asyncio

    async def blocking(info):
        await asyncio.sleep(0.3)
        return False

    service = _service(tmp_path, approver=blocking)
    session = _Session()
    offer_task = asyncio.create_task(service.on_offer(session, {
        "transfer_id": str(uuid.uuid4()), "name": "x.bin", "size": 4, "sha256": "1" * 64,
    }))
    await asyncio.sleep(0.02)
    service.shutdown()
    assert service._reservations == {}
    assert service.incoming == {}
    assert list((tmp_path / "inbox").glob("*.part")) == []
    await asyncio.gather(offer_task, return_exceptions=True)


@pytest.mark.asyncio
async def test_startup_cleanup_removes_orphaned_part_files(tmp_path):
    service = _service(tmp_path, files_auto_accept=True)
    inbox = tmp_path / "inbox"
    inbox.mkdir(exist_ok=True)
    (inbox / ".note.txt.22222222-2222-4222-8222-222222222222.part").write_bytes(b"junk")
    (inbox / ".keep.alive.part").write_bytes(b"kept")  # different suffix, still ours
    removed = service.startup_cleanup()
    assert removed == 2
    assert list(inbox.glob("*.part")) == []


@pytest.mark.asyncio
async def test_global_cap_bounded_across_peers(tmp_path):
    session_a, session_b = _Session(), _Session()
    session_b.peer.fingerprint = "b" * 64
    service = _service(tmp_path, files_auto_accept=True)
    made = 0
    for session in (session_a, session_b):
        for _ in range(MAX_PER_PEER):
            await _offer(service, session, name=f"a{made}.txt", payload=b"x")
            made += 1
    with pytest.raises(ProtocolError) as exc:
        await _offer(service, _Session(), name="g.txt", payload=b"x")
    assert exc.value.code == "limit.exceeded"
