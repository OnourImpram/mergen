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
        if not isinstance(report, dict):
            continue
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


def run_gate(claimed, verified, with_evidence, max_phantoms, min_work_done) -> int:
    """CI gate over the committed report. Honest about what it checks.

    A phantom is a task claimed done that the verifier did not confirm pass.
    The gate acts on the committed verification report, so a hand-edited report
    can still pass. The deepest guarantee rests on the verifier that produced
    the report, not on this check. What the gate buys is that phantom or
    unverified work fails the build by default rather than passing in silence.
    """
    print("gate")
    if claimed == 0:
        print("  no tasks claimed done. nothing to enforce. passing.")
        return 0
    phantoms = claimed - verified
    rate = with_evidence / claimed
    ok = phantoms <= max_phantoms and rate >= min_work_done
    print(f"  phantom completions: {phantoms}  (allowed {max_phantoms})")
    print(f"  work-done rate:      {rate:.2f}  (required {min_work_done:.2f})")
    print(f"  result:              {'PASS' if ok else 'FAIL'}")
    if not ok:
        print("  the committed verification report shows phantom or unverified work.",
              file=sys.stderr)
    return 0 if ok else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Mergen minimal evidence metric")
    ap.add_argument("report", help="verification-report.json file, or a directory to scan")
    ap.add_argument("--overbuild", help="optional overbuild.json with added_lines and lean_flagged_lines")
    ap.add_argument("--gate", action="store_true",
                    help="exit non-zero when the report shows phantom or unverified work (for CI)")
    ap.add_argument("--max-phantoms", type=int, default=0,
                    help="phantom completions tolerated under --gate (default 0)")
    ap.add_argument("--min-work-done", type=float, default=1.0,
                    help="minimum work-done rate required under --gate (default 1.0)")
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

    if args.gate:
        return run_gate(claimed, verified, with_evidence, args.max_phantoms, args.min_work_done)
    return 0


if __name__ == "__main__":
    sys.exit(main())
