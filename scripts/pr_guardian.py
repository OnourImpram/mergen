#!/usr/bin/env python3
"""mergen PR Guardian: a pull-request evidence summary and gate.

Reads one verification-report.json and produces a compact markdown summary a CI
step can post as a pull-request comment: the verdict, the risk level, how many
tasks were claimed done versus independently verified, the phantom-completion
count, the human sign-off state, and any integrity finding. It gates the same way
verify-lint does, and additionally fails on any phantom completion, so a phantom
or an unsigned high-trust report cannot merge in silence.

The gate decision reuses scripts/verify_report_lint.py rather than re-deriving
the rules, so the Guardian and the linter cannot drift. Posting the comment is
the CI host's job (gh or actions/github-script); this script only produces the
markdown and the exit code, so it runs anywhere with no network.

Exit codes mirror the rest of mergen: 0 clean, 1 a gate finding, 2 nothing to
read. Tier 0, pure standard library.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any


def _load_linter() -> Any:
    """Load scripts/verify_report_lint.py by path (scripts/ is not a package)."""
    repo = Path(__file__).resolve().parent
    spec = importlib.util.spec_from_file_location(
        "verify_report_lint", repo / "verify_report_lint.py")
    if spec is None or spec.loader is None:  # pragma: no cover - import wiring
        raise ImportError("cannot load verify_report_lint")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _safe(value: Any) -> str:
    """Neutralize a report value before it lands in the comment markdown.

    A hostile report could carry a backtick or a newline in a verdict, a path, or
    a message, which would break the rendered comment. This is cosmetic, not a
    security boundary (the value reaches gh through a --body-file, never a shell),
    but a clean comment is worth the one-line guard.
    """
    return str(value).replace("`", "'").replace("\n", " ").replace("\r", " ")


def task_counts(report: dict[str, Any]) -> tuple[int, int, int]:
    """Return (claimed_done, verified_pass, phantom) from the tasks array."""
    tasks = report.get("tasks")
    tasks = [t for t in tasks if isinstance(t, dict)] if isinstance(tasks, list) else []
    claimed = sum(1 for t in tasks if t.get("claimed_status") == "done")
    verified = sum(1 for t in tasks if t.get("verified_status") == "pass")
    phantom = sum(1 for t in tasks
                  if t.get("claimed_status") == "done" and t.get("verified_status") != "pass")
    return claimed, verified, phantom


def summarize(report: dict[str, Any], source: str, *,
              allow_conditional: bool = False) -> tuple[str, int]:
    """Return (markdown_summary, exit_code) for one report.

    The exit code is 1 when the linter reports an error or when any phantom
    completion is present, else 0. Phantom is gated explicitly because a report
    can record a phantom task while still declaring an overall pass verdict, and
    the Guardian refuses that.
    """
    linter = _load_linter()
    findings = linter.lint_report(report, source, allow_conditional=allow_conditional)
    errors = [f for f in findings if f.level == "error"]

    summary = report.get("summary")
    summary = summary if isinstance(summary, dict) else {}
    verdict = summary.get("verdict", "unknown")
    risk = summary.get("risk_level", "unstated")
    review = summary.get("human_review")
    sign = review.get("status", "none") if isinstance(review, dict) else "none"
    claimed, verified, phantom = task_counts(report)

    lines = [
        "## Mergen verification summary",
        "",
        f"- verdict: `{_safe(verdict)}`",
        f"- risk level: `{_safe(risk)}`",
        f"- tasks claimed done / verified pass: {claimed} / {verified}",
        f"- phantom completions: {phantom}",
        f"- human sign-off: `{_safe(sign)}`",
        "",
    ]
    failed = bool(errors) or phantom > 0
    if failed:
        lines.append("This report is not a clean, proven pass. Gate findings:")
        lines.append("")
        if phantom > 0:
            lines.append(f"- `PHANTOM_COMPLETIONS` {phantom} task(s) claimed done but not verified pass")
        for e in errors:
            lines.append(f"- `{_safe(e.code)}` {_safe(e.where)}: {_safe(e.message)}")
    else:
        lines.append("No gate findings. Every claimed task is verified with concrete evidence.")
    lines.append("")
    return "\n".join(lines), (1 if failed else 0)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Summarize and gate a verification report for a pull request")
    ap.add_argument("report", help="path to a verification-report.json")
    ap.add_argument("--allow-conditional", action="store_true",
                    help="accept a conditional_pass verdict (the caller owns the caveat)")
    ap.add_argument("--out", metavar="FILE",
                    help="also write the markdown summary to FILE (for the comment step)")
    args = ap.parse_args(argv)

    path = Path(args.report)
    if not path.is_file():
        print("pr-guardian: no verification-report.json found", file=sys.stderr)
        return 2
    try:
        report = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"pr-guardian: cannot read report: {exc}", file=sys.stderr)
        return 2
    if not isinstance(report, dict):
        print("pr-guardian: report is not a JSON object", file=sys.stderr)
        return 2

    markdown, rc = summarize(report, str(path), allow_conditional=args.allow_conditional)
    print(markdown)
    if args.out:
        Path(args.out).write_text(markdown, encoding="utf-8")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
