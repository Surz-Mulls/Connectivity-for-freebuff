"""Core unit tests: framing, identity, trust, SAS, envelope validation, path safety."""

from __future__ import annotations

import asyncio
import json
import os
import stat

import pytest

from continuityd import frames
from continuityd.identity import Identity, fingerprint_of_der
from continuityd.protocol import (
    Msg,
    ProtocolError,
    make,
    parse,
    sanitize_filename,
    validate_url,
)
from continuityd.sas import derive_sas, sas_matches, verify_signature
from continuityd.trust import TrustError, TrustStore


# ---------------------------------------------------------------- framing
def test_frame_roundtrip_json_and_blob():
    payload = json.dumps({"a": 1}).encode()
    assert frames.decode_header(frames.encode(frames.TYPE_JSON, payload)[:5]) == (
        frames.TYPE_JSON, len(payload))
    blob = os.urandom(1024)
    encoded = frames.encode(frames.TYPE_BLOB, blob)
    frame_type, length = frames.decode_header(encoded[:5])
    assert frame_type == frames.TYPE_BLOB and encoded[5:] == blob and length == 1024


def test_frame_rejects_oversized_before_allocation():
    with pytest.raises(frames.FrameError):
        frames.encode(frames.TYPE_JSON, b"x" * (frames.MAX_PAYLOAD + 1))
    header = (10**9).to_bytes(4, "big") + bytes((frames.TYPE_JSON,))
    with pytest.raises(frames.FrameError, match="exceeds"):
        frames.decode_header(header)


def test_frame_rejects_unknown_type():
    with pytest.raises(frames.FrameError):
        frames.decode_header(b"\x00\x00\x00\x01\x09")
    with pytest.raises(frames.FrameError):
        frames.encode(0x09, b"")


async def test_stream_truncation_is_fatal_and_eof_is_clean():
    reader = asyncio.StreamReader()
    reader.feed_eof()
    assert await frames.read_frame(reader) is None

    reader = asyncio.StreamReader()
    reader.feed_data(b"\x00\x00")
    reader.feed_eof()
    with pytest.raises(frames.FrameError, match="truncated header"):
        await frames.read_frame(reader)

    reader = asyncio.StreamReader()
    reader.feed_data(b"\x00\x00\x00\x10\x01short")
    reader.feed_eof()
    with pytest.raises(frames.FrameError, match="truncated payload"):
        await frames.read_frame(reader)


async def test_stream_roundtrip():
    class FakeWriter:
        def __init__(self, reader):
            self.reader = reader

        def write(self, data):
            self.reader.feed_data(data)

        async def drain(self):
            return None

    reader = asyncio.StreamReader()
    await frames.write_json(FakeWriter(reader), {"hello": "world"})
    frame_type, payload = await frames.read_frame(reader)
    assert frame_type == frames.TYPE_JSON
    assert json.loads(payload) == {"hello": "world"}


# ---------------------------------------------------------------- identity
def test_identity_is_stable_and_private(tmp_path):
    first = Identity.load_or_create(tmp_path / "id", "laptop")
    second = Identity.load_or_create(tmp_path / "id", "ignored")
    assert first.fingerprint == second.fingerprint
    assert first.device_id == second.device_id
    assert len(first.fingerprint) == 64
    key_path = tmp_path / "id" / "device-key.pem"
    assert stat.S_IMODE(key_path.stat().st_mode) == 0o600
    assert b"PRIVATE KEY" not in first.cert_pem


def test_identity_signatures_verify_and_tamper_fails(tmp_path):
    identity = Identity.load_or_create(tmp_path / "id", "laptop")
    data = b"nonce-a" + b"nonce-b"
    signature = identity.sign(data)
    assert len(signature) == 64
    assert verify_signature(identity.cert_der, data, signature)
    assert not verify_signature(identity.cert_der, data + b"x", signature)
    assert not verify_signature(identity.cert_der, data, b"\x00" * 64)
    other = Identity.load_or_create(tmp_path / "other", "phone")
    assert not verify_signature(other.cert_der, data, signature)


def test_fingerprint_matches_certificate():
    assert fingerprint_of_der(b"abc") == fingerprint_of_der(b"abc")
    assert fingerprint_of_der(b"abc") != fingerprint_of_der(b"abd")


