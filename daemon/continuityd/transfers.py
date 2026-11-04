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
* an id is reserved atomically *before* the user is asked, so two simultaneous offers with the
  same id (or from two peers) cannot both reach an approval and create separate state; the
  reservation is removed again on decline/timeout, so nothing is left behind;
* limits: at most ``MAX_PER_PEER`` active-or-pending transfers per peer and ``MAX_GLOBAL`` in
  total, approval-waiting offers included; each chunk is bounded by ``CHUNK_SIZE``;
* hashing and finalisation of a transfer hold the same per-transfer lock as chunk writes, so
  ``file.done`` can never finalise while a chunk is still being written in parallel;
* resume is **in-session** only: if the daemon process restarts, transfers are gone and orphaned
  ``.part`` staging files are removed at startup. This is documented limitation, not durable
  resume.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
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

log = logging.getLogger("continuityd.transfers")

MAX_FILE_SIZE = 8 * 1024 * 1024 * 1024  # 8 GiB
MAX_PER_PEER = 4
MAX_GLOBAL = 8
#: legacy name kept for tests/config that reference the single cap
MAX_CONCURRENT = MAX_PER_PEER
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
        #: pre-approval reservations keyed (peer, transfer_id): bound the approval wait so a
        #: duplicate offer for the same id can never open a second consent dialog
        self._reservations: dict[tuple[str, str], dict] = {}
        self._declined: dict[tuple[str, str], float] = {}
        self._semaphore = asyncio.Semaphore(MAX_GLOBAL)
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

    def _active_total(self) -> int:
        pending = sum(1 for r in self._reservations.values() if r["peer"])
        return pending + sum(1 for t in self.transfers.values()
                             if t.state in ("pending", "active"))

    def reserved_for_peer(self, peer: str) -> int:
        return sum(1 for r in self._reservations.values() if r["peer"] == peer)

    def _is_declined(self, peer: str, transfer_id: str) -> bool:
        self._prune_declined()
        return (peer, transfer_id) in self._declined

    def _decline(self, peer: str, transfer_id: str, reason: str) -> dict:
        self._declined[(peer, transfer_id)] = time.time()
        self.emit("transfer.rejected", {"id": transfer_id, "peer": peer, "reason": reason})
        return {"transfer_id": transfer_id, "offset": 0, "accept": False, "reason": reason}

    def declined_count(self) -> int:
        """Bounded tombstone count: pruning keeps the map small over long sessions."""
        self._prune_declined()
        return len(self._declined)

    def _prune_declined(self) -> None:
        now = time.time()
        expired = [key for key, when in self._declined.items() if now - when > DECLINED_TTL]
        for key in expired:
            self._declined.pop(key, None)
        while len(self._declined) > 512:  # size bound: pop the oldest regardless of age
            self._declined.pop(next(iter(self._declined)), None)

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
        raw_size = body.get("size", -1)
        if isinstance(raw_size, bool) or not isinstance(raw_size, int):
            raise ProtocolError("protocol.json", "invalid file size")
        size = raw_size
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
        # Approval-waiting offers count toward both limits (§ policy): a peer cannot park an
        # unlimited number of dialogs, and the global rate is not silently doubled.
        if self.reserved_for_peer(peer) + self._active_count(peer) >= MAX_PER_PEER:
            raise ProtocolError("limit.exceeded", "too many concurrent transfers")
        if self._active_total() >= MAX_GLOBAL:
            raise ProtocolError("limit.exceeded", "too many concurrent transfers")

        reservation = self._reservations.get((peer, transfer_id))
        if reservation is not None:
            # Atomic pre-approval reservation: one consent dialog per (peer, id). A second copy
            # of the same offer must not race into a second approval or a second staging file.
            if not reservation.get("accepted"):
                return {"transfer_id": transfer_id, "offset": 0, "accept": False,
                        "reason": "awaiting approval"}
            if (reservation["name"], reservation["size"],
                    reservation["sha256"]) != (name, size, digest):
                raise ProtocolError("protocol.json", "offer does not match the pending request")
        else:
            self._reservations[(peer, transfer_id)] = {
                "peer": peer, "name": name, "size": size, "sha256": digest,
                "accepted": False, "ts": time.time(),
            }

        approved = bool(self.settings.files_auto_accept)
        if not approved:
            if self.approver is None:
                self._reservations.pop((peer, transfer_id), None)
                return self._decline(peer, transfer_id, "no approval channel")
            self._reservations[(peer, transfer_id)]["accepted"] = False
            try:
                approved = bool(await asyncio.wait_for(self.approver({
                    "transfer_id": transfer_id, "name": name, "size": size,
                    "peer": peer_name, "peer_fingerprint": peer,
                }), timeout=OFFER_TIMEOUT))
            except asyncio.TimeoutError:
                self._reservations.pop((peer, transfer_id), None)
                return self._decline(peer, transfer_id, "approval timed out")
            except asyncio.CancelledError:
                self._reservations.pop((peer, transfer_id), None)
                raise
            except Exception:  # an approver bug must never auto-accept
                self._reservations.pop((peer, transfer_id), None)
                return self._decline(peer, transfer_id, "approval failed")
        if not approved:
            self._reservations.pop((peer, transfer_id), None)
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
        self._reservations.pop((peer, transfer_id), None)
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
        raw_offset = header.get("offset", -1)
        if isinstance(raw_offset, bool) or not isinstance(raw_offset, int):
            raise ProtocolError("protocol.json", "invalid chunk offset")
        offset = raw_offset
        lock = self._locks.setdefault(transfer_id, asyncio.Lock())
        async with lock:
            if offset != record["written"]:
                raise ProtocolError("protocol.json", "out-of-order chunk")
            if record["written"] == record["size"]:
                raise ProtocolError("limit.exceeded", "all chunks were received already")
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
        # The completion digest is required: exactly 64 hex characters, matching the offer. A
        # missing digest must never be treated as "trusted trust the staged bytes" blindly here
        # either way — the measurement below is compared against it.
        claimed = _digest(body.get("sha256"))
        if claimed != record["sha256"]:
            return self._fail(transfer_id, record, transfer, "offered digest changed")

        # Same lock as chunk writes: nothing can finalise while a chunk is still being written,
        # and nothing can write after the size is complete and while hashing runs.
        lock = self._locks.get(transfer_id) or asyncio.Lock()
        destination: Path
        try:
            async with lock:
                temp = Path(record["temp"])
                root = self._receive_root()
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

    # ---------------------------------------------------------------- lifecycle
    def startup_cleanup(self) -> int:
        """Remove orphaned ``.part`` staging files after a daemon restart.

        Resume is in-session only (see module docstring); nothing can resume across a restart,
        so leftover staging files from a previous process are deleted. Returns how many were
        removed. Call this once during daemon start, before any transfer can begin.
        """
        root = self._receive_root()
        removed = 0
        for path in root.iterdir():
            if path.name.startswith(".") and path.name.endswith(".part"):
                try:
                    path.unlink()
                    removed += 1
                except OSError as exc:
                    log.warning("could not remove orphaned staging file %s: %s", path, exc)
        return removed

    def shutdown(self) -> None:
        """Tear down all transfer state deterministically on daemon shutdown."""
        for record in list(self.incoming.values()):
            Path(record["temp"]).unlink(missing_ok=True)
        self.incoming.clear()
        self._locks.clear()
        self._reservations.clear()
        self._declined.clear()
        for transfer in self.transfers.values():
            if transfer.state in ("pending", "active"):
                transfer.state = "failed"
                transfer.error = "daemon is shutting down"
        self.transfers.clear()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()
