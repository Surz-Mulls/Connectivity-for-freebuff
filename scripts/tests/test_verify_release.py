#!/usr/bin/env python3
"""Unit tests for tools/verify_release.py (no network or release assets needed)."""

from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import json
import pathlib
import sys
import tempfile
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("verify_release", ROOT / "tools/verify_release.py")
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _digest(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    # ---------------------------------------------------------------- unsafe names
    for name in ("continuity.desktop", "BUILD-MANIFEST.json", "a" * 64):
        assert MODULE.safe_asset_name(name) == name
    for name in ("", ".", "..", "../escape", "/tmp/escape", "a/b", "a\\b", "x/../../y",
                 "\x00name"):
        assert MODULE.safe_asset_name(name) is None, name
    print("  ok: unsafe asset names are rejected before any path join")

    # ---------------------------------------------------------------- duplicate SHA256SUMS entries
    with tempfile.TemporaryDirectory() as tmp:
        directory = pathlib.Path(tmp)
        sums = directory / "SHA256SUMS"
        sums.write_text(
            f"{'a' * 64}  dup.bin\n{'b' * 64}  dup.bin\n", encoding="utf-8"
        )
        report = MODULE.Report()
        entries = MODULE.parse_sums(sums, report)
        assert entries == {"dup.bin": "a" * 64}, entries  # first wins, no silent overwrite
        assert report.failures == 1, report.failures
        print("  ok: a duplicate SHA256SUMS entry is a FAIL, not a dict overwrite")

    # ---------------------------------------------------------------- checksum fixtures
    with tempfile.TemporaryDirectory() as tmp:
        directory = pathlib.Path(tmp)
        listed = directory / "listed.bin"
        listed.write_bytes(b"listed payload")
        extra = directory / "extra.bin"
        extra.write_bytes(b"extra payload")
        sums = directory / "SHA256SUMS"
        sums.write_text(f"{_digest(listed)}  listed.bin\n", encoding="utf-8")
        report = MODULE.Report()
        entries, files = MODULE.check_sums(directory, report)
        assert entries == {"listed.bin": _digest(listed)}, entries
        assert report.failures == 0, report.failures
        assert report.warnings == 1, report.warnings  # extra.bin unlisted
        print("  ok: an extra unlisted file is a WARN, never a silent pass")

        sums.write_text(f"{'c' * 64}  listed.bin\n", encoding="utf-8")
        report = MODULE.Report()
        MODULE.check_sums(directory, report)
        assert report.failures == 1, report.failures
        print("  ok: a checksum mismatch is a FAIL")

        sums.write_text(f"{'a' * 64}  missing.bin\n", encoding="utf-8")
        report = MODULE.Report()
        MODULE.check_sums(directory, report)
        assert report.failures == 1, report.failures
        print("  ok: a listed-but-missing file is a FAIL")

    # ---------------------------------------------------------------- manifest checks
    with tempfile.TemporaryDirectory() as tmp:
        directory = pathlib.Path(tmp)
        manifest = directory / "BUILD-MANIFEST.json"
        manifest.write_text("{not valid json", encoding="utf-8")
        report = MODULE.Report()
        MODULE.check_manifest(directory, None, report)
        assert report.failures == 1, report.failures
        print("  ok: malformed manifest JSON is a FAIL")

        manifest.write_text(json.dumps({"commit": "a" * 40, "assets": []}), encoding="utf-8")
        report = MODULE.Report()
        MODULE.check_manifest(directory, "b" * 40, report)
        assert report.failures == 1, report.failures
        print("  ok: a manifest commit mismatch is a FAIL")

        report = MODULE.Report()
        MODULE.check_manifest(directory, "a" * 40, report)
        assert report.failures == 0, report.failures
        print("  ok: a matching manifest commit passes")

    # ---------------------------------------------------------------- duplicate release assets
    with tempfile.TemporaryDirectory() as tmp:
        directory = pathlib.Path(tmp)
        assets = [
            {"name": "same.bin", "browser_download_url": "https://example.invalid/1"},
            {"name": "same.bin", "browser_download_url": "https://example.invalid/2"},
        ]
        downloads: list[str] = []
        with mock.patch.object(MODULE, "api_json", return_value={"assets": assets}), \
                mock.patch.object(MODULE, "download",
                                  side_effect=lambda url, dest: downloads.append(dest.name)):
            report = MODULE.Report()
            ok = MODULE.download_release("v-test", directory, report)
        assert ok is False
        assert report.failures == 1, report.failures
        assert downloads == [], downloads  # nothing was overwritten or partially downloaded
        print("  ok: duplicate release asset names fail before the first download")

        assets = [{"name": "one.bin", "browser_download_url": "https://example.invalid/1"},
                  {"name": "two.bin", "browser_download_url": "https://example.invalid/2"}]
        with mock.patch.object(MODULE, "api_json", return_value={"assets": assets}), \
                mock.patch.object(MODULE, "download",
                                  side_effect=lambda url, dest: downloads.append(dest.name)):
            report = MODULE.Report()
            assert MODULE.download_release("v-test", directory, report) is True
        assert downloads == ["one.bin", "two.bin"], downloads
        assert report.failures == 0, report.failures
        print("  ok: distinct asset names still download normally")

    # ---------------------------------------------------------------- every validation report
    with tempfile.TemporaryDirectory() as tmp:
        directory = pathlib.Path(tmp)
        (directory / "VALIDATION_REPORT_one.md").write_text("a" * 64, encoding="utf-8")
        (directory / "VALIDATION_REPORT_two.md").write_text("b" * 64, encoding="utf-8")
        report = MODULE.Report()
        MODULE.check_report(directory, {"asset": "a" * 64}, report)
        assert report.warnings == 1, report.warnings
        print("  ok: every validation report is scanned, not just the first")

    # ---------------------------------------- a duplicate-SHA256SUMS fixture makes main exit 1
    with tempfile.TemporaryDirectory() as tmp:
        directory = pathlib.Path(tmp)
        (directory / "dup.bin").write_bytes(b"payload")
        (directory / "SHA256SUMS").write_text(
            f"{'a' * 64}  dup.bin\n{'b' * 64}  dup.bin\n", encoding="utf-8"
        )
        (directory / "BUILD-MANIFEST.json").write_text(
            json.dumps({"assets": []}), encoding="utf-8"
        )
        argv = ["verify_release.py", "--local", str(directory)]
        output = io.StringIO()
        with mock.patch.object(sys, "argv", argv), contextlib.redirect_stdout(output):
            code = MODULE.main()
        assert code == 1, code
        assert "duplicate entry for 'dup.bin'" in output.getvalue(), output.getvalue()
        print("  ok: verify_release.main() exits 1 on the duplicate-SHA256SUMS fixture")

    print("ok: duplicate assets/entries rejected; missing, extra, traversal and manifest failures covered")
    return 0


if __name__ == "__main__":
    sys.exit(main())
