"""mDNS advertisement and browsing for the ``_continuity._tcp`` service.

Discovery is convenience, never trust. The TXT record advertises a friendly name and platform so the
UI can offer peers before connecting; the full certificate fingerprint is omitted unless
``discovery_broadcast_fingerprint`` is enabled. A peer is authenticated by the handshake pin
regardless of what mDNS claimed.

A periodic browser drives the reconnect re-arm without a user-triggered ``discover`` command. It
runs slowly: an active connection or reconnect series browses every
:data:`DISCOVERY_ACTIVE_INTERVAL` seconds, an idle daemon every :data:`DISCOVERY_IDLE_INTERVAL`
seconds. Browsers are serialized and owned by one task handle, so a restart cannot leave a second
browser running.
"""

from __future__ import annotations

import asyncio
import logging
import socket
from dataclasses import dataclass
from typing import Callable

from .config import SERVICE_TYPE

log = logging.getLogger("continuityd.discovery")

#: Re-browse cadence while a session is connected or a bounded reconnect series is running.
DISCOVERY_ACTIVE_INTERVAL = 30.0
#: Re-browse cadence when nothing is connected and no reconnect series is running.
DISCOVERY_IDLE_INTERVAL = 120.0
#: How long one browse collects advertisements. Kept below the active interval.
DISCOVERY_BROWSE_TIMEOUT = 3.0


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


def _text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return str(value)


def decode_properties(properties) -> dict[str, str]:
    """Decode zeroconf TXT keys/values, which may be bytes, str or None."""
    return {_text(key): _text(value) for key, value in (properties or {}).items()}


def peer_addresses(info) -> list[str]:
    """Return every usable address of a zeroconf ``ServiceInfo``, IPv4 and IPv6 alike.

    ``socket.inet_ntoa`` only understands 4-byte addresses and raises (or crashes the callback) on
    the 16-byte IPv6 form, which silently dropped IPv6-only peers. Prefer zeroconf's own parsers,
    then fall back to length-aware ``inet_ntop`` for fakes and older versions.
    """
    for method in ("parsed_scoped_addresses", "parsed_addresses"):
        parser = getattr(info, method, None)
        if callable(parser):
            try:
                addresses = [_text(value) for value in parser() if _text(value)]
            except Exception:  # noqa: BLE001 - malformed ServiceInfo must not break discovery
                continue
            if addresses:
                return addresses
    addresses = []
    for raw in getattr(info, "addresses", None) or []:
        try:
            if len(raw) == 4:
                addresses.append(socket.inet_ntop(socket.AF_INET, raw))
            elif len(raw) == 16:
                addresses.append(socket.inet_ntop(socket.AF_INET6, raw))
        except (OSError, TypeError, ValueError):
            continue
    return addresses


def peer_from_info(info, service_name: str) -> DiscoveredPeer | None:
    """Build a peer from a zeroconf ``ServiceInfo``; None when it has no usable port."""
    if info is None:
        return None
    try:
        port = int(getattr(info, "port", 0) or 0)
    except (TypeError, ValueError):
        return None
    if not 1 <= port <= 65535:
        return None
    properties = decode_properties(getattr(info, "properties", None))
    addresses = peer_addresses(info)
    return DiscoveredPeer(
        name=properties.get("name") or _text(service_name).split(".")[0],
        host=addresses[0] if addresses else "",
        port=port,
        fingerprint=properties.get("fp", ""),
        device_id=properties.get("id", ""),
        platform=properties.get("platform", ""),
    )


class PeerListener:
    """ServiceBrowser callback: record each resolved service once, without touching the event loop."""

    def __init__(self, found: dict[str, dict]):
        self.found = found

    def add_service(self, zc, service_type, name):  # noqa: N802 - zeroconf API
        try:
            info = zc.get_service_info(service_type, name, timeout=2000)
        except Exception:  # noqa: BLE001 - a bad advertisement must not break discovery
            log.debug("could not resolve %s", name, exc_info=True)
            return
        peer = peer_from_info(info, name)
        if peer is not None:
            self.found[name] = peer.public()

    def update_service(self, *args):  # noqa: D401 - zeroconf API
        return None

    def remove_service(self, *args):
        return None


