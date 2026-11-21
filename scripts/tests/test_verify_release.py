#!/usr/bin/env python3
"""Unit tests for tools/verify_release.py (no network or release assets needed)."""

from __future__ import annotations

import importlib.util
import json
import pathlib
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("verify_release", ROOT / "tools/verify_release.py")
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def main() -> int:
    for name in ("continuity.desktop", "BUILD-MANIFEST.json", "a" * 64):
        assert MODULE.safe_asset_name(name) == name
    for name in ("", ".", "..", "../escape", "/tmp/escape", "a/b", "a\\b", "x/../../y"):
        assert MODULE.safe_asset_name(name) is None, name

    with tempfile.TemporaryDirectory() as tmp:
        directory = pathlib.Path(tmp)
        sums = directory / "SHA256SUMS"
        sums.write_text(
            f"{'a' * 64}  good.bin\n{'b' * 64}  ../escape\n", encoding="utf-8"
        )
        report = MODULE.Report()
        entries = MODULE.parse_sums(sums, report)
        assert entries == {"good.bin": "a" * 64}, entries
        assert report.failures == 1, report.failures

        report = MODULE.Report()
        (directory / "VALIDATION_REPORT_one.md").write_text("a" * 64, encoding="utf-8")
        (directory / "VALIDATION_REPORT_two.md").write_text("b" * 64, encoding="utf-8")
        MODULE.check_report(directory, {"asset": "a" * 64}, report)
        assert report.warnings == 1, report.warnings

        manifest = directory / "BUILD-MANIFEST.json"
        manifest.write_text(
            json.dumps({"commit": "d" * 40, "assets": []}), encoding="utf-8"
        )
        report = MODULE.Report()
        MODULE.check_manifest(directory, "d" * 40, report)
        assert report.failures == 0, report.failures

    print("ok: unsafe names rejected, every validation report scanned, manifest commit checked once")
    return 0


if __name__ == "__main__":
    sys.exit(main())
