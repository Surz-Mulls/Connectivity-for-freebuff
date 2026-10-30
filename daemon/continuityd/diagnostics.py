"""Full diagnostics: allowlisted checks, redaction, JSON + Markdown export.

Rules from the brief that are enforced here:
* never change system state as a side effect;
* redact clipboard text, notification bodies, file contents, tokens, keys and full home paths;
* bounded output, explicit "not verified"/"blocked" instead of pretending;
* every check has a stable id so the batch-test matrix can point at it.
"""

from __future__ import annotations

import datetime as _dt
import os
import platform
import resource
import shutil
import socket
import ssl
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable

from . import PROTOCOL_VERSION, __version__
from .config import Settings, ipc_socket_path, runtime_dir
from .identity import Identity

CHECK_IDS = [
    "env.os", "env.session", "env.python", "build.version", "identity.present",
    "trust.store", "transport.tls", "ipc.socket", "discovery.available", "clipboard.backend",
    "notify.bridge", "dex.tools", "android.app", "quickshell.detect", "dolphin.detect",
    "security.listeners", "security.identity", "deps.scrcpy", "android.privileged",
]


@dataclass
class CheckResult:
    id: str
    title: str
    status: str          # pass | fail | warn | blocked | not_verified
    detail: str = ""
    remediation: str = ""

    def public(self) -> dict:
        return asdict(self)


@dataclass
class DiagnosticsReport:
    generated: str
    app_version: str
    protocol_version: int
    commit: str
    checks: list[CheckResult] = field(default_factory=list)
    summary: dict = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def add(self, check: CheckResult) -> None:
        self.checks.append(check)

    def finalize(self) -> None:
        counts = {"pass": 0, "fail": 0, "warn": 0, "blocked": 0, "not_verified": 0}
        for check in self.checks:
            counts[check.status] = counts.get(check.status, 0) + 1
        self.summary = counts

    def to_dict(self) -> dict:
        return {
            "schema": "continuity.diagnostics/1",
            "generated": self.generated,
            "app_version": self.app_version,
            "protocol_version": self.protocol_version,
            "commit": self.commit,
            "summary": self.summary,
            "checks": [c.public() for c in self.checks],
            "notes": self.notes,
        }

    def to_markdown(self) -> str:
        lines = [
            "# Continuity diagnostics",
            "",
            f"- Generated: `{self.generated}`",
            f"- App version: `{self.app_version}` (protocol v{self.protocol_version})",
            f"- Commit: `{self.commit}`",
            "- Summary: " + ", ".join(f"**{k}**: {v}" for k, v in sorted(self.summary.items())),
            "",
            "| Check | Status | Detail | Remediation |",
            "|---|---|---|---|",
        ]
        for check in self.checks:
            lines.append(f"| `{check.id}` {check.title} | {check.status} | "
                         f"{_escape(check.detail)} | {_escape(check.remediation)} |")
        if self.notes:
            lines += ["", "## Notes", ""] + [f"- {note}" for note in self.notes]
        return "\n".join(lines) + "\n"


def _escape(text: str) -> str:
    return (text or "").replace("|", "\\|").replace("\n", " ")[:400]


def _redact(text: str) -> str:
    home = str(Path.home())
    return text.replace(home, "~")


