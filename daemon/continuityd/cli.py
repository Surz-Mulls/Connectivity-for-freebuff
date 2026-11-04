"""Command line: ``continuityd run`` starts the daemon, ``continuityctl`` talks to it.

Everything the CLI does goes through the same allowlisted IPC command surface as the Qt UI and the
Quickshell module, so there is exactly one implementation of each action.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import signal
import sys
from pathlib import Path

from . import __version__
from .config import (Settings, api_config_path, config_dir, data_dir, ipc_socket_path,
                     runtime_dir)
from .core import DeviceManager
from .identity import Identity
from .ipc import IPCServer
from .trust import TrustStore

LOG_FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"


def _setup_logging(level: str) -> None:
    logging.basicConfig(level=getattr(logging, level.upper(), logging.INFO), format=LOG_FORMAT)


async def _ipc_request(command: dict, timeout: float = 60.0) -> dict:
    path = ipc_socket_path()
    if not path.exists():
        raise SystemExit(f"daemon is not running (no socket at {path}); start it with "
                         f"'continuityd run'")
    reader, writer = await asyncio.open_unix_connection(str(path))
    try:
        hello = await reader.readline()
        if not hello:
            raise SystemExit("daemon closed the connection")
        writer.write((json.dumps(command) + "\n").encode())
        await writer.drain()
        while True:
            line = await asyncio.wait_for(reader.readline(), timeout)
            if not line:
                raise SystemExit("daemon closed the connection")
            payload = json.loads(line)
            if payload.get("event") == "result":
                return payload.get("data", {})
    finally:
        writer.close()


async def _daemon_main(settings: Settings, identity: Identity, trust: TrustStore,
                       ipc: IPCServer, manager: DeviceManager) -> None:
    await manager.start()
    info = await ipc.start()
    logging.getLogger("continuityd").info(
        "listening on 0.0.0.0:%s · fingerprint %s · ipc %s · http 127.0.0.1:%s",
        manager.port, identity.fingerprint, info["socket"], ipc.http_port)
    stop = asyncio.Event()
    ipc.stop_event = stop

    def _request_stop() -> None:
        stop.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _request_stop)
        except NotImplementedError:
            pass
    try:
        await stop.wait()
    finally:
        await ipc.stop()
        await manager.stop()


def cmd_run(args: argparse.Namespace) -> int:
    settings = Settings.load()
    _setup_logging(settings.log_level)
    identity_dir = config_dir() / "identity"
    identity = Identity.load_or_create(identity_dir, settings.device_name)
    if not settings.device_name:
        settings.device_name = identity.name
    trust = TrustStore.load(config_dir() / "trusted-peers.json")
    manager = DeviceManager(settings, identity, trust)
    ipc = IPCServer(manager)
    try:
        asyncio.run(_daemon_main(settings, identity, trust, ipc, manager))
    except KeyboardInterrupt:
        pass
    return 0


# ---------------------------------------------------------------------- client commands
def _print(payload, as_json: bool = False) -> None:
    if as_json:
        print(json.dumps(payload, indent=2, default=str))
        return
    result = payload.get("result") if isinstance(payload, dict) else payload
    if isinstance(payload, dict) and payload.get("ok") is False:
        print(f"error: {payload.get('code')}: {payload.get('message')}", file=sys.stderr)
        return
    print(json.dumps(result, indent=2, default=str))


def _dispatch(command: dict, as_json: bool, timeout: float = 60.0) -> int:
    """Run one IPC command and reflect its result in the process exit code.

    Exit codes (documented in docs/cli-schema.md):
      0 — the command succeeded (``ok: true``; ``--json`` prints the unwrapped result);
      1 — the daemon answered a structured ``{ok: false}`` error (also for ``--json``, which then
          prints the error envelope so scripts can read ``code``/``message``);
      2 — no daemon / transport problem or a usage error (argparse-style) so shell pipelines and
          the Dolphin/browser integrations never mistake a failed send for success.
    """
    try:
        payload = asyncio.run(_ipc_request(command, timeout))
    except SystemExit:
        raise
    except (OSError, json.JSONDecodeError) as exc:
        if as_json:
            print(json.dumps({"ok": False, "code": "internal", "message": str(exc)}))
        else:
            print(f"error: daemon request failed: {exc}", file=sys.stderr)
        return 1
    if isinstance(payload, dict) and payload.get("ok") is False:
        if as_json:
            print(json.dumps(payload, indent=2, default=str))
        else:
            print(f"error: {payload.get('code')}: {payload.get('message')}", file=sys.stderr)
        return 1
    body = payload.get("result") if isinstance(payload, dict) else payload
    if as_json:
        print(json.dumps(body, indent=2, default=str))
    else:
        # human output: the useful payload itself (the {ok,result} envelope stays inside IPC)
        print(json.dumps(body, indent=2, default=str))
    return 0


def cmd_status(args) -> int:
    return _dispatch({"cmd": "status"}, args.json)


def cmd_devices(args) -> int:
    return _dispatch({"cmd": "devices"}, args.json)


def cmd_pair(args) -> int:
    if args.action == "begin":
        return _dispatch({"cmd": "pair.begin"}, args.json)
    if args.action == "connect":
        return _dispatch({"cmd": "pair.connect", "host": args.host, "port": args.port,
                          "fingerprint": args.fingerprint}, args.json)
    if args.action == "discover":
        return _dispatch({"cmd": "pair.discover", "timeout": args.timeout}, args.json)
    return _dispatch({"cmd": "pair.approve", "fingerprint": args.fingerprint,
                      "accept": args.action == "approve"}, args.json)


def cmd_trust(args) -> int:
    if args.action == "revoke":
        return _dispatch({"cmd": "trust.revoke", "fingerprint": args.fingerprint}, args.json)
    return _dispatch({"cmd": "trust.list"}, args.json)


def cmd_clipboard(args) -> int:
    return _dispatch({"cmd": "clipboard.push", "fingerprint": args.fingerprint}, args.json)


def cmd_send(args) -> int:
    return _dispatch({"cmd": "file.send", "fingerprint": args.fingerprint,
                      "path": str(Path(args.path).expanduser())}, args.json)


def cmd_handoff(args) -> int:
    return _dispatch({"cmd": "handoff.send", "fingerprint": args.fingerprint,
                      "url": args.url}, args.json)


def cmd_ring(args) -> int:
    return _dispatch({"cmd": "find.ring", "fingerprint": args.fingerprint,
                      "duration_s": args.duration}, args.json)


def cmd_ping(args) -> int:
    return _dispatch({"cmd": "find.ping", "fingerprint": args.fingerprint}, args.json)


def cmd_privacy(args) -> int:
    command: dict = {"cmd": "privacy.set"}
    if args.on or args.off:
        command["privacy_mode"] = bool(args.on)
    if args.clipboard:
        command["clipboard_direction"] = args.clipboard
    return _dispatch(command, args.json)


def cmd_dex(args) -> int:
    if args.action == "probe":
        command = {"cmd": "dex.probe"}
    elif args.action == "start":
        command = {"cmd": "dex.start", "mode": args.mode, "package": args.app,
                   "serial": args.serial}
    elif args.action == "status":
        command = {"cmd": "dex.status"}
    else:
        command = {"cmd": "dex.stop"}
    return _dispatch(command, args.json)


def cmd_diagnostics(args) -> int:
    payload = asyncio.run(_ipc_request({"cmd": "diagnostics.run"}, timeout=120))
    if isinstance(payload, dict) and payload.get("ok") is False:
        if args.json:
            print(json.dumps(payload, indent=2, default=str))
        else:
            print(f"error: {payload.get('code')}: {payload.get('message')}", file=sys.stderr)
        return 1
    result = payload.get("result") if isinstance(payload, dict) else payload
    if args.json:
        print(json.dumps(result, indent=2, default=str))
    else:
        print(json.dumps(result, indent=2, default=str))
        paths = (result or {}).get("paths", {})
        print("\nreports:")
        for kind, path in paths.items():
            print(f"  {kind}: {path}")
    return 0


def cmd_events(args) -> int:
    async def stream() -> None:
        reader, writer = await asyncio.open_unix_connection(str(ipc_socket_path()))
        await reader.readline()
        writer.write((json.dumps({"cmd": "events"}) + "\n").encode())
        await writer.drain()
        while True:
            line = await reader.readline()
            if not line:
                break
            print(line.decode().rstrip())

    asyncio.run(stream())
    return 0


def cmd_version(args) -> int:
    print(f"continuityd {__version__}")
    return 0


def cmd_paths(args) -> int:
    """Authoritative local paths. Shell launchers must use these instead of guessing.

    This is a separate documented schema (docs/cli-schema.md): top-level ``runtime_dir``/``ipc``/
    ``api_config`` fields, NOT the ``{ok, result}`` envelope used by IPC-backed commands.
    """
    payload = {
        "runtime_dir": str(runtime_dir()),
        "ipc": str(ipc_socket_path()),
        "api_config": str(api_config_path()),
    }
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        for key, value in payload.items():
            print(f"{key}: {value}")
    return 0


# ---------------------------------------------------------------------- parser
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="continuityctl",
                                     description="Continuity daemon and control CLI")
    parser.add_argument("--version", action="version", version=f"continuityd {__version__}")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("version").set_defaults(func=cmd_version)
    paths = sub.add_parser("paths", help="print the authoritative runtime/socket/token paths")
    paths.add_argument("--json", action="store_true")
    paths.set_defaults(func=cmd_paths)

    run = sub.add_parser("run", help="run the daemon in the foreground")
    run.set_defaults(func=cmd_run)

    for name, func, helptext in (
        ("status", cmd_status, "full daemon state"),
        ("devices", cmd_devices, "connected devices"),
        ("events", cmd_events, "stream events as JSON lines"),
    ):
        item = sub.add_parser(name, help=helptext)
        item.add_argument("--json", action="store_true")
        item.set_defaults(func=func)

    pair = sub.add_parser("pair", help="pairing flows")
    pair.add_argument("action", choices=["begin", "connect", "discover", "approve", "deny"])
    pair.add_argument("--host")
    pair.add_argument("--port", type=int)
    pair.add_argument("--fingerprint")
    pair.add_argument("--timeout", type=float, default=3.0)
    pair.add_argument("--json", action="store_true")
    pair.set_defaults(func=cmd_pair)

    trust = sub.add_parser("trust", help="trust store")
    trust.add_argument("action", choices=["list", "revoke"])
    trust.add_argument("--fingerprint")
    trust.add_argument("--json", action="store_true")
    trust.set_defaults(func=cmd_trust)

    for name, func, helptext in (
        ("push-clipboard", cmd_clipboard, "send this desktop's clipboard to the phone"),
        ("send-file", cmd_send, "send a file to the phone"),
        ("handoff", cmd_handoff, "open a URL on the phone"),
        ("ring", cmd_ring, "make the phone ring"),
        ("ping", cmd_ping, "round-trip latency to a device"),
    ):
        item = sub.add_parser(name, help=helptext)
        item.add_argument("fingerprint")
        if name == "send-file":
            item.add_argument("path")
        if name == "handoff":
            item.add_argument("url")
        if name == "ring":
            item.add_argument("--duration", type=int, default=10)
        item.add_argument("--json", action="store_true")
        item.set_defaults(func=func)

    privacy = sub.add_parser("privacy", help="pause features / change clipboard direction")
    privacy.add_argument("--on", action="store_true")
    privacy.add_argument("--off", action="store_true")
    privacy.add_argument("--clipboard", choices=["off", "to_phone", "to_desktop", "both"])
    privacy.add_argument("--json", action="store_true")
    privacy.set_defaults(func=cmd_privacy)

    dex = sub.add_parser("dex", help="DeX workspace")
    dex.add_argument("action", choices=["probe", "start", "stop", "status"])
    dex.add_argument("--mode", default="virtual_display",
                     choices=["mirror", "virtual_display", "wireless"])
    dex.add_argument("--app")
    dex.add_argument("--serial", help="ADB device serial; required when several are connected")
    dex.add_argument("--json", action="store_true")
    dex.set_defaults(func=cmd_dex)

    diag = sub.add_parser("diagnostics", help="run full diagnostics and export reports")
    diag.add_argument("--json", action="store_true")
    diag.set_defaults(func=cmd_diagnostics)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 2
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
