"""File transfer: chunked, resumable, integrity-checked and path-safe.

Invariants:
* names are validated by ``protocol.sanitize_filename`` (no separators, no traversal, no hidden
  files, no reserved device names) and never joined with a peer-supplied path;
* every destination is resolved and re-checked to be inside the receive directory;
* data goes to ``<name>.<id>.part`` and only becomes visible after size + SHA-256 verification;
* existing files are never overwritten: a deterministic ``name-1.ext`` is chosen instead;
* at most ``MAX_CONCURRENT`` transfers run, each with a bounded chunk size.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .config import CHUNK_SIZE, Settings
from .protocol import Msg, ProtocolError, sanitize_filename
from .session import Session, SessionError

MAX_FILE_SIZE = 8 * 1024 * 1024 * 1024  # 8 GiB
MAX_CONCURRENT = 4
OFFER_TIMEOUT = 60.0
CHUNK_TIMEOUT = 600.0


@dataclass
class Transfer:
    id: str
    direction: str            # "send" | "receive"
    name: str
    size: int
    sha256: str
    peer: str
    path: str = ""
    offset: int = 0
    transferred: int = 0
    state: str = "pending"    # pending | active | done | failed | cancelled
    error: str = ""
    started: float = field(default_factory=time.time)
    finished: float | None = None

    def public(self) -> dict:
        return {
            "id": self.id, "direction": self.direction, "name": self.name,
            "size": self.size, "transferred": self.transferred, "state": self.state,
            "error": self.error, "peer": self.peer, "path": self.path,
            "progress": round(self.transferred / self.size, 4) if self.size else 1.0,
        }


class TransferService:
    def __init__(self, settings: Settings,
                 emit: Callable[[str, dict], None] | None = None,
                 approver: Callable[[dict], "asyncio.Future[bool]"] | None = None):
        self.settings = settings
        self.emit = emit or (lambda event, data: None)
        #: async callback asking the user to accept an incoming file; None means "reject"
        self.approver = approver
        self.transfers: dict[str, Transfer] = {}
        self.incoming: dict[str, dict] = {}
        self._semaphore = asyncio.Semaphore(MAX_CONCURRENT)
        self._locks: dict[str, asyncio.Lock] = {}

    # ---------------------------------------------------------------- helpers
    def _unique_destination(self, directory: Path, name: str) -> Path:
        candidate = directory / name
        if not candidate.exists():
            return candidate
        stem, suffix = os.path.splitext(name)
        for index in range(1, 1000):
            candidate = directory / f"{stem}-{index}{suffix}"
            if not candidate.exists():
                return candidate
        raise ProtocolError("path.unsafe", "could not find a free destination name")

    def _receive_file(self, transfer_id: str) -> Path:
        directory = Path(self.settings.receive_dir).expanduser().resolve()
        directory.mkdir(parents=True, exist_ok=True)
        record = self.incoming.get(transfer_id)
        if not record:
            raise ProtocolError("protocol.unsafe", "unknown transfer")
        return Path(record["temp"]).resolve()

    def _assert_inside(self, path: Path, root: Path) -> None:
        try:
            path.resolve().relative_to(root.resolve())
        except ValueError as exc:
            raise ProtocolError("path.unsafe", "destination escapes the receive directory") from exc

    # ---------------------------------------------------------------- send
    async def send_file(self, session: Session, path: Path, dest_name: str | None = None) -> Transfer:
        source = Path(path).expanduser()
        if not source.is_file():
            raise FileNotFoundError(str(source))
        size = source.stat().st_size
        if size > MAX_FILE_SIZE:
            raise ProtocolError("limit.exceeded", "file is larger than 8 GiB")
        name = sanitize_filename(dest_name or source.name)
        digest = await asyncio.to_thread(_sha256_file, source)
        transfer = Transfer(id=str(uuid.uuid4()), direction="send", name=name, size=size,
                            sha256=digest, peer=session.peer.name if session.peer else "",
                            path=str(source))
        self.transfers[transfer.id] = transfer
        self.emit("transfer.started", transfer.public())

        async with self._semaphore:
            accepted = await session.request(Msg.FILE_OFFER, {
                "transfer_id": transfer.id, "name": name, "size": size, "sha256": digest,
                "mime": "application/octet-stream",
            }, timeout=OFFER_TIMEOUT)
            body = accepted["body"]
            if accepted["type"] == Msg.FILE_REJECT or not body.get("accept", True):
                transfer.state = "failed"
                transfer.error = str(body.get("reason", "rejected"))
                self.emit("transfer.failed", transfer.public())
                return transfer
            offset = int(body.get("offset", 0))
            if offset < 0 or offset > size:
                raise ProtocolError("protocol.json", "invalid resume offset")
            transfer.state = "active"
            transfer.offset = transfer.transferred = offset
            self.emit("transfer.progress", transfer.public())

            with open(source, "rb") as handle:
                handle.seek(offset)
                while transfer.transferred < size and transfer.state == "active":
                    chunk = await asyncio.to_thread(handle.read, CHUNK_SIZE)
                    if not chunk:
                        break
                    await session.send_blob({"type": Msg.FILE_CHUNK, "transfer_id": transfer.id,
                                             "offset": transfer.transferred}, chunk)
                    transfer.transferred += len(chunk)
                    self.emit("transfer.progress", transfer.public())
            if transfer.state != "active":
                return transfer

            result = await session.request(Msg.FILE_DONE, {"transfer_id": transfer.id,
                                                           "sha256": digest},
                                           timeout=CHUNK_TIMEOUT)
            body = result["body"]
            transfer.finished = time.time()
            if body.get("ok"):
                transfer.state = "done"
                self.emit("transfer.done", transfer.public())
            else:
                transfer.state = "failed"
                transfer.error = str(body.get("error", "integrity check failed"))
                self.emit("transfer.failed", transfer.public())
            return transfer

    # ---------------------------------------------------------------- receive
    async def on_offer(self, session: Session, body: dict) -> dict:
        if not self.settings.files_enabled:
            raise SessionError("privacy.blocked", "file transfer is disabled")
        name = sanitize_filename(body.get("name"))
        size = int(body.get("size", -1))
        if size < 0 or size > MAX_FILE_SIZE:
            raise ProtocolError("limit.exceeded", "invalid file size")
        digest = str(body.get("sha256", ""))
        if len(digest) != 64:
            raise ProtocolError("protocol.json", "invalid sha256")
        transfer_id = str(body.get("transfer_id", ""))
        if not transfer_id or len(transfer_id) > 64:
            raise ProtocolError("protocol.json", "invalid transfer id")
        if transfer_id in self.incoming:
            record = self.incoming[transfer_id]
            return {"transfer_id": transfer_id, "offset": record["written"], "accept": True}

        authed = bool(self.settings.files_auto_accept)
        if not authed and self.approver is not None:
            authed = bool(await self.approver({"transfer_id": transfer_id, "name": name,
                                               "size": size,
                                               "peer": session.peer.name}))
        root = Path(self.settings.receive_dir).expanduser().resolve()
        destination = self._unique_destination(root, name)
        temp = destination.with_name(f".{destination.name}.{transfer_id}.part")
        self._assert_inside(temp, root)
        self.incoming[transfer_id] = {
            "name": name, "size": size, "sha256": digest, "written": 0,
            "temp": str(temp), "dest": str(destination), "accepted": authed,
        }
        transfer = Transfer(id=transfer_id, direction="receive", name=name, size=size,
                            sha256=digest, peer=session.peer.name if session.peer else "",
                            path=str(destination), state="active" if authed else "pending")
        self.transfers[transfer_id] = transfer
        self._locks[transfer_id] = asyncio.Lock()
        self.emit("transfer.started", transfer.public())
        return {"transfer_id": transfer_id, "offset": 0, "accept": authed}

    async def on_chunk(self, session: Session, header: dict, data: bytes) -> None:
        transfer_id = str(header.get("transfer_id", ""))
        record = self.incoming.get(transfer_id)
        if not record:
            raise ProtocolError("protocol.unsafe", "chunk for an unknown transfer")
        if not record["accepted"]:
            raise SessionError("capability.denied", "transfer was not accepted")
        if len(data) > CHUNK_SIZE:
            raise ProtocolError("limit.exceeded", "chunk larger than the negotiated maximum")
        offset = int(header.get("offset", -1))
        lock = self._locks.setdefault(transfer_id, asyncio.Lock())
        async with lock:
            if offset != record["written"]:
                raise ProtocolError("protocol.json", "out-of-order chunk")
            if record["written"] + len(data) > record["size"]:
                raise ProtocolError("limit.exceeded", "transfer exceeds the offered size")
            temp = Path(record["temp"])
            temp.parent.mkdir(parents=True, exist_ok=True)
            with open(temp, "ab") as handle:
                await asyncio.to_thread(handle.write, data)
            record["written"] += len(data)
            if transfer_id in self.transfers:
                self.transfers[transfer_id].transferred = record["written"]
            self.emit("transfer.progress",
                      self.transfers[transfer_id].public() if transfer_id in self.transfers else {})

    async def on_done(self, session: Session, body: dict) -> dict:
        transfer_id = str(body.get("transfer_id", ""))
        record = self.incoming.pop(transfer_id, None)
        transfer = self.transfers.get(transfer_id)
        if not record:
            raise ProtocolError("protocol.unsafe", "unknown transfer")
        temp = Path(record["temp"])
        dest = Path(record["dest"])
        root = Path(self.settings.receive_dir).expanduser().resolve()
        self._assert_inside(dest, root)
        try:
            actual_size = temp.stat().st_size if temp.exists() else 0
            actual_digest = await asyncio.to_thread(_sha256_file, temp) if temp.exists() else ""
            if actual_size != record["size"] or actual_digest != record["sha256"]:
                temp.unlink(missing_ok=True)
                if transfer:
                    transfer.state = "failed"
                    transfer.error = "size or checksum mismatch"
                    self.emit("transfer.failed", transfer.public())
                return {"transfer_id": transfer_id, "ok": False,
                        "error": "size or checksum mismatch"}
            os.replace(temp, dest)
            os.chmod(dest, 0o600)
            if transfer:
                transfer.state = "done"
                transfer.path = str(dest)
                transfer.transferred = actual_size
                transfer.finished = time.time()
                self.emit("transfer.done", transfer.public())
            return {"transfer_id": transfer_id, "ok": True, "sha256": actual_digest,
                    "path": str(dest)}
        except OSError as exc:
            if transfer:
                transfer.state = "failed"
                transfer.error = str(exc)
            return {"transfer_id": transfer_id, "ok": False, "error": str(exc)}

    def cancel(self, transfer_id: str) -> bool:
        transfer = self.transfers.get(transfer_id)
        if not transfer or transfer.state in ("done", "failed", "cancelled"):
            return False
        transfer.state = "cancelled"
        record = self.incoming.pop(transfer_id, None)
        if record:
            Path(record["temp"]).unlink(missing_ok=True)
        self.emit("transfer.cancelled", transfer.public())
        return True


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()
