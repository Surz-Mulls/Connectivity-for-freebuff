#!/usr/bin/env python3
"""Measure the real runtime symbol floors of an AppImage and enforce the documented floors.

The interpreter alone is not enough: bundled wheels and Qt libraries can require newer GLIBC,
GLIBCXX/CXXABI (libstdc++) and OPENSSL_ symbols. This walks every ELF file in the extracted image,
asks readelf for its version needs, and compares each family's highest requirement with the
documented floor.

Inspection is fail-closed per file. A file that cannot be read by readelf (missing binary, timeout,
non-zero exit, empty or unparseable output) is reported as FAIL with its path and reason, and the
scan exits non-zero. Only files that were fully inspected contribute to the measured floors.

An empty version-info output is not automatically a failure: it is accepted only when `readelf -S`
shows no `.gnu.version*` section, i.e. the file provably has no versioned symbol requirements. If
such a section exists but no version info could be parsed, the file is a FAIL, not a clean file.

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
from dataclasses import dataclass, field

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
READELF_TIMEOUT = 30
Version = tuple[int, int, int]

_NEEDS_HEADER = re.compile(r"^\s*Version needs section .* contains (\d+) entries")
_SECTION_HEADER = re.compile(r"^\s*Version (?:needs|definition) section")
_NAME_LINE = re.compile(r"^\s*0x[0-9a-fA-F]+:\s+Name:\s+\S+")


class InspectionError(Exception):
    """A valid ELF file exists but its version requirements could not be fully inspected."""


@dataclass
class ScanResult:
    highest: dict[str, Version] = field(
        default_factory=lambda: {family: (0, 0, 0) for family in FAMILIES}
    )
    worst: dict[str, pathlib.Path] = field(default_factory=dict)
    inspected: int = 0
    failures: list[tuple[pathlib.Path, str]] = field(default_factory=list)

    @property
    def count(self) -> int:
        return self.inspected + len(self.failures)


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


def _needs_entry_counts(readelf_output: str) -> tuple[int, int]:
    """(declared needs entries, parseable ``Name:`` lines inside needs sections)."""
    declared = 0
    named = 0
    in_needs = False
    for line in readelf_output.splitlines():
        header = _NEEDS_HEADER.match(line)
        if header:
            declared += int(header.group(1))
            in_needs = True
            continue
        if _SECTION_HEADER.match(line):
            in_needs = False
            continue
        if in_needs and _NAME_LINE.match(line):
            named += 1
    return declared, named


def is_elf(path: pathlib.Path) -> bool:
    try:
        with path.open("rb") as fh:
            return fh.read(4) == b"\x7fELF"
    except OSError:
        return False


def _readelf(path: pathlib.Path, option: str) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            ["readelf", option, str(path)],
            capture_output=True,
            text=True,
            timeout=READELF_TIMEOUT,
            check=False,
        )
    except FileNotFoundError as exc:
        raise InspectionError("readelf is not installed or not on PATH") from exc
    except subprocess.TimeoutExpired as exc:
        raise InspectionError(f"readelf {option} timed out after {READELF_TIMEOUT} s") from exc
    except OSError as exc:
        raise InspectionError(f"readelf {option} could not run: {exc}") from exc


def _stderr_detail(result: subprocess.CompletedProcess) -> str:
    lines = (result.stderr or result.stdout or "").strip().splitlines()
    return lines[-1][:200] if lines else "no output"


def _has_version_sections(path: pathlib.Path) -> bool:
    result = _readelf(path, "-S")
    if result.returncode != 0:
        raise InspectionError(f"readelf -S exited {result.returncode}: {_stderr_detail(result)}")
    return ".gnu.version" in (result.stdout or "")


def inspect_required_versions(path: pathlib.Path) -> dict[str, set[Version]]:
    """Return this ELF's version needs, or raise :class:`InspectionError` if it is not fully known."""
    result = _readelf(path, "--version-info")
    if result.returncode != 0:
        raise InspectionError(
            f"readelf --version-info exited {result.returncode}: {_stderr_detail(result)}"
        )
    output = result.stdout or ""
    if not output.strip():
        if not _has_version_sections(path):
            # No .gnu.version* section: this file provably has no versioned requirements.
            return {}
        raise InspectionError(
            "readelf printed no version-info for a file that has .gnu.version* sections"
        )
    if "No version information found" in output:
        return {}
    if "Version needs section" not in output and "Version definition section" not in output:
        raise InspectionError("readelf output has no recognizable version-info structure")
    declared, named = _needs_entry_counts(output)
    if declared > named:
        raise InspectionError(
            f"readelf declared {declared} version needs but only {named} Name: entries parsed"
        )
    return version_needs(output)


def scan(root: pathlib.Path) -> ScanResult:
    result = ScanResult()
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.is_symlink() or not is_elf(path):
            continue
        try:
            needs = inspect_required_versions(path)
        except InspectionError as exc:
            result.failures.append((path, str(exc)))
            continue
        result.inspected += 1
        for family, versions in needs.items():
            local_high = max(versions)
            if local_high > result.highest[family]:
                result.highest[family] = local_high
                result.worst[family] = path
    return result


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


def _display(path: pathlib.Path, root: pathlib.Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


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
        result = scan(root)
    else:
        image = args.image.resolve()
        if not image.is_file():
            raise SystemExit(f"not a file: {image}")
        with tempfile.TemporaryDirectory(prefix="continuity-glibc-") as tmp:
            root = extract(image, pathlib.Path(tmp))
            result = scan(root)

    if result.count == 0:
        raise SystemExit("no ELF files found; refusing to claim a symbol floor")

    for family in FAMILIES:
        measured = result.highest[family]
        label = LABELS[family]
        if measured == (0, 0, 0):
            print(f"{label}: not present in this image")
            continue
        where = result.worst.get(family)
        location = f" ({_display(where, root)})" if where else ""
        print(
            f"{label} floor: {format_version(measured, family)} across "
            f"{result.inspected} inspected ELF files{location}"
        )

    if result.failures:
        for path, reason in result.failures:
            print(f"FAIL: could not inspect {_display(path, root)}: {reason}", file=sys.stderr)
        print(
            f"FAIL: {len(result.failures)} of {result.count} ELF files could not be fully "
            "inspected; refusing to claim a symbol floor",
            file=sys.stderr,
        )
        return 1

    if result.highest["glibc"] == (0, 0, 0):
        raise SystemExit("no GLIBC_ version symbols found; readelf may be missing")

    failures = floor_failures(result.highest, floors)
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
        f"{LABELS[family]} {format_version(result.highest[family], family)}"
        for family in FAMILIES if result.highest[family] != (0, 0, 0)
    )
    print(f"ok: image needs {summary}; all documented floors hold")
    return 0


if __name__ == "__main__":
    sys.exit(main())
