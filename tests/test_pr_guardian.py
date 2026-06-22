"""Tests for the PR Guardian (scripts/pr_guardian.py): a pull-request evidence
summary and gate that reuses verify_report_lint for its rules.

Loaded by file path because scripts/ is not an importable package.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def _load():
    spec = importlib.util.spec_from_file_location("pr_guardian", REPO / "scripts" / "pr_guardian.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


guard = _load()


def _report(tasks, *, verdict="pass", risk=None, human_required=False,
            human_review=None, provenance=True):
    summary = {"verdict": verdict, "human_review_required": human_required}
    if risk is not None:
        summary["risk_level"] = risk
    if human_review is not None:
        summary["human_review"] = human_review
    report = {"schema_version": "1.0", "feature_id": "f",
              "verified_at": "2026-06-20T00:00:00Z", "summary": summary, "tasks": tasks}
    if provenance:
        report["provenance"] = {"verifier_version": "1", "tasks_state_sha256": "x"}
    return report


def _pass(tid="T1"):
    return {"task_id": tid, "claimed_status": "done", "verified_status": "pass",
            "confidence": "extracted", "files_checked": ["a.py"]}


def _phantom(tid="T2"):
    return {"task_id": tid, "claimed_status": "done", "verified_status": "fail",
            "confidence": "extracted"}


# --------------------------------------------------------------------------- #
# summarize
# --------------------------------------------------------------------------- #

def test_clean_report_passes_with_no_findings():
    md, rc = guard.summarize(_report([_pass()]), "x")
    assert rc == 0
    assert "No gate findings" in md
    assert "claimed done / verified pass: 1 / 1" in md


def test_phantom_fails_and_is_named_even_when_verdict_says_pass():
    # A report can claim an overall pass while carrying a phantom task. The
    # Guardian gates on the phantom regardless of the stated verdict.
    md, rc = guard.summarize(_report([_pass(), _phantom()], verdict="pass"), "x")
    assert rc == 1
    assert "PHANTOM_COMPLETIONS" in md
    assert "phantom completions: 1" in md


def test_unsigned_high_trust_fails():
    md, rc = guard.summarize(
        _report([_pass()], risk="high-trust", human_required=True), "x")
    assert rc == 1
    assert "UNSIGNED_HIGH_TRUST" in md


def test_signed_high_trust_passes():
    md, rc = guard.summarize(
        _report([_pass()], risk="high-trust", human_required=True,
                human_review={"status": "approved", "reviewer": "onour",
                              "approved_at": "2026-06-20T00:00:00Z",
                              "evidence": ["manual review"]}), "x")
    assert rc == 0
    assert "human sign-off: `approved`" in md


def test_conditional_fails_by_default_and_passes_when_allowed():
    rep = _report([_pass()], verdict="conditional_pass")
    _md, rc = guard.summarize(rep, "x")
    assert rc == 1
    _md2, rc2 = guard.summarize(rep, "x", allow_conditional=True)
    assert rc2 == 0


def test_task_counts():
    claimed, verified, phantom = guard.task_counts(_report([_pass(), _pass("T3"), _phantom()]))
    assert (claimed, verified, phantom) == (3, 2, 1)


# --------------------------------------------------------------------------- #
# main: exit codes and IO
# --------------------------------------------------------------------------- #

def _write(tmp_path, report):
    p = tmp_path / "verification-report.json"
    p.write_text(json.dumps(report), encoding="utf-8")
    return p


def test_main_returns_0_on_clean(tmp_path):
    assert guard.main([str(_write(tmp_path, _report([_pass()])))]) == 0


def test_main_returns_1_on_phantom(tmp_path):
    assert guard.main([str(_write(tmp_path, _report([_pass(), _phantom()])))]) == 1


def test_main_returns_2_on_missing_or_unreadable(tmp_path):
    assert guard.main([str(tmp_path / "nope.json")]) == 2
    bad = tmp_path / "verification-report.json"
    bad.write_text("{ not json", encoding="utf-8")
    assert guard.main([str(bad)]) == 2


def test_main_writes_summary_to_out(tmp_path):
    out = tmp_path / "comment.md"
    rc = guard.main([str(_write(tmp_path, _report([_pass()]))), "--out", str(out)])
    assert rc == 0
    assert out.read_text(encoding="utf-8").startswith("## Mergen verification summary")


def test_main_tolerates_bom(tmp_path):
    p = tmp_path / "verification-report.json"
    p.write_bytes(b"\xef\xbb\xbf" + json.dumps(_report([_pass()])).encode("utf-8"))
    assert guard.main([str(p)]) == 0


def test_main_returns_2_on_valid_non_object_json(tmp_path):
    # A JSON file that parses but is a list, not an object, is not a report.
    p = tmp_path / "verification-report.json"
    p.write_text(json.dumps(["not", "a", "report"]), encoding="utf-8")
    assert guard.main([str(p)]) == 2


def test_main_allow_conditional_passes_a_conditional_report(tmp_path, capsys):
    rep = _report([_pass()], verdict="conditional_pass")
    p = _write(tmp_path, rep)
    assert guard.main([str(p)]) == 1
    capsys.readouterr()
    assert guard.main([str(p), "--allow-conditional"]) == 0


def test_summary_neutralizes_a_hostile_value():
    # A backtick or newline in a report value must not survive into the rendered
    # value, so it cannot break the comment markdown.
    rep = _report([_pass()], verdict="pass`\ninjected")
    md, _rc = guard.summarize(rep, "x")
    assert "pass' injected" in md   # backtick downgraded to an apostrophe, newline flattened
    assert "pass`" not in md        # the value's own backtick did not survive
