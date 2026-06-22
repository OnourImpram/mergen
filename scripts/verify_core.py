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
import hashlib
import importlib.util
import os
import subprocess
import sys
import json
from pathlib import Path
from typing import Any

#: Bumped when the meaning of a lens or the report shape changes. Recorded in
#: every report's provenance so a consumer knows which verifier produced it.
#: 1.1 adds the per-task evidence calibration fields (evidence_strength,
#: evidence_tier) and the summary untested_passes count. The report still
#: conforms to schema_version 1.0 because those fields are additive and optional.
VERIFIER_VERSION = "1.1"

#: Wall-clock ceiling, in seconds, for a single test_task pytest run. A user's test
#: suite can hang (a deadlock, a prompt on stdin, an infinite loop), and an unbounded
#: subprocess would hang the whole verifier with it. The default is overridable per run
#: with --test-timeout or the MERGEN_TEST_TIMEOUT environment variable. A timeout is a
#: fail, never a silent pass: an unprovable test does not earn a done verdict.
DEFAULT_TEST_TIMEOUT = 120

#: Wall-clock ceiling for the small git queries the lenses run. Generous, since these
#: are local and fast, but bounded so a wedged git process cannot hang the harness.
_GIT_TIMEOUT = 30


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
# Evidence calibration
#
# A pass backed by an executed test is qualitatively stronger than a pass backed
# only by a file existing on disk. Calibration records that strength so a reader
# can tell a test-backed pass from a presence-only one, and so a reviewer can
# triage the weak passes first. It is pure observability. The weights below rank
# evidence strength, they are NOT calibrated probabilities, and nothing here
# changes a verdict: a failed hard gate still fails the task no matter how much
# other evidence corroborates it, and the Governor floor and human_review_required
# are untouched, so a soft signal can never weaken a hard gate.
# ---------------------------------------------------------------------------

#: Per-lens evidence weight, a strict ordering not a probability: an executed test
#: is the strongest evidence a task is done, a file being known to git is a weaker
#: corroboration, and mere file presence is weakest.
LENS_WEIGHTS: dict[str, int] = {
    "tests_pass": 3,
    "git_consistent": 2,
    "file_exists": 1,
}

#: Evidence tiers a task can earn, strongest first. "executed" means a test ran
#: and passed. "corroborated" means no test passed but a static lens did. "none"
#: means no lens passed (an all-na or wholly unverified task).
EVIDENCE_TIERS: tuple[str, ...] = ("executed", "corroborated", "none")


def calibrate(lens_results: dict[str, str]) -> tuple[float, str]:
    """Score how strongly the passing lenses ground this task.

    lens_results maps a lens name ("file_exists", "tests_pass", "git_consistent")
    to "pass", "fail", or "na". Returns (evidence_strength, evidence_tier).
    evidence_strength is the share of total lens weight that returned a pass,
    rounded to two places, in [0.0, 1.0]. evidence_tier names the strongest
    passing evidence class. Both describe the corroborating evidence, never the
    verdict: this function does not know and cannot change whether the task passed.

    Unknown keys are silently ignored (they earn no weight), so the caller is
    responsible for using the canonical lens names from LENS_WEIGHTS. The one
    caller, verify_task, passes a hardcoded dict literal, so a typo is caught at
    review rather than at runtime.
    """
    total = sum(LENS_WEIGHTS.values())
    earned = sum(
        weight for name, weight in LENS_WEIGHTS.items()
        if lens_results.get(name) == "pass"
    )
    strength = round(earned / total, 2) if total else 0.0
    if lens_results.get("tests_pass") == "pass":
        tier = "executed"
    elif any(lens_results.get(name) == "pass" for name in ("git_consistent", "file_exists")):
        tier = "corroborated"
    else:
        tier = "none"
    return strength, tier


