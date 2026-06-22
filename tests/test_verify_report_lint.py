"""Tests for the verification-report linter (scripts/verify_report_lint.py).

The linter is the stdlib enforcement of the verification-report schema: it
refuses a report that is not a clean, proven pass. Loaded by file path because
scripts/ is not an importable package. The tests build reports from the
schema-required surface so they prove the rules without a schema validator.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def _load():
    spec = importlib.util.spec_from_file_location(
        "verify_report_lint", REPO / "scripts" / "verify_report_lint.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


lint = _load()


def _report(tasks, *, verdict="pass", risk=None, human_required=False,
            human_review=None, provenance=True):
    summary = {"verdict": verdict, "human_review_required": human_required}
    if risk is not None:
        summary["risk_level"] = risk
    if human_review is not None:
        summary["human_review"] = human_review
    report = {
        "schema_version": "1.0",
        "feature_id": "f",
        "verified_at": "2026-06-20T00:00:00Z",
        "summary": summary,
        "tasks": tasks,
    }
    if provenance:
        report["provenance"] = {"verifier_version": "1", "tasks_state_sha256": "x"}
    return report


def _pass_task(tid="T1", confidence="extracted", **proof):
    task = {"task_id": tid, "claimed_status": "done",
            "verified_status": "pass", "confidence": confidence}
    task.update(proof or {"files_checked": ["a.py"]})
    return task


def _codes(findings):
    return {f.code for f in findings}


def _errors(findings):
    return [f for f in findings if f.level == "error"]


# --------------------------------------------------------------------------- #
# the clean baseline
# --------------------------------------------------------------------------- #

def test_clean_report_has_no_findings():
    findings = lint.lint_report(_report([_pass_task()]), "x")
    assert findings == []


def test_evidence_can_be_any_of_the_three_proof_arrays():
    for proof in ({"files_checked": ["a"]}, {"tests_run": ["t"]}, {"evidence": ["e"]}):
        findings = lint.lint_report(_report([_pass_task(**proof)]), "x")
        assert _errors(findings) == []


# --------------------------------------------------------------------------- #
# the refusals
# --------------------------------------------------------------------------- #

def test_proofless_pass_is_an_error():
    task = {"task_id": "T1", "claimed_status": "done",
            "verified_status": "pass", "confidence": "extracted"}
    findings = lint.lint_report(_report([task]), "x")
    assert "PROOFLESS_PASS" in _codes(findings)


def test_empty_proof_arrays_do_not_count_as_evidence():
    task = _pass_task(files_checked=[], tests_run=[], evidence=[])
    findings = lint.lint_report(_report([task]), "x")
    assert "PROOFLESS_PASS" in _codes(findings)


def test_ambiguous_pass_is_an_error():
    findings = lint.lint_report(_report([_pass_task(confidence="ambiguous")]), "x")
    assert "AMBIGUOUS_PASS" in _codes(findings)


def test_summary_verdict_fail_is_an_error():
    findings = lint.lint_report(_report([_pass_task()], verdict="fail"), "x")
    assert "SUMMARY_FAIL" in _codes(findings)


def test_conditional_pass_is_an_error_by_default():
    findings = lint.lint_report(_report([_pass_task()], verdict="conditional_pass"), "x")
    assert "CONDITIONAL_PASS" in _codes(findings)


def test_conditional_pass_is_accepted_with_allow_conditional():
    findings = lint.lint_report(
        _report([_pass_task()], verdict="conditional_pass"), "x", allow_conditional=True)
    assert "CONDITIONAL_PASS" not in _codes(findings)


def test_unsigned_high_trust_is_an_error():
    findings = lint.lint_report(
        _report([_pass_task()], risk="high-trust", human_required=True), "x")
    assert "UNSIGNED_HIGH_TRUST" in _codes(findings)


def test_high_trust_pending_review_is_still_unsigned():
    findings = lint.lint_report(
        _report([_pass_task()], risk="high-trust", human_required=True,
                human_review={"status": "pending"}), "x")
    assert "UNSIGNED_HIGH_TRUST" in _codes(findings)


def test_high_trust_with_recorded_approval_is_clean():
    # A real sign-off records who approved, when, and on what evidence.
    findings = lint.lint_report(
        _report([_pass_task()], risk="high-trust", human_required=True,
                human_review={"status": "approved", "reviewer": "onour",
                              "approved_at": "2026-06-20T00:00:00Z",
                              "evidence": ["manual security review of the auth path"]}), "x")
    assert _errors(findings) == []


def test_high_trust_partial_approval_is_incomplete():
    # A partial approval (a reviewer but no approved_at and no evidence) is not a real
    # sign-off. It must not pass as a signed high-trust report.
    findings = lint.lint_report(
        _report([_pass_task()], risk="high-trust", human_required=True,
                human_review={"status": "approved", "reviewer": "onour"}), "x")
    assert "INCOMPLETE_APPROVAL" in _codes(findings)


def test_high_trust_truly_bare_approval_is_incomplete():
    # The minimal case: only a status, no reviewer, approved_at, or evidence at all.
    findings = lint.lint_report(
        _report([_pass_task()], risk="high-trust", human_required=True,
                human_review={"status": "approved"}), "x")
    assert "INCOMPLETE_APPROVAL" in _codes(findings)


def test_empty_report_is_refused_unless_allowed():
    # A report with no tasks proves nothing. It fails by default and passes only with the
    # explicit allow_empty escape hatch for a genuine no-op run.
    assert "EMPTY_REPORT" in _codes(lint.lint_report(_report([]), "x"))
    assert "EMPTY_REPORT" not in _codes(lint.lint_report(_report([]), "x", allow_empty=True))


def test_high_trust_with_review_required_false_is_the_contradiction_the_linter_catches():
    # risk high-trust but human_review_required false is exactly the downgrade the schema's
    # if/then forbids: a high-trust report must require human review. The linter is now at least
    # as strict as the schema and flags it, rather than short-circuiting and letting it through
    # (which previously let an unsigned high-trust report pass clean, the floor's worst case).
    findings = lint.lint_report(
        _report([_pass_task()], risk="high-trust", human_required=False), "x")
    assert "UNSIGNED_HIGH_TRUST" in _codes(findings)


def test_missing_required_key_is_schema_invalid():
    report = _report([_pass_task()])
    del report["tasks"]
    findings = lint.lint_report(report, "x")
    assert "SCHEMA_INVALID" in _codes(findings)


def test_missing_verified_at_is_schema_invalid():
    # verified_at is in the schema's required surface, so the linter rejects a
    # report without it rather than issuing a verdict the schema would reject.
    report = _report([_pass_task()])
    del report["verified_at"]
    findings = lint.lint_report(report, "x")
    assert "SCHEMA_INVALID" in _codes(findings)


def test_missing_summary_verdict_is_schema_invalid():
    report = _report([_pass_task()])
    del report["summary"]["verdict"]
    findings = lint.lint_report(report, "x")
    assert "SCHEMA_INVALID" in _codes(findings)


def test_non_object_report_is_schema_invalid():
    findings = lint.lint_report(["not", "an", "object"], "x")
    assert _codes(findings) == {"SCHEMA_INVALID"}


# --------------------------------------------------------------------------- #
# provenance is a warning, promotable to an error
# --------------------------------------------------------------------------- #

def test_missing_provenance_is_a_warning_not_an_error():
    findings = lint.lint_report(_report([_pass_task()], provenance=False), "x")
    assert _errors(findings) == []
    assert "MISSING_PROVENANCE" in _codes(findings)
    assert all(f.level == "warn" for f in findings if f.code == "MISSING_PROVENANCE")


def test_missing_provenance_becomes_an_error_under_require_provenance():
    findings = lint.lint_report(
        _report([_pass_task()], provenance=False), "x", require_provenance=True)
    assert "MISSING_PROVENANCE" in _codes(_errors(findings))


# --------------------------------------------------------------------------- #
# main: exit codes and IO
# --------------------------------------------------------------------------- #

def _write(directory, report, name="verification-report.json", *, bom=False):
    raw = json.dumps(report).encode("utf-8")
    (directory / name).write_bytes((b"\xef\xbb\xbf" + raw) if bom else raw)
    return directory / name


def test_main_returns_0_on_a_clean_report(tmp_path):
    p = _write(tmp_path, _report([_pass_task()]))
    assert lint.main([str(p)]) == 0


def test_main_returns_1_on_a_proofless_pass(tmp_path):
    bad = _report([{"task_id": "T1", "claimed_status": "done",
                    "verified_status": "pass", "confidence": "extracted"}])
    p = _write(tmp_path, bad)
    assert lint.main([str(p)]) == 1


def test_main_returns_2_when_nothing_to_read(tmp_path):
    assert lint.main([str(tmp_path / "nope.json")]) == 2
    assert lint.main([str(tmp_path)]) == 2  # empty dir, no reports


def test_main_returns_1_on_unreadable_json(tmp_path):
    (tmp_path / "verification-report.json").write_text("{ not json", encoding="utf-8")
    assert lint.main([str(tmp_path)]) == 1


def test_main_scans_a_directory_and_tolerates_bom(tmp_path):
    sub = tmp_path / "run1"
    sub.mkdir()
    _write(sub, _report([_pass_task()]), bom=True)
    assert lint.main([str(tmp_path)]) == 0


def test_main_on_the_committed_sample_fails(capsys):
    # The sample is a conditional, unsigned high-trust report: not a clean pass.
    sample = REPO / "eval" / "sample" / "verification-report.json"
    rc = lint.main([str(sample)])
    out = capsys.readouterr().out
    assert rc == 1
    assert "CONDITIONAL_PASS" in out
    assert "UNSIGNED_HIGH_TRUST" in out
