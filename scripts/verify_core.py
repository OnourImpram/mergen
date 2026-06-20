"""Deterministic mechanical verification harness for Mergen task states.

Runs three filesystem and subprocess lenses against every done task and
emits a verification-report.json that validates against the schema at
core/schemas/verification-report.schema.json. Exit code 0 means every
applicable mechanical lens passed. Exit code 1 means at least one done
task failed a mechanical check.
"""

from __future__ import annotations

import argparse
import datetime
import subprocess
import sys
import json
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Canonical confidence vocabulary
#
# The one definition of how a verdict is known. Every surface that labels a
# claim references this single set: the verification-report schema enum,
# verify.md, core/CONVENTIONS.md, and MERGEN_PRINCIPLES.md (the prose home).
# Holding the labels in one place is the "unify the confidence vocabulary"
# guarantee. The code mirror here cannot drift from the schema because a test
# asserts CONFIDENCE_LABELS equals the schema enum.
# ---------------------------------------------------------------------------

CONFIDENCE_EXTRACTED = "extracted"
CONFIDENCE_INFERRED = "inferred"
CONFIDENCE_AMBIGUOUS = "ambiguous"

CONFIDENCE: dict[str, str] = {
    CONFIDENCE_EXTRACTED:
        "Backed by direct evidence the harness observed: a file on disk, a test "
        "exit code, a git record. The default for any mechanically checked verdict.",
    CONFIDENCE_INFERRED:
        "Reasoned from indirect signals rather than observed directly. Allowed for "
        "an agent lens that argues from context, never for a mechanical pass.",
    CONFIDENCE_AMBIGUOUS:
        "Evidence is absent or conflicting, so no confident verdict is possible. "
        "Resolves to fail, never to a guessed pass.",
}

#: The canonical label set, in calibration order (most to least grounded).
CONFIDENCE_LABELS: tuple[str, ...] = tuple(CONFIDENCE)


# ---------------------------------------------------------------------------
# Lens implementations
# ---------------------------------------------------------------------------


def lens_file_exists(files: list[str], root: Path) -> tuple[str, list[str], list[str]]:
    """Check that every declared file exists on disk relative to root.

    Returns a triple of (result, evidence, failures) where result is one of
    "pass", "fail", or "na".
    """
    if not files:
        return "na", [], []

    evidence: list[str] = []
    failures: list[str] = []
    for rel in files:
        target = root / rel
        if target.exists():
            evidence.append(f"exists: {rel}")
        else:
            failures.append(f"missing: {rel}")

    result = "fail" if failures else "pass"
    return result, evidence, failures


def lens_tests_pass(
    test_task: str | None, root: Path
) -> tuple[str, list[str], list[str]]:
    """Run pytest against test_task from root, capturing real exit code.

    Returns a triple of (result, evidence, failures).
    """
    if not test_task:
        return "na", [], []

    cmd = [sys.executable, "-m", "pytest", test_task, "-q"]
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(root),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except Exception as exc:
        return "fail", [], [f"pytest launch error: {exc}"]

    if proc.returncode == 0:
        evidence = [f"pytest exit 0 for {test_task}"]
        return "pass", evidence, []
    else:
        out = (proc.stdout or "").strip()
        err = (proc.stderr or "").strip()
        failures = [f"pytest exit {proc.returncode} for {test_task}"]
        if out:
            failures.append(out[-400:])
        if err:
            failures.append(err[-200:])
        return "fail", [], failures