# ---------------------------------------------------------------------------
# Path safety: the one chokepoint every declared path passes through
#
# A tasks-state file is untrusted input. Its test_task is handed to pytest and its
# files are read from disk, so a hostile or careless value must never become a pytest
# option (--version, -k expr), an absolute path, or a traversal out of the repository.
# Every lens validates the paths it is about to use through safe_repo_relative_path, and
# the report only ever records the normalized repo-relative form, so a machine-local
# absolute path cannot leak into an artifact either. This is defense in depth: each lens
# guards its own use of a path because each one is a real boundary (a subprocess, a
# filesystem read, a git query), not only the report assembly above them.
# ---------------------------------------------------------------------------


class UnsafePathError(ValueError):
    """A declared path is not a concrete file inside the repository root."""


#: Path metacharacters a tasks-state entry names one concrete file, never a pattern.
_GLOB_CHARS = ("*", "?", "[", "]")


def safe_repo_relative_path(raw: object, root: Path, *, kind: str) -> str:
    """Return raw normalized to a POSIX repo-relative path, or raise UnsafePathError.

    Rejects, never returns: a non-string or blank value; a value starting with "-" (a
    command option such as --version or -k, not a path); a leading path separator; an
    absolute path or a Windows drive (C:\\...); any ".." segment; a glob metacharacter;
    and any path that resolves outside root. kind ("test_task" or "files") names the field
    in the error message, which never echoes the raw value, so a rejected absolute path is
    not leaked through the message either.
    """
    if not isinstance(raw, str) or not raw.strip():
        raise UnsafePathError(f"{kind}: empty or non-string path")
    value = raw.strip()
    if value[0] == "-":
        raise UnsafePathError(f"{kind}: a leading '-' is a command option, not a path")
    if value[0] in ("/", "\\"):
        raise UnsafePathError(f"{kind}: a leading path separator is not allowed")
    if len(value) >= 2 and value[1] == ":":
        raise UnsafePathError(f"{kind}: a drive-qualified path is not allowed")
    if any(ch in value for ch in _GLOB_CHARS):
        raise UnsafePathError(f"{kind}: a glob metacharacter is not a concrete path")
    parts = value.replace("\\", "/").split("/")
    if ".." in parts:
        raise UnsafePathError(f"{kind}: '..' path traversal is not allowed")
    candidate = Path(value)
    if candidate.is_absolute():
        raise UnsafePathError(f"{kind}: an absolute path is not allowed")
    resolved = (root / candidate).resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError:
        raise UnsafePathError(f"{kind}: path resolves outside the repository root") from None
    normalized = "/".join(p for p in parts if p not in ("", "."))
    if not normalized:
        raise UnsafePathError(f"{kind}: path is empty after normalization")
    return normalized


def _display_path(raw: object, root: Path, kind: str) -> str:
    """The normalized repo-relative form for a report field, or a redacted marker.

    files_checked and tests_run echo the declared paths back into the report. Normalizing
    them here keeps a rejected or machine-local path out of the artifact: a valid path
    becomes its POSIX repo-relative form, a rejected one becomes a fixed marker that names
    no real path.
    """
    try:
        return safe_repo_relative_path(raw, root, kind=kind)
    except UnsafePathError:
        return f"<rejected {kind}>"


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
    for raw in files:
        try:
            rel = safe_repo_relative_path(raw, root, kind="files")
        except UnsafePathError as exc:
            # A rejected path is a fail, never a silently skipped file: it must not let a
            # task pass by naming an unreachable target. The message carries no raw value.
            failures.append(f"unsafe path: {exc}")
            continue
        if (root / rel).exists():
            evidence.append(f"exists: {rel}")
        else:
            failures.append(f"missing: {rel}")

    result = "fail" if failures else "pass"
    return result, evidence, failures


