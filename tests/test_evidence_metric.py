"""Tests for the eval evidence metric (eval/evidence_metric.py): the work-done
rate, phantom-completion detection, and the pass/fail gate with its thresholds.

Loaded by file path because eval/ is not an importable package.
"""

import importlib.util
import json
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def _load(rel_path: str):
    path = REPO / rel_path
    spec = importlib.util.spec_from_file_location(path.stem.replace("-", "_"), path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_evidence_metric_work_done(capsys):
    metric = _load("eval/evidence_metric.py")
    rc = metric.main([str(REPO / "eval" / "sample" / "verification-report.json")])
    out = capsys.readouterr().out
    assert rc == 0
    assert "work-done rate:      0.67" in out
    assert "phantom completions: 1" in out
    assert "abstaining on minimal-change" in out


def test_evidence_metric_gate_fails_on_phantom(capsys):
    metric = _load("eval/evidence_metric.py")
    sample = str(REPO / "eval" / "sample" / "verification-report.json")
    rc = metric.main([sample, "--gate"])
    out = capsys.readouterr().out
    assert rc == 1
    assert "result:              FAIL" in out


def test_evidence_metric_gate_passes_when_tolerant(capsys):
    metric = _load("eval/evidence_metric.py")
    sample = str(REPO / "eval" / "sample" / "verification-report.json")
    rc = metric.main([sample, "--gate", "--max-phantoms", "1", "--min-work-done", "0.6"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "result:              PASS" in out


_EMPTY_REPORT = {
    "schema_version": "1.0",
    "feature_id": "empty",
    "verified_at": "2026-06-20T00:00:00Z",
    "summary": {"verdict": "pass", "human_review_required": False},
    "tasks": [],
}


def _write(path: Path, payload, *, bom: bool = False) -> str:
    raw = json.dumps(payload).encode("utf-8")
    path.write_bytes((b"\xef\xbb\xbf" + raw) if bom else raw)
    return str(path)


def test_gate_empty_report_passes_by_default(tmp_path, capsys):
    # Default min-claimed 0: an empty report abstains and passes. Honest, because
    # you cannot enforce work that was never claimed done.
    metric = _load("eval/evidence_metric.py")
    rc = metric.main([_write(tmp_path / "verification-report.json", _EMPTY_REPORT), "--gate"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "nothing to enforce" in out


def test_gate_empty_report_fails_with_min_claimed(tmp_path, capsys):
    # The Codex P1: a downstream gate that must prove work sets --min-claimed 1,
    # and then an empty report fails instead of passing silently.
    metric = _load("eval/evidence_metric.py")
    rc = metric.main(
        [_write(tmp_path / "verification-report.json", _EMPTY_REPORT), "--gate", "--min-claimed", "1"]
    )
    out = capsys.readouterr().out
    assert rc == 1
    assert "result:              FAIL" in out


def test_gate_min_claimed_passes_when_work_is_real(capsys):
    # The real sample carries claimed-done tasks, so --min-claimed 1 is satisfied
    # and the gate decides on phantom/work-done as usual (tolerant thresholds here).
    metric = _load("eval/evidence_metric.py")
    sample = str(REPO / "eval" / "sample" / "verification-report.json")
    rc = metric.main(
        [sample, "--gate", "--min-claimed", "1", "--max-phantoms", "1", "--min-work-done", "0.6"]
    )
    out = capsys.readouterr().out
    assert rc == 0
    assert "result:              PASS" in out


def test_load_reports_tolerates_utf8_bom(tmp_path, capsys):
    # PowerShell-produced BOM JSON must be read, not skipped. With a BOM and the
    # old utf-8 read the file was skipped and the metric reported none found.
    metric = _load("eval/evidence_metric.py")
    rc = metric.main([_write(tmp_path / "verification-report.json", _EMPTY_REPORT, bom=True)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "reports read: 1" in out
    assert "skip" not in out


_CLEAN_REPORT = {
    "schema_version": "1.0",
    "feature_id": "clean",
    "verified_at": "2026-06-20T00:00:00Z",
    "summary": {"verdict": "pass", "human_review_required": False},
    "tasks": [
        {"task_id": "T1", "claimed_status": "done", "verified_status": "pass",
         "confidence": "extracted", "files_checked": ["a.py"]}
    ],
    "provenance": {"verifier_version": "1", "tasks_state_sha256": "x"},
}


def test_strict_fails_on_the_sample(capsys):
    # The committed sample is a conditional, unsigned high-trust report with a
    # phantom. --strict runs both the gate and the integrity lint, so it fails and
    # surfaces the lint codes the plain gate never checks.
    metric = _load("eval/evidence_metric.py")
    sample = str(REPO / "eval" / "sample" / "verification-report.json")
    rc = metric.main([sample, "--strict"])
    out = capsys.readouterr().out
    assert rc == 1
    assert "CONDITIONAL_PASS" in out
    assert "UNSIGNED_HIGH_TRUST" in out


def test_strict_passes_on_a_clean_report(tmp_path, capsys):
    metric = _load("eval/evidence_metric.py")
    p = _write(tmp_path / "verification-report.json", _CLEAN_REPORT)
    rc = metric.main([p, "--strict"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "result:              PASS" in out


def test_strict_empty_report_fails_by_default(tmp_path):
    # Strict refuses an empty report: a report that proves nothing is not a pass.
    metric = _load("eval/evidence_metric.py")
    p = _write(tmp_path / "verification-report.json", _EMPTY_REPORT)
    assert metric.main([p, "--strict"]) == 1


def test_strict_empty_report_passes_with_allow_empty(tmp_path):
    metric = _load("eval/evidence_metric.py")
    p = _write(tmp_path / "verification-report.json", _EMPTY_REPORT)
    assert metric.main([p, "--strict", "--allow-empty"]) == 0


def test_strict_conditional_needs_allow_conditional(tmp_path, capsys):
    metric = _load("eval/evidence_metric.py")
    report = {**_CLEAN_REPORT,
              "summary": {"verdict": "conditional_pass", "human_review_required": False}}
    p = _write(tmp_path / "verification-report.json", report)
    assert metric.main([p, "--strict"]) == 1
    capsys.readouterr()
    assert metric.main([p, "--strict", "--allow-conditional"]) == 0
