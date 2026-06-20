#!/usr/bin/env python3
"""Deterministic phantom-detection benchmark for Mergen's verify harness.

No LLM, no network, no live spec-kit. This builds a corpus of task-completion
scenarios with KNOWN ground truth inside throwaway git repos, runs the real
shipped harness (scripts/verify_core.py) over each one, and measures how many
planted phantom completions the harness catches versus how many genuine
completions it wrongly fails.

This produces REAL measured numbers for metric 1 (phantom-completion) and a
deterministic slice of metric 3 (adversarial catch) from methodology.md,
replacing the SYNTHETIC placeholders for the harness-detection sub-claim. It
does NOT replace the live head-to-head for metric 2 (parallel speedup) or
metric 4 (over-build), which need a live model and stay on the roadmap.

What is compared:

  baseline arm   bare spec-kit behavior: trust the [X] checkbox. By construction
                 it catches zero phantoms, because nothing re-checks the claim.
  treatment arm  verify_core's three mechanical lenses (file-exists, tests-pass,
                 git-consistent). The benchmark imports the shipped module and
                 runs the actual lenses, so it measures the real harness, not a
                 reimplementation.

A phantom here is a task marked done whose completion the harness cannot
mechanically confirm. This set is a SUPERSET of methodology.md's strict
definition (declared file missing, or declared test failing). It also includes
two adjacent cases the harness likewise refuses to bless: a claim with no
checkable evidence at all (no files, no test), and a declared artifact the
repository will not track (git-ignored), which exists on disk yet is absent from
the recorded tree. All of them share the property that the bare checkbox accepts
them and the harness rejects them.

Stdlib only. The only third-party process invoked is pytest, launched by the
harness itself for the tests-pass lens, exactly as it runs in production.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO / "scripts"))
import verify_core  # noqa: E402


# ---------------------------------------------------------------------------
# The corpus. Each case has exactly one done task so scoring is 1:1. `truth`
# is the ground truth label. `expect_lens` names the lens that should decide a
# phantom, so a regression that blinds one lens is localized, not just counted.
# ---------------------------------------------------------------------------

_PASS_TEST = "def test_ok():\n    assert True\n"
_FAIL_TEST = "def test_bad():\n    assert False\n"

CASES: list[dict[str, Any]] = [
    # ---- genuine completions: the harness must PASS these (no false alarms) --
    {
        "name": "real_file_and_passing_test",
        "truth": "real",
        "expect_lens": None,
        "create_files": {"feature.py": "VALUE = 1\n"},
        "test_files": {"test_feature.py": _PASS_TEST},
        "task": {"id": "T001", "status": "done",
                 "files": ["feature.py"], "test_task": "test_feature.py"},
    },
    {
        "name": "real_file_only_no_test",
        "truth": "real",
        "expect_lens": None,
        "create_files": {"docs/guide.md": "# Guide\n"},
        "test_files": {},
        "task": {"id": "T002", "status": "done",
                 "files": ["docs/guide.md"], "test_task": None},
    },
    {
        "name": "real_multi_file_all_present",
        "truth": "real",
        "expect_lens": None,
        "create_files": {"a.py": "A = 1\n", "b.py": "B = 2\n", "c.py": "C = 3\n"},
        "test_files": {},
        "task": {"id": "T003", "status": "done",
                 "files": ["a.py", "b.py", "c.py"], "test_task": None},
    },
    # ---- phantoms: the harness must FAIL (catch) these -----------------------
    {
        "name": "phantom_missing_file",
        "truth": "phantom",
        "expect_lens": "lens_file_exists",
        "create_files": {},
        "test_files": {},
        "task": {"id": "T101", "status": "done",
                 "files": ["never_written.py"], "test_task": None},
    },
    {
        "name": "phantom_one_of_three_missing",
        "truth": "phantom",
        "expect_lens": "lens_file_exists",
        "create_files": {"a.py": "A = 1\n", "b.py": "B = 2\n"},
        "test_files": {},
        "task": {"id": "T102", "status": "done",
                 "files": ["a.py", "b.py", "missing.py"], "test_task": None},
    },
    {
        "name": "phantom_failing_test",
        "truth": "phantom",
        "expect_lens": "lens_tests_pass",
        "create_files": {"feature.py": "VALUE = 1\n"},
        "test_files": {"test_feature.py": _FAIL_TEST},
        "task": {"id": "T103", "status": "done",
                 "files": ["feature.py"], "test_task": "test_feature.py"},
    },
    {
        "name": "phantom_zero_evidence",
        "truth": "phantom",
        "expect_lens": None,  # no lens applies; the harness refuses to bless it
        "create_files": {},
        "test_files": {},
        "task": {"id": "T104", "status": "done",
                 "files": [], "test_task": None},
    },
    {
        "name": "phantom_gitignored_file",
        "truth": "phantom",
        "expect_lens": "lens_git_consistent",
        "create_files": {"build/output.bin": "binary\n"},
        "test_files": {},
        "gitignore": ["build/"],
        "task": {"id": "T105", "status": "done",
                 "files": ["build/output.bin"], "test_task": None},
    },
]


# ---------------------------------------------------------------------------
# Case materialization and execution
# ---------------------------------------------------------------------------


def _git(root: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(root), *args],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )


def _write(root: Path, rel: str, content: str) -> None:
    target = root / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content.encode("utf-8"))


def build_case(case: dict[str, Any], root: Path) -> dict[str, Any]:
    """Materialize a case in `root` (a fresh git repo) and return its tasks-state."""
    _git(root, "init")
    if case.get("gitignore"):
        _write(root, ".gitignore", "\n".join(case["gitignore"]) + "\n")
    for rel, content in case.get("create_files", {}).items():
        _write(root, rel, content)
    for rel, content in case.get("test_files", {}).items():
        _write(root, rel, content)
    # Stage everything not ignored. No commit is needed: the git-consistent lens
    # accepts staged files (porcelain "A") and rejects ignored/unknown ones.
    _git(root, "add", "-A")
    return {"feature_id": case["name"], "tasks": [case["task"]]}


def run_case(case: dict[str, Any]) -> dict[str, Any]:
    """Run the real harness over one freshly built case, return its verdict."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp).resolve()
        tasks_state = build_case(case, root)
        report, _ = verify_core.build_report(tasks_state, root)
    item = next(t for t in report["tasks"] if t["task_id"] == case["task"]["id"])
    failing = sorted(
        k for k, v in item.items()
        if k.startswith("lens_") and v == "fail"
    )
    return {
        "name": case["name"],
        "truth": case["truth"],
        "expect_lens": case["expect_lens"],
        "verdict": item["verified_status"],
        "failing_lenses": failing,
    }


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------