def lens_tests_pass(
    test_task: str | None, root: Path, *, timeout_s: int = DEFAULT_TEST_TIMEOUT
) -> tuple[str, list[str], list[str]]:
    """Run pytest against test_task from root, capturing real exit code.

    test_task is validated to a repo-relative path before it touches the command line, so
    it can never be a pytest option (--version, -k expr) or a path outside the repo, the
    exact bypass that would let a crafted tasks-state earn a pass with no real test. The
    "--" then terminates option parsing as a second guard. The run is bounded by timeout_s;
    a timeout is a fail, since an unprovable test is not a done verdict.

    Returns a triple of (result, evidence, failures).
    """
    if not test_task:
        return "na", [], []

    try:
        rel = safe_repo_relative_path(test_task, root, kind="test_task")
    except UnsafePathError as exc:
        return "fail", [], [f"unsafe test_task: {exc}"]

    cmd = [sys.executable, "-m", "pytest", "-q", "--", rel]
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(root),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout_s,
        )
    except subprocess.TimeoutExpired:
        return "fail", [], [f"pytest timed out after {timeout_s}s for {rel}"]
    except Exception as exc:
        return "fail", [], [f"pytest launch error: {exc}"]

    if proc.returncode == 0:
        evidence = [f"pytest exit 0 for {rel}"]
        return "pass", evidence, []
    else:
        out = (proc.stdout or "").strip()
        err = (proc.stderr or "").strip()
        failures = [f"pytest exit {proc.returncode} for {rel}"]
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
            timeout=_GIT_TIMEOUT,
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

    for raw in files:
        try:
            rel = safe_repo_relative_path(raw, root, kind="files")
        except UnsafePathError as exc:
            failures.append(f"unsafe path: {exc}")
            continue
        # rel is already normalized to forward slashes, the form git emits.
        if rel in porcelain_paths:
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
                timeout=_GIT_TIMEOUT,
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


def verify_task(
    task: dict[str, Any], root: Path, *, test_timeout: int = DEFAULT_TEST_TIMEOUT
) -> dict[str, Any]:
    """Run the three mechanical lenses against one done task.

    Returns a dict that is a valid verification-report tasks item.
    """
    task_id = task["id"]
    files: list[str] = task.get("files") or []
    test_task: str | None = task.get("test_task") or None

    fe_result, fe_evidence, fe_failures = lens_file_exists(files, root)
    tp_result, tp_evidence, tp_failures = lens_tests_pass(test_task, root, timeout_s=test_timeout)
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

    # Calibration is a non-verdict-changing observability signal computed from the
    # same three lens results the verdict used. It records how strongly the passing
    # lenses ground this task, never whether it passed.
    evidence_strength, evidence_tier = calibrate({
        "file_exists": fe_result,
        "tests_pass": tp_result,
        "git_consistent": gc_result,
    })

    return {
        "task_id": task_id,
        "claimed_status": "done",
        "verified_status": verified_status,
        "confidence": confidence,
        "evidence_strength": evidence_strength,
        "evidence_tier": evidence_tier,
        "lens_file_exists": fe_result,
        "lens_tests_pass": tp_result,
        "lens_git_consistent": gc_result,
        "lens_spec_match": "deferred-to-LLM",
        # Echo only the normalized repo-relative form into the report, never the raw
        # declared value, so a rejected or machine-local absolute path cannot leak here.
        "files_checked": [_display_path(f, root, "files") for f in files],
        "tests_run": [_display_path(test_task, root, "test_task")] if test_task else [],
        "evidence": all_evidence,
        "failures": all_failures,
    }


# ---------------------------------------------------------------------------
# Report assembly
# ---------------------------------------------------------------------------


_GOVERNOR_FLOOR_MOD: Any = None


def _governor_floor() -> Any:
    """Load the sibling governor_floor module by path, cached (scripts/ is not a package).

    Wiring the floor in here is what makes the high-trust tier of a report real. Without it the
    report's risk_level would never reflect the Governor floor, and the unsigned-high-trust lint
    that conditions on risk_level == high-trust could never fire on a live verify_core report.
    """
    global _GOVERNOR_FLOOR_MOD
    if _GOVERNOR_FLOOR_MOD is None:
        spec = importlib.util.spec_from_file_location(
            "governor_floor", Path(__file__).resolve().parent / "governor_floor.py")
        if spec is None or spec.loader is None:  # pragma: no cover - import wiring
            raise ImportError("cannot load governor_floor")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _GOVERNOR_FLOOR_MOD = mod
    return _GOVERNOR_FLOOR_MOD