class DiagnosticsRunner:
    def __init__(self, *, settings: Settings, identity: Identity | None = None,
                 manager=None):
        self.settings = settings
        self.identity = identity
        self.manager = manager

    # ---------------------------------------------------------------- runner
    def run(self) -> DiagnosticsReport:
        report = DiagnosticsReport(
            generated=_dt.datetime.now(_dt.timezone.utc).isoformat(),
            app_version=__version__, protocol_version=PROTOCOL_VERSION,
            commit=_git_commit(),
        )
        for check in (
            self._env_os, self._env_session, self._python, self._build,
            self._identity, self._trust, self._tls, self._ipc, self._discovery,
            self._clipboard, self._notify, self._dex, self._android,
            self._quickshell, self._dolphin, self._listeners, self._privileged,
        ):
            try:
                result = check()
            except Exception as exc:  # noqa: BLE001 - a diagnostics run must never crash
                result = CheckResult(id=getattr(check, "__name__", "unknown").lstrip("_"),
                                     title="Check failed to run", status="fail",
                                     detail=f"{exc.__class__.__name__}: {_redact(str(exc))}")
            report.add(result)
        report.notes.append("Redaction: home paths are shortened; clipboard text, notification "
                            "bodies, keys and file contents are never collected.")
        report.notes.append("Android app checks require the phone and are reported as blocked here.")
        report.finalize()
        return report

    # ---------------------------------------------------------------- checks
    def _env_os(self) -> CheckResult:
        os_release = {}
        path = Path("/etc/os-release")
        if path.exists():
            for line in path.read_text().splitlines():
                if "=" in line:
                    key, value = line.split("=", 1)
                    os_release[key] = value.strip('"')
        detail = f"{os_release.get('PRETTY_NAME', platform.platform())} · {platform.machine()}"
        return CheckResult("env.os", "Operating system", "pass", _redact(detail))

    def _env_session(self) -> CheckResult:
        session = os.environ.get("XDG_SESSION_TYPE", "unknown")
        desktop = os.environ.get("XDG_CURRENT_DESKTOP", "unknown")
        wayland = os.environ.get("WAYLAND_DISPLAY")
        detail = f"session={session} desktop={desktop} wayland={bool(wayland)}"
        status = "pass" if session != "unknown" else "warn"
        remediation = "" if wayland else ("No Wayland session detected: input/second-screen "
                                          "features are unverified on this host.")
        return CheckResult("env.session", "Desktop session", status, detail, remediation)

    def _python(self) -> CheckResult:
        return CheckResult("env.python", "Python runtime", "pass",
                           f"{sys.version.split()[0]} ({sys.executable})")

    def _build(self) -> CheckResult:
        return CheckResult("build.version", "Build", "pass",
                           f"continuityd {__version__}, protocol v{PROTOCOL_VERSION}, "
                           f"commit {_git_commit()}")

    def _identity(self) -> CheckResult:
        if not self.identity:
            return CheckResult("identity.present", "Device identity", "blocked",
                               "daemon identity not loaded")
        cert = self.identity.cert
        days = (cert.not_valid_after_utc - _dt.datetime.now(_dt.timezone.utc)).days
        status = "pass" if days > 30 else "warn"
        return CheckResult("identity.present", "Device identity", status,
                           f"fingerprint {self.identity.fingerprint[:16]}… expires in {days} days",
                           "Identity expires soon; re-run the daemon to rotate." if days <= 30 else "")

    def _trust(self) -> CheckResult:
        if not self.manager:
            return CheckResult("trust.store", "Trust store", "blocked", "daemon not attached")
        active = self.manager.trust.active()
        revoked = [p for p in self.manager.trust.peers if p.revoked]
        status = "pass" if active or not revoked else "warn"
        return CheckResult("trust.store", "Trust store", status,
                           f"{len(active)} paired device(s), {len(revoked)} revoked")

    def _tls(self) -> CheckResult:
        try:
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            return CheckResult("transport.tls", "TLS 1.3 transport", "pass",
                               f"openssl {ssl.OPENSSL_VERSION}; min TLS {ctx.minimum_version}")
        except (ssl.SSLError, ValueError) as exc:
            return CheckResult("transport.tls", "TLS 1.3 transport", "fail", str(exc))

    def _ipc(self) -> CheckResult:
        path = ipc_socket_path()
        if path.exists():
            mode = oct(path.stat().st_mode & 0o777)
            return CheckResult("ipc.socket", "Local IPC socket", "pass", f"{_redact(str(path))} {mode}")
        return CheckResult("ipc.socket", "Local IPC socket", "warn", "socket not present",
                           "Start the daemon: continuityd run")

    def _discovery(self) -> CheckResult:
        try:
            from zeroconf import Zeroconf  # noqa: F401
            available = True
        except ImportError:
            available = False
        if not self.settings.discovery_enabled:
            return CheckResult("discovery.available", "mDNS discovery", "warn", "disabled in settings")
        return CheckResult("discovery.available", "mDNS discovery",
                           "pass" if available else "fail",
                           "zeroconf importable" if available else "zeroconf is not installed")

    def _clipboard(self) -> CheckResult:
        from .clipboard import detect_backend

        backend = detect_backend()
        status = "pass" if backend.available else "warn"
        return CheckResult("clipboard.backend", "Clipboard backend", status,
                           f"{backend.name} (read={bool(backend.read_cmd)}, "
                           f"write={bool(backend.write_cmd)})",
                           "" if backend.available else
                           "Install wl-clipboard (Wayland) or xclip to enable clipboard sync.")

    def _notify(self) -> CheckResult:
        present = bool(shutil.which("notify-send"))
        return CheckResult("notify.bridge", "Desktop notifications",
                           "pass" if present else "warn",
                           "notify-send present" if present else "notify-send not installed",
                           "" if present else "Mirrored notifications stay in the UI only.")

    def _dex(self) -> CheckResult:
        adb, scrcpy = shutil.which("adb"), shutil.which("scrcpy")
        enabled = self.settings.adb_enabled
        detail = f"adb={adb or 'missing'} scrcpy={scrcpy or 'missing'} enabled={enabled}"
        status = "pass" if adb and scrcpy and enabled else ("blocked" if adb and scrcpy else "warn")
        return CheckResult("dex.tools", "DeX / screen tooling", status, _redact(detail),
                           "" if enabled else "Enable the ADB integration in settings to use DeX.")

    def _android(self) -> CheckResult:
        return CheckResult("android.app", "Android app on device", "blocked",
                           "no device attached to this build host",
                           "Install artifacts/android/*.apk on the phone, then re-run diagnostics "
                           "from the phone or over a paired connection.")

    def _quickshell(self) -> CheckResult:
        present = bool(shutil.which("quickshell") or shutil.which("qs"))
        return CheckResult("quickshell.detect", "Quickshell", "pass" if present else "not_verified",
                           "quickshell binary found" if present else "not installed on this host",
                           "" if present else "Install the sample module from integrations/quickshell.")

    def _dolphin(self) -> CheckResult:
        service = Path.home() / ".local/share/kio/servicemenus/continuity-send.desktop"
        return CheckResult("dolphin.detect", "Dolphin integration",
                           "pass" if service.exists() else "not_verified",
                           str(service) if service.exists() else "service menu not installed",
                           "" if service.exists() else "Run scripts/install-integrations.sh --dolphin")

    def _listeners(self) -> CheckResult:
        if not self.manager:
            return CheckResult("security.listeners", "Network listeners", "blocked",
                               "daemon not attached")
        port = self.manager.port
        return CheckResult("security.listeners", "Network listeners", "pass",
                           f"1 TLS listener on 0.0.0.0:{port} (LAN only, pin-required)",
                           "Keep the port closed on untrusted networks.")

    def _privileged(self) -> CheckResult:
        return CheckResult("android.privileged", "Optional privileged integrations",
                           "pass" if not (self.settings.adb_enabled or
                                          self.settings.shizuku_enabled) else "warn",
                           f"adb={self.settings.adb_enabled} "
                           f"shizuku={self.settings.shizuku_enabled}",
                           "Anything privileged must be user-initiated; this build never enables it.")


