"""Periodic mDNS discovery and its IPv4/IPv6 peer capture.

The periodic browser is what makes the reconnect re-arm automatic; these tests drive it with a fake
browse source, so no mDNS traffic or second host is needed.
"""

from __future__ import annotations

import asyncio
import socket

import pytest

from continuityd.config import Settings
from continuityd.core import DeviceManager, ReconnectPolicy, ReconnectState
from continuityd.discovery import (
    DISCOVERY_ACTIVE_INTERVAL,
    DISCOVERY_IDLE_INTERVAL,
    Discovery,
    PeerListener,
    peer_addresses,
)
from continuityd.trust import TrustStore, TrustedPeer

FINGERPRINT = "f" * 64


def _settings(tmp_path) -> Settings:
    return Settings(receive_dir=str(tmp_path / "inbox"), device_name="test")


def _manager(tmp_path) -> DeviceManager:
    settings = _settings(tmp_path)
    manager = DeviceManager.__new__(DeviceManager)  # no async startup needed
    manager.settings = settings
    manager.trust = TrustStore(path=tmp_path / "trust.json")
    manager.trust.peers.append(TrustedPeer(fingerprint=FINGERPRINT, device_id="d", name="phone",
                                           paired_at="2020-01-01"))
    manager.reconnect_policy = ReconnectPolicy(base=0.01, max_delay=0.05, max_attempts=3)
    manager.reconnects = {}
    manager.devices = {}
    manager.sessions = {}
    manager.transfers = None
    manager.emit = lambda *args, **kwargs: None
    manager.discovery = Discovery(None, settings, manager.emit,
                                  on_results=manager.on_discovered_peers)
    return manager


class _Info:
    """Minimal zeroconf ``ServiceInfo`` stand-in (no parsed_* helpers, like older versions)."""

    def __init__(self, raw: bytes, port: int = 4242):
        self.properties = {b"name": b"phone", b"id": b"device-1", b"platform": b"android"}
        self.addresses = [raw]
        self.port = port


class _Zeroconf:
    def __init__(self, info):
        self.info = info

    def get_service_info(self, service_type, name, timeout=2000):  # noqa: N802 - zeroconf API
        return self.info


@pytest.mark.asyncio
async def test_periodic_discovery_rearms_an_exhausted_trusted_peer_exactly_once(
        tmp_path, monkeypatch):
    manager = _manager(tmp_path)
    manager.reconnect_policy = ReconnectPolicy(base=0.01, max_delay=0.02, max_attempts=2)
    state = ReconnectState(fingerprint=FINGERPRINT, host="127.0.0.1", port=1)
    manager.reconnects[FINGERPRINT] = state
    attempts: list[int] = []

    async def dead_host(host, port, expected_fingerprint=None, timeout=15.0):
        attempts.append(1)
        raise ConnectionError("host unreachable")

    monkeypatch.setattr(manager, "connect", dead_host)
    manager.schedule_reconnect(FINGERPRINT, "session closed")
    await asyncio.wait_for(state.task, 2)
    assert state.state == "offline"
    assert len(attempts) == 2  # one bounded series, then gave up

    async def rediscovered(timeout=3.0):
        return [{"fingerprint": FINGERPRINT}]

    monkeypatch.setattr(manager.discovery, "_browse_once", rediscovered)
    manager.discovery.available = True
    manager.discovery.interval_for = lambda: 0.05
    manager.discovery.start_periodic()
    try:
        for _ in range(300):
            if len(attempts) >= 4:
                break
            await asyncio.sleep(0.01)
    finally:
        await manager.discovery.stop()
    # Exactly one new bounded series (2 attempts), not a second re-arm while it was running.
    assert len(attempts) == 4
    assert state.state == "offline"