def lens_git_consistent(
    files: list[str], root: Path
) -> tuple[str, list[str], list[str]]:
    """Check that every declared file is known to git (tracked or staged).

    A file counts as known if it appears in git status --porcelain output
    OR if git ls-files --error-unmatch succeeds for it. This covers both
    newly-added staged files and already-tracked files.

    Returns a triple of (result, evidence, failures).
    """
    if not files:
        return "na", [], []

    # Collect porcelain lines once for efficiency.
    try:
        porcelain = subprocess.run(
            ["git", "-C", str(root), "status", "--porcelain"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        porcelain_output = porcelain.stdout if porcelain.returncode == 0 else ""
    except Exception:
        porcelain_output = ""

    # Build a set of paths that appear in porcelain output.
    porcelain_paths: set[str] = set()
    for line in porcelain_output.splitlines():
        # Porcelain format: "XY path" or "XY old -> new" for renames.
        raw = line[3:].strip()
        if " -> " in raw:
            porcelain_paths.add(raw.split(" -> ")[-1].strip())
        else:
            porcelain_paths.add(raw)

    evidence: list[str] = []
    failures: list[str] = []

    for rel in files:
        # Normalize separators to forward slashes for git.
        norm = rel.replace("\\", "/")
        if norm in porcelain_paths or rel in porcelain_paths:
            evidence.append(f"git-porcelain: {rel}")
            continue

        # Check if the file is tracked in the committed tree.
        try:
            ls = subprocess.run(
                ["git", "-C", str(root), "ls-files", "--error-unmatch", rel],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            if ls.returncode == 0:
                evidence.append(f"git-tracked: {rel}")
                continue
        except Exception:
            pass

        failures.append(f"git-unknown: {rel}")

    result = "fail" if failures else "pass"
    return result, evidence, failures


# ---------------------------------------------------------------------------
# Task verification
# ---------------------------------------------------------------------------


def verify_task(task: dict[str, Any], root: Path) -> dict[str, Any]:
    """Run the three mechanical lenses against one done task.

    Returns a dict that is a valid verification-report tasks item.
    """
    task_id = task["id"]
    files: list[str] = task.get("files") or []
    test_task: str | None = task.get("test_task") or None

    fe_result, fe_evidence, fe_failures = lens_file_exists(files, root)
    tp_result, tp_evidence, tp_failures = lens_tests_pass(test_task, root)
    gc_result, gc_evidence, gc_failures = lens_git_consistent(files, root)

    all_results = [fe_result, tp_result, gc_result]
    applicable = [r for r in all_results if r != "na"]
    any_failed = any(r == "fail" for r in applicable)

    # Mechanical verdict: pass iff no applicable lens failed.
    if not applicable:
        # All lenses were na, cannot confirm nor deny.
        verified_status = "fail"
        confidence = CONFIDENCE_AMBIGUOUS
    elif any_failed:
        verified_status = "fail"
        confidence = CONFIDENCE_EXTRACTED
    else:
        verified_status = "pass"
        confidence = CONFIDENCE_EXTRACTED

    all_evidence = fe_evidence + tp_evidence + gc_evidence
    all_failures = fe_failures + tp_failures + gc_failures

    return {
        "task_id": task_id,
        "claimed_status": "done",
        "verified_status": verified_status,
        "confidence": confidence,
        "lens_file_exists": fe_result,
        "lens_tests_pass": tp_result,
        "lens_git_consistent": gc_result,
        "lens_spec_match": "deferred-to-LLM",
        "files_checked": list(files),
        "tests_run": [test_task] if test_task else [],
        "evidence": all_evidence,
        "failures": all_failures,
    }


# ---------------------------------------------------------------------------
# Report assembly
# ---------------------------------------------------------------------------


def build_report(
    tasks_state: dict[str, Any],
    root: Path,
) -> tuple[dict[str, Any], bool]:
    """Verify all done tasks and assemble the report dict.

    Returns (report, overall_pass) where overall_pass is True iff every
    applicable mechanical lens passed for every done task. Ambiguous tasks
    (all lenses na) are not counted as failures.
    """
    feature_id = tasks_state.get("feature_id", "unknown")
    tasks = tasks_state.get("tasks", [])

    done_tasks = [t for t in tasks if t.get("status") == "done"]
    verified_items: list[dict[str, Any]] = []

    for task in done_tasks:
        item = verify_task(task, root)
        verified_items.append(item)

    # Pass through pending tasks as unverified entries. They are not counted
    # against the mechanical pass verdict.
    pending_items: list[dict[str, Any]] = []
    for task in tasks:
        if task.get("status") != "done":
            pending_items.append(
                {
                    "task_id": task["id"],
                    "claimed_status": "todo",
                    "verified_status": "fail",
                    "confidence": CONFIDENCE_AMBIGUOUS,
                    "lens_file_exists": "na",
                    "lens_tests_pass": "na",
                    "lens_git_consistent": "na",
                    "lens_spec_match": "deferred-to-LLM",
                    "files_checked": [],
                    "tests_run": [],
                    "evidence": [],
                    "failures": ["task not done, no mechanical check performed"],
                }
            )

    all_items = verified_items + pending_items

    ambiguous = sum(1 for i in verified_items if i["confidence"] == CONFIDENCE_AMBIGUOUS)

    # Only count items where at least one lens applied (confidence extracted).
    mech_passed = sum(
        1
        for i in verified_items
        if i["confidence"] == CONFIDENCE_EXTRACTED and i["verified_status"] == "pass"
    )
    mech_failed = sum(
        1
        for i in verified_items
        if i["confidence"] == CONFIDENCE_EXTRACTED and i["verified_status"] == "fail"
    )

    # Ambiguous tasks do not fail the overall pass check.
    overall_pass = mech_failed == 0

    if mech_failed > 0:
        verdict = "fail"
    elif ambiguous > 0:
        verdict = "conditional_pass"
    else:
        verdict = "pass"

    report: dict[str, Any] = {
        "schema_version": "1.0",
        "feature_id": feature_id,
        "verified_at": datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z"),
        "verifier": {
            "tool": "verify_core.py",
            "mode": "mechanical",
            "agent": "none",
        },
        "summary": {
            "verdict": verdict,
            "risk_level": "standard",
            "human_review_required": not overall_pass or ambiguous > 0,
            "total_done_tasks": len(done_tasks),
            "mechanically_passed": mech_passed,
            "mechanically_failed": mech_failed,
            "ambiguous": ambiguous,
        },
        "tasks": all_items,
    }

    return report, overall_pass


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Mechanical verification harness for Mergen task states."
    )
    parser.add_argument(
        "--tasks-state",
        required=True,
        help="Path to tasks-state JSON file.",
    )
    parser.add_argument(
        "--root",
        default=".",
        help="Root directory for file and git checks (default: current directory).",
    )
    parser.add_argument(
        "--out",
        default=None,
        help="Write JSON report to this path (default: stdout).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Force JSON output to stdout even when --out is set.",
    )

    args = parser.parse_args(argv)

    tasks_state_path = Path(args.tasks_state)
    if not tasks_state_path.exists():
        print(f"error: tasks-state file not found: {tasks_state_path}", file=sys.stderr)
        return 2

    with open(tasks_state_path, encoding="utf-8") as fh:
        tasks_state = json.load(fh)

    root = Path(args.root).resolve()

    report, overall_pass = build_report(tasks_state, root)

    report_json = json.dumps(report, indent=2)

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(report_json.encode("utf-8"))
        if args.json:
            print(report_json)
    else:
        print(report_json)

    return 0 if overall_pass else 1


if __name__ == "__main__":
    sys.exit(main())