def build_report(
    tasks_state: dict[str, Any],
    root: Path,
    *,
    test_timeout: int = DEFAULT_TEST_TIMEOUT,
) -> tuple[dict[str, Any], bool]:
    """Verify all done tasks and assemble the report dict.

    Returns (report, overall_pass) where overall_pass is True iff every
    applicable mechanical lens passed for every done task. Ambiguous tasks
    (all lenses na) are not counted as failures.

    The report's risk_level is the Governor floor classified over the change surface (the files
    the done tasks declare), not a fixed value, so a change that touches a guarded surface is
    high-trust and forces a human sign-off. The path classifier matches a flat file by its stem,
    so src/auth.py is caught, not only src/auth/login.py.
    """
    feature_id = tasks_state.get("feature_id", "unknown")
    tasks = tasks_state.get("tasks", [])

    done_tasks = [t for t in tasks if t.get("status") == "done"]
    verified_items: list[dict[str, Any]] = []

    for task in done_tasks:
        item = verify_task(task, root, test_timeout=test_timeout)
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
                    "evidence_strength": 0.0,
                    "evidence_tier": "none",
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

    # A pass that no test exercised is a weaker pass. "corroborated" is the only
    # non-executed pass tier (a pass always has at least one passing lens, so a
    # verified pass can never be tier "none"), so this filter captures every
    # untested pass. Surfacing the count lets a reviewer triage the soft passes
    # without changing any verdict.
    untested_passes = sum(
        1
        for i in verified_items
        if i["verified_status"] == "pass" and i["evidence_tier"] == "corroborated"
    )

    # Ambiguous tasks do not fail the overall pass check.
    overall_pass = mech_failed == 0

    if mech_failed > 0:
        verdict = "fail"
    elif ambiguous > 0:
        verdict = "conditional_pass"
    else:
        verdict = "pass"

    # Classify the Governor floor over the change surface, the files the done tasks declare. The
    # floor is the lower bound on the report's risk tier: a change touching a guarded surface is
    # high-trust, which forces human_review_required and is what the unsigned-high-trust lint then
    # enforces. risk_triggers records WHY, so a reviewer sees which surface tripped it.
    changed_paths = [
        f for t in done_tasks for f in (t.get("files") or []) if isinstance(f, str)
    ]
    floor = _governor_floor().classify_floor(changed_paths)
    risk_level = "high-trust" if floor.get("tier") == "high-trust" else "standard"
    risk_triggers = list(floor.get("triggers_matched", []))
    human_review_required = (not overall_pass) or (ambiguous > 0) or (risk_level == "high-trust")

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
            "risk_level": risk_level,
            "risk_triggers": risk_triggers,
            "human_review_required": human_review_required,
            "total_done_tasks": len(done_tasks),
            "mechanically_passed": mech_passed,
            "mechanically_failed": mech_failed,
            "ambiguous": ambiguous,
            "untested_passes": untested_passes,
        },
        "tasks": all_items,
    }

    return report, overall_pass


# ---------------------------------------------------------------------------
# Provenance and the tamper-evident manifest
# ---------------------------------------------------------------------------


def _git_head(root: Path) -> str | None:
    """Current commit of root, or None when root is not a git work tree."""
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except Exception:
        return None
    if proc.returncode != 0:
        return None
    head = proc.stdout.strip()
    return head or None


def _working_tree_clean(root: Path) -> bool | None:
    """True or False when root is a git work tree, None when it is not."""
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), "status", "--porcelain"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except Exception:
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout.strip() == ""