@pytest.mark.asyncio
@pytest.mark.parametrize("trust", ["unknown", "revoked"])
async def test_periodic_discovery_never_rearms_an_untrusted_peer(tmp_path, monkeypatch, trust):
    manager = _manager(tmp_path)
    if trust == "unknown":
        manager.trust.peers.clear()
    else:
        manager.trust.peers[0].revoked = True
    state = ReconnectState(fingerprint=FINGERPRINT, host="127.0.0.1", port=1,
                           state="offline", attempt=3)
    manager.reconnects[FINGERPRINT] = state
    attempts: list[int] = []

    async def dead_host(host, port, expected_fingerprint=None, timeout=15.0):
        attempts.append(1)
        raise ConnectionError("host unreachable")

    async def rediscovered(timeout=3.0):
        return [{"fingerprint": FINGERPRINT}, {"fingerprint": "a" * 64}]

    monkeypatch.setattr(manager, "connect", dead_host)
    monkeypatch.setattr(manager.discovery, "_browse_once", rediscovered)
    manager.discovery.available = True
    manager.discovery.interval_for = lambda: 0.05
    manager.discovery.start_periodic()
    await asyncio.sleep(0.18)  # more than three ticks
    await manager.discovery.stop()
    assert attempts == []
    assert state.task is None
    assert state.state == "offline"


@pytest.mark.asyncio
async def test_start_periodic_keeps_exactly_one_browser_task(tmp_path):
    discovery = Discovery(None, _settings(tmp_path))
    discovery.available = True
    calls: list[int] = []

    async def browse(timeout=3.0):
        calls.append(1)
        return []

    discovery._browse_once = browse
    discovery.interval_for = lambda: 0.03
    first = discovery.start_periodic()
    second = discovery.start_periodic()
    assert first is second
    await asyncio.sleep(0.1)
    await discovery.stop()
    assert 2 <= len(calls) <= 3
    assert discovery._loop_task is None


@pytest.mark.asyncio
async def test_stop_cancels_the_periodic_browser_cleanly(tmp_path):
    discovery = Discovery(None, _settings(tmp_path))
    discovery.available = True
    calls: list[int] = []

    async def browse(timeout=3.0):
        calls.append(1)
        return []

    discovery._browse_once = browse
    discovery.interval_for = lambda: 0.03
    task = discovery.start_periodic()
    await asyncio.sleep(0.05)
    await discovery.stop()
    assert task.done()
    assert discovery._loop_task is None
    stopped_at = len(calls)
    await asyncio.sleep(0.1)
    assert len(calls) == stopped_at  # no tick survives shutdown
    await discovery.stop()  # idempotent


def test_ipv6_service_entry_keeps_the_full_address():
    name = "phone._continuity._tcp.local."
    found: dict[str, dict] = {}
    listener = PeerListener(found)
    listener.add_service(_Zeroconf(_Info(socket.inet_pton(socket.AF_INET6, "2001:db8::7"))),
                         "_continuity._tcp.local.", name)
    assert found[name]["host"] == "2001:db8::7"
    assert found[name]["port"] == 4242
    assert found[name]["name"] == "phone"


def test_address_lengths_drive_ipv4_and_ipv6_decoding():
    assert peer_addresses(_Info(socket.inet_pton(socket.AF_INET, "192.168.1.10"))) == [
        "192.168.1.10"
    ]
    assert peer_addresses(_Info(b"\x01\x02\x03")) == []  # unknown length is dropped, not crashed


@pytest.mark.asyncio
async def test_discovery_interval_is_active_only_while_busy(tmp_path):
    assert DISCOVERY_ACTIVE_INTERVAL >= 30
    assert DISCOVERY_IDLE_INTERVAL > DISCOVERY_ACTIVE_INTERVAL
    manager = _manager(tmp_path)
    assert manager.discovery_interval() == DISCOVERY_IDLE_INTERVAL
    manager.sessions["peer"] = object()
    assert manager.discovery_interval() == DISCOVERY_ACTIVE_INTERVAL
    manager.sessions.clear()
    task = asyncio.create_task(asyncio.sleep(1))
    manager.reconnects["g" * 64] = ReconnectState(fingerprint="g" * 64, task=task)
    assert manager.discovery_interval() == DISCOVERY_ACTIVE_INTERVAL
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    assert manager.discovery_interval() == DISCOVERY_IDLE_INTERVAL
