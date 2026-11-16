"""mDNS TXT privacy: no certificate fingerprint unless the user opts in."""

from __future__ import annotations

from types import SimpleNamespace

from continuityd.discovery import Discovery


class _Identity:
    device_id = "device-1234"
    fingerprint = "a" * 64
    name = "laptop"


def _discovery(*, broadcast: bool) -> Discovery:
    settings = SimpleNamespace(
        discovery_enabled=True,
        discovery_broadcast_fingerprint=broadcast,
    )
    return Discovery(_Identity(), settings)


def test_txt_record_hides_fingerprint_by_default():
    properties = _discovery(broadcast=False).txt_properties()
    assert "fp" not in properties
    assert properties["id"] == "device-1234"
    assert properties["name"] == "laptop"
    assert properties["platform"] == "linux"


def test_txt_record_includes_fingerprint_only_when_enabled():
    properties = _discovery(broadcast=True).txt_properties()
    assert properties["fp"] == "a" * 64
