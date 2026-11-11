"""Shared fixtures for the transfer-policy tests.

Imported as ``tests.transfer_support``. ``daemon/pyproject.toml`` puts the daemon
directory on pytest's pythonpath, so this works both as
``python -m pytest daemon/tests`` from the repository root and as
``python -m pytest`` from ``daemon/``. It does not depend on the test module
itself being a top-level import.
"""

from __future__ import annotations

import hashlib
import uuid
from pathlib import Path

from continuityd.config import Settings
from continuityd.transfers import TransferService

FPR_A = "a" * 64
FPR_B = "b" * 64


class _Peer:
    def __init__(self, fingerprint: str = FPR_A, name: str = "desktop") -> None:
        self.fingerprint = fingerprint
        self.name = name


class _Session:
    def __init__(self, fingerprint: str = FPR_A, name: str = "desktop") -> None:
        self.peer = _Peer(fingerprint, name)


def _service(tmp_path: Path, **kwargs) -> TransferService:
    approver = kwargs.pop("approver", None)
    return TransferService(Settings(receive_dir=str(tmp_path / "inbox"), **kwargs),
                           approver=approver)


async def _offer(service: TransferService, session: _Session, *, transfer_id: str | None = None,
                 name: str = "note.txt", payload: bytes = b"hello",
                 digest: str | None = None) -> tuple[str, bytes, dict]:
    if transfer_id is None:
        transfer_id = str(uuid.uuid4())
    digest = digest or hashlib.sha256(payload).hexdigest()
    reply = await service.on_offer(session, {
        "transfer_id": transfer_id, "name": name, "size": len(payload), "sha256": digest,
    })
    return transfer_id, payload, reply
