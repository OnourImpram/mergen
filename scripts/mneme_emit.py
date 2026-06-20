#!/usr/bin/env python3
"""Mergen <-> mneme decision-record seam (bidirectional).

Write direction: convert a Mergen verification-report.json into a mneme-style
decision record in Markdown, so mneme can ingest it through its own public vault
format. Read direction (weighted equally): parse those same records back from a
mneme vault directory, so a new decision can be informed by prior ones. This is
the only bridge between the two systems. Mergen stores no memory of its own. It
emits an already-safe, provenance-bearing, confidence-labeled record and hands
it to mneme, and reads records back in that same documented shape.

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
from typing import Any


def to_decision_markdown(report: dict[str, Any]) -> str:
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


# --------------------------------------------------------------------------- #
# Read direction: parse mneme-stored records back into mergen. The format is
# mergen's own emitted shape above, which is the documented seam contract, so
# reading never guesses mneme's internals. Zero hard dependency: an absent vault
# yields [], honoring mneme's markdown-ground-truth and no-network invariants.
# --------------------------------------------------------------------------- #

def _csv_or_none(value: str) -> list[str]:
    if not value or value.strip().lower() == "none":
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def parse_decision_record(markdown: str) -> dict[str, Any]:
    """Parse one decision record (the shape to_decision_markdown emits)."""
    record: dict[str, Any] = {"feature_id": "", "verdict": "", "confidence": "",
                              "verified_at": "", "proven": [], "unproven": []}
    for raw in markdown.splitlines():
        s = raw.strip()
        if s.startswith("# Decision:"):
            record["feature_id"] = s[len("# Decision:"):].strip()
        elif s.startswith("- source:"):
            val = s[len("- source:"):].strip()
            if val.endswith(")") and "(" in val:
                record["verified_at"] = val[val.rfind("(") + 1:-1].strip()
        elif s.startswith("- verdict:"):
            record["verdict"] = s[len("- verdict:"):].strip()
        elif s.startswith("- confidence:"):
            record["confidence"] = s[len("- confidence:"):].strip()
        elif s.startswith("- proven tasks:"):
            record["proven"] = _csv_or_none(s[len("- proven tasks:"):])
        elif s.startswith("- unproven tasks:"):
            record["unproven"] = _csv_or_none(s[len("- unproven tasks:"):])
    return record


def read_decision_records(vault_dir: str | Path) -> list[dict[str, Any]]:
    """Read and parse every decision record under a mneme vault directory.

    Returns [] when the directory is absent, so mergen has zero hard dependency
    on mneme being present.
    """
    d = Path(vault_dir)
    if not d.is_dir():
        return []
    records: list[dict[str, Any]] = []
    for f in sorted(d.glob("*.md")):
        try:
            rec = parse_decision_record(f.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 - skip an unreadable record, do not crash
            continue
        if rec["feature_id"]:
            rec["path"] = str(f)
            records.append(rec)
    return records


def prior_decisions_for(vault_dir: str | Path, feature_id: str) -> list[dict[str, Any]]:
    """Prior decision records for one feature, to inform a new decision."""
    return [r for r in read_decision_records(vault_dir) if r["feature_id"] == feature_id]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="mergen <-> mneme decision-record seam: emit a report, or read a vault"
    )
    ap.add_argument("report", nargs="?",
                    help="path to a verification-report.json (write direction)")
    ap.add_argument("--read", metavar="DIR",
                    help="read prior decision records from a mneme vault directory")
    ap.add_argument("--feature", metavar="ID",
                    help="with --read, return only records for this feature_id")
    args = ap.parse_args(argv)

    if args.read:
        records = (prior_decisions_for(args.read, args.feature)
                   if args.feature else read_decision_records(args.read))
        print(json.dumps(records, indent=2))
        return 0

    if not args.report:
        ap.error("provide a verification-report.json to emit, or --read DIR")
    try:
        # utf-8-sig so a BOM-prefixed report (the form Windows PowerShell writes,
        # and which evidence_metric.py already tolerates) reads here too.
        report = json.loads(Path(args.report).read_text(encoding="utf-8-sig"))
    except Exception as exc:  # noqa: BLE001
        print(f"cannot read report: {exc}", file=sys.stderr)
        return 1
    if not isinstance(report, dict):
        print(f"cannot process report: expected a JSON object, got {type(report).__name__}",
              file=sys.stderr)
        return 1
    sys.stdout.write(to_decision_markdown(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
