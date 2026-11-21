#!/usr/bin/env python3
"""Measure the real runtime symbol floors of an AppImage and enforce the documented floors.

The interpreter alone is not enough: bundled wheels and Qt libraries can require newer GLIBC,
GLIBCXX/CXXABI (libstdc++) and OPENSSL_ symbols. This walks every ELF file in the extracted image,
asks readelf for its version needs, and compares each family's highest requirement with the
documented floor.

Usage:
  scripts/check-appimage-glibc.py IMAGE.AppImage [--floor 2.34]
  scripts/check-appimage-glibc.py --root AppDir [--floor 2.34]
"""

from __future__ import annotations

import argparse
import os
import pathlib
import re
import subprocess
import sys
import tempfile

FAMILIES = ("glibc", "glibcxx", "cxxabi", "openssl")
LABELS = {"glibc": "glibc", "glibcxx": "GLIBCXX", "cxxabi": "CXXABI", "openssl": "OPENSSL"}
PATTERNS = {
    "glibc": re.compile(r"\bGLIBC_(\d+)\.(\d+)\b"),
    "glibcxx": re.compile(r"\bGLIBCXX_(\d+)\.(\d+)(?:\.(\d+))?\b"),
    "cxxabi": re.compile(r"\bCXXABI_(\d+)\.(\d+)(?:\.(\d+))?\b"),
    "openssl": re.compile(r"\bOPENSSL_(\d+)\.(\d+)(?:\.(\d+))?\b"),
}
DEFAULT_FLOORS = {
    "glibc": "2.34",
    "glibcxx": "3.4.29",
    "cxxabi": "1.3.13",
    # No OPENSSL_ symbols are bundled today; if a future build adds libssl, this is the floor.
    "openssl": "3.0.0",
}
Version = tuple[int, int, int]


def parse_version(value: str, family: str = "glibc") -> Version:
    if family not in FAMILIES:
        raise SystemExit(f"unknown symbol family: {family!r}")
    parts = value.strip().split(".")
    if len(parts) not in (2, 3) or any(not part.isdigit() for part in parts):
        raise SystemExit(f"invalid {LABELS[family]} version: {value!r}")
    numbers = [int(part) for part in parts]
    return (numbers[0], numbers[1], numbers[2] if len(numbers) == 3 else 0)


def format_version(value: Version, family: str) -> str:
    if family == "glibc" or value[2] == 0:
        return f"{value[0]}.{value[1]}"
    return f"{value[0]}.{value[1]}.{value[2]}"


def version_needs(readelf_output: str) -> dict[str, set[Version]]:
    """Extract versioned symbol requirements from ``readelf --version-info`` output."""
    needs: dict[str, set[Version]] = {family: set() for family in FAMILIES}
    for family, pattern in PATTERNS.items():
        for match in pattern.finditer(readelf_output):
            groups = match.groups()
            major, minor = groups[0], groups[1]
            patch = groups[2] if len(groups) > 2 else None
            needs[family].add((int(major), int(minor), int(patch or 0)))
    return {family: versions for family, versions in needs.items() if versions}


def is_elf(path: pathlib.Path) -> bool:
    try:
        with path.open("rb") as fh:
            return fh.read(4) == b"\x7fELF"
    except OSError:
        return False


def required_versions(path: pathlib.Path) -> dict[str, set[Version]]:
    try:
        result = subprocess.run(
            ["readelf", "--version-info", str(path)],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return {}
    return version_needs(result.stdout)


def scan(root: pathlib.Path) -> tuple[dict[str, Version], dict[str, pathlib.Path], int]:
    highest: dict[str, Version] = {family: (0, 0, 0) for family in FAMILIES}
    worst: dict[str, pathlib.Path] = {}
    count = 0
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.is_symlink() or not is_elf(path):
            continue
        count += 1
        needs = required_versions(path)
        for family, versions in needs.items():
            local_high = max(versions)
            if local_high > highest[family]:
                highest[family] = local_high
                worst[family] = path
    return highest, worst, count


def floor_failures(highest: dict[str, Version],
                   floors: dict[str, Version]) -> list[tuple[str, Version, Version]]:
    failures = []
    for family in FAMILIES:
        measured = highest.get(family, (0, 0, 0))
        if measured == (0, 0, 0):
            continue
        if measured > floors[family]:
            failures.append((family, measured, floors[family]))
    return failures


def extract(image: pathlib.Path, workdir: pathlib.Path) -> pathlib.Path:
    env = dict(os.environ, APPIMAGE_EXTRACT_AND_RUN="1")
    subprocess.run(
        [str(image), "--appimage-extract"],
        cwd=workdir,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        check=True,
        timeout=180,
    )
    root = workdir / "squashfs-root"
    if not root.is_dir():
        raise SystemExit(f"{image} did not extract to squashfs-root")
    return root


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("image", nargs="?", type=pathlib.Path)
    parser.add_argument("--root", type=pathlib.Path)
    parser.add_argument("--floor", default=DEFAULT_FLOORS["glibc"],
                        help="documented glibc floor (default: 2.34)")
    parser.add_argument("--glibcxx-floor", default=DEFAULT_FLOORS["glibcxx"])
    parser.add_argument("--cxxabi-floor", default=DEFAULT_FLOORS["cxxabi"])
    parser.add_argument("--openssl-floor", default=DEFAULT_FLOORS["openssl"])
    args = parser.parse_args()
    floors = {
        "glibc": parse_version(args.floor, "glibc"),
        "glibcxx": parse_version(args.glibcxx_floor, "glibcxx"),
        "cxxabi": parse_version(args.cxxabi_floor, "cxxabi"),
        "openssl": parse_version(args.openssl_floor, "openssl"),
    }

    if bool(args.image) == bool(args.root):
        raise SystemExit("provide exactly one of IMAGE.AppImage or --root DIR")

    if args.root:
        root = args.root.resolve()
        if not root.is_dir():
            raise SystemExit(f"not a directory: {root}")
        highest, worst, count = scan(root)
    else:
        image = args.image.resolve()
        if not image.is_file():
            raise SystemExit(f"not a file: {image}")
        with tempfile.TemporaryDirectory(prefix="continuity-glibc-") as tmp:
            root = extract(image, pathlib.Path(tmp))
            highest, worst, count = scan(root)

    if count == 0:
        raise SystemExit("no ELF files found; refusing to claim a symbol floor")
    if highest["glibc"] == (0, 0, 0):
        raise SystemExit("no GLIBC_ version symbols found; readelf may be missing")

    for family in FAMILIES:
        measured = highest[family]
        label = LABELS[family]
        if measured == (0, 0, 0):
            print(f"{label}: not present in this image")
            continue
        where = worst.get(family)
        location = f" ({where.relative_to(root) if where and args.root else where})" if where else ""
        print(f"{label} floor: {format_version(measured, family)} across {count} ELF files{location}")

    failures = floor_failures(highest, floors)
    if failures:
        detail = "; ".join(
            f"{LABELS[family]} {format_version(measured, family)} > "
            f"documented {format_version(floor, family)}"
            for family, measured, floor in failures
        )
        print(
            f"FAIL: image exceeds the documented floor(s): {detail}. "
            "Update the docs and the floor constants before shipping.",
            file=sys.stderr,
        )
        return 1

    summary = ", ".join(
        f"{LABELS[family]} {format_version(highest[family], family)}"
        for family in FAMILIES if highest[family] != (0, 0, 0)
    )
    print(f"ok: image needs {summary}; all documented floors hold")
    return 0


if __name__ == "__main__":
    sys.exit(main())
