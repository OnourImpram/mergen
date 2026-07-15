"""Tests for the fail-closed milestone supervisor."""

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
    proc = subprocess.run(
        list(args),
        cwd=cwd,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return proc.stdout.strip()


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


def _base_state() -> dict:
    return {
        "schema_version": "1.0",
        "feature_id": "M001",
        "tasks": [
            {
                "id": "T001",
                "status": "done",
                "files": ["src/a.py"],
                "test_task": None,
            }
        ],
    }


def _base_report(head: str, state_raw: bytes) -> dict:
    return {
        "schema_version": "1.0",
        "feature_id": "M001",
        "verified_at": "2026-07-15T00:00:00Z",
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
                "files_checked": ["src/a.py"],
                "tests_run": [],
                "evidence": ["exists: src/a.py", "git-tracked: src/a.py"],
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


def _case(tmp_path: Path, *, state: dict | None = None, report_edit=None) -> tuple[Path, Path, dict]:
    root = tmp_path
    _run("git", "init", "-q", cwd=root)
    _run("git", "config", "user.name", "Mergen Tests", cwd=root)
    _run("git", "config", "user.email", "tests@example.invalid", cwd=root)
    (root / "src").mkdir()
    (root / "src" / "a.py").write_text("VALUE = 1\n", encoding="utf-8")
    state_path = root / "tasks-state.json"
    state_raw = _write_json(state_path, state or _base_state())
    _run("git", "add", "src/a.py", "tasks-state.json", cwd=root)
    _run("git", "commit", "-q", "-m", "fixture", cwd=root)
    head = _run("git", "rev-parse", "HEAD", cwd=root)

    report = _base_report(head, state_raw)
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


def test_clean_current_evidence_is_the_only_advancing_state(tmp_path):
    _case(tmp_path)
    decision = _supervise(tmp_path)
    assert decision["verdict"] == "pass"
    assert decision["decision"] == "advance"
    assert all(check["result"] == "pass" for check in decision["checks"])


def test_missing_manifest_is_unverifiable_and_blocks(tmp_path):
    report_path, _, _ = _case(tmp_path)
    report_path.with_name(report_path.name + ".sha256").unlink()
    decision = _supervise(tmp_path)
    assert decision["verdict"] == "unverifiable"
    assert decision["decision"] == "block"


def test_manifest_mismatch_is_fail_and_blocks(tmp_path):
    report_path, _, _ = _case(tmp_path)
    report_path.write_text(report_path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    decision = _supervise(tmp_path)
    assert decision["verdict"] == "fail"
    assert decision["decision"] == "block"


def test_stale_source_commit_is_unverifiable(tmp_path):
    _case(tmp_path)
    (tmp_path / "src" / "a.py").write_text("VALUE = 2\n", encoding="utf-8")
    _run("git", "add", "src/a.py", cwd=tmp_path)
    _run("git", "commit", "-q", "-m", "move head", cwd=tmp_path)
    decision = _supervise(tmp_path)
    assert decision["verdict"] == "unverifiable"
    assert decision["decision"] == "block"
    assert any(check["check_id"] == "source-commit" for check in decision["checks"])


def test_tasks_state_digest_mismatch_is_fail(tmp_path):
    _, state_path, _ = _case(tmp_path)
    state_path.write_text(state_path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    decision = _supervise(tmp_path)
    assert decision["verdict"] == "fail"
    assert decision["decision"] == "block"


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
    assert any(
        check["check_id"] == "task-completion" and check["result"] == "fail"
        for check in decision["checks"]
    )


def test_ambiguous_done_task_is_unverifiable(tmp_path):
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
    assert decision["decision"] == "block"


def test_task_set_mismatch_is_fail(tmp_path):
    def edit(report):
        report["tasks"][0]["task_id"] = "T999"

    _case(tmp_path, report_edit=edit)
    decision = _supervise(tmp_path)
    assert decision["verdict"] == "fail"
    assert decision["decision"] == "block"


def test_report_path_cannot_escape_trusted_root(tmp_path):
    decision = _supervise(tmp_path, report_arg="../verification-report.json")
    assert decision["verdict"] == "unverifiable"
    assert decision["decision"] == "block"
    assert decision["checks"][0]["check_id"] == "evidence-paths"


def test_positive_review_claim_is_observed_but_not_independence_proof(tmp_path):
    _case(tmp_path)
    review = {
        "reviewer": "implementation-agent",
        "verdict": "pass",
        "independent": True,
        "workspace_root": "/tmp/attacker-selected-root",
    }
    _write_json(tmp_path / "review.json", review)
    decision = _supervise(tmp_path, review_arg="review.json")
    assert decision["verdict"] == "pass"
    assert decision["decision"] == "advance"
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
    assert decision["decision"] == "block"


def test_unresolved_external_review_is_unverifiable(tmp_path):
    _case(tmp_path)
    _write_json(tmp_path / "review.json", {"reviewer": "reviewer", "verdict": "pending"})
    decision = _supervise(tmp_path, review_arg="review.json")
    assert decision["verdict"] == "unverifiable"
    assert decision["decision"] == "block"


def test_required_human_approval_without_bound_token_is_unverifiable(tmp_path):
    def edit(report):
        report["summary"]["human_review_required"] = True
        report["summary"]["human_review"] = {
            "status": "approved",
            "reviewer": "operator",
            "approved_at": "2026-07-15T00:00:00Z",
            "evidence": ["reviewed report and diff"],
        }

    _case(tmp_path, report_edit=edit)
    decision = _supervise(tmp_path)
    assert decision["verdict"] == "unverifiable"
    assert decision["decision"] == "block"


def test_valid_artifact_bound_human_approval_advances(tmp_path, monkeypatch):
    key = "Ab9!" * 16
    monkeypatch.setenv("MERGEN_SIGNING_KEY", key)

    def edit(report):
        report["summary"]["human_review_required"] = True
        report["summary"]["human_review"] = {
            "status": "approved",
            "reviewer": "operator",
            "approved_at": "2026-07-15T00:00:00Z",
            "evidence": ["reviewed report and diff"],
        }

    report_path, _, _ = _case(tmp_path, report_edit=edit)
    raw = report_path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    token = hmac.new(key.encode(), digest.encode(), hashlib.sha256).hexdigest()
    (tmp_path / "approval-token.txt").write_text(token + "\n", encoding="utf-8")
    decision = _supervise(
        tmp_path,
        approval_token=token,
        approval_token_path_arg="approval-token.txt",
    )
    assert decision["verdict"] == "pass"
    assert decision["decision"] == "advance"


def test_invalid_artifact_bound_human_approval_fails(tmp_path, monkeypatch):
    monkeypatch.setenv("MERGEN_SIGNING_KEY", "Bc8@" * 16)

    def edit(report):
        report["summary"]["human_review_required"] = True
        report["summary"]["human_review"] = {
            "status": "approved",
            "reviewer": "operator",
            "approved_at": "2026-07-15T00:00:00Z",
            "evidence": ["reviewed report and diff"],
        }

    _case(tmp_path, report_edit=edit)
    decision = _supervise(tmp_path, approval_token="0" * 64)
    assert decision["verdict"] == "fail"
    assert decision["decision"] == "block"


def test_rejected_human_review_is_fail_even_without_token(tmp_path):
    def edit(report):
        report["summary"]["human_review_required"] = True
        report["summary"]["human_review"] = {
            "status": "rejected",
            "reviewer": "operator",
            "approved_at": None,
            "evidence": ["unsafe change"],
        }

    _case(tmp_path, report_edit=edit)
    decision = _supervise(tmp_path)
    assert decision["verdict"] == "fail"
    assert decision["decision"] == "block"


def test_cli_writes_decision_and_manifest(tmp_path):
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
    assert decision["decision"] == "advance"
    sidecar = out.with_name(out.name + ".sha256")
    expected = hashlib.sha256(out.read_bytes()).hexdigest()
    assert sidecar.read_text(encoding="utf-8").split()[0] == expected


def test_cli_returns_two_for_unverifiable(tmp_path):
    _case(tmp_path)
    (tmp_path / "verification-report.json.sha256").unlink()
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


@pytest.mark.parametrize("verdict", ["fail", "unverifiable"])
def test_decision_builder_never_advances_non_pass(verdict):
    checks = [mergen_supervise._check("fixture", verdict, "fixture")]
    decision = mergen_supervise._decision("M001", checks, {}, None)
    assert decision["verdict"] == verdict
    assert decision["decision"] == "block"
