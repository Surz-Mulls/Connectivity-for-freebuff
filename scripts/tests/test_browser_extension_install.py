#!/usr/bin/env python3
"""Test the browser extension's deterministic ID and native-messaging installer.

No browser is required. This proves the ID Chromium will derive from manifest.json's pinned key,
that install.sh writes that exact ID into every allowed_origins entry, and that no placeholder is
left behind. Browser loading and native messaging itself remain implemented-unverified elsewhere.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import pathlib
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[2]
EXT = ROOT / "integrations/browser-extension"
MANIFEST = EXT / "manifest.json"
INSTALLER = EXT / "install.sh"
EXPECTED_ID = "pocpmobopjgeddenbhlieogenkjfldjn"
PROFILES = [
    ".config/google-chrome/NativeMessagingHosts",
    ".config/chromium/NativeMessagingHosts",
    ".config/vivaldi/NativeMessagingHosts",
    ".config/BraveSoftware/Brave-Browser/NativeMessagingHosts",
]


def derive_id(key_b64: str) -> str:
    der = base64.b64decode(key_b64, validate=True)
    digest = hashlib.sha256(der).hexdigest()[:32]
    return "".join(chr(ord("a") + int(nibble, 16)) for nibble in digest)


def main() -> int:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    key = str(manifest.get("key", ""))
    if not key:
        raise SystemExit("manifest.json has no pinned key")
    extension_id = derive_id(key)
    if extension_id != EXPECTED_ID:
        raise SystemExit(
            f"derived extension ID {extension_id} != pinned expected ID {EXPECTED_ID}"
        )
    if len(key) < 300:
        raise SystemExit("pinned key looks too short to be an RSA public key")

    subprocess.run(["bash", "-n", str(INSTALLER)], check=True)
    with tempfile.TemporaryDirectory(prefix="continuity home ") as home:
        env = dict(os.environ, HOME=home)
        result = subprocess.run(
            ["bash", str(INSTALLER)], check=True, capture_output=True, text=True, env=env
        )
        if "REPLACE_WITH_EXTENSION_ID" in result.stdout:
            raise SystemExit("installer output still mentions the placeholder")
        if extension_id not in result.stdout:
            raise SystemExit("installer output does not name the derived extension ID")

        host_dir = pathlib.Path(home) / ".local/share/continuity/native-host"
        wrapper = host_dir / "continuity-native-host"
        if not wrapper.is_file() or not os.access(wrapper, os.X_OK):
            raise SystemExit("native host wrapper missing or not executable")
        if not (host_dir / "continuity_native.py").is_file():
            raise SystemExit("native host script was not installed")

        for relative in PROFILES:
            path = pathlib.Path(home) / relative / "dev.continuity.handoff.json"
            if not path.is_file():
                raise SystemExit(f"missing native-messaging manifest: {path}")
            payload = json.loads(path.read_text(encoding="utf-8"))
            origins = payload.get("allowed_origins")
            expected = [f"chrome-extension://{extension_id}/"]
            if origins != expected:
                raise SystemExit(f"{path}: allowed_origins={origins!r}, expected {expected!r}")
            if "REPLACE_WITH_EXTENSION_ID" in path.read_text(encoding="utf-8"):
                raise SystemExit(f"{path}: placeholder survived")

        second = subprocess.run(
            ["bash", str(INSTALLER)], check=True, capture_output=True, text=True, env=env
        )
        if extension_id not in second.stdout:
            raise SystemExit("second install did not report the same ID")

    print(f"ok: deterministic extension ID {extension_id}; installer writes it and no placeholder")
    return 0


if __name__ == "__main__":
    sys.exit(main())
