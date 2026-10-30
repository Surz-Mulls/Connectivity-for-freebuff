"""Diagnostics must be structured, redacted and exported in both formats."""

from __future__ import annotations

import json
from pathlib import Path

from continuityd.config import Settings
from continuityd.core import DeviceManager
from continuityd.diagnostics import DiagnosticsRunner, export
from continuityd.identity import Identity
from continuityd.trust import TrustStore


def build_manager(tmp_path: Path) -> DeviceManager:
    settings = Settings.load(tmp_path / "settings.json")
    identity = Identity.load_or_create(tmp_path / "identity", "diag-desktop")
    trust = TrustStore.load(tmp_path / "trust.json")
    return DeviceManager(settings, identity, trust)


def test_report_has_required_sections(tmp_path):
    manager = build_manager(tmp_path)
    report = manager.diagnostics.run()
    ids = {check.id for check in report.checks}
    for required in ("env.os", "env.python", "build.version", "identity.present", "trust.store",
                     "transport.tls", "discovery.available", "clipboard.backend", "dex.tools",
                     "android.app", "security.listeners", "android.privileged"):
        assert required in ids, required
    assert report.summary["pass"] >= 4
    # Android cannot be verified from a cloud host: it must be blocked, never "pass"
    assert next(c for c in report.checks if c.id == "android.app").status == "blocked"
    json.dumps(report.to_dict())  # must be JSON-serialisable


def test_report_redacts_home_paths(tmp_path):
    manager = build_manager(tmp_path)
    report = manager.diagnostics.run()
    text = json.dumps(report.to_dict())
    assert str(Path.home()) not in text


def test_export_writes_json_and_markdown(tmp_path):
    manager = build_manager(tmp_path)
    report = manager.diagnostics.run()
    paths = export(report, tmp_path / "reports")
    assert Path(paths["json"]).exists() and Path(paths["markdown"]).exists()
    payload = json.loads(Path(paths["json"]).read_text())
    assert payload["schema"] == "continuity.diagnostics/1"
    markdown = Path(paths["markdown"]).read_text()
    assert "# Continuity diagnostics" in markdown
    assert "android.app" in markdown


def test_diagnostics_never_claim_verified_android(tmp_path):
    settings = Settings.load(tmp_path / "settings.json")
    runner = DiagnosticsRunner(settings=settings)
    report = runner.run()
    android = next(c for c in report.checks if c.id == "android.app")
    assert android.status == "blocked"
    assert "no device" in android.detail.lower()
