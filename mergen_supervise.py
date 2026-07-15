#!/usr/bin/env python3
"""Fail-closed, deterministic milestone supervision for Mergen.

This module is deliberately outside the implementation path. It consumes evidence
that another process produced, verifies that evidence against the current repository,
and emits one of three verdicts:

* pass: evidence is complete and internally consistent.
* fail: evidence positively demonstrates a failed or tampered milestone.
* unverifiable: required evidence is absent, stale, ambiguous, or malformed.

Only pass authorizes the action "advance". Both fail and unverifiable authorize
"block". A review record may be observed, and a negative review can block, but a
self-declared reviewer identity or ``independent: true`` claim is never treated as
proof of independence.

The trusted workspace boundary is the operator-supplied ``--root`` argument. Evidence
files must resolve inside that root. No JSON input is allowed to select or replace the
workspace root.

Runtime dependencies: Python standard library only. No network and no model.
Exit codes: 0 pass/advance, 1 fail/block, 2 unverifiable/block.
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import hmac
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "1.0"
REPORT_SCHEMA_VERSION = "1.0"
SIGNING_KEY_ENV = "MERGEN_SIGNING_KEY"
APPROVAL_TOKEN_ENV = "MERGEN_ACK_TOKEN"
_GIT_TIMEOUT = 30
_ALLOWED_RESULTS = frozenset({"pass", "fail", "unverifiable"})


class UnsafeEvidencePath(ValueError):
    """An evidence path escaped the trusted repository root."""


def _check(check_id: str, result: str, reason: str) -> dict[str, str]:
    if result not in _ALLOWED_RESULTS:
        raise ValueError(f"unknown check result: {result}")
    return {"check_id": check_id, "result": result, "reason": reason}


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _safe_evidence_path(raw: str, root: Path, *, kind: str) -> Path:
    """Resolve an operator-named evidence file and require that it stays under root."""
    if not raw or any(ord(ch) < 32 or ch == "\x7f" for ch in raw):
        raise UnsafeEvidencePath(f"{kind}: empty or control-character path")
    candidate = Path(raw)
    resolved = candidate.resolve() if candidate.is_absolute() else (root / candidate).resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError:
        raise UnsafeEvidencePath(f"{kind}: path resolves outside the trusted root") from None
    return resolved


def _relative(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return "<outside-root>"


def _read_json(path: Path, *, kind: str) -> tuple[dict[str, Any] | None, bytes | None, dict[str, str]]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        return None, None, _check(f"{kind}-readable", "unverifiable", f"{kind} cannot be read: {exc}")
    try:
        value: Any = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return None, raw, _check(f"{kind}-readable", "unverifiable", f"{kind} is not valid JSON: {exc}")
    if not isinstance(value, dict):
        return None, raw, _check(f"{kind}-readable", "unverifiable", f"{kind} must be a JSON object")
    return value, raw, _check(f"{kind}-readable", "pass", f"{kind} is readable JSON")


def _manifest_check(report_path: Path, report_bytes: bytes) -> dict[str, str]:
    sidecar = report_path.with_name(report_path.name + ".sha256")
    try:
        fields = sidecar.read_text(encoding="utf-8-sig").split()
    except OSError as exc:
        return _check("report-manifest", "unverifiable", f"manifest sidecar cannot be read: {exc}")
    if not fields or len(fields[0]) != 64:
        return _check("report-manifest", "unverifiable", "manifest sidecar has no valid SHA-256 digest")
    expected = fields[0].lower()
    if any(ch not in "0123456789abcdef" for ch in expected):
        return _check("report-manifest", "unverifiable", "manifest digest is not hexadecimal")
    actual = _sha256(report_bytes)
    if not hmac.compare_digest(expected, actual):
        return _check("report-manifest", "fail", "report bytes do not match the manifest digest")
    return _check("report-manifest", "pass", f"report digest matches ({actual[:12]})")


def _git_command(root: Path, *args: str) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(
            ["git", "-C", str(root), *args],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=_GIT_TIMEOUT,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None


def _git_head(root: Path) -> str | None:
    proc = _git_command(root, "rev-parse", "HEAD")
    if proc is None or proc.returncode != 0:
        return None
    value = proc.stdout.strip()
    return value or None


def _worktree_check(root: Path, allowed_paths: set[str]) -> dict[str, str]:
    proc = _git_command(root, "status", "--porcelain=v1", "--untracked-files=all")
    if proc is None or proc.returncode != 0:
        return _check("worktree-state", "unverifiable", "repository status could not be read")
    unexpected: list[str] = []
    for line in proc.stdout.splitlines():
        if len(line) < 4:
            unexpected.append("<malformed-status-entry>")
            continue
        raw = line[3:].strip()
        # Porcelain rename output uses "old -> new". Either side outside the allowed
        # evidence set means the tree changed after verification.
        paths = [part.strip().strip('"') for part in raw.split(" -> ")]
        for item in paths:
            normalized = item.replace("\\", "/")
            if normalized not in allowed_paths:
                unexpected.append(normalized)
    if unexpected:
        shown = ", ".join(sorted(set(unexpected))[:5])
        return _check("worktree-state", "unverifiable", f"tree has changes outside evidence files: {shown}")
    return _check("worktree-state", "pass", "tree differs only by the supplied evidence artifacts")


def _provenance_checks(
    report: dict[str, Any],
    root: Path,
    report_path: Path,
    tasks_state_path: Path,
    extra_allowed_paths: list[Path] | None = None,
) -> list[dict[str, str]]:
    checks: list[dict[str, str]] = []
    provenance = report.get("provenance")
    if not isinstance(provenance, dict):
        return [_check("report-provenance", "unverifiable", "report has no provenance object")]

    recorded_commit = provenance.get("source_commit")
    current_commit = _git_head(root)
    if not isinstance(recorded_commit, str) or not recorded_commit:
        checks.append(_check("source-commit", "unverifiable", "report records no source commit"))
    elif current_commit is None:
        checks.append(_check("source-commit", "unverifiable", "trusted root is not a readable git work tree"))
    elif recorded_commit != current_commit:
        checks.append(
            _check(
                "source-commit",
                "unverifiable",
                f"report is stale, recorded {recorded_commit[:12]} but current HEAD is {current_commit[:12]}",
            )
        )
    else:
        checks.append(_check("source-commit", "pass", f"report source matches HEAD ({current_commit[:12]})"))

    if provenance.get("working_tree_clean") is True:
        checks.append(_check("recorded-tree-state", "pass", "verifier recorded a clean tree at verification start"))
    else:
        checks.append(
            _check("recorded-tree-state", "unverifiable", "verifier did not record a clean tree at verification start")
        )

    allowed = {
        _relative(report_path, root),
        _relative(report_path.with_name(report_path.name + ".sha256"), root),
        _relative(tasks_state_path, root),
    }
    for path in extra_allowed_paths or []:
        allowed.add(_relative(path, root))
    checks.append(_worktree_check(root, allowed))
    return checks


def _tasks_state_hash_check(
    report: dict[str, Any],
    tasks_state_bytes: bytes,
) -> dict[str, str]:
    provenance = report.get("provenance")
    expected = provenance.get("tasks_state_sha256") if isinstance(provenance, dict) else None
    if not isinstance(expected, str) or len(expected) != 64:
        return _check("tasks-state-digest", "unverifiable", "report has no valid tasks-state SHA-256")
    actual = _sha256(tasks_state_bytes)
    if not hmac.compare_digest(expected.lower(), actual):
        return _check("tasks-state-digest", "fail", "tasks-state bytes do not match report provenance")
    return _check("tasks-state-digest", "pass", f"tasks-state digest matches ({actual[:12]})")


def _task_semantic_checks(
    report: dict[str, Any],
    tasks_state: dict[str, Any],
) -> list[dict[str, str]]:
    checks: list[dict[str, str]] = []
    if report.get("schema_version") != REPORT_SCHEMA_VERSION:
        checks.append(
            _check(
                "report-schema-version",
                "unverifiable",
                f"unsupported verification-report schema: {report.get('schema_version')!r}",
            )
        )
    else:
        checks.append(_check("report-schema-version", "pass", "verification-report schema version is supported"))

    report_feature = report.get("feature_id")
    state_feature = tasks_state.get("feature_id")
    if not isinstance(report_feature, str) or not report_feature:
        checks.append(_check("feature-binding", "unverifiable", "report has no feature_id"))
    elif state_feature != report_feature:
        checks.append(_check("feature-binding", "fail", "report feature_id does not match tasks-state feature_id"))
    else:
        checks.append(_check("feature-binding", "pass", f"feature binding matches ({report_feature})"))

    report_tasks = report.get("tasks")
    state_tasks = tasks_state.get("tasks")
    if not isinstance(report_tasks, list) or not isinstance(state_tasks, list):
        checks.append(_check("task-set", "unverifiable", "report or tasks-state has no tasks array"))
        return checks

    state_by_id: dict[str, dict[str, Any]] = {}
    malformed_state = False
    for item in state_tasks:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            malformed_state = True
            continue
        state_by_id[item["id"]] = item
    report_by_id: dict[str, dict[str, Any]] = {}
    malformed_report = False
    for item in report_tasks:
        if not isinstance(item, dict) or not isinstance(item.get("task_id"), str):
            malformed_report = True
            continue
        report_by_id[item["task_id"]] = item

    if malformed_state or malformed_report or not state_by_id:
        checks.append(_check("task-set", "unverifiable", "task records are malformed or empty"))
        return checks
    if set(state_by_id) != set(report_by_id):
        checks.append(_check("task-set", "fail", "report task ids do not exactly match tasks-state task ids"))
        return checks
    checks.append(_check("task-set", "pass", f"report covers all {len(state_by_id)} tasks"))

    direct_failures: list[str] = []
    ambiguous: list[str] = []
    weak_passes: list[str] = []
    pending: list[str] = []
    for task_id, state_item in state_by_id.items():
        report_item = report_by_id[task_id]
        state_status = state_item.get("status")
        claimed = report_item.get("claimed_status")
        verified = report_item.get("verified_status")
        confidence = report_item.get("confidence")
        if state_status != "done" or claimed != "done":
            pending.append(task_id)
            continue
        if verified == "fail":
            direct_failures.append(task_id)
            continue
        if verified != "pass":
            ambiguous.append(task_id)
            continue
        if confidence == "ambiguous" or confidence not in {"extracted", "inferred"}:
            ambiguous.append(task_id)
            continue
        evidence = report_item.get("evidence")
        files_checked = report_item.get("files_checked")
        tests_run = report_item.get("tests_run")
        has_evidence = any(
            isinstance(value, list) and bool(value)
            for value in (evidence, files_checked, tests_run)
        )
        if not has_evidence:
            weak_passes.append(task_id)

    if pending:
        checks.append(_check("task-completion", "fail", f"milestone still has pending tasks: {', '.join(pending)}"))
    else:
        checks.append(_check("task-completion", "pass", "every tasks-state item is marked done"))
    if direct_failures:
        checks.append(_check("task-verdicts", "fail", f"verification failed tasks: {', '.join(direct_failures)}"))
    elif ambiguous:
        checks.append(_check("task-verdicts", "unverifiable", f"ambiguous task verdicts: {', '.join(ambiguous)}"))
    elif weak_passes:
        checks.append(_check("task-verdicts", "unverifiable", f"passes without concrete evidence: {', '.join(weak_passes)}"))
    else:
        checks.append(_check("task-verdicts", "pass", "every completed task has a non-ambiguous evidenced pass"))

    summary = report.get("summary")
    if not isinstance(summary, dict):
        checks.append(_check("report-summary", "unverifiable", "report has no summary object"))
        return checks
    verdict = summary.get("verdict")
    if verdict == "fail":
        checks.append(_check("report-summary", "fail", "verification report summary is fail"))
    elif verdict == "conditional_pass":
        checks.append(_check("report-summary", "unverifiable", "conditional pass cannot authorize advancement"))
    elif verdict == "pass":
        checks.append(_check("report-summary", "pass", "verification report summary is pass"))
    else:
        checks.append(_check("report-summary", "unverifiable", f"unknown report verdict: {verdict!r}"))

    done_count = sum(1 for item in state_by_id.values() if item.get("status") == "done")
    actual_pass = sum(
        1
        for item in report_by_id.values()
        if item.get("claimed_status") == "done"
        and item.get("verified_status") == "pass"
        and item.get("confidence") != "ambiguous"
    )
    actual_fail = sum(
        1
        for item in report_by_id.values()
        if item.get("claimed_status") == "done"
        and item.get("verified_status") == "fail"
        and item.get("confidence") != "ambiguous"
    )
    actual_ambiguous = sum(
        1
        for item in report_by_id.values()
        if item.get("claimed_status") == "done" and item.get("confidence") == "ambiguous"
    )
    expected_counts = (
        summary.get("total_done_tasks"),
        summary.get("mechanically_passed"),
        summary.get("mechanically_failed"),
        summary.get("ambiguous"),
    )
    actual_counts = (done_count, actual_pass, actual_fail, actual_ambiguous)
    if expected_counts != actual_counts:
        checks.append(
            _check(
                "summary-counts",
                "fail",
                f"summary counts {expected_counts!r} do not match task evidence {actual_counts!r}",
            )
        )
    else:
        checks.append(_check("summary-counts", "pass", "summary counts agree with task evidence"))

    policy_results = report.get("policy_results", [])
    if not isinstance(policy_results, list):
        checks.append(_check("policy-results", "unverifiable", "policy_results is not an array"))
    else:
        failed_policies: list[str] = []
        warned_policies: list[str] = []
        malformed_policy = False
        for item in policy_results:
            if not isinstance(item, dict) or not isinstance(item.get("policy_id"), str):
                malformed_policy = True
                continue
            result = item.get("result")
            if result == "fail":
                failed_policies.append(item["policy_id"])
            elif result == "warn":
                warned_policies.append(item["policy_id"])
            elif result != "pass":
                malformed_policy = True
        if failed_policies:
            checks.append(_check("policy-results", "fail", f"failed policies: {', '.join(failed_policies)}"))
        elif warned_policies:
            checks.append(_check("policy-results", "unverifiable", f"policy warnings require review: {', '.join(warned_policies)}"))
        elif malformed_policy:
            checks.append(_check("policy-results", "unverifiable", "policy results contain malformed entries"))
        else:
            checks.append(_check("policy-results", "pass", "no policy failure or warning is recorded"))
    return checks


_SIGNER: Any = None


def _signer() -> Any:
    global _SIGNER
    if _SIGNER is None:
        path = Path(__file__).resolve().parent / "scripts" / "preaction_sign.py"
        spec = importlib.util.spec_from_file_location("mergen_preaction_sign", path)
        if spec is None or spec.loader is None:
            raise ImportError("cannot load preaction_sign.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _SIGNER = module
    return _SIGNER


def _approval_check(
    report: dict[str, Any],
    report_bytes: bytes,
    token: str | None,
) -> dict[str, str]:
    summary = report.get("summary")
    if not isinstance(summary, dict):
        return _check("human-approval", "unverifiable", "report has no summary for approval evaluation")
    required = summary.get("human_review_required")
    review = summary.get("human_review")

    if required is not True:
        if token is None:
            return _check("human-approval", "pass", "human approval is not required for this report")
        # A supplied token is evidence. Refuse to ignore it if it is invalid.
    else:
        if not isinstance(review, dict):
            return _check("human-approval", "unverifiable", "required human review record is missing")
        status = review.get("status")
        if status == "rejected":
            return _check("human-approval", "fail", "human reviewer rejected the milestone")
        if status != "approved":
            return _check("human-approval", "unverifiable", "required human review is not approved")
        if not isinstance(review.get("reviewer"), str) or not review.get("reviewer"):
            return _check("human-approval", "unverifiable", "approval records no reviewer")
        if not isinstance(review.get("approved_at"), str) or not review.get("approved_at"):
            return _check("human-approval", "unverifiable", "approval records no timestamp")
        evidence = review.get("evidence")
        if not isinstance(evidence, list) or not evidence:
            return _check("human-approval", "unverifiable", "approval records no evidence")
        if token is None:
            return _check("human-approval", "unverifiable", "approval is not bound to the report bytes")

    key = os.environ.get(SIGNING_KEY_ENV, "")
    if not key:
        return _check("human-approval", "unverifiable", f"{SIGNING_KEY_ENV} is unavailable for token verification")
    assert token is not None
    try:
        digest = _signer().artifact_hash(report_bytes)
        valid = bool(_signer().verify(digest, token, key))
    except (ImportError, OSError, ValueError) as exc:
        return _check("human-approval", "unverifiable", f"approval token could not be verified: {exc}")
    if not valid:
        return _check("human-approval", "fail", "approval token does not authorize these exact report bytes")
    return _check("human-approval", "pass", "artifact-bound human approval token is valid")


def _review_observation(
    review: dict[str, Any] | None,
) -> tuple[dict[str, Any] | None, dict[str, str] | None]:
    if review is None:
        return None, None
    verdict_raw = review.get("verdict", review.get("status"))
    verdict = verdict_raw.lower() if isinstance(verdict_raw, str) else None
    reviewer = review.get("reviewer")
    claimed_independent = review.get("independent") is True or review.get("claimed_independent") is True
    ignored_root_fields = sorted(key for key in ("root", "workspace_root", "repository_root") if key in review)
    observation: dict[str, Any] = {
        "reviewer_claim": reviewer if isinstance(reviewer, str) else None,
        "verdict_claim": verdict,
        "claimed_independent": claimed_independent,
        "independence_verified": False,
        "used_as_positive_proof": False,
        "ignored_root_fields": ignored_root_fields,
    }
    if verdict in {"fail", "failed", "reject", "rejected"}:
        return observation, _check("external-review", "fail", "external review records a negative verdict")
    if verdict in {"unverifiable", "unknown", "ambiguous", "pending"}:
        return observation, _check("external-review", "unverifiable", "external review is unresolved")
    if verdict in {"pass", "passed", "approve", "approved"}:
        return observation, _check(
            "external-review",
            "pass",
            "positive review claim observed but not used as proof of reviewer independence",
        )
    return observation, _check("external-review", "unverifiable", "external review has no recognized verdict")


def _decision(
    milestone_id: str,
    checks: list[dict[str, str]],
    source: dict[str, Any],
    review_observation: dict[str, Any] | None,
) -> dict[str, Any]:
    results = {item["result"] for item in checks}
    if "fail" in results:
        verdict = "fail"
    elif "unverifiable" in results or not checks:
        verdict = "unverifiable"
    else:
        verdict = "pass"
    action = "advance" if verdict == "pass" else "block"
    decision: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "milestone_id": milestone_id,
        "evaluated_at": datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z"),
        "verdict": verdict,
        "decision": action,
        "checks": checks,
        "source": source,
        "authority": {
            "mode": "deterministic-separate-process",
            "implements_changes": False,
            "trusts_self_declared_independence": False,
        },
    }
    if review_observation is not None:
        decision["review_observation"] = review_observation
    # Structural invariant. Keep it executable at the boundary where the artifact is built.
    if decision["decision"] == "advance" and decision["verdict"] != "pass":
        raise AssertionError("only pass may authorize advance")
    return decision


def _blocked_decision(
    milestone_id: str,
    check: dict[str, str],
    *,
    source: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return _decision(milestone_id, [check], source or {}, None)


def supervise(
    *,
    root: Path,
    report_arg: str,
    tasks_state_arg: str,
    milestone_id: str | None = None,
    approval_token: str | None = None,
    approval_token_path_arg: str | None = None,
    review_arg: str | None = None,
) -> dict[str, Any]:
    """Collect evidence under root and return a fail-closed milestone decision."""
    trusted_root = root.resolve()
    selected_id = milestone_id or "unknown"
    try:
        report_path = _safe_evidence_path(report_arg, trusted_root, kind="report")
        tasks_state_path = _safe_evidence_path(tasks_state_arg, trusted_root, kind="tasks-state")
        review_path = (
            _safe_evidence_path(review_arg, trusted_root, kind="review-record")
            if review_arg is not None
            else None
        )
        approval_token_path = (
            _safe_evidence_path(approval_token_path_arg, trusted_root, kind="approval-token")
            if approval_token_path_arg is not None
            else None
        )
    except UnsafeEvidencePath as exc:
        return _blocked_decision(selected_id, _check("evidence-paths", "unverifiable", str(exc)))

    report, report_bytes, report_read = _read_json(report_path, kind="report")
    if report is None or report_bytes is None:
        return _blocked_decision(
            selected_id,
            report_read,
            source={"report": _relative(report_path, trusted_root)},
        )
    if milestone_id is None and isinstance(report.get("feature_id"), str):
        selected_id = report["feature_id"]

    tasks_state, tasks_state_bytes, state_read = _read_json(tasks_state_path, kind="tasks-state")
    checks: list[dict[str, str]] = [report_read, state_read]
    source: dict[str, Any] = {
        "report": _relative(report_path, trusted_root),
        "report_sha256": _sha256(report_bytes),
        "tasks_state": _relative(tasks_state_path, trusted_root),
        "tasks_state_sha256": _sha256(tasks_state_bytes) if tasks_state_bytes is not None else None,
        "source_commit": (report.get("provenance") or {}).get("source_commit")
        if isinstance(report.get("provenance"), dict)
        else None,
    }
    if tasks_state is None or tasks_state_bytes is None:
        return _decision(selected_id, checks, source, None)

    checks.append(_manifest_check(report_path, report_bytes))
    extra_allowed = [path for path in (review_path, approval_token_path) if path is not None]
    checks.extend(
        _provenance_checks(
            report,
            trusted_root,
            report_path,
            tasks_state_path,
            extra_allowed_paths=extra_allowed,
        )
    )
    checks.append(_tasks_state_hash_check(report, tasks_state_bytes))
    checks.extend(_task_semantic_checks(report, tasks_state))
    checks.append(_approval_check(report, report_bytes, approval_token))

    observation: dict[str, Any] | None = None
    if review_path is not None:
        review, _, review_read = _read_json(review_path, kind="review-record")
        checks.append(review_read)
        observation, review_check = _review_observation(review)
        if review_check is not None:
            checks.append(review_check)

    return _decision(selected_id, checks, source, observation)


def _read_token(path_arg: str | None, root: Path) -> tuple[str | None, dict[str, str] | None]:
    if path_arg is None:
        value = os.environ.get(APPROVAL_TOKEN_ENV)
        return (value.strip() if value else None), None
    try:
        path = _safe_evidence_path(path_arg, root, kind="approval-token")
        value = path.read_text(encoding="utf-8-sig").strip()
    except (UnsafeEvidencePath, OSError) as exc:
        return None, _check("approval-token-input", "unverifiable", f"approval token cannot be read: {exc}")
    if not value:
        return None, _check("approval-token-input", "unverifiable", "approval token file is empty")
    return value, _check("approval-token-input", "pass", "approval token was read from a file inside root")


def _write_decision(path: Path, decision: dict[str, Any]) -> None:
    payload = (json.dumps(decision, indent=2, sort_keys=True) + "\n").encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    digest = _sha256(payload)
    sidecar = path.with_name(path.name + ".sha256")
    sidecar.write_text(f"{digest}  {path.name}\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mergen-supervise",
        description="Issue a fail-closed milestone verdict from independent verification evidence.",
    )
    parser.add_argument("--root", default=".", help="trusted repository root selected by the operator")
    parser.add_argument("--report", required=True, help="verification-report JSON inside --root")
    parser.add_argument("--tasks-state", required=True, help="tasks-state JSON inside --root")
    parser.add_argument("--milestone-id", default=None, help="explicit milestone id, defaults to report feature_id")
    parser.add_argument(
        "--approval-token-file",
        default=None,
        help=f"artifact-bound approval token file inside --root, otherwise read {APPROVAL_TOKEN_ENV}",
    )
    parser.add_argument(
        "--review-record",
        default=None,
        help="optional external review JSON to observe, never accepted as proof of independence",
    )
    parser.add_argument("--out", default=None, help="write decision JSON and a .sha256 sidecar")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    token, token_check = _read_token(args.approval_token_file, root)
    decision = supervise(
        root=root,
        report_arg=args.report,
        tasks_state_arg=args.tasks_state,
        milestone_id=args.milestone_id,
        approval_token=token,
        approval_token_path_arg=args.approval_token_file,
        review_arg=args.review_record,
    )
    if token_check is not None:
        decision["checks"].insert(0, token_check)
        # Recompute after adding a potentially blocking token-input check.
        decision = _decision(
            decision["milestone_id"],
            decision["checks"],
            decision["source"],
            decision.get("review_observation"),
        )

    rendered = json.dumps(decision, indent=2, sort_keys=True)
    if args.out:
        _write_decision(Path(args.out), decision)
    else:
        print(rendered)

    verdict = decision["verdict"]
    if verdict == "pass":
        return 0
    if verdict == "fail":
        return 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
