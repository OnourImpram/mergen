"""Tests for the eval evidence metric (eval/evidence_metric.py): the work-done
rate, phantom-completion detection, and the pass/fail gate with its thresholds.

Loaded by file path because eval/ is not an importable package.
"""

import importlib.util
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
