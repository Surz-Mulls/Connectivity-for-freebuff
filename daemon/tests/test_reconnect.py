"""Automatic reconnect: bounded backoff, jitter, reset on success, no revoked-peer storms."""

from __future__ import annotations

import asyncio

import pytest

from continuityd.config import Settings
from continuityd.core import DeviceManager, ReconnectPolicy, ReconnectState
from continuityd.trust import TrustStore, TrustedPeer


# ---------------------------------------------------------------- pure policy
def test_backoff_is_exponential_and_bounded():
    policy = ReconnectPolicy(base=1.0, max_delay=60.0, max_attempts=10)
    delays = [policy.delay_for(n) for n in range(1, 8)]
    assert delays == [1, 2, 4, 8, 16, 32, 60]
    assert policy.delay_for(50) == 60.0  # never grows past the cap


def test_policy_bounds_the_series():
    policy = ReconnectPolicy(base=1.0, max_delay=60.0, max_attempts=10)
    assert not policy.exhausted(9)
    assert policy.exhausted(10)
    with pytest.raises(ValueError):
        policy.delay_for(0)


# ---------------------------------------------------------------- manager loop
def _manager(tmp_path) -> DeviceManager:
    settings = Settings(receive_dir=str(tmp_path / "inbox"), device_name="test")
    manager = DeviceManager.__new__(DeviceManager)  # no async startup needed
    manager.settings = settings
    manager.trust = TrustStore(path=tmp_path / "trust.json")
    # the peer is paired: it was trusted when the session dropped
    manager.trust.peers.append(TrustedPeer(fingerprint="f" * 64, device_id="d", name="phone",
                                           paired_at="2020-01-01"))
    manager.reconnect_policy = ReconnectPolicy(base=0.01, max_delay=0.05, max_attempts=3)
    manager.reconnects = {}
    manager.devices = {}
    manager.sessions = {}
    manager.transfers = None
    manager.emit = lambda *args, **kwargs: None
    return manager


@pytest.mark.asyncio
async def test_reconnect_loop_gives_up_after_bounded_attempts(tmp_path, monkeypatch):
    manager = _manager(tmp_path)
    attempts = []

    async def fake_connect(host, port, expected_fingerprint=None, timeout=15.0):
        attempts.append(1)
        raise ConnectionError("network unreachable")

    monkeypatch.setattr(manager, "connect", fake_connect)
    state = ReconnectState(fingerprint="f" * 64, host="127.0.0.1", port=1)
    state.task = asyncio.create_task(manager._reconnect_loop(state, "test"))
    await asyncio.wait_for(state.task, 2)
    assert state.state == "offline"
    # bounded: exactly max_attempts connection attempts, then an explicit offline state
    assert len(attempts) == manager.reconnect_policy.max_attempts


@pytest.mark.asyncio
async def test_reconnect_stops_when_peer_is_revoked(tmp_path, monkeypatch):
    manager = _manager(tmp_path)
    manager.trust.peers.clear()
    manager.trust.peers.append(TrustedPeer(fingerprint="f" * 64, device_id="d", name="phone",
                                           paired_at="2020-01-01", revoked=True))
    started = []

    async def fake_connect(host, port, expected_fingerprint=None, timeout=15.0):
        started.append(1)
        return {}

    monkeypatch.setattr(manager, "connect", fake_connect)
    state = ReconnectState(fingerprint="f" * 64, host="127.0.0.1", port=1)
    state.task = asyncio.create_task(manager._reconnect_loop(state, "test"))
    await asyncio.wait_for(state.task, 2)
    assert state.state == "offline"
    assert started == []  # a revoked peer is never re-connected


@pytest.mark.asyncio
async def test_reconnect_success_leaves_the_state_idle(tmp_path, monkeypatch):
    manager = _manager(tmp_path)
    state = ReconnectState(fingerprint="f" * 64, host="127.0.0.1", port=4242)
    manager.reconnects[state.fingerprint] = state  # the loop and connect() share one state

    async def fake_connect(host, port, expected_fingerprint=None, timeout=15.0):
        assert expected_fingerprint == "f" * 64  # pinned fingerprint requirement
        manager._record_reconnect_target("f" * 64, host, port)  # mirrors real connect()
        return {}

    monkeypatch.setattr(manager, "connect", fake_connect)
    state.task = asyncio.create_task(manager._reconnect_loop(state, "test"))
    await asyncio.wait_for(state.task, 2)
    assert state.state == "idle"      # reset on success by connect()
    assert state.attempt == 0


def test_public_state_never_leaks_internal_fields():
    state = ReconnectState(fingerprint="f" * 64, host="10.0.0.2", port=1716, name="phone")
    published = state.public()
    assert published["fingerprint"] == "f" * 64
    assert published["target"] == {"host": "10.0.0.2", "port": 1716}
    assert "task" not in published
