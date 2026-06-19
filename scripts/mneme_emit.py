#!/usr/bin/env python3
"""Mergen to mneme seam (stub).

Convert a Mergen verification-report.json into a mneme-style decision record in
Markdown, so mneme can ingest it through its own public vault format. This is
the only bridge between the two systems. Mergen stores no memory of its own. It
emits an already-safe, provenance-bearing, confidence-labeled record and hands
it to mneme.

There is no network call and no LLM here, which honors mneme's
no-network-on-critical-path and markdown-ground-truth invariants. Redaction
remains mneme's responsibility at ingest. See docs/MNEME-SEAM.md.

Stdlib only.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def to_decision_markdown(report: dict) -> str:
    feature_id = report.get("feature_id", "unknown")
    summary = report.get("summary", {})
    verdict = summary.get("verdict", "unknown")
    verified_at = report.get("verified_at", "")
    tasks = report.get("tasks", [])
    proven = [
        t.get("task_id", "?")
        for t in tasks
        if t.get("verified_status") == "pass" and (t.get("files_checked") or t.get("tests_run"))
    ]
    unproven = [t.get("task_id", "?") for t in tasks if t.get("verified_status") != "pass"]

    lines = [
        f"# Decision: {feature_id}",
        "",
        f"- source: mergen verification-report ({verified_at})",
        f"- verdict: {verdict}",
        "- confidence: extracted",
        f"- proven tasks: {', '.join(proven) if proven else 'none'}",
        f"- unproven tasks: {', '.join(unproven) if unproven else 'none'}",
        "",
        "Provenance is the verification report. Each proven task carries filesystem and test evidence. "
        "Unproven tasks are recorded as such and are not claimed as done.",
        "",
    ]
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Emit a mneme-ingestable decision record from a Mergen verification report"
    )
    ap.add_argument("report", help="path to a verification-report.json")
    args = ap.parse_args(argv)
    try:
        report = json.loads(Path(args.report).read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        print(f"cannot read report: {exc}", file=sys.stderr)
        return 1
    if not isinstance(report, dict):
        print(f"cannot process report: expected a JSON object, got {type(report).__name__}", file=sys.stderr)
        return 1
    sys.stdout.write(to_decision_markdown(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
