"""mDNS advertisement and browsing for the ``_continuity._tcp`` service.

Discovery is convenience, never trust. The TXT record advertises a friendly name and platform so the
UI can offer peers before connecting; the full certificate fingerprint is omitted unless
``discovery_broadcast_fingerprint`` is enabled. A peer is authenticated by the handshake pin
regardless of what mDNS claimed.
"""

from __future__ import annotations

import asyncio
import logging
import socket
from dataclasses import dataclass
from typing import Callable

from .config import SERVICE_TYPE

log = logging.getLogger("continuityd.discovery")


@dataclass
class DiscoveredPeer:
    name: str
    host: str
    port: int
    fingerprint: str = ""
    device_id: str = ""
    platform: str = ""

    def public(self) -> dict:
        return {"name": self.name, "host": self.host, "port": self.port,
                "fingerprint": self.fingerprint, "device_id": self.device_id,
                "platform": self.platform}


class Discovery:
    """Wraps python-zeroconf; absent dependency degrades to manual pairing by address."""

    def __init__(self, identity, settings, emit: Callable[[str, dict], None] | None = None,
                 on_results: Callable[[list[dict]], None] | None = None):
        self.identity = identity
        self.settings = settings
        self.emit = emit or (lambda event, data: None)
        self.on_results = on_results
        self.zeroconf = None
        self.service_info = None
        self.browser = None
        self.available = False

    def _local_ip(self) -> str:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.connect(("8.8.8.8", 80))
                return sock.getsockname()[0]
        except OSError:
            return "127.0.0.1"

    def txt_properties(self) -> dict[str, str]:
        """TXT record fields. The fingerprint is opt-in because mDNS is unauthenticated."""
        properties = {
            "id": self.identity.device_id,
            "name": self.identity.name,
            "platform": "linux",
            "proto": "1",
        }
        if self.settings.discovery_broadcast_fingerprint:
            properties["fp"] = self.identity.fingerprint
        return properties

    async def start(self, port: int) -> bool:
        if not self.settings.discovery_enabled:
            return False
        try:
            from zeroconf import ServiceBrowser, ServiceInfo, Zeroconf
            from zeroconf.asyncio import AsyncZeroconf
        except ImportError:
            log.warning("zeroconf not installed; discovery disabled")
            return False
        try:
            properties = self.txt_properties()
            info = ServiceInfo(
                SERVICE_TYPE,
                f"{self.identity.name}.{SERVICE_TYPE}",
                addresses=[socket.inet_aton(self._local_ip())],
                port=port,
                properties=properties,
            )
            self._azc = AsyncZeroconf()
            await self._azc.async_register_service(info)
            self.available = True
            self.port = port
            return True
        except Exception as exc:  # noqa: BLE001 - discovery must never break the daemon
            log.warning("mDNS advertisement failed: %s", exc)
            return False

    async def browse(self, timeout: float = 3.0) -> list[dict]:
        """One-shot browse; returns peers seen within ``timeout`` seconds."""
        if not self.available:
            return []
        from zeroconf import ServiceBrowser, Zeroconf

        found: dict[str, dict] = {}
        loop = asyncio.get_running_loop()

        class Listener:
            def add_service(self, zc, service_type, name):  # noqa: N802 - zeroconf API
                info = zc.get_service_info(service_type, name, timeout=2000)
                if not info:
                    return
                props = {k.decode(): v.decode() for k, v in (info.properties or {}).items()}
                addresses = [socket.inet_ntoa(a) for a in info.addresses]
                found[name] = DiscoveredPeer(
                    name=props.get("name", name.split(".")[0]),
                    host=addresses[0] if addresses else "",
                    port=info.port,
                    fingerprint=props.get("fp", ""),
                    device_id=props.get("id", ""),
                    platform=props.get("platform", ""),
                ).public()

            def update_service(self, *args):  # noqa: D401 - zeroconf API
                return None

            def remove_service(self, *args):
                return None

        zc = Zeroconf()
        try:
            ServiceBrowser(zc, SERVICE_TYPE, Listener())
            await asyncio.sleep(timeout)
        finally:
            zc.close()
        peers = list(found.values())
        self.emit("discovery.results", {"peers": peers})
        if self.on_results is not None:
            try:
                self.on_results(peers)
            except Exception:  # noqa: BLE001 - discovery must never break the daemon
                log.exception("discovery result callback failed")
        return peers

    async def stop(self) -> None:
        azc = getattr(self, "_azc", None)
        if azc:
            try:
                await azc.async_unregister_all_services()
                await azc.async_close()
            except Exception:  # noqa: BLE001
                pass
        self.available = False
