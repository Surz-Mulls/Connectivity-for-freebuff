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


def read_message() -> dict | None:
    raw = sys.stdin.buffer.read(4)
    if len(raw) != 4:
        return None
    (length,) = struct.unpack("<I", raw)
    if length == 0 or length > MAX_MESSAGE:
        return None
    payload = sys.stdin.buffer.read(length)
    try:
        return json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
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
    url = str(message.get("url", ""))
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        write_message({"ok": False, "error": "only http(s) URLs may be sent"})
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
        result = subprocess.run([CONTINUITYCTL, "handoff", fingerprint, url],
                                capture_output=True, timeout=30, check=False)
        if result.returncode != 0:
            write_message({"ok": False, "error": "handoff failed"})
            return 1
        write_message({"ok": True})
        return 0
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
        write_message({"ok": False, "error": f"daemon unavailable: {exc.__class__.__name__}"})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
