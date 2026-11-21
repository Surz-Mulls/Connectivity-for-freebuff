#!/usr/bin/env python3
"""Unit tests for the AppImage symbol-floor scanner (no AppImage needed)."""

from __future__ import annotations

import importlib.util
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "check_appimage_glibc", ROOT / "scripts/check-appimage-glibc.py"
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

READELF_FIXTURE = """
Version needs section '.gnu.version_r' contains 4 entries:
  0x0010: Name: GLIBC_2.34 Flags: none Version: 6
  0x0020: Name: GLIBCXX_3.4.29 Flags: none Version: 9
  0x0030: Name: CXXABI_1.3.13 Flags: none Version: 8
  0x0040: Name: OPENSSL_3.0.0 Flags: none Version: 7
"""


def main() -> int:
    needs = MODULE.version_needs(READELF_FIXTURE)
    assert needs["glibc"] == {(2, 34, 0)}, needs
    assert needs["glibcxx"] == {(3, 4, 29)}, needs
    assert needs["cxxabi"] == {(1, 3, 13)}, needs
    assert needs["openssl"] == {(3, 0, 0)}, needs

    # GLIBCXX_ must not be mistaken for GLIBC_.
    assert (3, 4, 29) not in needs["glibc"]

    floors = {
        "glibc": MODULE.parse_version("2.34", "glibc"),
        "glibcxx": MODULE.parse_version("3.4.20", "glibcxx"),
        "cxxabi": MODULE.parse_version("1.3.13", "cxxabi"),
        "openssl": MODULE.parse_version("3.0.0", "openssl"),
    }
    highest = {family: max(versions) for family, versions in needs.items()}
    failures = MODULE.floor_failures(highest, floors)
    assert failures == [("glibcxx", (3, 4, 29), (3, 4, 20))], failures

    passed = dict(floors)
    passed["glibcxx"] = MODULE.parse_version("3.4.29", "glibcxx")
    assert MODULE.floor_failures(highest, passed) == []

    assert MODULE.format_version((3, 4, 29), "glibcxx") == "3.4.29"
    assert MODULE.format_version((2, 34, 0), "glibc") == "2.34"
    print("ok: GLIBCXX_3.4.29 detected above a 3.4.20 floor; all four families parsed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