def compute_provenance(root: Path, tasks_state_path: Path) -> dict[str, Any]:
    """Record what produced a report so tampering or staleness is detectable.

    source_commit and working_tree_clean are None when root is not a git work
    tree (the harness still runs, the staleness signal just is not available).
    tasks_state_sha256 hashes the actual input bytes, pinning the report to the
    exact task state it verified.
    """
    digest = hashlib.sha256(tasks_state_path.read_bytes()).hexdigest()
    return {
        "verifier_version": VERIFIER_VERSION,
        "source_commit": _git_head(root),
        "working_tree_clean": _working_tree_clean(root),
        "tasks_state_sha256": digest,
    }


def write_manifest(report_path: Path, report_bytes: bytes) -> Path:
    """Write the sha256 sidecar for a report in sha256sum format.

    The sidecar hashes the exact bytes written, so any later edit to the report
    breaks the match. Returns the sidecar path.
    """
    digest = hashlib.sha256(report_bytes).hexdigest()
    sidecar = report_path.with_name(report_path.name + ".sha256")
    sidecar.write_bytes(f"{digest}  {report_path.name}\n".encode("utf-8"))
    return sidecar


def check_manifest(report_path: Path, root: Path, require_fresh: bool) -> int:
    """Verify a report against its sha256 sidecar and, optionally, its freshness.

    Tamper-evidence is always checked: the report bytes must hash to the value in
    <report>.sha256. With require_fresh, the recorded source_commit must also
    match the current HEAD of root, so a report describing a since-moved tree
    fails. Returns 0 when every requested check passes, 1 on a failed check, 2
    for a missing report or sidecar.

    This is tamper-evident, not tamper-proof. An attacker who controls both the
    report and the sidecar can recompute the hash. The guarantee is meaningful in
    CI, where the sidecar is recomputed from the live tree rather than trusted.
    """
    if not report_path.exists():
        print(f"error: report not found: {report_path}", file=sys.stderr)
        return 2
    sidecar = report_path.with_name(report_path.name + ".sha256")
    if not sidecar.exists():
        print(f"error: manifest sidecar not found: {sidecar}", file=sys.stderr)
        return 2

    print("manifest check")
    report_bytes = report_path.read_bytes()
    actual = hashlib.sha256(report_bytes).hexdigest()
    # First whitespace-delimited token is the digest (sha256sum format). Parse
    # defensively so a blank or malformed sidecar yields "" rather than crashing.
    sidecar_parts = sidecar.read_text(encoding="utf-8").split()
    expected = sidecar_parts[0] if sidecar_parts else ""
    ok = True
    if actual == expected:
        print(f"  [OK ] report hash matches manifest ({actual[:12]})")
    else:
        print(f"  [TAMPER] report hash {actual[:12]} does not match manifest "
              f"{expected[:12] or '(empty)'}", file=sys.stderr)
        ok = False

    if require_fresh:
        try:
            report = json.loads(report_bytes.decode("utf-8-sig"))
        except Exception:
            report = {}
        recorded = (report.get("provenance") or {}).get("source_commit")
        current = _git_head(root)
        if not recorded:
            print("  [STALE] --require-fresh set but the report records no source_commit "
                  "(generated outside a git work tree, or by an older verifier)",
                  file=sys.stderr)
            ok = False
        elif current is None:
            print(f"  [STALE] --require-fresh set but root is not a git work tree: {root}",
                  file=sys.stderr)
            ok = False
        elif current != recorded:
            print(f"  [STALE] report generated at {recorded[:12]}, root HEAD is now "
                  f"{current[:12]}", file=sys.stderr)
            ok = False
        else:
            print(f"  [OK ] source commit matches root HEAD ({current[:12]})")

    print(f"  result: {'OK' if ok else 'FAIL'}")
    return 0 if ok else 1


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Mechanical verification harness for Mergen task states."
    )
    parser.add_argument(
        "--tasks-state",
        default=None,
        help="Path to tasks-state JSON file. Required unless --check-manifest is given.",
    )
    parser.add_argument(
        "--root",
        default=".",
        help="Root directory for file and git checks (default: current directory).",
    )
    parser.add_argument(
        "--out",
        default=None,
        help="Write JSON report to this path (default: stdout). Also writes a "
             "<path>.sha256 tamper-evidence sidecar.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Force JSON output to stdout even when --out is set.",
    )
    parser.add_argument(
        "--check-manifest",
        default=None,
        metavar="REPORT",
        help="Verify REPORT against its .sha256 sidecar instead of running the "
             "harness. Exits non-zero if the report was edited after it was written.",
    )
    parser.add_argument(
        "--require-fresh",
        action="store_true",
        help="With --check-manifest, also fail when the report's source_commit "
             "does not match the current HEAD of --root (stale report).",
    )
    parser.add_argument(
        "--test-timeout",
        type=int,
        default=None,
        metavar="SECONDS",
        help=f"Per-test_task pytest timeout in seconds (default {DEFAULT_TEST_TIMEOUT}, or "
             "the MERGEN_TEST_TIMEOUT env var). A test that exceeds it fails, never passes.",
    )

    args = parser.parse_args(argv)

    # Resolve the test timeout: explicit flag wins, then the environment, then the default.
    # A non-integer or non-positive environment value falls back to the default rather than
    # disabling the bound.
    if args.test_timeout is not None and args.test_timeout > 0:
        test_timeout = args.test_timeout
    else:
        env_timeout = os.environ.get("MERGEN_TEST_TIMEOUT", "")
        test_timeout = int(env_timeout) if env_timeout.isdigit() and int(env_timeout) > 0 \
            else DEFAULT_TEST_TIMEOUT

    root = Path(args.root).resolve()

    # Manifest check is a separate mode: it reads an existing report, it does not
    # run the harness, so it needs no tasks-state.
    if args.check_manifest is not None:
        return check_manifest(Path(args.check_manifest), root, args.require_fresh)

    if args.tasks_state is None:
        parser.error("--tasks-state is required unless --check-manifest is given")

    tasks_state_path = Path(args.tasks_state)
    if not tasks_state_path.exists():
        print(f"error: tasks-state file not found: {tasks_state_path}", file=sys.stderr)
        return 2

    # A tasks-state that cannot be read or parsed is a harness input error, not a
    # verdict. Return exit 2 (the same code as a missing file) so a CI gate can
    # tell "no report could be produced" apart from "the report shows failures"
    # (exit 1). utf-8-sig tolerates the UTF-8 BOM Windows PowerShell writes, so a
    # BOM in tasks-state.json does not crash the read.
    try:
        with open(tasks_state_path, encoding="utf-8-sig") as fh:
            tasks_state = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"error: could not read tasks-state {tasks_state_path}: {exc}", file=sys.stderr)
        return 2

    # Capture provenance BEFORE the lenses run. The tests-pass lens executes
    # pytest inside root and leaves __pycache__ behind, so computing the
    # working-tree state afterward would record our own verification artifacts as
    # uncommitted changes. Provenance is the tree state at verification start.
    provenance = compute_provenance(root, tasks_state_path)

    # Any harness crash while building the report is a no-report condition, so it
    # also exits 2. A phantom is never a crash: it is a normal fail verdict with
    # the report written (exit 1), so this never hides incomplete work.
    try:
        report, overall_pass = build_report(tasks_state, root, test_timeout=test_timeout)
    except Exception as exc:  # noqa: BLE001 - a harness crash is a no-report error
        print(f"error: verify harness failed to build the report: {exc}", file=sys.stderr)
        return 2

    # Provenance pins the report to the commit, the tree state, and the exact
    # task-state file that produced it. It is an I/O concern bound to real paths,
    # so it lives here and not in the pure build_report.
    report["provenance"] = provenance

    report_json = json.dumps(report, indent=2)

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        report_bytes = report_json.encode("utf-8")
        out_path.write_bytes(report_bytes)
        sidecar = write_manifest(out_path, report_bytes)
        print(f"wrote {out_path} and {sidecar.name}", file=sys.stderr)
        if args.json:
            print(report_json)
    else:
        print(report_json)

    return 0 if overall_pass else 1


if __name__ == "__main__":
    sys.exit(main())
