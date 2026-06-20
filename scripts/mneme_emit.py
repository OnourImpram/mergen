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
no-network-on-critical-path and markdown-ground-truth invariants. A bounded
write-to-vault direction (write_decision_record, CLI --write) persists a record
into a directory the operator names, with a producer-side redaction preflight and
duplicate detection. mneme still does its own redaction at ingest, and the store
integration (direct vault write versus MCP) is not decided here. See
docs/MNEME-SEAM.md.

Stdlib only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
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


# --------------------------------------------------------------------------- #
# Write-to-vault direction: persist a decision record into a directory the user
# names. No vault path is hardcoded and no store integration is decided here
# (direct write versus MCP stays the operator's call). Two producer-side
# safeguards: a redaction preflight that fails closed on a secret-like pattern,
# and substantive duplicate detection so a re-verify does not clutter the vault.
# mneme still does its own redaction at ingest. This is defense in depth.
# --------------------------------------------------------------------------- #

_SECRET_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("private-key-block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("aws-access-key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("assigned-secret", re.compile(
        r"(?i)\b(password|passwd|secret|token|api[_-]?key|access[_-]?key|client[_-]?secret)\b"
        r"\s*[:=]\s*\S{6,}")),
    # Well-known token prefixes that carry their own entropy and so appear bare,
    # without a key=value shape: GitHub, Stripe, OpenAI, Anthropic, Google, Slack.
    ("known-token-prefix", re.compile(
        r"\b(ghp_|gho_|ghu_|ghs_|ghr_|github_pat_|sk_live_|rk_live_|pk_live_|"
        r"sk-proj-|sk-ant-|sk-org-|AIza|xox[baprs]-)[A-Za-z0-9_-]{10,}")),
    # A bare bearer token or a JWT (three base64url segments), which also carry no
    # key=value shape.
    ("jwt-or-bearer", re.compile(
        r"(?i)\bbearer\s+[A-Za-z0-9._-]{12,}"
        r"|\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}")),
    ("email-address", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")),
]


def redaction_preflight(text: str) -> list[str]:
    """Report secret or PII patterns in text, by label and offset only.

    This is defense in depth, not a comprehensive secret scanner. It catches PEM
    private-key blocks, AWS-format keys, several well-known token prefixes (GitHub,
    Stripe, OpenAI, Anthropic, Google, Slack), JWT and bearer tokens, labeled
    key=value secrets, and email addresses. A high-entropy token in an
    unrecognized format can still slip through, so an empty list means clean by
    THESE checks, not provably secret-free. mneme still redacts at ingest.

    The matched text itself is never returned, so a finding does not leak the
    secret it found.
    """
    findings: list[str] = []
    for label, pattern in _SECRET_PATTERNS:
        for m in pattern.finditer(text):
            findings.append(f"{label} (offset {m.start()})")
    return findings


def _slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9._-]+", "-", text.lower()).strip("-")
    return s or "decision"


def _dedup_key(record: dict[str, Any]) -> tuple[Any, ...]:
    """Substantive identity of a decision, ignoring the timestamp.

    Two records with the same feature, verdict, and proven/unproven sets are the
    same decision even if re-verified at a different time.
    """
    return (record.get("feature_id", ""), record.get("verdict", ""),
            tuple(record.get("proven", [])), tuple(record.get("unproven", [])))


def write_decision_record(
    report: dict[str, Any], out_dir: str | Path, force: bool = False
) -> tuple[Path | None, str, list[str]]:
    """Write the decision record for report into out_dir.

    Returns (path, status, findings). status is one of:
      blocked    the redaction preflight found a secret and force is False. No
                 file is written and the markdown is not returned, so nothing
                 leaks. path is None, findings lists the labels.
      duplicate  a substantively-equal record already exists. path points to it,
                 no new file is written.
      written    a new record was written at path.
    Filenames embed a content hash, so two distinct records get distinct names
    (a collision needs two different records to share a 48-bit prefix).
    """
    markdown = to_decision_markdown(report)
    findings = redaction_preflight(markdown)
    if findings and not force:
        return None, "blocked", findings

    directory = Path(out_dir)
    new_key = _dedup_key(parse_decision_record(markdown))
    for existing in read_decision_records(directory):
        if _dedup_key(existing) == new_key:
            return Path(existing["path"]), "duplicate", []

    feature_id = report.get("feature_id") or "unknown"
    digest = hashlib.sha256(markdown.encode("utf-8")).hexdigest()[:12]
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"decision-{_slug(str(feature_id))}-{digest}.md"
    path.write_bytes(markdown.encode("utf-8"))
    return path, "written", []


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
    ap.add_argument("--write", metavar="DIR",
                    help="write the decision record into DIR. Runs a redaction "
                         "preflight (fails closed on a secret) and skips a "
                         "substantively-equal existing record.")
    ap.add_argument("--force", action="store_true",
                    help="with --write, write even if the redaction preflight flags a "
                         "secret-like pattern. Not recommended.")
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

    if args.write:
        path, status, findings = write_decision_record(report, args.write, force=args.force)
        if status == "blocked":
            # Fail closed: do not write the file and do not echo the markdown,
            # so the flagged secret never reaches a file or stdout.
            print("redaction preflight blocked the write:", file=sys.stderr)
            for f in findings:
                print(f"  {f}", file=sys.stderr)
            print("fix the source report or pass --force to override (not recommended).",
                  file=sys.stderr)
            return 1
        print(f"{status}: {path}", file=sys.stderr)
        return 0

    sys.stdout.write(to_decision_markdown(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
