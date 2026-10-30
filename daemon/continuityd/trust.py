"""Trust store: fingerprint-pinned peers, explicitly revocable.

Stored as ``trusted-peers.json`` (0600). A peer is identified *only* by the SHA-256 fingerprint
of its certificate; ``device_id`` and ``name`` are labels that can be spoofed and are never used
for authorization.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path


class TrustError(Exception):
    pass


@dataclass
class TrustedPeer:
    fingerprint: str
    device_id: str
    name: str
    paired_at: str
    platform: str = "unknown"
    revoked: bool = False
    revoked_at: str | None = None
    notes: str = ""

    def label(self) -> str:
        return self.name or self.device_id[:8] or self.fingerprint[:8]


@dataclass
class TrustStore:
    path: Path
    peers: list[TrustedPeer] = field(default_factory=list)

    @classmethod
    def load(cls, path: Path) -> "TrustStore":
        store = cls(path=path)
        if path.exists():
            try:
                raw = json.loads(path.read_text() or "{}")
            except json.JSONDecodeError:
                raw = {}
            store.peers = [TrustedPeer(**p) for p in raw.get("peers", [])]
        return store

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"version": 1, "peers": [asdict(p) for p in self.peers]}
        fd, tmp = tempfile.mkstemp(dir=str(self.path.parent), prefix=".trust-")
        try:
            with os.fdopen(fd, "w") as fh:
                json.dump(payload, fh, indent=2)
            os.chmod(tmp, 0o600)
            os.replace(tmp, self.path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

    def get(self, fingerprint: str) -> TrustedPeer | None:
        return next((p for p in self.peers if p.fingerprint == fingerprint), None)

    def is_trusted(self, fingerprint: str) -> bool:
        peer = self.get(fingerprint)
        return bool(peer and not peer.revoked)

    def active(self) -> list[TrustedPeer]:
        return [p for p in self.peers if not p.revoked]

    def fingerprint_for_device(self, device_id: str) -> str | None:
        for peer in self.peers:
            if peer.device_id == device_id and not peer.revoked:
                return peer.fingerprint
        return None

    def add(self, fingerprint: str, device_id: str, name: str,
            platform: str = "unknown") -> TrustedPeer:
        if len(fingerprint) != 64 or any(c not in "0123456789abcdef" for c in fingerprint):
            raise TrustError("fingerprint must be 64 lower-case hex characters")
        existing = self.get(fingerprint)
        if existing:
            existing.revoked = False
            existing.revoked_at = None
            existing.name = name or existing.name
            existing.device_id = device_id or existing.device_id
            existing.platform = platform
            self.save()
            return existing
        peer = TrustedPeer(
            fingerprint=fingerprint,
            device_id=device_id,
            name=name,
            platform=platform,
            paired_at=_dt.datetime.now(_dt.timezone.utc).isoformat(),
        )
        self.peers.append(peer)
        self.save()
        return peer

    def revoke(self, fingerprint: str) -> bool:
        peer = self.get(fingerprint)
        if not peer or peer.revoked:
            return False
        peer.revoked = True
        peer.revoked_at = _dt.datetime.now(_dt.timezone.utc).isoformat()
        self.save()
        return True

    def remove(self, fingerprint: str) -> bool:
        before = len(self.peers)
        self.peers = [p for p in self.peers if p.fingerprint != fingerprint]
        if len(self.peers) != before:
            self.save()
            return True
        return False
