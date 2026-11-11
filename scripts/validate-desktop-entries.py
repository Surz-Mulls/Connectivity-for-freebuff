#!/usr/bin/env python3
"""Validate the desktop entries this project ships.

Application entries are checked against the freedesktop rules that
`desktop-file-validate` enforces in CI (exactly one main category, no duplicate
categories, required keys). The Dolphin file is a KDE service menu, not an
application entry: `desktop-file-validate` rejects Type=Service outright, so it
is validated with the rules that actually apply to KDE service menus.

Usage: scripts/validate-desktop-entries.py [REPO_ROOT]
"""
from __future__ import annotations

import configparser
import pathlib
import sys

# https://specifications.freedesktop.org/menu-spec/latest/apa.html
MAIN_CATEGORIES = {
    "AudioVideo", "Audio", "Video", "Development", "Education", "Game",
    "Graphics", "Network", "Office", "Science", "Settings", "System", "Utility",
}


def parse(path: pathlib.Path) -> configparser.ConfigParser:
    cp = configparser.ConfigParser(interpolation=None, strict=False, delimiters=("=",))
    cp.optionxform = str  # keep key case; KDE/service keys are case-sensitive
    with path.open(encoding="utf-8") as fh:
        cp.read_file(fh)
    return cp


def validate_application(path: pathlib.Path) -> None:
    cp = parse(path)
    if "Desktop Entry" not in cp:
        raise SystemExit(f"{path}: missing [Desktop Entry] section")
    entry = cp["Desktop Entry"]
    if entry.get("Type") != "Application":
        raise SystemExit(f"{path}: Type must be Application, got {entry.get('Type')!r}")
    for key in ("Name", "Comment", "Exec", "Icon"):
        if not entry.get(key, "").strip():
            raise SystemExit(f"{path}: missing required key {key}")
    if entry.get("Terminal", "false") not in {"true", "false"}:
        raise SystemExit(f"{path}: Terminal must be true or false")
    raw = entry.get("Categories", "")
    categories = [c for c in raw.split(";") if c]
    if not categories:
        raise SystemExit(f"{path}: Categories is empty")
    if len(categories) != len(set(categories)):
        raise SystemExit(f"{path}: duplicate categories in {raw!r}")
    main = [c for c in categories if c in MAIN_CATEGORIES]
    if len(main) != 1:
        raise SystemExit(
            f"{path}: Categories={raw!r} must contain exactly one main category, found {main}"
        )
    # FileTransfer is an additional category and is valid next to Network as the main one.
    if "FileTransfer" not in categories:
        raise SystemExit(f"{path}: Categories={raw!r} should list the FileTransfer category")
    print(f"ok application entry: {path} (Categories={raw})")


def validate_kde_service(path: pathlib.Path) -> None:
    cp = parse(path)
    if "Desktop Entry" not in cp:
        raise SystemExit(f"{path}: missing [Desktop Entry] section")
    entry = cp["Desktop Entry"]
    problems = []
    if entry.get("Type") != "Service":
        problems.append(f"Type must be Service, got {entry.get('Type')!r}")
    if "KonqPopupMenu/Plugin" not in entry.get("ServiceTypes", ""):
        problems.append("ServiceTypes must include KonqPopupMenu/Plugin")
    actions = [a for a in entry.get("Actions", "").split(";") if a]
    if not actions:
        problems.append("Actions is empty")
    for action in actions:
        section = f"Desktop Action {action}"
        if section not in cp:
            problems.append(f"missing section [{section}]")
            continue
        action_exec = cp[section].get("Exec", "")
        if not action_exec.strip():
            problems.append(f"[{section}] has no Exec")
        if "%F" not in action_exec:
            problems.append(f"[{section}] Exec must pass selected files with %F")
        if "@HELPER@" not in action_exec:
            problems.append(
                f"[{section}] Exec must keep the @HELPER@ placeholder substituted by install.sh"
            )
        if not cp[section].get("Name", "").strip():
            problems.append(f"[{section}] has no Name")
    if problems:
        raise SystemExit(f"{path}: " + "; ".join(problems))
    print(f"ok KDE service entry: {path} (actions={','.join(actions)})")


def main() -> int:
    root = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    validate_application(root / "packaging/continuity.desktop")
    validate_kde_service(root / "integrations/dolphin/continuity-send.desktop")
    return 0


if __name__ == "__main__":
    sys.exit(main())
