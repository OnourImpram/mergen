#!/usr/bin/env python3
"""mergen verify-lint: refuse a verification report that is not a clean, proven pass.

The verification report is the artifact Mergen stakes its name on. verify_core
produces an honest one. This linter is the guard for the reports Mergen did not
produce: a hand-authored report, a third-party agent's report, or a report that
drifted after the fact. It enforces in pure Python the same invariants the JSON
schema declares, so the check holds with no schema-validation dependency and no
network. The schema is the contract a generic validator can read. This is the
contract a plain Python install can run.

What it refuses (each an error that fails the lint):
  - a report missing the keys a report must have (schema shape invalid)
  - a proofless pass: a task verified pass with no file, no test, and no recorded
    output. A verdict without evidence is a fail, never an inferred pass.
  - an ambiguous pass: a pass labelled with the ambiguous confidence. The report
    cannot be both unsure and a pass.
  - a report whose own summary verdict is fail
  - a conditional_pass, unless --allow-conditional says the caller owns the caveat
  - an unsigned high-trust report: high-trust with human review required but no
    recorded approval is not a pass until a human signs it

What it warns on (reported, non-fatal unless promoted):
  - a report with no provenance block. Older reports predate it. --require-provenance
    turns this into an error for a pipeline that demands traceability.

Exit codes mirror the rest of mergen's gates: 0 clean (warnings allowed), 1 a
lint error was found, 2 no report could be read at all.

Stdlib only. No network, no model, no third-party schema validator.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

# The keys a verification report cannot omit. Mirrors the schema's top-level
# required list exactly, minus verifier (optional) and the audit arrays, so the
# linter and the schema reject the same incomplete report.
_REQUIRED_TOP = ("schema_version", "feature_id", "verified_at", "summary", "tasks")
_EVIDENCE_KEYS = ("files_checked", "tests_run", "evidence")


class Finding:
    """One lint result. level is "error" (fails the lint) or "warn" (reported)."""

    __slots__ = ("level", "code", "where", "message")

    def __init__(self, level: str, code: str, where: str, message: str) -> None:
        self.level = level
        self.code = code
        self.where = where
        self.message = message

    def __str__(self) -> str:
        return f"  [{self.level.upper()}] {self.code} ({self.where}): {self.message}"


def _has_evidence(task: dict[str, Any]) -> bool:
    """True when the task records at least one concrete proof array with content."""
    for key in _EVIDENCE_KEYS:
        value = task.get(key)
        if isinstance(value, list) and len(value) > 0:
            return True
    return False


def lint_report(report: Any, source: str, *, allow_conditional: bool = False,
                require_provenance: bool = False) -> list[Finding]:
    """Return every lint finding for one report. Pure, so it is trivially testable."""
    if not isinstance(report, dict):
        return [Finding("error", "SCHEMA_INVALID", source, "report is not a JSON object")]

    findings: list[Finding] = []

    missing = [k for k in _REQUIRED_TOP if k not in report]
    if missing:
        findings.append(Finding("error", "SCHEMA_INVALID", source,
                                f"missing required key(s): {', '.join(missing)}"))

    summary = report.get("summary")
    summary = summary if isinstance(summary, dict) else {}
    verdict = summary.get("verdict")
    if "summary" in report and "verdict" not in summary:
        findings.append(Finding("error", "SCHEMA_INVALID", source,
                                "summary has no verdict"))
    if verdict == "fail":
        findings.append(Finding("error", "SUMMARY_FAIL", source,
                                "the report's own summary verdict is fail"))
    if verdict == "conditional_pass" and not allow_conditional:
        findings.append(Finding("error", "CONDITIONAL_PASS", source,
                                "verdict is conditional_pass, a caveat is unresolved "
                                "(pass --allow-conditional to accept it)"))

    # Unsigned high-trust. A high-trust report is not a pass until it both flags that human
    # review is required and records an approval. The two cannot disagree: a high-trust report
    # with human_review_required false is itself the contradiction the schema's if/then forbids,
    # and is flagged here so the linter is at least as strict as the schema (it previously
    # short-circuited on that case and let it through, the exact downgrade the floor must refuse).
    if summary.get("risk_level") == "high-trust":
        review = summary.get("human_review")
        status = review.get("status") if isinstance(review, dict) else None
        if not bool(summary.get("human_review_required")) or status != "approved":
            findings.append(Finding(
                "error", "UNSIGNED_HIGH_TRUST", source,
                "high-trust report is not signed off: it must set human_review_required and record "
                f"human_review.status approved (human_review_required="
                f"{summary.get('human_review_required')!r}, status={status!r})"))

    tasks = report.get("tasks")
    if isinstance(tasks, list):
        for task in tasks:
            if not isinstance(task, dict):
                findings.append(Finding("error", "SCHEMA_INVALID", source,
                                        "a task entry is not an object"))
                continue
            if task.get("verified_status") != "pass":
                continue
            where = f"{source}:{task.get('task_id', '?')}"
            if not _has_evidence(task):
                findings.append(Finding("error", "PROOFLESS_PASS", where,
                                        "task verified pass with no files_checked, "
                                        "tests_run, or evidence"))
            if task.get("confidence") == "ambiguous":
                findings.append(Finding("error", "AMBIGUOUS_PASS", where,
                                        "task is an ambiguous pass, a pass cannot be unsure"))

    if not isinstance(report.get("provenance"), dict):
        level = "error" if require_provenance else "warn"
        findings.append(Finding(level, "MISSING_PROVENANCE", source,
                                "no provenance block, the report's source commit and "
                                "tasks-state hash are unrecorded"))
    return findings


def _discover(path: Path) -> list[Path] | None:
    """The report files to lint, or None when there is nothing to read (exit 2)."""
    if path.is_dir():
        files = sorted(path.glob("**/verification-report.json"))
        return files or None
    if path.is_file():
        return [path]
    return None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Refuse a verification report that is not a clean, proven pass")
    ap.add_argument("report", help="verification-report.json file, or a directory to "
                                    "scan recursively for verification-report.json files")
    ap.add_argument("--allow-conditional", action="store_true",
                    help="accept a conditional_pass verdict (the caller owns the caveat)")
    ap.add_argument("--require-provenance", action="store_true",
                    help="treat a missing provenance block as an error, not a warning")
    args = ap.parse_args(argv)

    files = _discover(Path(args.report))
    if files is None:
        print("verify-lint: no verification-report.json found", file=sys.stderr)
        return 2

    findings: list[Finding] = []
    unreadable = 0
    for f in files:
        try:
            report = json.loads(f.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as exc:
            unreadable += 1
            findings.append(Finding("error", "UNREADABLE", str(f), str(exc)))
            continue
        findings.extend(lint_report(report, str(f),
                                    allow_conditional=args.allow_conditional,
                                    require_provenance=args.require_provenance))

    errors = [x for x in findings if x.level == "error"]
    warns = [x for x in findings if x.level == "warn"]
    print(f"verify-lint: {len(files)} report(s) scanned")
    for x in findings:
        print(str(x))
    print(f"  errors: {len(errors)}   warnings: {len(warns)}")
    print(f"  result: {'FAIL' if errors else 'PASS'}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
