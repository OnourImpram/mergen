#!/usr/bin/env python3
"""Independent, fail-closed milestone supervision for Mergen.

The supervisor consumes artifacts produced by an external executor, reproduces the
available deterministic evidence, and returns an advancement decision. It is read-only
with respect to implementation artifacts. Its only writes are the requested decision
report, a SHA-256 sidecar, and a human-readable Markdown rendering.

Exit codes: 0 pass, 1 fail, 2 conditional_pass or unverifiable.
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
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "1.1"
REPORT_SCHEMA_VERSION = "1.0"
VERIFIER_VERSION = "2.0"
SIGNING_KEY_ENV = "MERGEN_SIGNING_KEY"
APPROVAL_TOKEN_ENV = "MERGEN_ACK_TOKEN"
_GIT_TIMEOUT = 30
_RESULTS = frozenset({"pass", "fail", "unverifiable"})
_HEX = frozenset("0123456789abcdef")
_MODULES: dict[str, Any] = {}


class UnsafeEvidencePath(ValueError):
    """An evidence path escaped the operator-selected repository root."""


def _check(check_id: str, result: str, reason: str, evidence_class: str = "independently_observed") -> dict[str, str]:
    if result not in _RESULTS:
        raise ValueError(f"unknown check result: {result}")
    return {
        "check_id": check_id,
        "result": result,
        "reason": reason,
        "evidence_class": evidence_class,
    }


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _is_digest(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(ch in _HEX for ch in value.lower())


def _safe_evidence_path(raw: str, root: Path, *, kind: str) -> Path:
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


def _read_json(path: Path, kind: str) -> tuple[dict[str, Any] | None, bytes | None, dict[str, str]]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        return None, None, _check(f"{kind}-readable", "unverifiable", f"{kind} cannot be read: {exc}", "unavailable")
    try:
        value: Any = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return None, raw, _check(f"{kind}-readable", "unverifiable", f"{kind} is not valid JSON: {exc}", "unavailable")
    if not isinstance(value, dict):
        return None, raw, _check(f"{kind}-readable", "unverifiable", f"{kind} must be a JSON object", "unavailable")
    return value, raw, _check(f"{kind}-readable", "pass", f"{kind} is readable JSON")


def _manifest_check(report_path: Path, report_bytes: bytes) -> dict[str, str]:
    sidecar = report_path.with_name(report_path.name + ".sha256")
    try:
        fields = sidecar.read_text(encoding="utf-8-sig").split()
    except OSError as exc:
        return _check("report-manifest", "unverifiable", f"manifest sidecar cannot be read: {exc}", "unavailable")
    if not fields or not _is_digest(fields[0]):
        return _check("report-manifest", "unverifiable", "manifest sidecar has no valid SHA-256 digest", "unavailable")
    actual = _sha256(report_bytes)
    if not hmac.compare_digest(fields[0].lower(), actual):
        return _check("report-manifest", "fail", "report bytes do not match the manifest digest", "conflicting")
    return _check("report-manifest", "pass", f"report digest matches ({actual[:12]})", "cryptographically_verified")


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[bytes] | None:
    try:
        return subprocess.run(
            ["git", "-C", str(root), *args],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=_GIT_TIMEOUT,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None


def _git_head(root: Path) -> str | None:
    proc = _git(root, "rev-parse", "HEAD")
    if proc is None or proc.returncode != 0:
        return None
    value = proc.stdout.decode("ascii", errors="replace").strip()
    return value or None


def _status_paths(raw: bytes) -> tuple[list[str], bool]:
    records = raw.split(b"\x00")
    paths: list[str] = []
    malformed = False
    index = 0
    while index < len(records):
        record = records[index]
        index += 1
        if not record:
            continue
        if len(record) < 4:
            malformed = True
            continue
        status = record[:2].decode("ascii", errors="replace")
        paths.append(record[3:].decode("utf-8", errors="surrogateescape").replace("\\", "/"))
        if "R" in status or "C" in status:
            if index >= len(records) or not records[index]:
                malformed = True
            else:
                paths.append(records[index].decode("utf-8", errors="surrogateescape").replace("\\", "/"))
                index += 1
    return paths, malformed


def _worktree_check(root: Path, allowed_paths: set[str]) -> dict[str, str]:
    proc = _git(root, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    if proc is None or proc.returncode != 0:
        return _check("worktree-state", "unverifiable", "repository status could not be read", "unavailable")
    paths, malformed = _status_paths(proc.stdout)
    unexpected = [path for path in paths if path not in allowed_paths]
    if malformed:
        unexpected.append("<malformed-status-entry>")
    if unexpected:
        shown = ", ".join(sorted(set(unexpected))[:5])
        return _check(
            "worktree-state", "unverifiable",
            f"tree has changes outside evidence files: {shown}", "conflicting"
        )
    return _check("worktree-state", "pass", "tree differs only by the supplied evidence artifacts")


def _provenance_checks(
    report: dict[str, Any],
    root: Path,
    report_path: Path,
    tasks_path: Path,
    extra_paths: list[Path],
) -> list[dict[str, str]]:
    provenance = report.get("provenance")
    if not isinstance(provenance, dict):
        return [_check("report-provenance", "unverifiable", "report has no provenance object", "unavailable")]
    checks: list[dict[str, str]] = []
    recorded = provenance.get("source_commit")
    current = _git_head(root)
    if not isinstance(recorded, str) or not recorded:
        checks.append(_check("source-commit", "unverifiable", "report records no source commit", "unavailable"))
    elif current is None:
        checks.append(_check(
            "source-commit", "unverifiable",
            "trusted root is not a readable git work tree", "unavailable"
        ))
    elif recorded != current:
        reason = f"report is stale, recorded {recorded[:12]} but current HEAD is {current[:12]}"
        checks.append(_check("source-commit", "unverifiable", reason, "conflicting"))
    else:
        checks.append(_check(
            "source-commit", "pass",
            f"report source matches HEAD ({current[:12]})", "source_verified"
        ))
    tree_clean = provenance.get("working_tree_clean") is True
    result = "pass" if tree_clean else "unverifiable"
    reason = (
        "verifier recorded a clean tree at verification start"
        if tree_clean else "verifier did not record a clean tree"
    )
    checks.append(_check("recorded-tree-state", result, reason, "source_verified" if tree_clean else "unavailable"))
    allowed = {
        _relative(report_path, root),
        _relative(report_path.with_name(report_path.name + ".sha256"), root),
        _relative(tasks_path, root),
    }
    allowed.update(_relative(path, root) for path in extra_paths)
    checks.append(_worktree_check(root, allowed))
    return checks


def _tasks_hash_check(report: dict[str, Any], tasks_bytes: bytes) -> dict[str, str]:
    provenance = report.get("provenance")
    expected = provenance.get("tasks_state_sha256") if isinstance(provenance, dict) else None
    if not _is_digest(expected):
        return _check("tasks-state-digest", "unverifiable", "report has no valid tasks-state digest", "unavailable")
    actual = _sha256(tasks_bytes)
    if not hmac.compare_digest(str(expected).lower(), actual):
        return _check("tasks-state-digest", "fail", "tasks-state bytes do not match report provenance", "conflicting")
    return _check(
        "tasks-state-digest", "pass",
        f"tasks-state digest matches ({actual[:12]})",
        "cryptographically_verified"
    )


def _index(items: object, key: str) -> tuple[dict[str, dict[str, Any]], bool]:
    if not isinstance(items, list):
        return {}, True
    indexed: dict[str, dict[str, Any]] = {}
    malformed = False
    for item in items:
        if not isinstance(item, dict):
            malformed = True
            continue
        item_id = item.get(key)
        if not isinstance(item_id, str) or not item_id or item_id in indexed:
            malformed = True
            continue
        indexed[item_id] = item
    return indexed, malformed


def _semantic_checks(
    report: dict[str, Any], tasks_state: dict[str, Any], explicit_milestone_id: str | None = None
) -> list[dict[str, str]]:
    checks: list[dict[str, str]] = []
    report_version = report.get("schema_version")
    state_version = tasks_state.get("schema_version")
    checks.append(_check(
        "report-schema-version",
        "pass" if report_version == REPORT_SCHEMA_VERSION else "unverifiable",
        f"verification-report schema is {report_version!r}"
    ))
    checks.append(_check(
        "tasks-schema-version",
        "pass" if state_version == "1.0" else "unverifiable",
        f"tasks-state schema is {state_version!r}"
    ))
    feature = report.get("feature_id")
    if not isinstance(feature, str) or not feature:
        checks.append(_check("feature-binding", "unverifiable", "report has no feature_id", "unavailable"))
    elif tasks_state.get("feature_id") != feature:
        checks.append(_check("feature-binding", "fail", "feature identifiers conflict", "conflicting"))
    elif explicit_milestone_id is not None and explicit_milestone_id != feature:
        checks.append(_check(
            "feature-binding", "fail",
            "explicit milestone id conflicts with report feature_id", "conflicting"
        ))
    else:
        checks.append(_check("feature-binding", "pass", f"feature binding matches ({feature})", "source_verified"))
    state, bad_state = _index(tasks_state.get("tasks"), "id")
    supplied, bad_report = _index(report.get("tasks"), "task_id")
    if bad_state or bad_report or not state:
        checks.append(_check(
            "task-set", "unverifiable",
            "task records are malformed, duplicated, or empty", "unavailable"
        ))
        return checks
    if set(state) != set(supplied):
        checks.append(_check("task-set", "fail", "report task ids do not exactly match tasks-state", "conflicting"))
        return checks
    checks.append(_check("task-set", "pass", f"report covers all {len(state)} tasks", "source_verified"))
    pending: list[str] = []
    failed: list[str] = []
    ambiguous: list[str] = []
    weak: list[str] = []
    for task_id, state_item in state.items():
        item = supplied[task_id]
        if state_item.get("status") != "done" or item.get("claimed_status") != "done":
            pending.append(task_id)
            continue
        confidence = item.get("confidence")
        if confidence == "ambiguous" or confidence not in {"extracted", "inferred"}:
            ambiguous.append(task_id)
            continue
        if item.get("verified_status") == "fail":
            failed.append(task_id)
            continue
        if item.get("verified_status") != "pass":
            ambiguous.append(task_id)
            continue
        evidence = (item.get("files_checked"), item.get("tests_run"), item.get("evidence"))
        if not any(isinstance(value, list) and value for value in evidence):
            weak.append(task_id)
    checks.append(_check(
        "task-completion", "fail" if pending else "pass",
        f"pending tasks: {', '.join(sorted(pending))}"
        if pending else "every task is marked done",
        "source_verified"
    ))
    if failed:
        checks.append(_check("task-verdicts", "fail", f"failed tasks: {', '.join(sorted(failed))}", "source_verified"))
    elif ambiguous:
        checks.append(_check(
            "task-verdicts", "unverifiable",
            f"ambiguous tasks: {', '.join(sorted(ambiguous))}", "unavailable"
        ))
    elif weak:
        checks.append(_check(
            "task-verdicts", "unverifiable",
            f"passes without evidence: {', '.join(sorted(weak))}", "unavailable"
        ))
    else:
        checks.append(_check("task-verdicts", "pass", "every completed task has an evidenced pass", "source_verified"))
    summary = report.get("summary")
    if not isinstance(summary, dict):
        checks.append(_check("report-summary", "unverifiable", "report has no summary", "unavailable"))
        return checks
    verdict = summary.get("verdict")
    summary_result = "pass" if verdict == "pass" else "fail" if verdict == "fail" else "unverifiable"
    checks.append(_check("report-summary", summary_result, f"verification summary is {verdict!r}", "source_verified"))
    done = sum(item.get("status") == "done" for item in state.values())
    passed = sum(
        item.get("claimed_status") == "done"
        and item.get("verified_status") == "pass"
        and item.get("confidence") == "extracted"
        for item in supplied.values()
    )
    direct_fail = sum(
        item.get("claimed_status") == "done"
        and item.get("verified_status") == "fail"
        and item.get("confidence") == "extracted"
        for item in supplied.values()
    )
    unsure = sum(
        item.get("claimed_status") == "done"
        and item.get("confidence") == "ambiguous"
        for item in supplied.values()
    )
    expected = (
        summary.get("total_done_tasks"), summary.get("mechanically_passed"),
        summary.get("mechanically_failed"), summary.get("ambiguous")
    )
    actual = (done, passed, direct_fail, unsure)
    checks.append(_check(
        "summary-counts", "pass" if expected == actual else "fail",
        "summary counts agree with task evidence"
        if expected == actual else f"summary counts {expected!r} conflict with {actual!r}",
        "source_verified" if expected == actual else "conflicting"
    ))
    policies = report.get("policy_results", [])
    if not isinstance(policies, list):
        checks.append(_check("policy-results", "unverifiable", "policy_results is not an array", "unavailable"))
    else:
        bad: list[str] = []
        warned: list[str] = []
        malformed = False
        for item in policies:
            if not isinstance(item, dict):
                malformed = True
                continue
            policy_id, result = item.get("policy_id"), item.get("result")
            if not isinstance(policy_id, str) or not policy_id:
                malformed = True
                continue
            if result == "fail":
                bad.append(policy_id)
            elif result == "warn":
                warned.append(policy_id)
            elif result != "pass":
                malformed = True
        result = "fail" if bad else "unverifiable" if warned or malformed else "pass"
        if bad:
            reason = f"failed policies: {', '.join(sorted(bad))}"
        elif warned:
            reason = f"policy warnings: {', '.join(sorted(warned))}"
        elif malformed:
            reason = "policy results contain malformed entries"
        else:
            reason = "policy results are complete"
        checks.append(_check(
            "policy-results", result, reason,
            "source_verified" if result == "pass" else "conflicting"
        ))
    return checks


def _load_script(name: str) -> Any:
    if name in _MODULES:
        return _MODULES[name]
    path = Path(__file__).resolve().parent / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"mergen_{name}", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path.name}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    _MODULES[name] = module
    return module


def _reverify(
    tasks_state: dict[str, Any], root: Path
) -> tuple[dict[str, str], dict[str, Any] | None]:
    try:
        fresh, _ = _load_script("verify_core").build_report(tasks_state, root)
    except Exception as exc:  # noqa: BLE001, a verifier crash is an unverifiable outcome
        return _check(
            "independent-reverification", "unverifiable",
            f"fresh verification could not run: {exc}", "unavailable"
        ), None
    if not isinstance(fresh, dict):
        return _check(
            "independent-reverification", "unverifiable",
            "fresh verifier returned no report object", "unavailable"
        ), None
    summary = fresh.get("summary")
    verdict = summary.get("verdict") if isinstance(summary, dict) else None
    if verdict == "fail":
        return _check(
            "independent-reverification", "fail",
            "fresh deterministic verification failed", "independently_executed"
        ), fresh
    if verdict != "pass":
        return _check(
            "independent-reverification", "unverifiable",
            f"fresh verification is {verdict!r}", "independently_executed"
        ), fresh
    return _check(
        "independent-reverification", "pass",
        "fresh deterministic verification passed", "independently_executed"
    ), fresh


def _risk_check(
    report: dict[str, Any], fresh_report: dict[str, Any] | None
) -> tuple[dict[str, str], dict[str, Any]]:
    supplied = report.get("summary")
    supplied = supplied if isinstance(supplied, dict) else {}
    fresh = fresh_report.get("summary") if isinstance(fresh_report, dict) else {}
    fresh = fresh if isinstance(fresh, dict) else {}
    supplied_risk, fresh_risk = supplied.get("risk_level"), fresh.get("risk_level")
    fresh_triggers = fresh.get("risk_triggers")
    supplied_triggers = supplied.get("risk_triggers")
    trigger_values: list[str] = []
    for values in (fresh_triggers, supplied_triggers):
        if isinstance(values, list):
            trigger_values.extend(item for item in values if isinstance(item, str))
    triggers = sorted(set(trigger_values))
    tiers = ("tiny", "standard", "spec", "high-trust")
    allowed = set(tiers)
    if supplied_risk not in allowed or fresh_risk not in allowed:
        info: dict[str, Any] = {
            "risk_level": None,
            "risk_triggers": triggers,
            "human_review_required": bool(triggers),
        }
        return _check(
            "governor-risk", "unverifiable",
            "supplied or freshly reproduced risk level is unsupported", "unavailable"
        ), info
    effective_risk = tiers[max(tiers.index(supplied_risk), tiers.index(fresh_risk))]
    trigger_requires_high = bool(triggers)
    effective_high = effective_risk == "high-trust" or trigger_requires_high
    if trigger_requires_high:
        effective_risk = "high-trust"
    info = {
        "risk_level": effective_risk,
        "risk_triggers": triggers,
        "human_review_required": (
            effective_high or supplied.get("human_review_required") is True
        ),
    }
    if (fresh_risk == "high-trust" or trigger_requires_high) and supplied_risk != "high-trust":
        return _check(
            "governor-risk", "fail",
            "fresh evidence or a recorded trigger requires high-trust, but the report downgraded it",
            "conflicting"
        ), info
    if effective_high and supplied.get("human_review_required") is not True:
        return _check(
            "governor-risk", "fail",
            "high-trust work did not declare required human review", "conflicting"
        ), info
    return _check(
        "governor-risk", "pass", f"effective risk is {effective_risk}"
    ), info


def _normalize_token(value: str) -> str:
    for line in value.strip().splitlines():
        key, separator, token = line.partition(":")
        if separator and key.strip().lower() == "mergen-ack-token":
            return token.strip()
    return value.strip()


def _approval_check(
    report: dict[str, Any], report_bytes: bytes, token: str | None,
    required_by_governor: bool = False,
) -> dict[str, str]:
    summary = report.get("summary")
    if not isinstance(summary, dict):
        return _check("human-approval", "unverifiable", "report has no summary", "unavailable")
    required = required_by_governor or summary.get("human_review_required") is True
    review = summary.get("human_review")
    if required:
        if not isinstance(review, dict):
            return _check("human-approval", "unverifiable", "required review record is missing", "unavailable")
        if review.get("status") == "rejected":
            return _check("human-approval", "fail", "human reviewer rejected the milestone", "human_attested")
        complete = (
            review.get("status") == "approved"
            and isinstance(review.get("reviewer"), str)
            and bool(review.get("reviewer"))
            and isinstance(review.get("approved_at"), str)
            and bool(review.get("approved_at"))
            and isinstance(review.get("evidence"), list)
            and bool(review.get("evidence"))
        )
        if not complete:
            return _check("human-approval", "unverifiable", "required human approval is incomplete", "unavailable")
        if token is None:
            return _check("human-approval", "unverifiable", "approval is not bound to the report bytes", "unavailable")
    elif token is None:
        return _check("human-approval", "pass", "human approval is not required")
    normalized = _normalize_token(token or "")
    if not _is_digest(normalized):
        return _check("human-approval", "unverifiable", "approval token is not valid hexadecimal", "unavailable")
    key = os.environ.get(SIGNING_KEY_ENV, "")
    if not key:
        return _check("human-approval", "unverifiable", f"{SIGNING_KEY_ENV} is unavailable", "unavailable")
    try:
        signer = _load_script("preaction_sign")
        valid = bool(signer.verify(signer.artifact_hash(report_bytes), normalized, key))
    except (ImportError, OSError, ValueError) as exc:
        return _check("human-approval", "unverifiable", f"approval token could not be verified: {exc}", "unavailable")
    if not valid:
        return _check("human-approval", "fail", "approval token does not authorize these report bytes", "conflicting")
    return _check(
        "human-approval", "pass",
        "artifact-bound human approval token is valid",
        "cryptographically_verified"
    )


def _review(review: dict[str, Any] | None) -> tuple[dict[str, Any] | None, dict[str, str] | None]:
    if review is None:
        return None, None
    raw = review.get("verdict", review.get("status"))
    verdict = raw.lower() if isinstance(raw, str) else None
    observation = {
        "reviewer_claim": review.get("reviewer") if isinstance(review.get("reviewer"), str) else None,
        "verdict_claim": verdict,
        "claimed_independent": review.get("independent") is True or review.get("claimed_independent") is True,
        "independence_verified": False,
        "used_as_positive_proof": False,
        "ignored_root_fields": sorted(key for key in ("root", "workspace_root", "repository_root") if key in review),
    }
    if verdict in {"fail", "failed", "reject", "rejected"}:
        return observation, _check("external-review", "fail", "external review is negative", "executor_supplied")
    if verdict in {"pass", "passed", "approve", "approved"}:
        return observation, _check(
            "external-review", "pass",
            "positive review claim observed but not used as independence proof",
            "executor_supplied"
        )
    return observation, _check("external-review", "unverifiable", "external review is unresolved", "executor_supplied")


def _decision_hash(decision: dict[str, Any]) -> str:
    body = {key: value for key, value in decision.items() if key != "decision_hash"}
    raw = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return _sha256(raw)


def _decision(
    milestone_id: str,
    checks: list[dict[str, str]],
    source: dict[str, Any],
    observation: dict[str, Any] | None,
) -> dict[str, Any]:
    failures = [item for item in checks if item["result"] == "fail"]
    unknown = [item for item in checks if item["result"] == "unverifiable"]
    approval_only = bool(unknown) and all(item["check_id"] == "human-approval" for item in unknown)
    if failures:
        verdict, action = "fail", "return_for_remediation"
    elif approval_only:
        verdict, action = "conditional_pass", "human_review_required"
    elif unknown or not checks:
        verdict, action = "unverifiable", "hold"
    else:
        verdict, action = "pass", "advance"
    decision: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "verifier_version": VERIFIER_VERSION,
        "milestone_id": milestone_id,
        "evaluated_at": datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z"),
        "verification_profile": "software-engineering/legacy-task-report@1",
        "verdict": verdict,
        "advancement_action": action,
        "decision": "advance" if verdict == "pass" else "block",
        "checks": checks,
        "evidence_summary": {
            evidence_class: sum(
                1 for item in checks if item.get("evidence_class") == evidence_class
            )
            for evidence_class in sorted(
                {item.get("evidence_class", "unavailable") for item in checks}
            )
        },
        "passed_criteria": [
            item["check_id"] for item in checks if item["result"] == "pass"
        ],
        "failed_criteria": [
            item["check_id"] for item in checks if item["result"] == "fail"
        ],
        "unverifiable_criteria": [
            item["check_id"] for item in checks if item["result"] == "unverifiable"
        ],
        "governor_decision": source.get("governor_decision", {}),
        "source": source,
        "authority": {
            "mode": "deterministic-separate-process",
            "implements_changes": False,
            "trusts_self_declared_independence": False,
            "starts_next_stage": False,
        },
        "honest_limitations": [
            "The verdict is bounded by the declared artifacts and checks that were available.",
            "Provenance proves lineage, not universal semantic correctness.",
            "The bundled profile verifies software task reports, not every domain artifact.",
        ],
    }
    if observation is not None:
        decision["review_observation"] = observation
    decision["decision_hash"] = _decision_hash(decision)
    if (decision["verdict"] == "pass") != (decision["advancement_action"] == "advance"):
        raise AssertionError("pass and advance must be equivalent")
    return decision


def _blocked(milestone_id: str, item: dict[str, str]) -> dict[str, Any]:
    return _decision(milestone_id, [item], {}, None)


def supervise(
    *,
    root: Path,
    report_arg: str,
    tasks_state_arg: str,
    milestone_id: str | None = None,
    approval_token: str | None = None,
    approval_token_path_arg: str | None = None,
    review_arg: str | None = None,
    reproduce: bool = True,
) -> dict[str, Any]:
    trusted_root = root.resolve()
    selected_id = milestone_id or "unknown"
    try:
        report_path = _safe_evidence_path(report_arg, trusted_root, kind="report")
        tasks_path = _safe_evidence_path(tasks_state_arg, trusted_root, kind="tasks-state")
        review_path = _safe_evidence_path(review_arg, trusted_root, kind="review") if review_arg else None
        token_path = (
            _safe_evidence_path(
                approval_token_path_arg, trusted_root, kind="approval-token"
            )
            if approval_token_path_arg else None
        )
    except UnsafeEvidencePath as exc:
        return _blocked(selected_id, _check("evidence-paths", "unverifiable", str(exc), "unavailable"))
    report, report_bytes, report_read = _read_json(report_path, "report")
    if report is None or report_bytes is None:
        return _decision(selected_id, [report_read], {"report": _relative(report_path, trusted_root)}, None)
    if milestone_id is None and isinstance(report.get("feature_id"), str):
        selected_id = report["feature_id"]
    tasks, tasks_bytes, tasks_read = _read_json(tasks_path, "tasks-state")
    checks = [report_read, tasks_read]
    source: dict[str, Any] = {
        "report": _relative(report_path, trusted_root),
        "report_sha256": _sha256(report_bytes),
        "tasks_state": _relative(tasks_path, trusted_root),
        "tasks_state_sha256": _sha256(tasks_bytes) if tasks_bytes is not None else None,
        "source_commit": (
            (report.get("provenance") or {}).get("source_commit")
            if isinstance(report.get("provenance"), dict) else None
        ),
        "independent_reverification": reproduce,
    }
    if tasks is None or tasks_bytes is None:
        return _decision(selected_id, checks, source, None)
    checks.append(_manifest_check(report_path, report_bytes))
    extras = [path for path in (review_path, token_path) if path is not None]
    checks.extend(_provenance_checks(report, trusted_root, report_path, tasks_path, extras))
    checks.append(_tasks_hash_check(report, tasks_bytes))
    checks.extend(_semantic_checks(report, tasks, milestone_id))
    if reproduce:
        reverify_check, fresh_report = _reverify(tasks, trusted_root)
    else:
        reverify_check = _check(
            "independent-reverification", "unverifiable",
            "fresh reproduction was disabled", "unavailable"
        )
        fresh_report = None
    checks.append(reverify_check)
    risk_check, risk_info = _risk_check(report, fresh_report)
    checks.append(risk_check)
    source["governor_decision"] = risk_info
    source["source_state_hash"] = _sha256(json.dumps(
        {
            "report_sha256": source.get("report_sha256"),
            "tasks_state_sha256": source.get("tasks_state_sha256"),
            "source_commit": source.get("source_commit"),
            "governor_decision": risk_info,
        },
        sort_keys=True, separators=(",", ":")
    ).encode("utf-8"))
    checks.append(_approval_check(
        report, report_bytes, approval_token,
        bool(risk_info.get("human_review_required"))
    ))
    observation: dict[str, Any] | None = None
    if review_path is not None:
        review_value, _, review_read = _read_json(review_path, "review-record")
        checks.append(review_read)
        observation, review_check = _review(review_value)
        if review_check is not None:
            checks.append(review_check)
    return _decision(selected_id, checks, source, observation)


def _read_token(path_arg: str | None, root: Path) -> tuple[str | None, dict[str, str] | None]:
    if path_arg is None:
        value = os.environ.get(APPROVAL_TOKEN_ENV)
        return (_normalize_token(value) if value else None), None
    try:
        path = _safe_evidence_path(path_arg, root, kind="approval-token")
        value = _normalize_token(path.read_text(encoding="utf-8-sig"))
    except (UnsafeEvidencePath, OSError) as exc:
        return None, _check(
            "approval-token-input", "unverifiable",
            f"approval token cannot be read: {exc}", "unavailable"
        )
    if not _is_digest(value):
        return None, _check("approval-token-input", "unverifiable", "approval token file is invalid", "unavailable")
    return value, _check("approval-token-input", "pass", "approval token was read inside root")


def _render_markdown(decision: dict[str, Any]) -> str:
    lines = [
        f"# Mergen milestone verification, {decision['milestone_id']}",
        "",
        f"**Verdict:** `{decision['verdict']}`",
        "",
        f"**Advancement action:** `{decision['advancement_action']}`",
        "",
        f"**Decision hash:** `{decision['decision_hash']}`",
        "",
        "## Checks",
        "",
        "| Check | Result | Evidence class | Reason |",
        "| --- | --- | --- | --- |",
    ]
    for item in decision.get("checks", []):
        reason = str(item.get("reason", "")).replace("|", "\\|").replace("\n", " ")
        lines.append(
            f"| `{item.get('check_id')}` | `{item.get('result')}` | "
            f"`{item.get('evidence_class')}` | {reason} |"
        )
    lines.extend(["", "## Honest limitations", ""])
    lines.extend(f"- {item}" for item in decision.get("honest_limitations", []))
    lines.append("")
    return "\n".join(lines)


def _write_decision(path: Path, decision: dict[str, Any], markdown_path: Path | None = None) -> None:
    payload = (json.dumps(decision, indent=2, sort_keys=True) + "\n").encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    path.with_name(path.name + ".sha256").write_text(f"{_sha256(payload)}  {path.name}\n", encoding="utf-8")
    target = markdown_path or path.with_suffix(".md")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(_render_markdown(decision), encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mergen-supervise", description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=".", help="trusted repository root selected by the operator")
    parser.add_argument("--report", required=True, help="verification-report JSON inside --root")
    parser.add_argument("--tasks-state", required=True, help="tasks-state JSON inside --root")
    parser.add_argument("--milestone-id", default=None, help="explicit milestone id, defaults to report feature_id")
    parser.add_argument(
        "--approval-token-file", default=None,
        help=f"approval token inside --root, otherwise read {APPROVAL_TOKEN_ENV}"
    )
    parser.add_argument("--review-record", default=None, help="optional external review record inside --root")
    parser.add_argument(
        "--no-reproduce", action="store_true",
        help="disable fresh reproduction, preventing a clean pass"
    )
    parser.add_argument("--out", default=None, help="write JSON, SHA-256 sidecar, and Markdown")
    parser.add_argument("--markdown-out", default=None, help="override the Markdown output path")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.markdown_out and not args.out:
        parser.error("--markdown-out requires --out")
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
        reproduce=not args.no_reproduce,
    )
    if token_check is not None:
        decision["checks"].insert(0, token_check)
        decision = _decision(
            decision["milestone_id"], decision["checks"],
            decision["source"], decision.get("review_observation")
        )
    if args.out:
        _write_decision(Path(args.out), decision, Path(args.markdown_out) if args.markdown_out else None)
    else:
        print(json.dumps(decision, indent=2, sort_keys=True))
    return 0 if decision["verdict"] == "pass" else 1 if decision["verdict"] == "fail" else 2


if __name__ == "__main__":
    raise SystemExit(main())