# ---------------------------------------------------------------- trust
def test_trust_store_roundtrip_and_revoke(tmp_path):
    store = TrustStore.load(tmp_path / "trust.json")
    peer = store.add("a" * 64, "device-1", "Pixel", "android")
    assert store.is_trusted(peer.fingerprint)
    assert stat.S_IMODE((tmp_path / "trust.json").stat().st_mode) == 0o600

    reloaded = TrustStore.load(tmp_path / "trust.json")
    assert reloaded.is_trusted(peer.fingerprint)
    assert reloaded.active()[0].name == "Pixel"

    assert store.revoke(peer.fingerprint)
    assert not store.is_trusted(peer.fingerprint)
    assert not store.revoke(peer.fingerprint)
    assert TrustStore.load(tmp_path / "trust.json").get(peer.fingerprint).revoked


def test_trust_rejects_malformed_fingerprint(tmp_path):
    store = TrustStore.load(tmp_path / "trust.json")
    with pytest.raises(TrustError):
        store.add("NOT-A-FINGERPRINT", "d", "n")
    with pytest.raises(TrustError):
        store.add("A" * 64, "d", "n")


# ---------------------------------------------------------------- SAS
def test_sas_is_symmetric_and_depends_on_every_input():
    a, b = "1" * 64, "2" * 64
    na, nb = b"\x01" * 32, b"\x02" * 32
    client = derive_sas(a, b, na, nb)
    server = derive_sas(a, b, na, nb)
    assert client == server
    assert len(client["digits"]) == 6 and client["digits"].isdigit()
    assert len(client["emoji"]) == 4
    assert derive_sas(a, b, b"\x03" * 32, nb)["digits"] != client["digits"]
    assert derive_sas(b, a, na, nb)["digits"] != client["digits"]


def test_sas_confirmation_matching():
    sas = derive_sas("a" * 64, "b" * 64, b"n" * 32, b"m" * 32)
    assert sas_matches(sas, sas["digits"], sas["emoji"])
    assert sas_matches(sas, sas["digits"], sas["emoji_text"])
    wrong = "000000" if sas["digits"] != "000000" else "111111"
    assert not sas_matches(sas, wrong, sas["emoji"])
    assert not sas_matches(sas, sas["digits"], ["🍎"])
    assert not sas_matches(sas, "12345a", sas["emoji"])


# ---------------------------------------------------------------- protocol
def test_envelope_make_parse():
    msg = make(Msg.PING, {"ts": "now"})
    parsed = parse(json.dumps(msg).encode())
    assert parsed["type"] == Msg.PING and parsed["body"] == {"ts": "now"}


def test_envelope_validation_errors():
    with pytest.raises(ProtocolError) as exc:
        parse(b"not json")
    assert exc.value.code == "protocol.json"

    with pytest.raises(ProtocolError):
        parse(json.dumps({"v": 99, "id": make(Msg.PING)["id"], "type": Msg.PING}).encode())

    with pytest.raises(ProtocolError):
        parse(json.dumps({"v": 1, "id": "nope", "type": Msg.PING}).encode())

    with pytest.raises(ProtocolError) as exc:
        make("evil.message")
    assert exc.value.code == "protocol.unsupported"


def test_required_body_fields_enforced():
    msg = make(Msg.FILE_OFFER, {"transfer_id": "t"})
    with pytest.raises(ProtocolError, match="missing body"):
        parse(json.dumps(msg).encode())


def test_device_info_validation_rejects_unknown_capabilities():
    from continuityd.protocol import validate_device

    info = validate_device({"id": "d1", "name": "phone", "caps": ["files.send"]})
    assert info["caps"] == ["files.send"]
    with pytest.raises(ProtocolError):
        validate_device({"id": "d1", "caps": ["files.send", "root.shell"]})
    with pytest.raises(ProtocolError):
        validate_device({"name": "no-id"})


def test_url_validation_only_allows_http():
    assert validate_url("https://example.com/a?b=c") == "https://example.com/a?b=c"
    for bad in ("file:///etc/passwd", "javascript:alert(1)", "intent://x", "http://",
                "https://x/" + "a" * 5000):
        with pytest.raises(ProtocolError):
            validate_url(bad)


@pytest.mark.parametrize("bad", [
    "../etc/passwd", "/etc/passwd", "a/b", "a\\b", "..", ".", ".hidden", "nul.txt",
    "con", "", "x" * 300, "bad\x00name", "tab\tname",
])
def test_unsafe_names_rejected(bad):
    with pytest.raises(ProtocolError) as exc:
        sanitize_filename(bad)
    assert exc.value.code == "path.unsafe"


@pytest.mark.parametrize("good", ["report.pdf", "IMG_0001.JPG", "a b-c_d.tar.gz"])
def test_safe_names_accepted(good):
    assert sanitize_filename(good) == good
