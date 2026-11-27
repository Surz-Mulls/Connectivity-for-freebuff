#!/usr/bin/env python3
"""Unit tests for the AppImage symbol-floor scanner (no AppImage needed).

Every readelf failure mode is mocked so the fail-closed behaviour is proven without a broken
toolchain: missing binary, timeout, non-zero exit, empty output, unparseable output, and a
multi-file scan where only the readable file contributes a floor.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import pathlib
import subprocess
import sys
import tempfile
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "check_appimage_glibc", ROOT / "scripts/check-appimage-glibc.py"
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE  # dataclasses resolves its module through sys.modules
SPEC.loader.exec_module(MODULE)

READELF_FIXTURE = """
Version needs section '.gnu.version_r' contains 4 entries:
  0x0010: Name: GLIBC_2.34 Flags: none Version: 6
  0x0020: Name: GLIBCXX_3.4.29 Flags: none Version: 9
  0x0030: Name: CXXABI_1.3.13 Flags: none Version: 8
  0x0040: Name: OPENSSL_3.0.0 Flags: none Version: 7
"""

SECTIONS_WITHOUT_VERSIONING = """
There are 30 section headers, starting at offset 0x1234:
  [ 1] .interp PROGBITS 0000000000000318 000318 00001c 00 A 0 0 1
  [12] .text PROGBITS 0000000000001000 001000 000123 00 AX 0 0 16
