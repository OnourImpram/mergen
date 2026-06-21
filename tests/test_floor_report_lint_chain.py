"""End-to-end test of the floor to report to lint chain the council found broken.

Before this, verify_core hardcoded risk_level='standard', so the Governor floor never reached a
report and the unsigned-high-trust lint was structurally dead for live output. These tests prove
the chain is now connected: a done task touching a guarded surface produces a high-trust report
that requires a sign-off, the linter catches it unsigned, and the report still validates against
the schema (including the production summary fields).
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import tempfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, REPO / "scripts" / f"{name}.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


verify_core = _load("verify_core")
lint = _load("verify_report_lint")


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], stdin=subprocess.DEVNULL,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)


def test_a_guarded_path_makes_the_report_high_trust_even_when_declared_only():
    # The floor classifies over the declared task files. A task touching src/auth.py is high-trust
    # regardless of whether the file passes, so the risk tier reflects the floor, not a constant.
    state = {"feature_id": "f", "tasks": [
        {"id": "T1", "status": "done", "files": ["src/auth.py"]}]}
    report, _ = verify_core.build_report(state, Path("."))
    assert report["summary"]["risk_level"] == "high-trust"
    assert "auth-path" in report["summary"]["risk_triggers"]
    assert report["summary"]["human_review_required"] is True


def test_a_flat_sensitive_file_is_caught_not_only_a_directory():
    # The extension-stem fix: src/payments.py fires the same way src/payments/charge.py would.
    state = {"feature_id": "f", "tasks": [
        {"id": "T1", "status": "done", "files": ["src/payments.py"]}]}
    report, _ = verify_core.build_report(state, Path("."))
    assert report["summary"]["risk_level"] == "high-trust"


def test_a_benign_change_stays_standard():
    state = {"feature_id": "f", "tasks": [
        {"id": "T1", "status": "done", "files": ["docs/readme.md"]}]}
    report, _ = verify_core.build_report(state, Path("."))
    assert report["summary"]["risk_level"] == "standard"
    assert report["summary"]["risk_triggers"] == []


def test_a_high_trust_pass_is_caught_unsigned_by_the_linter():
    # The chain: a sensitive task that genuinely passes still produces a high-trust report, and
    # the linter refuses it until a human approval is recorded. This is the invariant that was
    # structurally unreachable before the floor was wired into the report.
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp).resolve()
        _git(root, "init")
        (root / "src").mkdir()
        (root / "src" / "auth.py").write_bytes(b"TOKEN = 1\n")
        _git(root, "add", "-A")
        state = {"feature_id": "f", "tasks": [
            {"id": "T1", "status": "done", "files": ["src/auth.py"]}]}
        report, overall_pass = verify_core.build_report(state, root)

    assert report["summary"]["risk_level"] == "high-trust"
    # No human_review recorded, so the linter flags the unsigned high-trust report.
    findings = lint.lint_report(report, "x")
    assert any(f.code == "UNSIGNED_HIGH_TRUST" for f in findings)


def test_a_produced_report_validates_against_the_schema():
    # The council found no test validated production output against the schema, so a summary field
    # rename or a tightening would pass silently. This closes that gap with a real round-trip.
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads(
        (REPO / "core" / "schemas" / "verification-report.schema.json").read_text(encoding="utf-8"))
    state = {"feature_id": "f", "tasks": [
        {"id": "T1", "status": "done", "files": ["src/auth.py"]}]}
    report, _ = verify_core.build_report(state, Path("."))
    # build_report omits provenance (main() adds it); validate the summary-bearing core shape.
    jsonschema.Draft202012Validator(schema).validate(report)
