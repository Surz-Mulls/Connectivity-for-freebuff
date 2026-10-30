"""Integration tests for the real TLS + pinning + pairing + transfer path.

No phone is required: a second ``Session`` with its own identity acts as the peer over a real
loopback TLS 1.3 socket, which exercises framing, the handshake, signature verification, SAS
pairing, capability checks and checksum-verified file transfer.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from continuityd.config import Settings
from continuityd.identity import Identity
from continuityd.protocol import Msg, make
from continuityd.session import Session, SessionError, connect, server_context
from continuityd.transfers import TransferService
from continuityd.trust import TrustStore


class Bench:
    """A listening server session plus the client session that talks to it."""

    def __init__(self, tmp_path: Path, *, pair: bool = True, revoke_server: bool = False,
                 tamper_sas: bool = False):
        self.tmp_path = tmp_path
        self.server_id = Identity.load_or_create(tmp_path / "server", "desktop")
        self.client_id = Identity.load_or_create(tmp_path / "client", "phone")
        self.server_trust = TrustStore.load(tmp_path / "server-trust.json")
        self.client_trust = TrustStore.load(tmp_path / "client-trust.json")
        self.pair = pair
        self.tamper_sas = tamper_sas
        self.server_settings = Settings.load(tmp_path / "server-settings.json")
        self.server_settings.files_auto_accept = True
        self.client_settings = Settings.load(tmp_path / "client-settings.json")
        self.client_settings.receive_dir = str(tmp_path / "client-recv")
        self.server_settings.receive_dir = str(tmp_path / "server-recv")
        self.events: list[tuple[str, dict]] = []
        self.sessions: list[Session] = []
        self.server: asyncio.Server | None = None
        self.paired_sas: list[dict] = []

    async def __aenter__(self):
        self.server = await asyncio.start_server(
            self._handle_server, host="127.0.0.1", port=0, ssl=server_context(self.server_id))
        self.port = self.server.sockets[0].getsockname()[1]
        return self

    async def __aexit__(self, *exc):
        for session in self.sessions:
            await session.close()
        if self.server:
            self.server.close()
            await self.server.wait_closed()

    async def _handle_server(self, reader, writer):
        service = TransferService(self.server_settings,
                                  lambda event, data: self.events.append((event, data)))

        async def approver(peer) -> bool:
            self.paired_sas.append(peer.sas)
            return self.pair

        async def handler(session: Session, msg: dict):
            if msg["type"] == Msg.FILE_OFFER:
                return await service.on_offer(session, msg["body"])
            if msg["type"] == Msg.FILE_DONE:
                return await service.on_done(session, msg["body"])
            if msg["type"] == Msg.CLIPBOARD_SET:
                return {"digest": msg["body"]["digest"], "applied": True}
            return None

        async def blob(session: Session, header: dict, data: bytes):
            await service.on_chunk(session, header, data)

        session = Session(identity=self.server_id, trust=self.server_trust,
                          settings=self.server_settings, handler=handler,
                          blob_handler=blob, pair_approver=approver,
                          capabilities=["files.send", "files.receive", "clipboard.write"])
        self.sessions.append(session)
        await session.run(reader, writer)

    async def client(self, *, approver=None, expected=None) -> Session:
        reader, writer = await connect("127.0.0.1", self.port)
        service = TransferService(self.client_settings,
                                  lambda event, data: self.events.append((event, data)))

        async def handler(session: Session, msg: dict):
            if msg["type"] == Msg.FILE_OFFER:
                return await service.on_offer(session, msg["body"])
            if msg["type"] == Msg.FILE_DONE:
                return await service.on_done(session, msg["body"])
            return None

        async def blob(session: Session, header: dict, data: bytes):
            await service.on_chunk(session, header, data)

        session = Session(identity=self.client_id, trust=self.client_trust,
                          settings=self.client_settings, handler=handler, blob_handler=blob,
                          initiator=True, expected_fingerprint=expected,
                          pair_approver=approver or (lambda peer: asyncio.sleep(0, True)),
                          capabilities=["files.send", "files.receive", "clipboard.write"])
        self.sessions.append(session)
        session.service = service  # type: ignore[attr-defined]
        task = asyncio.create_task(session.run(reader, writer))
        session._task = task  # type: ignore[attr-defined]
        for _ in range(200):
            if session.peer is not None:
                break
            await asyncio.sleep(0.01)
        if session.peer is None:
            await task
        return session


async def test_pairing_trusts_both_sides_and_persists(tmp_path):
    async with Bench(tmp_path, pair=True) as bench:
        client = await bench.client()
        for _ in range(100):
            if client.trusted:
                break
            await asyncio.sleep(0.01)
        assert client.trusted
        assert bench.client_trust.is_trusted(bench.server_id.fingerprint)
        assert bench.server_trust.is_trusted(bench.client_id.fingerprint)
        assert bench.paired_sas and bench.paired_sas[0]["digits"].isdigit()
        # a second connection must be trusted without pairing
        again = await bench.client()
        assert again.trusted
        assert again.peer.fingerprint == bench.server_id.fingerprint


async def test_declined_pairing_does_not_establish_trust(tmp_path):
    async with Bench(tmp_path, pair=False) as bench:
        client = await bench.client(approver=lambda peer: asyncio.sleep(0, False))
        await asyncio.gather(*[s._task for s in [client] if hasattr(s, "_task")],
                             return_exceptions=True)
        assert not bench.client_trust.is_trusted(bench.server_id.fingerprint)
        assert not bench.server_trust.is_trusted(bench.client_id.fingerprint)


async def test_pinned_fingerprint_mismatch_is_refused(tmp_path):
    async with Bench(tmp_path, pair=True) as bench:
        client = await bench.client(expected="0" * 64)
        await asyncio.gather(client._task, return_exceptions=True)  # type: ignore[attr-defined]
        assert client.peer is None
        assert client.failure is not None and client.failure.code == "identity.mismatch"
        assert not bench.client_trust.is_trusted(bench.server_id.fingerprint)


async def test_revoked_identity_cannot_connect(tmp_path):
    async with Bench(tmp_path, pair=True) as bench:
        bench.server_trust.add(bench.client_id.fingerprint, "client", "phone", "android")
        bench.server_trust.revoke(bench.client_id.fingerprint)
        bench.client_trust.add(bench.server_id.fingerprint, "server", "desktop", "linux")
        client = await bench.client()
        await asyncio.gather(client._task, return_exceptions=True)  # type: ignore[attr-defined]
        assert not client.trusted


async def test_file_transfer_roundtrip_is_integrity_checked(tmp_path):
    async with Bench(tmp_path, pair=True) as bench:
        client = await bench.client()
        for _ in range(100):
            if client.trusted:
                break
            await asyncio.sleep(0.01)
        payload = (b"continuity-test-block" * 4096) + b"tail"
        source = tmp_path / "payload.bin"
        source.write_bytes(payload)
        transfer = await client.service.send_file(client, source)  # type: ignore[attr-defined]
        assert transfer.state == "done", transfer.error
        received = Path(bench.server_settings.receive_dir) / "payload.bin"
        assert received.exists()
        assert received.read_bytes() == payload


async def test_transfer_rejects_unsafe_names(tmp_path):
    async with Bench(tmp_path, pair=True) as bench:
        client = await bench.client()
        for _ in range(100):
            if client.trusted:
                break
            await asyncio.sleep(0.01)
        service = bench.server_sessions if False else None  # noqa: F841
        # craft an offer with a traversal name directly against the server service
        from continuityd.transfers import TransferService as TS

        server_service = TS(bench.server_settings)
        fake_session = type("S", (), {"peer": type("P", (), {"name": "x"})()})()
        with pytest.raises(Exception):
            await server_service.on_offer(fake_session, {
                "transfer_id": "t1", "name": "../escape.txt", "size": 3,
                "sha256": "a" * 64,
            })


async def test_untrusted_peer_is_limited_to_pairing(tmp_path):
    server_id = Identity.load_or_create(tmp_path / "s", "desktop")
    trust = TrustStore.load(tmp_path / "t.json")
    settings = Settings.load(tmp_path / "settings.json")
    session = Session(identity=server_id, trust=trust, settings=settings)
    session.peer = type("Peer", (), {"trusted": False, "caps": set(),
                                     "device": {"caps": []}})()

    with pytest.raises(SessionError) as exc:
        session.authorize(Msg.FILE_OFFER)
    assert exc.value.code == "auth.required"


async def test_capability_is_enforced(tmp_path):
    server_id = Identity.load_or_create(tmp_path / "s2", "desktop")
    trust = TrustStore.load(tmp_path / "t2.json")
    settings = Settings.load(tmp_path / "settings2.json")
    session = Session(identity=server_id, trust=trust, settings=settings)
    session.peer = type("Peer", (), {"trusted": True, "caps": {"files.receive"},
                                     "device": {"caps": ["files.receive"]}})()
    with pytest.raises(SessionError) as exc:
        session.authorize(Msg.FILE_OFFER)  # needs files.send
    assert exc.value.code == "capability.denied"