"""

SECTIONS_WITH_VERSIONING = SECTIONS_WITHOUT_VERSIONING + "  [26] .gnu.version_r VERSYM\n"


def _completed(stdout: str = "", returncode: int = 0, stderr: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=["readelf"], returncode=returncode,
                                       stdout=stdout, stderr=stderr)


def _elf(path: pathlib.Path) -> pathlib.Path:
    path.write_bytes(b"\x7fELF" + b"\x00" * 60)
    return path


def _inspect_error(path: pathlib.Path, *results) -> str:
    with mock.patch.object(MODULE.subprocess, "run", side_effect=list(results)):
        try:
            MODULE.inspect_required_versions(path)
        except MODULE.InspectionError as exc:
            return str(exc)
    raise AssertionError(f"expected InspectionError for {path}")


def main() -> int:
    # ---------------------------------------------------------------- parsing (unchanged contract)
    needs = MODULE.version_needs(READELF_FIXTURE)
    assert needs["glibc"] == {(2, 34, 0)}, needs
    assert needs["glibcxx"] == {(3, 4, 29)}, needs
    assert needs["cxxabi"] == {(1, 3, 13)}, needs
    assert needs["openssl"] == {(3, 0, 0)}, needs
    assert (3, 4, 29) not in needs["glibc"]  # GLIBCXX_ must not be mistaken for GLIBC_

    floors = {
        "glibc": MODULE.parse_version("2.34", "glibc"),
        "glibcxx": MODULE.parse_version("3.4.20", "glibcxx"),
        "cxxabi": MODULE.parse_version("1.3.13", "cxxabi"),
        "openssl": MODULE.parse_version("3.0.0", "openssl"),
    }
    highest = {family: max(versions) for family, versions in needs.items()}
    assert MODULE.floor_failures(highest, floors) == [("glibcxx", (3, 4, 29), (3, 4, 20))]
    passed = dict(floors)
    passed["glibcxx"] = MODULE.parse_version("3.4.29", "glibcxx")
    assert MODULE.floor_failures(highest, passed) == []
    assert MODULE.format_version((3, 4, 29), "glibcxx") == "3.4.29"
    assert MODULE.format_version((2, 34, 0), "glibc") == "2.34"
    print("  ok: all four families parsed; GLIBCXX_3.4.29 breaches a 3.4.20 floor")

    with tempfile.TemporaryDirectory() as tmp:
        directory = pathlib.Path(tmp)
        elf = _elf(directory / "libexample.so")

        # ------------------------------------------------------------ clean inspection
        parsed = None
        with mock.patch.object(MODULE.subprocess, "run",
                               side_effect=[_completed(READELF_FIXTURE)]):
            parsed = MODULE.inspect_required_versions(elf)
        assert parsed == needs, parsed
        print("  ok: a clean readelf run yields the parsed version needs")

        # ------------------------------------------------------------ missing readelf
        reason = _inspect_error(elf, FileNotFoundError("readelf"))
        assert "readelf" in reason.lower() and "not installed" in reason.lower(), reason
        print("  ok: missing readelf fails with a path-level reason")

        # ------------------------------------------------------------ timeout
        reason = _inspect_error(elf, subprocess.TimeoutExpired(["readelf"], 30))
        assert "timed out" in reason, reason
        print("  ok: a readelf timeout fails instead of returning {}")

        # ------------------------------------------------------------ non-zero exit
        reason = _inspect_error(elf, _completed("", 1, "readelf: Error: not an ELF file"))
        assert "exited 1" in reason and "not an ELF file" in reason, reason
        print("  ok: a non-zero readelf exit fails with stderr detail")

        # ---------------------------------------- empty output with no version sections is clean
        with mock.patch.object(MODULE.subprocess, "run",
                               side_effect=[_completed(""), _completed(SECTIONS_WITHOUT_VERSIONING)]):
            assert MODULE.inspect_required_versions(elf) == {}
        print("  ok: empty output is clean only when no .gnu.version* section exists")

        # ---------------------------------------- empty output with version sections is a failure
        reason = _inspect_error(elf, _completed(""), _completed(SECTIONS_WITH_VERSIONING))
        assert "no version-info" in reason and ".gnu.version" in reason, reason
        print("  ok: empty output with .gnu.version* sections fails closed")

        # ------------------------------------------------------------ unparseable output
        reason = _inspect_error(elf, _completed("garbage that readelf would never print\n"))
        assert "no recognizable version-info" in reason, reason
        print("  ok: non-version-info output fails closed")

        # ------------------------------------------------------------ declared but unparsed needs
        declared = ("Version needs section '.gnu.version_r' contains 2 entries:\n"
                    " Addr: 0x0000  Offset: 0x0000  Link: 6 (.dynstr)\n")
        reason = _inspect_error(elf, _completed(declared))
        assert "declared 2 version needs" in reason and "0 Name: entries" in reason, reason
        print("  ok: a needs section whose entries do not parse fails closed")

        # ------------------------------------------------------------ multi-file partial failure
        scan_root = directory / "scan"
        scan_root.mkdir()
        good = _elf(scan_root / "good.bin")
        bad = _elf(scan_root / "bad.bin")
        calls = []

        def fake_run(command, **kwargs):
            path = pathlib.Path(command[-1])
            calls.append((path.name, command[1]))
            if path.name == "bad.bin":
                return _completed("", 1, "readelf: Error: cannot read")
            return _completed(READELF_FIXTURE)

        with mock.patch.object(MODULE.subprocess, "run", side_effect=fake_run):
            result = MODULE.scan(scan_root)
        assert result.count == 2, result
        assert result.inspected == 1, result
        assert [path.name for path, _ in result.failures] == ["bad.bin"], result.failures
        assert result.highest["glibc"] == (2, 34, 0), result.highest
        assert result.highest["glibcxx"] == (3, 4, 29), result.highest
        assert calls, calls
        print("  ok: only the fully inspected file contributes to the measured floors")

        # ------------------------------------------------------------ unreadable fixture -> main fails
        unreadable = directory / "unreadable.so"
        _elf(unreadable)
        argv = ["check-appimage-glibc.py", "--root", str(directory)]
        stderr = io.StringIO()
        with mock.patch.object(MODULE.subprocess, "run", side_effect=FileNotFoundError("readelf")), \
                mock.patch.object(sys, "argv", argv), \
                contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(stderr):
            code = MODULE.main()
        assert code == 1, code
        assert "FAIL: could not inspect" in stderr.getvalue(), stderr.getvalue()
        assert "unreadable.so" in stderr.getvalue(), stderr.getvalue()
        print("  ok: an unreadable-file fixture makes the scanner exit 1 with its path")

    print("ok: fail-closed per-file inspection covers every readelf failure mode")
    return 0


if __name__ == "__main__":
    sys.exit(main())
