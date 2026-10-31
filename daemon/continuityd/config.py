"""Settings + XDG paths. Every private directory is created 0700."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

APP = "continuity"
DEFAULT_PORT = 47820
SERVICE_TYPE = "_continuity._tcp.local."

#: bytes per ``file.chunk`` binary frame payload
CHUNK_SIZE = 256 * 1024


def _xdg(env: str, fallback: str) -> Path:
    value = os.environ.get(env)
    base = Path(value) if value else Path.home() / fallback
    base.mkdir(parents=True, exist_ok=True)
    return base


def config_dir() -> Path:
    path = _xdg("XDG_CONFIG_HOME", ".config") / APP
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    return path


def data_dir() -> Path:
    path = _xdg("XDG_DATA_HOME", ".local/share") / APP
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    return path


def state_dir() -> Path:
    path = _xdg("XDG_STATE_HOME", ".local/state") / APP
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    return path


def runtime_dir() -> Path:
    """Directory for the IPC socket. 0700 so only this user can connect."""
    base = os.environ.get("XDG_RUNTIME_DIR")
    # Never fall back to a world-writable /tmp: another local user could pre-create the directory
    # and read the HTTP bearer token. Use a 0700 directory under the user's own state dir instead.
    path = (Path(base) / APP) if base else (state_dir() / "run")
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(path, 0o700)
    return path


def ipc_socket_path() -> Path:
    return runtime_dir() / "ipc.sock"


@dataclass
class Settings:
    device_name: str = ""
    port: int = DEFAULT_PORT
    clipboard_enabled: bool = True
    clipboard_direction: str = "both"          # off | to_phone | to_desktop | both
    clipboard_allow_sensitive: bool = False
    clipboard_images: bool = False
    clipboard_auto_clear_s: int = 45
    notifications_enabled: bool = True
    notifications_include_sensitive: bool = False
    notifications_retention_days: int = 7
    verification_code_handoff: bool = False
    files_enabled: bool = True
    files_auto_accept: bool = False
    receive_dir: str = ""
    sync_folders: list[str] = field(default_factory=list)
    history_retention_days: int = 7
    history_enabled: bool = True
    privacy_mode: bool = False
    paused_features: list[str] = field(default_factory=list)
    discovery_enabled: bool = True
    # privileged integrations stay off until the user explicitly enables them
    adb_enabled: bool = False
    shizuku_enabled: bool = False
    log_level: str = "info"

    def __post_init__(self) -> None:
        if not self.receive_dir:
            self.receive_dir = str(data_dir() / "received")
        Path(self.receive_dir).expanduser().mkdir(parents=True, exist_ok=True)
        if self.clipboard_direction not in ("off", "to_phone", "to_desktop", "both"):
            self.clipboard_direction = "both"
        if not 1024 <= self.port <= 65535:
            self.port = DEFAULT_PORT

    @property
    def path(self) -> Path:
        return Path(getattr(self, "_explicit_path", config_dir() / "settings.json"))

    @classmethod
    def load(cls, path: Path | None = None, device_name: str = "") -> "Settings":
        target = path or (config_dir() / "settings.json")
        data: dict = {}
        if target.exists():
            try:
                data = json.loads(target.read_text())
            except (OSError, json.JSONDecodeError):
                data = {}
        known = {f.name for f in fields(cls)}
        settings = cls(**{k: v for k, v in data.items() if k in known})
        if not settings.device_name:
            settings.device_name = device_name or os.environ.get("HOSTNAME") or "Continuity desktop"
        object.__setattr__(settings, "_explicit_path", target)
        return settings

    def save(self) -> None:
        target = self.path
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(target.parent), prefix=".settings-")
        try:
            with os.fdopen(fd, "w") as fh:
                json.dump(asdict(self), fh, indent=2)
            os.chmod(tmp, 0o600)
            os.replace(tmp, target)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

    def feature_allowed(self, feature: str) -> bool:
        if self.privacy_mode:
            return False
        return feature not in self.paused_features

    def public(self) -> dict:
        return asdict(self)