def run_all() -> dict[str, Any]:
    """Run every case and score the treatment arm against the baseline."""
    results = [run_case(c) for c in CASES]

    phantoms = [r for r in results if r["truth"] == "phantom"]
    reals = [r for r in results if r["truth"] == "real"]

    caught = [r for r in phantoms if r["verdict"] == "fail"]
    missed = [r for r in phantoms if r["verdict"] != "fail"]
    clean = [r for r in reals if r["verdict"] == "pass"]
    false_alarm = [r for r in reals if r["verdict"] != "pass"]

    # A phantom is "caught by the expected lens" when that lens is among the
    # failing lenses, or, for the zero-evidence case (expect_lens None), when the
    # harness still refused to pass it.
    by_expected_lens = []
    for r in phantoms:
        if r["expect_lens"] is None:
            by_expected_lens.append(r["verdict"] == "fail")
        else:
            by_expected_lens.append(r["expect_lens"] in r["failing_lenses"])

    total_phantom = len(phantoms)
    total_real = len(reals)
    return {
        "cases": results,
        "total_phantom": total_phantom,
        "caught": len(caught),
        "missed": [r["name"] for r in missed],
        "total_real": total_real,
        "clean": len(clean),
        "false_alarm_cases": [r["name"] for r in false_alarm],
        "phantom_catch_rate": (len(caught) / total_phantom) if total_phantom else 0.0,
        "false_alarm_rate": (len(false_alarm) / total_real) if total_real else 0.0,
        "expected_lens_hit_rate": (sum(by_expected_lens) / total_phantom) if total_phantom else 0.0,
        # The bare-checkbox baseline re-checks nothing, so it catches no phantom.
        "baseline_catch_rate": 0.0,
    }


# ---------------------------------------------------------------------------
# Reporting and CLI
# ---------------------------------------------------------------------------


def _print_summary(scored: dict[str, Any]) -> None:
    print("Mergen phantom-detection benchmark (deterministic, no LLM)")
    print(f"  cases: {len(scored['cases'])} "
          f"({scored['total_phantom']} phantom, {scored['total_real']} genuine)")
    print("")
    print(f"  {'case':32s} {'truth':8s} {'verdict':8s} failing lenses")
    for r in scored["cases"]:
        lenses = ", ".join(s[len('lens_'):] for s in r["failing_lenses"]) or "-"
        print(f"  {r['name']:32s} {r['truth']:8s} {r['verdict']:8s} {lenses}")
    print("")
    print(f"  phantom catch rate (treatment): {scored['phantom_catch_rate']:.2f}"
          f"  ({scored['caught']}/{scored['total_phantom']} caught)")
    print(f"  phantom catch rate (baseline):  {scored['baseline_catch_rate']:.2f}"
          f"  (trust the [X] checkbox, re-checks nothing)")
    print(f"  false-alarm rate (treatment):   {scored['false_alarm_rate']:.2f}"
          f"  ({len(scored['false_alarm_cases'])}/{scored['total_real']} genuine wrongly failed)")
    print(f"  caught by the expected lens:    {scored['expected_lens_hit_rate']:.2f}")
    if scored["missed"]:
        print(f"  MISSED phantoms: {', '.join(scored['missed'])}")
    if scored["false_alarm_cases"]:
        print(f"  FALSE ALARMS:    {', '.join(scored['false_alarm_cases'])}")


def run_gate(scored: dict[str, Any]) -> int:
    """Fail when the harness regresses: any phantom missed or any genuine failed."""
    ok = (
        scored["phantom_catch_rate"] >= 1.0
        and scored["false_alarm_rate"] <= 0.0
        and scored["expected_lens_hit_rate"] >= 1.0
    )
    print(f"  gate result: {'PASS' if ok else 'FAIL'}")
    if not ok:
        print("  the verify harness regressed: a planted phantom went uncaught or a "
              "genuine completion was wrongly failed.", file=sys.stderr)
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Mergen phantom-detection benchmark")
    ap.add_argument("--out", help="write the scored result as JSON to this path")
    ap.add_argument("--json", action="store_true", help="print the scored result as JSON to stdout")
    ap.add_argument("--gate", action="store_true",
                    help="exit non-zero if the harness misses a phantom or false-alarms a genuine task")
    args = ap.parse_args(argv)

    scored = run_all()

    if args.json:
        print(json.dumps(scored, indent=2))
    else:
        _print_summary(scored)

    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(json.dumps(scored, indent=2).encode("utf-8"))

    if args.gate:
        return run_gate(scored)
    return 0


if __name__ == "__main__":
    sys.exit(main())
