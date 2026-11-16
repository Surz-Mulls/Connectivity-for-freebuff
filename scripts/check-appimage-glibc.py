#!/usr/bin/env python3
"""Measure the real glibc floor of an AppImage and enforce the documented floor.

The interpreter alone is not enough: bundled wheels and Qt libraries can require newer GLIBC_
symbols. This walks every ELF file in the extracted image, asks readelf for its version needs, and
compares the highest GLIBC_x.y with the documented floor.

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

GLIBC_RE = re.compile(r"GLIBC_(\d+)\.(\d+)")
DEFAULT_FLOOR = "2.34"


def parse_version(value: str) -> tuple[int, int]:
    match = re.fullmatch(r"(\d+)\.(\d+)", value.strip())
    if not match:
        raise SystemExit(f"invalid glibc version: {value!r}")
    return int(match.group(1)), int(match.group(2))


def is_elf(path: pathlib.Path) -> bool:
    try:
        with path.open("rb") as fh:
            return fh.read(4) == b"\x7fELF"
    except OSError:
        return False


def required_versions(path: pathlib.Path) -> set[tuple[int, int]]:
    try:
        result = subprocess.run(
            ["readelf", "--version-info", str(path)],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return set()
    return {(int(major), int(minor)) for major, minor in GLIBC_RE.findall(result.stdout)}


def scan(root: pathlib.Path) -> tuple[tuple[int, int], pathlib.Path | None, int]:
    highest = (0, 0)
    worst: pathlib.Path | None = None
    count = 0
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.is_symlink() or not is_elf(path):
            continue
        count += 1
        versions = required_versions(path)
        if not versions:
            continue
        local_high = max(versions)
        if local_high > highest:
            highest, worst = local_high, path
    return highest, worst, count


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
    parser.add_argument("--floor", default=DEFAULT_FLOOR)
    args = parser.parse_args()
    floor = parse_version(args.floor)

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
        raise SystemExit("no ELF files found; refusing to claim a glibc floor")
    if highest == (0, 0):
        raise SystemExit("no GLIBC_ version symbols found; readelf may be missing")

    measured = f"{highest[0]}.{highest[1]}"
    where = f" ({worst.relative_to(root) if worst and args.root else worst})" if worst else ""
    print(f"glibc floor: {measured} across {count} ELF files{where}")
    if highest > floor:
        print(
            f"FAIL: image requires glibc {measured}, above the documented floor "
            f"{args.floor}. Update the docs and the floor constant before shipping.",
            file=sys.stderr,
        )
        return 1
    print(f"ok: image needs glibc {measured}, documented floor {args.floor}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