class Discovery:
    """Wraps python-zeroconf; absent dependency degrades to manual pairing by address."""

    def __init__(self, identity, settings, emit: Callable[[str, dict], None] | None = None,
                 on_results: Callable[[list[dict]], None] | None = None,
                 interval_for: Callable[[], float] | None = None):
        self.identity = identity
        self.settings = settings
        self.emit = emit or (lambda event, data: None)
        self.on_results = on_results
        self.interval_for = interval_for or (lambda: DISCOVERY_IDLE_INTERVAL)
        self.zeroconf = None
        self.service_info = None
        self.browser = None
        self.available = False
        self._loop_task: asyncio.Task | None = None
        self._browse_lock = asyncio.Lock()

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
        # A restart (network change) must not leave the previous periodic browser running.
        await self._stop_periodic()
        if not self.settings.discovery_enabled:
            return False
        try:
            from zeroconf import ServiceInfo
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
            self.start_periodic()
            return True
        except Exception as exc:  # noqa: BLE001 - discovery must never break the daemon
            log.warning("mDNS advertisement failed: %s", exc)
            return False

    def _interval(self) -> float:
        try:
            return max(0.01, float(self.interval_for()))
        except Exception:  # noqa: BLE001 - a broken policy must not kill discovery
            log.debug("discovery interval provider failed", exc_info=True)
            return DISCOVERY_IDLE_INTERVAL

    def start_periodic(self) -> asyncio.Task | None:
        """Start the single periodic browse task, or return the one already running."""
        if not self.available:
            return None
        if self._loop_task is not None and not self._loop_task.done():
            return self._loop_task
        self._loop_task = asyncio.create_task(self._periodic_browse(),
                                              name="continuity-discovery")
        return self._loop_task

    async def _periodic_browse(self) -> None:
        while True:
            await asyncio.sleep(self._interval())
            if not self.available:
                continue
            try:
                await self.browse()
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 - a failed tick is retried on the next interval
                log.exception("periodic discovery failed")

    async def _stop_periodic(self) -> None:
        task, self._loop_task = self._loop_task, None
        if task is None:
            return
        if not task.done():
            task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        except Exception:  # noqa: BLE001 - retrieve late errors so shutdown stays quiet
            log.debug("periodic discovery ended with an error", exc_info=True)

    async def _browse_once(self, timeout: float) -> list[dict]:
        """Collect advertisements for ``timeout`` seconds; no event or callback side effects."""
        if not self.available:
            return []
        from zeroconf import ServiceBrowser, Zeroconf

        found: dict[str, dict] = {}
        listener = PeerListener(found)
        # One browser at a time: a shutdown/restart or an IPC ``discover`` running while the
        # periodic tick fires must not create two unclosed Zeroconf instances.
        async with self._browse_lock:
            zc = Zeroconf()
            try:
                ServiceBrowser(zc, SERVICE_TYPE, listener)
                await asyncio.sleep(timeout)
            finally:
                zc.close()
        return list(found.values())

    async def browse(self, timeout: float = DISCOVERY_BROWSE_TIMEOUT) -> list[dict]:
        """One-shot browse; returns peers seen within ``timeout`` seconds."""
        if not self.available:
            return []
        peers = await self._browse_once(timeout)
        self.emit("discovery.results", {"peers": peers})
        if self.on_results is not None:
            try:
                self.on_results(peers)
            except Exception:  # noqa: BLE001 - discovery must never break the daemon
                log.exception("discovery result callback failed")
        return peers

    async def stop(self) -> None:
        await self._stop_periodic()
        azc = getattr(self, "_azc", None)
        if azc:
            try:
                await azc.async_unregister_all_services()
                await azc.async_close()
            except Exception:  # noqa: BLE001
                pass
        self.available = False
