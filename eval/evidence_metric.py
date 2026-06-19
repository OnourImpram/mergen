#!/usr/bin/env python3
"""Minimal evidence metric for Mergen (v1.0).

Reads one or more verification-report.json files and reports two honest
summaries derived only from recorded evidence:

  work-done rate: of the tasks claimed done, how many were independently
    verified pass with concrete evidence (files, tests, or output). The gap
    between claimed and verified is the phantom-completion count.

  minimal-change: lean-flagged lines over added lines, when a lean report is
    supplied with --overbuild. Absent that, the metric abstains rather than
    guess.

This is the smallest measurement that proves the system does what its name
claims: that work was actually done, and was no larger than needed. The full
benchmark is on the roadmap. Calibration is dog-fooded here. The metric reports
what the evidence supports and abstains on what it cannot derive.

Stdlib only. No network, no LLM.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def load_reports(path_str: str):
    path = Path(path_str)
    files = sorted(path.glob("**/verification-report.json")) if path.is_dir() else [path]
    reports = []
    for f in files:
        try:
            reports.append((f, json.loads(f.read_text(encoding="utf-8"))))
        except Exception as exc:  # noqa: BLE001 - report and skip, do not crash the metric
            print(f"skip {f}: {exc}", file=sys.stderr)
    return reports


def work_done(reports):
    claimed = verified = with_evidence = 0
    for _, report in reports:
        for task in report.get("tasks", []):
            if task.get("claimed_status") == "done":
                claimed += 1
                if task.get("verified_status") == "pass":
                    verified += 1
                    if task.get("files_checked") or task.get("tests_run") or task.get("evidence"):
                        with_evidence += 1
    return claimed, verified, with_evidence


def minimal_change(overbuild_path: str | None):
    if not overbuild_path:
        return None
    try:
        data = json.loads(Path(overbuild_path).read_text(encoding="utf-8"))
        added = data.get("added_lines")
        flagged = data.get("lean_flagged_lines")
        if isinstance(added, int) and added > 0 and isinstance(flagged, int):
            return flagged, added, flagged / added
    except Exception as exc:  # noqa: BLE001
        print(f"overbuild read failed: {exc}", file=sys.stderr)
    return None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Mergen minimal evidence metric")
    ap.add_argument("report", help="verification-report.json file, or a directory to scan")
    ap.add_argument("--overbuild", help="optional overbuild.json with added_lines and lean_flagged_lines")
    args = ap.parse_args(argv)

    reports = load_reports(args.report)
    if not reports:
        print("no verification-report.json found", file=sys.stderr)
        return 1

    claimed, verified, with_evidence = work_done(reports)
    print(f"reports read: {len(reports)}")
    print("work-done metric (evidence over claim)")
    if claimed == 0:
        print("  no tasks claimed done. abstaining on work-done rate.")
    else:
        print(f"  claimed done:        {claimed}")
        print(f"  verified pass:       {verified}")
        print(f"  with concrete proof: {with_evidence}")
        print(f"  work-done rate:      {with_evidence / claimed:.2f}  (proof / claimed)")
        print(f"  phantom completions: {claimed - verified}  (claimed done, not verified)")

    mc = minimal_change(args.overbuild)
    print("minimal-change metric")
    if mc is None:
        print("  no lean data supplied. abstaining on minimal-change (pass --overbuild).")
    else:
        flagged, added, ratio = mc
        print(f"  lean-flagged lines:  {flagged}")
        print(f"  added lines:         {added}")
        print(f"  over-build ratio:    {ratio:.2f}  (flagged / added)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