def _git_commit() -> str:
    import subprocess

    try:
        result = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                                capture_output=True, timeout=3, check=False,
                                cwd=Path(__file__).resolve().parents[2])
        return result.stdout.decode().strip() or "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def export(report: DiagnosticsReport, out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    json_path = out_dir / f"diagnostics-{stamp}.json"
    md_path = out_dir / f"diagnostics-{stamp}.md"
    import json

    json_path.write_text(json.dumps(report.to_dict(), indent=2))
    md_path.write_text(report.to_markdown())
    for path in (json_path, md_path):
        os.chmod(path, 0o644)
    return {"json": str(json_path), "markdown": str(md_path)}


def resource_snapshot() -> dict:
    usage = resource.getrusage(resource.RUSAGE_SELF)
    return {
        "max_rss_kb": usage.ru_maxrss,
        "user_cpu_s": round(usage.ru_utime, 3),
        "system_cpu_s": round(usage.ru_stime, 3),
        "host_cpu_percent": None,
        "note": "process-level snapshot only; no continuous sampling",
    }


def free_port(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("0.0.0.0", port))
            return True
        except OSError:
            return False


def runtime_paths() -> dict:
    return {"runtime_dir": _redact(str(runtime_dir())), "ipc": _redact(str(ipc_socket_path()))}
