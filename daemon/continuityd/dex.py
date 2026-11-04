"""DeX Workspace: supervised, allowlisted scrcpy/ADB sessions.

This is a first-class mode, not a mirror button. It never builds a shell string: every argument is
a list element, packages must match an Android package-name pattern, and the only executables used
are the ones found on PATH by absolute path.

Honesty rules encoded here:
* ``probe()`` reports what the *installed* scrcpy supports (``--new-display`` needs scrcpy >= 3.0)
  and what ADB can see; it never upgrades a "mirror" into "native desktop mode";
* nothing runs until the user enables the privileged integration in settings;
* a failed probe/session never breaks continuity features.
"""

from __future__ import annotations

import asyncio
import re
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .config import Settings

PACKAGE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*(\.[A-Za-z][A-Za-z0-9_]*)+$")
#: adb -l serial formats that prove an actual TCP transport is connected (§ DeX truthfulness:
#: "adb installed" is never evidence that wireless debugging works). IPv4 host:port only; the
#: device must ALSO list with state == device.
TCP_SERIAL_RE = re.compile(r"^\d{1,3}(\.\d{1,3}){3}:\d{4,5}$")
MODES = ("mirror", "virtual_display", "wireless")
MAX_SESSION_SECONDS = 12 * 3600


class DexError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class DexSession:
    session_id: str
    mode: str
    package: str | None
    argv: list[str]
    started: float = field(default_factory=time.time)
    state: str = "starting"     # starting | running | stopped | failed
    error: str = ""
    pid: int | None = None

    def public(self) -> dict:
        return {"session_id": self.session_id, "mode": self.mode, "package": self.package,
                "state": self.state, "started": self.started, "pid": self.pid,
                "error": self.error}


