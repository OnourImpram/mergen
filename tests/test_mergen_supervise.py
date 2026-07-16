"""Tests for independent, fail-closed milestone supervision."""

from __future__ import annotations

import hashlib
import hmac
import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import mergen_supervise  # noqa: E402


def _run(*args: str, cwd: Path) -> str:
    process = subprocess.run(
        list(args),
        cwd=cwd,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return process.stdout.strip()


def _write_json(path: Path, value: dict) -> bytes:
    raw = (json.dumps(value, indent=2) + "\n").encode("utf-8")
    path.write_bytes(raw)
    return raw


def _write_manifest(path: Path, raw: bytes) -> None:
    digest = hashlib.sha256(raw).hexdigest()
    path.with_name(path.name + ".sha256").write_text(
        f"{digest}  {path.name}\n",
        encoding="utf-8",
    )


def _base_state(file_path: str = "src/a.py") -> dict:
    return {
        "schema_version": "1.0",
        "feature_id": "M001",
        "tasks": [
            {
                "id": "T001",
                "status": "done",
                "files": [file_path],
                "test_task": None,
            }
        ],
    }


def _base_report(head: str, state_raw: bytes, file_path: str = "src/a.py") -> dict:
    return {
        "schema_version": "1.0",
        "feature_id": "M001",
        "verified_at": "2026-07-16T00:00:00Z",
        "verifier": {"tool": "verify_core.py", "mode": "mechanical", "agent": "none"},
        "summary": {
            "verdict": "pass",
            "risk_level": "standard",
            "risk_triggers": [],
            "human_review_required": False,
            "total_done_tasks": 1,
            "mechanically_passed": 1,
            "mechanically_failed": 0,
            "ambiguous": 0,
            "untested_passes": 1,
        },
        "tasks": [
            {
                "task_id": "T001",
                "claimed_status": "done",
                "verified_status": "pass",
                "confidence": "extracted",
                "evidence_strength": 0.5,
                "evidence_tier": "corroborated",
                "files_checked": [file_path],
                "tests_run": [],
                "evidence": [f"exists: {file_path}", f"git-tracked: {file_path}"],
                "failures": [],
            }
        ],
        "policy_results": [],
        "provenance": {
            "verifier_version": "1.1",
            "source_commit": head,
            "working_tree_clean": True,
            "tasks_state_sha256": hashlib.sha256(state_raw).hexdigest(),
        },
    }


def _case(
    tmp_path: Path,
    *,
    file_path: str = "src/a.py",
    state: dict | None = None,
    report_edit=None,
) -> tuple[Path, Path, dict]:
    root = tmp_path
    _run("git", "init", "-q", cwd=root)
    _run("git", "config", "user.name", "Mergen Tests", cwd=root)
    _run("git", "config", "user.email", "tests@example.invalid", cwd=root)
    artifact = root / file_path
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text("VALUE = 1\n", encoding="utf-8")
    state_path = root / "tasks-state.json"
    state_value = state or _base_state(file_path)
    state_raw = _write_json(state_path, state_value)
    _run("git", "add", file_path, "tasks-state.json", cwd=root)
    _run("git", "commit", "-q", "-m", "fixture", cwd=root)
    head = _run("git", "rev-parse", "HEAD", cwd=root)

    report = _base_report(head, state_raw, file_path)
    if report_edit is not None:
        report_edit(report)
    report_path = root / "verification-report.json"
    report_raw = _write_json(report_path, report)
    _write_manifest(report_path, report_raw)
    return report_path, state_path, report


def _supervise(root: Path, **kwargs) -> dict:
    return mergen_supervise.supervise(
        root=root,
        report_arg=kwargs.pop("report_arg", "verification-report.json"),
        tasks_state_arg=kwargs.pop("tasks_state_arg", "tasks-state.json"),
        **kwargs,
    )


def test_clean_current_evidence_advances(tmp_path):
    _case(tmp_path)
    decision = _supervise(tmp_path)
    assert decision["verdict"] == "pass"
    assert decision["advancement_action"] == "advance"
    assert decision["decision"] == "advance"
    assert all(check["result"] == "pass" for check in decision["checks"])
    assert decision["source"]["source_state_hash"]
    assert decision["decision_hash"] == mergen_supervise._decision_hash(decision)
    assert decision["evidence_summary"]["independently_executed"] == 1


def test_missing_manifest_is_unverifiable_and_holds(tmp_path):
    report_path, _, _ = _case(tmp_path)
    report_path.with_name(report_path.name + ".sha256").unlink()
    decision = _supervise(tmp_path)
    assert decision["verdict"] == "unverifiable"
    assert decision["advancement_action"] == "hold"


def test_manifest_mismatch_is_fail(tmp_path):
    report_path, _, _ = _case(tmp_path)
    report_path.write_text(report_path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    decision = _supervise(tmp_path)
    assert decision["verdict"] == "fail"
    assert decision["advancement_action"] == "return_for_remediation"


def test_stale_source_commit_is_unverifiable(tmp_path):
    _case(tmp_path)
    (tmp_path / "src" / "a.py").write_text("VALUE = 2\n", encoding="utf-8")
    _run("git", "add", "src/a.py", cwd=tmp_path)
    _run("git", "commit", "-q", "-m", "move head", cwd=tmp_path)
    decision = _supervise(tmp_path)
    assert decision["verdict"] == "unverifiable"
    assert "source-commit" in decision["unverifiable_criteria"]


def test_dirty_tree_outside_evidence_is_unverifiable(tmp_path):
    _case(tmp_path)
    (tmp_path / "unexpected.txt").write_text("dirty\n", encoding="utf-8")
    decision = _supervise(tmp_path)
    assert decision["verdict"] == "unverifiable"
    assert any(check["check_id"] == "worktree-state" for check in decision["checks"])


def test_tasks_state_digest_mismatch_is_fail(tmp_path):
    _, state_path, _ = _case(tmp_path)
    state_path.write_text(state_path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    decision = _supervise(tmp_path)
    assert decision["verdict"] == "fail"
    assert "tasks-state-digest" in decision["failed_criteria"]


def test_pending_task_is_direct_failure(tmp_path):
    state = _base_state()
    state["tasks"][0]["status"] = "todo"

    def edit(report):
        item = report["tasks"][0]
        item["claimed_status"] = "todo"
        item["verified_status"] = "fail"
        item["confidence"] = "ambiguous"
        item["evidence"] = []
        item["files_checked"] = []
        report["summary"].update(
            {
                "verdict": "conditional_pass",
                "total_done_tasks": 0,
                "mechanically_passed": 0,
                "mechanically_failed": 0,
                "ambiguous": 0,
            }
        )

    _case(tmp_path, state=state, report_edit=edit)
    decision = _supervise(tmp_path)
    assert decision["verdict"] == "fail"
    assert "task-completion" in decision["failed_criteria"]


def test_ambiguous_done_task_is_unverifiable_not_fail(tmp_path):
    def edit(report):
        item = report["tasks"][0]
        item["verified_status"] = "fail"
        item["confidence"] = "ambiguous"
        item["evidence"] = []
        item["files_checked"] = []
        report["summary"].update(
            {
                "verdict": "conditional_pass",
                "mechanically_passed": 0,
                "mechanically_failed": 0,
                "ambiguous": 1,
            }
        )

    _case(tmp_path, report_edit=edit)
    decision = _supervise(tmp_path)
    assert decision["verdict"] == "unverifiable"
    task_check = next(item for item in decision["checks"] if item["check_id"] == "task-verdicts")
    assert task_check["result"] == "unverifiable"


def test_duplicate_task_ids_are_unverifiable(tmp_path):
    state = _base_state()
    state["tasks"].append(dict(state["tasks"][0]))
    _case(tmp_path, state=state)
    decision = _supervise(tmp_path)
    assert decision["verdict"] == "unverifiable"
    assert "task-set" in decision["unverifiable_criteria"]


def test_task_set_mismatch_is_fail(tmp_path):
    def edit(report):
        report["tasks"][0]["task_id"] = "T999"

    _case(tmp_path, report_edit=edit)
    decision = _supervise(tmp_path)
    assert decision["verdict"] == "fail"


def test_explicit_milestone_id_must_match_report(tmp_path):
    _case(tmp_path)
    decision = _supervise(tmp_path, milestone_id="M999")
    assert decision["verdict"] == "fail"
    assert "feature-binding" in decision["failed_criteria"]


def test_report_path_cannot_escape_root(tmp_path):
    decision = _supervise(tmp_path, report_arg="../verification-report.json")
    assert decision["verdict"] == "unverifiable"
    assert decision["checks"][0]["check_id"] == "evidence-paths"


def test_symlinked_report_cannot_escape_root(tmp_path):
    outside = tmp_path.parent / "outside-report.json"
    outside.write_text("{}\n", encoding="utf-8")
    (tmp_path / "link.json").symlink_to(outside)
    decision = _supervise(tmp_path, report_arg="link.json")
    assert decision["verdict"] == "unverifiable"
    assert decision["checks"][0]["check_id"] == "evidence-paths"


def test_option_shaped_path_is_data_not_command(tmp_path):
    decision = _supervise(tmp_path, report_arg="--version")
    assert decision["verdict"] == "unverifiable"
    assert decision["checks"][0]["check_id"] == "report-readable"


def test_high_trust_downgrade_is_rejected(tmp_path):
    _case(tmp_path, file_path="src/auth.py")
    decision = _supervise(tmp_path)
    assert decision["verdict"] == "fail"
    assert "governor-risk" in decision["failed_criteria"]
    assert decision["governor_decision"]["risk_level"] == "high-trust"


def test_recorded_high_trust_trigger_cannot_carry_standard_risk(tmp_path):
    def edit(report):
        report["summary"]["risk_triggers"] = ["auth-path"]

    _case(tmp_path, report_edit=edit)
    decision = _supervise(tmp_path)
    assert decision["verdict"] == "fail"
    assert decision["governor_decision"]["risk_level"] == "high-trust"


def test_effective_risk_preserves_the_higher_non_high_trust_tier(tmp_path):
    def edit(report):
        report["summary"]["risk_level"] = "spec"

    _case(tmp_path, report_edit=edit)
    decision = _supervise(tmp_path)
    assert decision["verdict"] == "pass"
    assert decision["governor_decision"]["risk_level"] == "spec"


def test_high_trust_without_bound_approval_is_conditional(tmp_path):
    def edit(report):
        report["summary"].update(
            {
                "risk_level": "high-trust",
                "risk_triggers": ["auth-path"],
                "human_review_required": True,
            }
        )

    _case(tmp_path, file_path="src/auth.py", report_edit=edit)
    decision = _supervise(tmp_path)
    assert decision["verdict"] == "conditional_pass"
    assert decision["advancement_action"] == "human_review_required"
    assert decision["decision"] == "block"


def test_valid_artifact_bound_human_approval_advances(tmp_path, monkeypatch):
    key = "Ab9!" * 16
    monkeypatch.setenv("MERGEN_SIGNING_KEY", key)

    def edit(report):
        report["summary"].update(
            {
                "risk_level": "high-trust",
                "risk_triggers": ["auth-path"],
                "human_review_required": True,
                "human_review": {
                    "status": "approved",
                    "reviewer": "operator",
                    "approved_at": "2026-07-16T00:00:00Z",
                    "evidence": ["reviewed exact report and diff"],
                },
            }
        )

    report_path, _, _ = _case(tmp_path, file_path="src/auth.py", report_edit=edit)
    digest = hashlib.sha256(report_path.read_bytes()).hexdigest()
    token = hmac.new(key.encode(), digest.encode(), hashlib.sha256).hexdigest()
    decision = _supervise(tmp_path, approval_token=token)
    assert decision["verdict"] == "pass"
    assert decision["advancement_action"] == "advance"


def test_invalid_artifact_bound_approval_fails(tmp_path, monkeypatch):
    monkeypatch.setenv("MERGEN_SIGNING_KEY", "Bc8@" * 16)

    def edit(report):
        report["summary"].update(
            {
                "risk_level": "high-trust",
                "human_review_required": True,
                "human_review": {
                    "status": "approved",
                    "reviewer": "operator",
                    "approved_at": "2026-07-16T00:00:00Z",
                    "evidence": ["reviewed exact report and diff"],
                },
            }
        )

    _case(tmp_path, file_path="src/auth.py", report_edit=edit)
    decision = _supervise(tmp_path, approval_token="0" * 64)
    assert decision["verdict"] == "fail"
    assert "human-approval" in decision["failed_criteria"]


def test_rejected_human_review_fails_without_token(tmp_path):
    def edit(report):
        report["summary"].update(
            {
                "risk_level": "high-trust",
                "human_review_required": True,
                "human_review": {
                    "status": "rejected",
                    "reviewer": "operator",
                    "approved_at": None,
                    "evidence": ["unsafe change"],
                },
            }
        )

    _case(tmp_path, file_path="src/auth.py", report_edit=edit)
    decision = _supervise(tmp_path)
    assert decision["verdict"] == "fail"


def test_positive_review_is_observed_but_not_independence_proof(tmp_path):
    _case(tmp_path)
    _write_json(
        tmp_path / "review.json",
        {
            "reviewer": "implementation-agent",
            "verdict": "pass",
            "independent": True,
            "workspace_root": "/tmp/attacker-selected-root",
        },
    )
    decision = _supervise(tmp_path, review_arg="review.json")
    assert decision["verdict"] == "pass"
    observation = decision["review_observation"]
    assert observation["claimed_independent"] is True
    assert observation["independence_verified"] is False
    assert observation["used_as_positive_proof"] is False
    assert observation["ignored_root_fields"] == ["workspace_root"]


def test_negative_external_review_blocks(tmp_path):
    _case(tmp_path)
    _write_json(tmp_path / "review.json", {"reviewer": "reviewer", "verdict": "reject"})
    decision = _supervise(tmp_path, review_arg="review.json")
    assert decision["verdict"] == "fail"


def test_unresolved_external_review_is_unverifiable(tmp_path):
    _case(tmp_path)
    _write_json(tmp_path / "review.json", {"reviewer": "reviewer", "verdict": "pending"})
    decision = _supervise(tmp_path, review_arg="review.json")
    assert decision["verdict"] == "unverifiable"


def test_malformed_policy_result_is_unverifiable(tmp_path):
    def edit(report):
        report["policy_results"] = [{"result": "pass"}]

    _case(tmp_path, report_edit=edit)
    decision = _supervise(tmp_path)
    assert decision["verdict"] == "unverifiable"
    assert "policy-results" in decision["unverifiable_criteria"]


def test_no_reproduction_can_never_cleanly_pass(tmp_path):
    _case(tmp_path)
    decision = _supervise(tmp_path, reproduce=False)
    assert decision["verdict"] == "unverifiable"
    assert decision["advancement_action"] == "hold"


def test_status_parser_handles_nul_terminated_rename():
    paths, malformed = mergen_supervise._status_paths(b"R  new name\x00old name\x00")
    assert paths == ["new name", "old name"]
    assert malformed is False


def test_cli_writes_json_manifest_and_markdown(tmp_path):
    _case(tmp_path)
    out = tmp_path / "milestone-decision.json"
    rc = mergen_supervise.main(
        [
            "--root",
            str(tmp_path),
            "--report",
            "verification-report.json",
            "--tasks-state",
            "tasks-state.json",
            "--out",
            str(out),
        ]
    )
    assert rc == 0
    decision = json.loads(out.read_text(encoding="utf-8"))
    assert decision["verdict"] == "pass"
    sidecar = out.with_name(out.name + ".sha256")
    assert sidecar.read_text(encoding="utf-8").split()[0] == hashlib.sha256(out.read_bytes()).hexdigest()
    markdown = out.with_suffix(".md").read_text(encoding="utf-8")
    assert "Advancement action" in markdown
    assert "independently_executed" in markdown


def test_cli_returns_two_for_conditional_pass(tmp_path):
    def edit(report):
        report["summary"].update(
            {
                "risk_level": "high-trust",
                "human_review_required": True,
            }
        )

    _case(tmp_path, file_path="src/auth.py", report_edit=edit)
    rc = mergen_supervise.main(
        [
            "--root",
            str(tmp_path),
            "--report",
            "verification-report.json",
            "--tasks-state",
            "tasks-state.json",
        ]
    )
    assert rc == 2


def test_cli_returns_one_for_fail(tmp_path):
    report_path, _, _ = _case(tmp_path)
    report_path.write_text(report_path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    rc = mergen_supervise.main(
        [
            "--root",
            str(tmp_path),
            "--report",
            "verification-report.json",
            "--tasks-state",
            "tasks-state.json",
        ]
    )
    assert rc == 1


def test_cli_rejects_markdown_out_without_json_out():
    with pytest.raises(SystemExit) as exc:
        mergen_supervise.main(
            [
                "--report",
                "report.json",
                "--tasks-state",
                "tasks.json",
                "--markdown-out",
                "report.md",
            ]
        )
    assert exc.value.code == 2


@pytest.mark.parametrize("result", ["fail", "unverifiable"])
def test_decision_builder_never_advances_non_pass(result):
    decision = mergen_supervise._decision(
        "M001",
        [mergen_supervise._check("fixture", result, "fixture")],
        {},
        None,
    )
    assert decision["verdict"] == result
    assert decision["decision"] == "block"
    assert decision["advancement_action"] != "advance"
