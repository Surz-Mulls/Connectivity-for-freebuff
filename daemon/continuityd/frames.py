"""Length-prefixed framing for the Continuity protocol (see protocol/PROTOCOL.md §2).

A frame is ``length (u32 BE) | type (u8) | payload``. The length is checked against
``MAX_PAYLOAD`` *before* any allocation, so a hostile peer cannot make us reserve 4 GiB.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

MAX_PAYLOAD = 1 << 20  # 1 MiB
HEADER_SIZE = 5
TYPE_JSON = 0x01
TYPE_BLOB = 0x02
VALID_TYPES = (TYPE_JSON, TYPE_BLOB)


class FrameError(Exception):
    """Fatal framing error: the stream can no longer be trusted."""


def encode(frame_type: int, payload: bytes) -> bytes:
    if frame_type not in VALID_TYPES:
        raise FrameError(f"unknown frame type {frame_type}")
    if len(payload) > MAX_PAYLOAD:
        raise FrameError(f"payload {len(payload)} exceeds {MAX_PAYLOAD}")
    return len(payload).to_bytes(4, "big") + bytes((frame_type,)) + payload


def encode_json(obj: Any) -> bytes:
    return encode(TYPE_JSON, json.dumps(obj, separators=(",", ":"), ensure_ascii=False).encode())


def decode_header(header: bytes) -> tuple[int, int]:
    if len(header) != HEADER_SIZE:
        raise FrameError("truncated header")
    length = int.from_bytes(header[:4], "big")
    frame_type = header[4]
    if frame_type not in VALID_TYPES:
        raise FrameError(f"unknown frame type {frame_type}")
    if length > MAX_PAYLOAD:
        raise FrameError(f"frame length {length} exceeds {MAX_PAYLOAD}")
    return frame_type, length


async def read_frame(reader: asyncio.StreamReader) -> tuple[int, bytes] | None:
    """Read one frame. ``None`` means the peer closed cleanly between frames."""
    try:
        header = await reader.readexactly(HEADER_SIZE)
    except asyncio.IncompleteReadError as exc:
        if not exc.partial:
            return None
        raise FrameError("truncated header") from exc
    frame_type, length = decode_header(header)
    if length == 0:
        return frame_type, b""
    try:
        payload = await reader.readexactly(length)
    except asyncio.IncompleteReadError as exc:
        raise FrameError("truncated payload") from exc
    return frame_type, payload


async def write_frame(writer: asyncio.StreamWriter, frame_type: int, payload: bytes) -> None:
    writer.write(encode(frame_type, payload))
    await writer.drain()


async def write_json(writer: asyncio.StreamWriter, obj: Any) -> None:
    await write_frame(writer, TYPE_JSON,
                      json.dumps(obj, separators=(",", ":"), ensure_ascii=False).encode())
