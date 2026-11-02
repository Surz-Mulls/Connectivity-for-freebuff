"""File transfer: chunked, resumable, integrity-checked, peer-bound and path-safe.

Invariants:
* transfer ids are canonical RFC-4122 UUIDs on both platforms; anything else is rejected before it
  is used in a path or a map key;
* every transfer is bound to the authenticated peer fingerprint. A different trusted device cannot
  resume, continue or finalise somebody else's transfer by reusing its id;
* names are validated by ``protocol.sanitize_filename`` (no separators, no traversal, no hidden
  files, no reserved device names) and never joined with a peer-supplied path;
* every destination is resolved and re-checked to be inside the receive directory;
* data goes to ``<name>.<id>.part`` and only becomes visible after size + SHA-256 verification;
* existing files are never overwritten: finalisation uses ``os.link`` (atomic, fails on an existing
  destination) and retries with a deterministic ``name-1.ext``, so two same-name transfers that
  finish together cannot clobber each other or a file created in the meantime;
* a declined, timed-out or unapproved offer leaves **no** record, staging file or lock behind;
* at most ``MAX_CONCURRENT`` transfers run, each with a bounded chunk size.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import string
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
#: how long a declined offer id stays poisoned, so a replay cannot turn a "no" into a "yes"
DECLINED_TTL = 600.0


@dataclass
class Transfer:
    id: str
    direction: str            # "send" | "receive"
    name: str
    size: int
    sha256: str
    peer: str = ""
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


def canonical_transfer_id(value: object) -> str:
    """Return the canonical (lowercase, hyphenated) UUID or raise ``protocol.json``.

    The Android client uses ``UUID.fromString`` and sends the canonical form; accepting braces,
    uppercase hex or a bare 32-character run here would let the two ends disagree about the map key.
    """
    text = str(value or "")
    try:
        parsed = uuid.UUID(text)
    except (ValueError, AttributeError, TypeError) as exc:
        raise ProtocolError("protocol.json", "invalid transfer id") from exc
    if str(parsed) != text:
        raise ProtocolError("protocol.json", "transfer id must be a canonical UUID")
    return text


def _peer_key(session: Session) -> str:
    fingerprint = getattr(getattr(session, "peer", None), "fingerprint", "") or ""
    if not fingerprint:
        raise SessionError("identity.untrusted", "transfer requires an authenticated peer")
    return fingerprint


def _digest(value: object) -> str:
    digest = str(value or "").lower()
    if len(digest) != 64 or any(ch not in string.hexdigits for ch in digest):
        raise ProtocolError("protocol.json", "invalid sha256")
    return digest


class TransferService:
    def __init__(self, settings: Settings,
                 emit: Callable[[str, dict], None] | None = None,
                 approver: Callable[[dict], "asyncio.Future[bool]"] | None = None):
        self.settings = settings
        self.emit = emit or (lambda event, data: None)
        #: async callback asking the user to accept an incoming file; None means "cannot ask"
        self.approver = approver
        self.transfers: dict[str, Transfer] = {}
        self.incoming: dict[str, dict] = {}
        self._declined: dict[tuple[str, str], float] = {}
        self._semaphore = asyncio.Semaphore(MAX_CONCURRENT)
        self._locks: dict[str, asyncio.Lock] = {}
        self._finalise_lock = asyncio.Lock()

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

    def _assert_inside(self, path: Path, root: Path) -> None:
        try:
            path.resolve().relative_to(root.resolve())
        except ValueError as exc:
            raise ProtocolError("path.unsafe", "path escapes the receive directory") from exc

    def _receive_root(self) -> Path:
        root = Path(self.settings.receive_dir).expanduser().resolve()
        root.mkdir(parents=True, exist_ok=True)
        return root

    def _active_count(self, peer: str) -> int:
        return sum(1 for t in self.transfers.values()
                   if t.state in ("pending", "active") and t.peer == peer)

    def _is_declined(self, peer: str, transfer_id: str) -> bool:
        now = time.time()
        for key, when in list(self._declined.items()):
            if now - when > DECLINED_TTL:
                self._declined.pop(key, None)
        return (peer, transfer_id) in self._declined

    def _decline(self, peer: str, transfer_id: str, reason: str) -> dict:
        self._declined[(peer, transfer_id)] = time.time()
        self.emit("transfer.rejected", {"id": transfer_id, "peer": peer, "reason": reason})
        return {"transfer_id": transfer_id, "offset": 0, "accept": False, "reason": reason}

    def _release(self, transfer_id: str) -> None:
        self._locks.pop(transfer_id, None)
        self.incoming.pop(transfer_id, None)

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
                            sha256=digest, peer=getattr(getattr(session, "peer", None),
                                                        "name", "") or "",
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
        peer = _peer_key(session)
        name = sanitize_filename(body.get("name"))
        try:
            size = int(body.get("size", -1))
        except (TypeError, ValueError) as exc:
            raise ProtocolError("protocol.json", "invalid file size") from exc
        if size < 0 or size > MAX_FILE_SIZE:
            raise ProtocolError("limit.exceeded", "invalid file size")
        digest = _digest(body.get("sha256"))
        transfer_id = canonical_transfer_id(body.get("transfer_id"))
        peer_name = getattr(getattr(session, "peer", None), "name", "") or ""

        existing = self.incoming.get(transfer_id)
        if existing is not None:
            if existing["peer"] != peer:
                raise SessionError("identity.mismatch", "transfer belongs to another device")
            if not existing["accepted"]:
                return {"transfer_id": transfer_id, "offset": 0, "accept": False,
                        "reason": "awaiting approval"}
            if (existing["name"], existing["size"], existing["sha256"]) != (name, size, digest):
                raise ProtocolError("protocol.json",
                                    "offer does not match the existing transfer")
            if not Path(existing["temp"]).exists():
                existing["written"] = 0
            return {"transfer_id": transfer_id, "offset": existing["written"], "accept": True}

        if self._is_declined(peer, transfer_id):
            raise SessionError("capability.denied", "transfer was already declined")
        if self._active_count(peer) >= MAX_CONCURRENT:
            raise ProtocolError("limit.exceeded", "too many concurrent transfers")

        approved = bool(self.settings.files_auto_accept)
        if not approved:
            if self.approver is None:
                return self._decline(peer, transfer_id, "no approval channel")
            try:
                approved = bool(await asyncio.wait_for(self.approver({
                    "transfer_id": transfer_id, "name": name, "size": size,
                    "peer": peer_name, "peer_fingerprint": peer,
                }), timeout=OFFER_TIMEOUT))
            except asyncio.TimeoutError:
                return self._decline(peer, transfer_id, "approval timed out")
            except asyncio.CancelledError:
                raise
            except Exception:  # an approver bug must never auto-accept
                return self._decline(peer, transfer_id, "approval failed")
        if not approved:
            return self._decline(peer, transfer_id, "rejected")

        root = self._receive_root()
        destination = self._unique_destination(root, name)
        temp = destination.with_name(f".{destination.name}.{transfer_id}.part")
        self._assert_inside(temp, root)
        try:
            with open(temp, "xb"):
                pass
            os.chmod(temp, 0o600)
        except OSError as exc:
            raise ProtocolError("internal", f"cannot create the staging file: {exc}") from exc
        self.incoming[transfer_id] = {
            "id": transfer_id, "name": name, "size": size, "sha256": digest,
            "peer": peer, "written": 0, "temp": str(temp), "dest": str(destination),
            "accepted": True,
        }
        self._locks[transfer_id] = asyncio.Lock()
        transfer = Transfer(id=transfer_id, direction="receive", name=name, size=size,
                            sha256=digest, peer=peer, path=str(destination), state="active")
        self.transfers[transfer_id] = transfer
        self.emit("transfer.started", transfer.public())
        return {"transfer_id": transfer_id, "offset": 0, "accept": True}

    async def on_chunk(self, session: Session, header: dict, data: bytes) -> None:
        peer = _peer_key(session)
        transfer_id = canonical_transfer_id(header.get("transfer_id"))
        record = self.incoming.get(transfer_id)
        if not record:
            raise ProtocolError("protocol.unsafe", "chunk for an unknown transfer")
        if record["peer"] != peer:
            raise SessionError("identity.mismatch", "transfer belongs to another device")
        if not record["accepted"]:
            raise SessionError("capability.denied", "transfer was not accepted")
        if not data or len(data) > CHUNK_SIZE:
            raise ProtocolError("limit.exceeded", "invalid chunk size")
        try:
            offset = int(header.get("offset", -1))
        except (TypeError, ValueError) as exc:
            raise ProtocolError("protocol.json", "invalid chunk offset") from exc
        lock = self._locks.setdefault(transfer_id, asyncio.Lock())
        async with lock:
            if offset != record["written"]:
                raise ProtocolError("protocol.json", "out-of-order chunk")
            if record["written"] + len(data) > record["size"]:
                raise ProtocolError("limit.exceeded", "transfer exceeds the offered size")
            temp = Path(record["temp"])
            self._assert_inside(temp, self._receive_root())
            with open(temp, "ab") as handle:
                await asyncio.to_thread(handle.write, data)
            record["written"] += len(data)
            if transfer_id in self.transfers:
                self.transfers[transfer_id].transferred = record["written"]
                self.emit("transfer.progress", self.transfers[transfer_id].public())

    async def on_done(self, session: Session, body: dict) -> dict:
        peer = _peer_key(session)
        transfer_id = canonical_transfer_id(body.get("transfer_id"))
        record = self.incoming.get(transfer_id)
        transfer = self.transfers.get(transfer_id)
        if not record:
            raise ProtocolError("protocol.unsafe", "unknown transfer")
        if record["peer"] != peer:
            raise SessionError("identity.mismatch", "transfer belongs to another device")
        claimed = str(body.get("sha256", "")).lower()
        if claimed and claimed != record["sha256"]:
            return self._fail(transfer_id, record, transfer, "offered digest changed")

        temp = Path(record["temp"])
        root = self._receive_root()
        try:
            self._assert_inside(temp, root)
            actual_size = temp.stat().st_size if temp.exists() else 0
            actual_digest = (await asyncio.to_thread(_sha256_file, temp)) if temp.exists() else ""
            if actual_size != record["size"] or actual_digest != record["sha256"]:
                return self._fail(transfer_id, record, transfer, "size or checksum mismatch")
            destination = await self._finalise(record, root)
        except ProtocolError:
            raise
        except OSError as exc:
            return self._fail(transfer_id, record, transfer, str(exc))
        finally:
            self._release(transfer_id)
        if transfer:
            transfer.state = "done"
            transfer.path = str(destination)
            transfer.transferred = record["size"]
            transfer.finished = time.time()
            self.emit("transfer.done", transfer.public())
        return {"transfer_id": transfer_id, "ok": True, "sha256": record["sha256"],
                "path": str(destination)}

    async def _finalise(self, record: dict, root: Path) -> Path:
        """Atomically publish the staging file without ever replacing an existing file."""
        temp = Path(record["temp"])
        async with self._finalise_lock:
            destination = Path(record["dest"])
            for _ in range(1000):
                self._assert_inside(destination, root)
                try:
                    os.link(temp, destination)      # atomic no-clobber; same directory/fs
                except FileExistsError:
                    destination = self._unique_destination(root, record["name"])
                    continue
                os.unlink(temp)
                os.chmod(destination, 0o600)
                return destination
            raise ProtocolError("path.unsafe", "could not find a free destination name")

    def _fail(self, transfer_id: str, record: dict, transfer: Transfer | None,
              error: str) -> dict:
        Path(record["temp"]).unlink(missing_ok=True)
        self._release(transfer_id)
        if transfer:
            transfer.state = "failed"
            transfer.error = error
            self.emit("transfer.failed", transfer.public())
        return {"transfer_id": transfer_id, "ok": False, "error": error}

    def cancel(self, transfer_id: str) -> bool:
        transfer = self.transfers.get(transfer_id)
        if not transfer or transfer.state in ("done", "failed", "cancelled"):
            return False
        transfer.state = "cancelled"
        record = self.incoming.get(transfer_id)
        if record:
            Path(record["temp"]).unlink(missing_ok=True)
            self._declined[(record["peer"], transfer_id)] = time.time()
        self._release(transfer_id)
        self.emit("transfer.cancelled", transfer.public())
        return True


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()