class DexService:
    def __init__(self, settings: Settings, emit: Callable[[str, dict], None] | None = None):
        self.settings = settings
        self.emit = emit or (lambda event, data: None)
        self.adb = shutil.which("adb")
        self.scrcpy = shutil.which("scrcpy")
        self.process: asyncio.subprocess.Process | None = None
        self.session: DexSession | None = None
        self._supervisor: asyncio.Task | None = None

    # ---------------------------------------------------------------- probing
    async def _run(self, argv: list[str], timeout: float = 8.0) -> tuple[int, str]:
        try:
            proc = await asyncio.create_subprocess_exec(
                *argv, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
            out, _ = await asyncio.wait_for(proc.communicate(), timeout)
            return proc.returncode or 0, out.decode("utf-8", "replace")
        except (OSError, asyncio.TimeoutError) as exc:
            return 127, str(exc)

    @staticmethod
    def _authorized_devices(report: dict) -> list[dict]:
        return [d for d in report["devices"] if d["state"] == "device"]

    async def probe(self) -> dict:
        report: dict = {
            "adb": {"path": self.adb, "available": bool(self.adb)},
            "scrcpy": {"path": self.scrcpy, "available": bool(self.scrcpy),
                       "version": None, "supports_new_display": False,
                       "supports_flex_display": False, "supports_start_app": False},
            "devices": [], "capabilities": {}, "notes": [],
        }
        if not self.adb:
            report["notes"].append("adb is not installed; DeX sessions are unavailable")
        else:
            code, out = await self._run([self.adb, "devices", "-l"])
            if code == 0:
                for line in out.splitlines()[1:]:
                    parts = line.split()
                    if len(parts) >= 2 and parts[1] in ("device", "unauthorized", "offline"):
                        report["devices"].append({
                            "serial": parts[0], "state": parts[1],
                            "model": next((p.split(":", 1)[1] for p in parts
                                           if p.startswith("model:")), ""),
                        })
            else:
                report["notes"].append("adb could not list devices")
        if self.scrcpy:
            code, out = await self._run([self.scrcpy, "--version"])
            if code == 0:
                first = out.splitlines()[0] if out else ""
                report["scrcpy"]["version"] = first.strip()
                match = re.search(r"(\d+)\.(\d+)", first)
                if match:
                    major = int(match.group(1))
                    report["scrcpy"]["supports_new_display"] = major >= 3
            code, help_out = await self._run([self.scrcpy, "--help"])
            if code == 0:
                report["scrcpy"]["supports_new_display"] |= "--new-display" in help_out
                report["scrcpy"]["supports_flex_display"] = "--flex-display" in help_out
                report["scrcpy"]["supports_start_app"] = "--start-app" in help_out
                report["scrcpy"]["supports_audio"] = bool(
                    "--audio" in help_out or "--audio-source" in help_out)
        else:
            report["notes"].append("scrcpy is not installed; no DeX or mirroring session is possible")
        authorized = self._authorized_devices(report)
        wireless = [d for d in authorized
                    if d["serial"] and TCP_SERIAL_RE.match(d["serial"])]
        report["capabilities"] = {
            "device_manager": bool(self.adb),
            "adb_authorized_device": bool(authorized),
            "single_screen_mirror": bool(self.scrcpy and authorized),
            "virtual_display": bool(report["scrcpy"]["supports_new_display"] and authorized),
            "independent_app_windows": bool(
                report["scrcpy"]["supports_new_display"]
                and report["scrcpy"]["supports_start_app"] and authorized),
            # documented as available_but_unverified until an actual session runs on the target
            "wireless_adb": bool(wireless),
            "wireless_note": ("an adb TCP transport is currently connected" if wireless
                              else "no connected adb TCP transport; wireless is not asserted"),
            "audio_forwarding": bool(self.scrcpy and authorized
                                     and report["scrcpy"].get("supports_audio", False)),
            "keyboard_mouse_injection": bool(self.scrcpy and authorized),
            # neither of the two below is ever assumed from a binary being installed:
            "wireless_verified_by_session": False,
            "native_dex_desktop_mode": False,  # HyperOS on the Mi 12 does not expose Samsung DeX
        }
        if (self.scrcpy and self.adb
                and not self.settings.adb_enabled):
            report["notes"].append("DeX integration is disabled in settings; capabilities above "
                                   "describe what the binaries support, not what is enabled")
        report["notes"].append("keyboard/mouse injection on HyperOS may additionally require the "
                               "firmware's 'USB debugging (Security settings)' option; verify on "
                               "the device before enabling")
        report["enabled"] = self.settings.adb_enabled
        return report

    # ---------------------------------------------------------------- session
    def _require_enabled(self) -> None:
        if not self.settings.adb_enabled:
            raise DexError("privacy.blocked",
                           "the DeX integration is disabled; enable ADB integration first")
        if not self.scrcpy or not self.adb:
            raise DexError("capability.denied", "scrcpy and adb are required for DeX sessions")

    async def _resolve_serial(self, requested: str | None) -> str:
        """Resolve the ADB serial to target. A session is never aimed at an ambiguous device."""
        if not self.adb:
            raise DexError("capability.denied", "adb is required to list devices")
        code, out = await self._run([self.adb, "devices", "-l"])
        if code != 0:
            raise DexError("internal", "adb could not list devices")
        authorized = []
        for line in out.splitlines()[1:]:
            parts = line.split()
            if len(parts) >= 2 and parts[1] == "device":
                authorized.append(parts[0])
        if requested:
            if requested not in authorized:
                raise DexError("protocol.json",
                               f"device {requested!r} is not connected and authorized")
            return requested
        if len(authorized) == 0:
            raise DexError("capability.denied",
                           "no authorized ADB device; unlock the phone and accept the prompt")
        if len(authorized) > 1:
            raise DexError("protocol.json",
                           f"multiple authorized devices ({', '.join(authorized)}); "
                           "pass an explicit serial")
        return authorized[0]

    async def start(self, mode: str = "virtual_display", package: str | None = None,
                    serial: str | None = None, session_id: str | None = None) -> dict:
        self._require_enabled()
        if mode not in MODES:
            raise DexError("protocol.unsupported", f"unknown DeX mode {mode!r}")
        if package and not PACKAGE_RE.match(package):
            raise DexError("path.unsafe", "package name is not an Android package id")
        if self.session and self.session.state == "running":
            raise DexError("internal", "a DeX session is already running")

        serial = await self._resolve_serial(serial)
        argv = [self.scrcpy, "-s", serial]
        if mode == "mirror":
            pass
        else:
            argv.append("--no-playback-control")
            supports = (await self.probe())["scrcpy"]
            if not supports["supports_new_display"]:
                raise DexError("capability.denied",
                               "installed scrcpy does not support --new-display (needs >= 3.0)")
            argv += ["--new-display=1920x1080/240"]
            if supports["supports_flex_display"]:
                argv.append("--flex-display")
            if package:
                if not supports["supports_start_app"]:
                    raise DexError("capability.denied",
                                   "installed scrcpy cannot launch a specific app")
                argv.append(f"--start-app={package}")
        if mode == "wireless":
            # the caller must have paired/connected adb over TCP first; this daemon never enables
            # wireless debugging or changes any device setting by itself
            report = await self.probe()
            if not report["capabilities"]["wireless_adb"]:
                raise DexError("capability.denied",
                               "no wireless (TCP) ADB transport is connected; connect it on the "
                               "phone/laptop first, this daemon never enables wireless debugging")

        try:
            self.process = await asyncio.create_subprocess_exec(
                *argv, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE)
        except OSError as exc:
            raise DexError("internal", f"could not start scrcpy: {exc}") from exc
        self.session = DexSession(
            session_id=session_id or f"dex-{int(time.time())}", mode=mode, package=package,
            argv=argv, state="running", pid=self.process.pid)
        self.emit("dex.session", self.session.public())
        self._supervisor = asyncio.create_task(self._watch())
        return {"ok": True, "session": self.session.public(), "serial": serial}

    async def _watch(self) -> None:
        if not self.process or not self.session:
            return
        try:
            _, stderr = await self.process.communicate()
        except asyncio.CancelledError:
            return
        if self.session:
            if self.process.returncode not in (0, None):
                self.session.state = "failed"
                self.session.error = stderr.decode("utf-8", "replace")[-400:] if stderr else ""
            else:
                self.session.state = "stopped"
            self.emit("dex.session", self.session.public())

    async def stop(self) -> dict:
        if not self.process or not self.session:
            return {"ok": False, "reason": "no session"}
        if self.process.returncode is None:
            self.process.terminate()
            try:
                await asyncio.wait_for(self.process.wait(), 5)
            except (asyncio.TimeoutError, TimeoutError):
                self.process.kill()
                await self.process.wait()
        self.session.state = "stopped"
        self.emit("dex.session", self.session.public())
        return {"ok": True, "session": self.session.public()}

    def status(self) -> dict:
        return {"enabled": self.settings.adb_enabled,
                "session": self.session.public() if self.session else None,
                "paths": {"adb": self.adb, "scrcpy": self.scrcpy}}
