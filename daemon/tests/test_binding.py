"""Handshake-binding regressions (protocol v2).

These exercise the real network path: a real ``DeviceManager``, real TLS, real frames. The earlier
suite talked to ``Session`` helpers directly, which is why ``await writer.get_extra_info(...)`` —
a ``TypeError`` on every inbound connection — never showed up.
"""

from __future__ import annotations

import asyncio
import base64
import contextlib

import pytest

from continuityd import PROTOCOL_VERSION
from continuityd.config import Settings
from continuityd.core import DeviceManager
from continuityd.frames import TYPE_JSON, read_frame, write_json
from continuityd.identity import Identity
from continuityd.protocol import Msg, make, parse
from continuityd.session import (
    Session,
    SessionError,
    advertised_capabilities,
    connect,
    handshake_transcript,
    start_server,
)
from continuityd.trust import TrustStore


@pytest.fixture()
def identity(tmp_path):
    return Identity.load_or_create(tmp_path / "id", "test-linux")


@pytest.fixture()
def settings(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
    settings = Settings()
    settings.port = 0
    settings.discovery_enabled = False
    settings.receive_dir = str(tmp_path / "received")
    return settings


async def _manager(settings, identity, tmp_path):
    manager = DeviceManager(settings, identity, TrustStore.load(tmp_path / "trust.json"))
    await manager.start()
    return manager


@pytest.mark.asyncio
async def test_daemon_accepts_real_inbound_connection(settings, identity, tmp_path):
    manager = await _manager(settings, identity, tmp_path)
    writer = None
    try:
        reader, writer = await connect("127.0.0.1", manager.port)
        frame = await asyncio.wait_for(read_frame(reader), 5)
        assert frame is not None, "daemon closed before sending the challenge"
        assert frame[0] == TYPE_JSON
        challenge = parse(frame[1])
        assert challenge["type"] == Msg.HELLO_CHALLENGE
        assert challenge["body"]["proto"] == PROTOCOL_VERSION == 2
        assert len(base64.b64decode(challenge["body"]["cert"])) > 100
    finally:
        if writer is not None:
            writer.close()
            with contextlib.suppress(Exception):
                await writer.wait_closed()
        await manager.stop()


@pytest.mark.asyncio
async def test_v1_envelope_is_rejected_without_downgrade(settings, identity, tmp_path):
    manager = await _manager(settings, identity, tmp_path)
    client = Identity.load_or_create(tmp_path / "client", "old-android")
    writer = None
    try:
        reader, client_writer = await connect("127.0.0.1", manager.port)
        writer = client_writer
        parse((await asyncio.wait_for(read_frame(reader), 5))[1])
        nonce = client.nonce()
        hello = make(Msg.HELLO, {
            "proto": 1, "nonce": base64.b64encode(nonce).decode(),
            "device": client.info("android", ["status.battery"]),
            "cert": base64.b64encode(client.cert_der).decode(),
            "sig": base64.b64encode(client.sign(b"nope")).decode(),
            "tls": identity.fingerprint,
        })
        hello["v"] = 1
        await write_json(writer, hello)
        reply = parse((await asyncio.wait_for(read_frame(reader), 5))[1])
        assert reply["type"] == Msg.ERROR
        assert reply["body"]["code"] == "protocol.version"
    finally:
        if writer is not None:
            writer.close()
        await manager.stop()


@pytest.mark.asyncio
async def test_hello_claiming_a_different_tls_certificate_is_rejected(settings, identity, tmp_path):
    manager = await _manager(settings, identity, tmp_path)
    client = Identity.load_or_create(tmp_path / "client", "relay")
    writer = None
    try:
        reader, client_writer = await connect("127.0.0.1", manager.port)
        writer = client_writer
        challenge = parse((await asyncio.wait_for(read_frame(reader), 5))[1])
        server_nonce = base64.b64decode(challenge["body"]["nonce"])
        nonce = client.nonce()
        await write_json(writer, make(Msg.HELLO, {
            "proto": PROTOCOL_VERSION,
            "nonce": base64.b64encode(nonce).decode(),
            "device": client.info("android", ["status.battery"]),
            "cert": base64.b64encode(client.cert_der).decode(),
            "sig": base64.b64encode(client.sign(handshake_transcript(
                "client", client.fingerprint, identity.fingerprint, nonce, server_nonce,
                "00" * 32))).decode(),
            "tls": "00" * 32,
        }))
        reply = parse((await asyncio.wait_for(read_frame(reader), 5))[1])
        assert reply["type"] == Msg.ERROR
        assert reply["body"]["code"] == "identity.mismatch"
        assert "TLS" in reply["body"]["message"]
    finally:
        if writer is not None:
            writer.close()
        await manager.stop()


@pytest.mark.asyncio
async def test_client_aborts_when_a_relay_terminates_tls(settings, identity, tmp_path):
    """A TLS-terminating relay forwards the real certificate in-band but shows its own on TLS."""
    daemon = await _manager(settings, identity, tmp_path)
    relay_identity = Identity.load_or_create(tmp_path / "relay", "relay")
    relay_server = None
    try:
        async def relay(reader, writer):
            upstream_reader, upstream_writer = await connect("127.0.0.1", daemon.port)

            async def pump(source, sink):
                try:
                    while True:
                        data = await source.read(65536)
                        if not data:
                            break
                        sink.write(data)
                        await sink.drain()
                except Exception:  # noqa: BLE001 - the relay only needs to stop cleanly
                    pass
                finally:
                    with contextlib.suppress(Exception):
                        sink.close()

            await asyncio.gather(pump(reader, upstream_writer),
                                pump(upstream_reader, writer))

        relay_server = await start_server(relay, relay_identity, host="127.0.0.1", port=0)
        port = relay_server.sockets[0].getsockname()[1]
        client = Identity.load_or_create(tmp_path / "client", "client")
        reader, writer = await connect("127.0.0.1", port)
        session = Session(identity=client, trust=TrustStore.load(tmp_path / "client.json"),
                          settings=settings, initiator=True)
        await session.run(reader, writer)
        assert session.failure is not None
        assert session.failure.code == "identity.mismatch"
        assert "TLS" in session.failure.message
        assert session.peer is None
    finally:
        if relay_server is not None:
            relay_server.close()
            await relay_server.wait_closed()
        await daemon.stop()


def test_transcript_binds_role_identities_nonces_and_tls_channel():
    client_nonce = b"\x01" * 32
    server_nonce = b"\x02" * 32
    base = handshake_transcript("client", "aa" * 32, "bb" * 32,
                                client_nonce, server_nonce, "bb" * 32)
    variants = {
        handshake_transcript("server", "aa" * 32, "bb" * 32, client_nonce, server_nonce, "bb" * 32),
        handshake_transcript("client", "cc" * 32, "bb" * 32, client_nonce, server_nonce, "bb" * 32),
        handshake_transcript("client", "aa" * 32, "dd" * 32, client_nonce, server_nonce, "bb" * 32),
        handshake_transcript("client", "aa" * 32, "bb" * 32, server_nonce, client_nonce, "bb" * 32),
        handshake_transcript("client", "aa" * 32, "bb" * 32, client_nonce, server_nonce, "ee" * 32),
    }
    assert len(variants) == 5
    assert base not in variants
    assert handshake_transcript("client", "aa", "bb", b"x", b"y", "z") != \
        handshake_transcript("client", "aaa", "b", b"x", b"y", "z")


def test_unimplemented_features_are_not_advertised(settings):
    caps = advertised_capabilities(settings)
    for fake in ("camera.capture", "media.control", "sync.folders"):
        assert fake not in caps
    assert "files.send" in caps and "status.battery" in caps


def test_session_error_codes_are_stable():
    error = SessionError("identity.mismatch", "x")
    assert error.code == "identity.mismatch"
