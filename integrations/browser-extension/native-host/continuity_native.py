#!/usr/bin/env python3
"""Native messaging host: forwards a browser tab URL to the local Continuity daemon.

Chrome speaks native messaging as: 4-byte little-endian length + UTF-8 JSON, both directions.
The URL is validated here (http/https only) and passed as argv to `continuityctl` — never through a
shell — so a hostile page cannot inject commands.
"""

from __future__ import annotations

import json
import os
import struct
import subprocess
import sys
from urllib.parse import urlparse

MAX_MESSAGE = 1 << 20
CONTINUITYCTL = os.environ.get("CONTINUITYCTL", "continuityctl")


def _read_exactly(stream, count: int) -> bytes:
    """Native messaging framing must read the full announced payload; read(n) may return less."""
    chunks = bytearray()
    while len(chunks) < count:
        block = stream.read(count - len(chunks))
        if not block:
            raise EOFError("native-messaging payload truncated")
        chunks.extend(block)
    return bytes(chunks)


def read_message() -> dict | None:
    try:
        raw = _read_exactly(sys.stdin.buffer, 4)
        (length,) = struct.unpack("<I", raw)
        if length == 0 or length > MAX_MESSAGE:
            return None
        payload = _read_exactly(sys.stdin.buffer, length)
        decoded = json.loads(payload.decode("utf-8"))
        if not isinstance(decoded, dict):
            return None
        return decoded
    except (EOFError, UnicodeDecodeError, json.JSONDecodeError):
        return None


def write_message(payload: dict) -> None:
    body = json.dumps(payload).encode("utf-8")
    sys.stdout.buffer.write(struct.pack("<I", len(body)) + body)
    sys.stdout.buffer.flush()


def main() -> int:
    message = read_message()
    if message is None:
        write_message({"ok": False, "error": "invalid message"})
        return 1
    url = str(message.get("url", ""))[:8192]
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        write_message({"ok": False, "error": "only http(s) URLs may be sent"})
        return 1
    if parsed.username or parsed.password:
        write_message({"ok": False, "error": "URLs with embedded credentials are rejected"})
        return 1
    if parsed.port is not None and not 1 <= parsed.port <= 65535:
        write_message({"ok": False, "error": "invalid URL port"})
        return 1

    try:
        state = subprocess.run([CONTINUITYCTL, "status", "--json"], capture_output=True,
                               timeout=10, check=False)
        snapshot = json.loads(state.stdout or b"{}")
        devices = [d for d in snapshot.get("devices", []) if d.get("state") == "connected"]
        if not devices:
            write_message({"ok": False, "error": "no connected phone"})
            return 1
        fingerprint = devices[0]["fingerprint"]
        result = subprocess.run([CONTINUITYCTL, "handoff", fingerprint, url, "--json"],
                                capture_output=True, timeout=30, check=False)
        if result.returncode != 0:
            detail = result.stdout.decode("utf-8", "replace")[:200]
            write_message({"ok": False, "error": f"handoff failed: {detail}"})
            return 1
        # The CLI exit code reflects failure, but the phone's reply is the authoritative result:
        # a structured {ok:false} or accepted:false is a failed handoff, not a success.
        reply = json.loads(result.stdout or b"{}")
        accepted = bool(reply.get("accepted")) or bool(reply.get("ok"))
        write_message({"ok": True, "accepted": accepted})
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
        write_message({"ok": False, "error": f"daemon unavailable: {exc.__class__.__name__}"})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
