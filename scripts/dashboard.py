#!/usr/bin/env python3
"""Local static dashboard over Mergen verification reports.

Reads a directory of verification-report.json files and emits one self-contained
HTML page (inline CSS, no network, no external asset, no JavaScript) summarizing
each report's verdict, task counts, phantom completions, and provenance.

Agent agnostic and Tier 0: pure standard library, no Claude Code, no network, no
model. Every value from a report is HTML-escaped before it reaches the page, so a
report can carry arbitrary strings without breaking out of the markup.
"""

from __future__ import annotations

import argparse
import html
import json
import sys
from pathlib import Path
from typing import Any

_VERDICT_CLASS = {"pass": "ok", "conditional_pass": "warn", "fail": "bad"}


def load_reports(directory: Path) -> list[tuple[str, dict[str, Any]]]:
    """Read every verification-report-shaped JSON under directory.

    utf-8-sig tolerates a BOM. A file that does not parse, or is not a report
    (no summary block), is skipped with a note, never crashing the run.
    """
    reports: list[tuple[str, dict[str, Any]]] = []
    for f in sorted(directory.glob("*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8-sig"))
        except Exception as exc:  # noqa: BLE001 - skip and report, do not crash
            print(f"skip {f.name}: {exc}", file=sys.stderr)
            continue
        if isinstance(data, dict) and isinstance(data.get("summary"), dict):
            reports.append((f.name, data))
    return reports


def _int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def summarize(name: str, report: dict[str, Any]) -> dict[str, Any]:
    """Reduce one report to the row fields the dashboard renders."""
    summary = report.get("summary", {})
    prov = report.get("provenance", {}) if isinstance(report.get("provenance"), dict) else {}
    commit = prov.get("source_commit")
    clean = prov.get("working_tree_clean")
    if clean is True:
        tree = "clean"
    elif clean is False:
        tree = "dirty"
    else:
        tree = "n/a"
    return {
        "file": name,
        "feature_id": str(report.get("feature_id", "unknown")),
        "verdict": str(summary.get("verdict", "unknown")),
        "verified_at": str(report.get("verified_at", "")),
        "passed": _int(summary.get("mechanically_passed")),
        # A phantom is a task claimed done that no lens confirmed.
        "phantoms": _int(summary.get("mechanically_failed")),
        "ambiguous": _int(summary.get("ambiguous")),
        "done": _int(summary.get("total_done_tasks")),
        "commit": commit[:12] if isinstance(commit, str) and commit else "n/a",
        "tree": tree,
    }


_CSS = """
body { font: 15px/1.5 system-ui, sans-serif; margin: 2rem; color: #1c2128; background: #fff; }
h1 { font-size: 1.4rem; margin: 0 0 .25rem; }
.sub { color: #57606a; margin: 0 0 1.5rem; }
.cards { display: flex; gap: 1rem; flex-wrap: wrap; margin-bottom: 1.5rem; }
.card { border: 1px solid #d0d7de; border-radius: 8px; padding: .75rem 1rem; min-width: 7rem; }
.card .n { font-size: 1.6rem; font-weight: 600; }
.card .l { color: #57606a; font-size: .85rem; }
table { border-collapse: collapse; width: 100%; }
th, td { text-align: left; padding: .5rem .6rem; border-bottom: 1px solid #d0d7de; }
th { color: #57606a; font-weight: 600; font-size: .85rem; }
.tag { display: inline-block; padding: .1rem .5rem; border-radius: 99px; font-size: .8rem; font-weight: 600; }
.ok { background: #dafbe1; color: #1a7f37; }
.warn { background: #fff8c5; color: #7d4e00; }
.bad { background: #ffebe9; color: #cf222e; }
.muted { color: #8c959f; }
.empty { color: #57606a; padding: 2rem 0; }
""".strip()


def render_html(reports: list[tuple[str, dict[str, Any]]]) -> str:
    """Render the reports into one self-contained HTML page."""
    rows = [summarize(name, rep) for name, rep in reports]
    total = len(rows)
    n_pass = sum(1 for r in rows if r["verdict"] == "pass")
    n_cond = sum(1 for r in rows if r["verdict"] == "conditional_pass")
    n_fail = sum(1 for r in rows if r["verdict"] == "fail")
    phantoms = sum(r["phantoms"] for r in rows)

    def esc(value: Any) -> str:
        return html.escape(str(value))

    cards = "".join(
        f'<div class="card"><div class="n">{n}</div><div class="l">{esc(label)}</div></div>'
        for n, label in (
            (total, "reports"),
            (n_pass, "pass"),
            (n_cond, "conditional"),
            (n_fail, "fail"),
            (phantoms, "phantom completions"),
        )
    )

    if rows:
        body_rows = "".join(
            "<tr>"
            f"<td>{esc(r['feature_id'])}</td>"
            f'<td><span class="tag {_VERDICT_CLASS.get(r["verdict"], "muted")}">{esc(r["verdict"])}</span></td>'
            f"<td>{r['passed']}</td>"
            f"<td>{r['phantoms']}</td>"
            f"<td>{r['ambiguous']}</td>"
            f"<td>{r['done']}</td>"
            f'<td class="muted">{esc(r["commit"])}</td>'
            f'<td class="muted">{esc(r["tree"])}</td>'
            f'<td class="muted">{esc(r["verified_at"])}</td>'
            f'<td class="muted">{esc(r["file"])}</td>'
            "</tr>"
            for r in rows
        )
        table = (
            "<table><thead><tr>"
            "<th>feature</th><th>verdict</th><th>passed</th><th>phantoms</th>"
            "<th>ambiguous</th><th>done</th><th>commit</th><th>tree</th>"
            "<th>verified at</th><th>report</th>"
            "</tr></thead><tbody>" + body_rows + "</tbody></table>"
        )
    else:
        table = '<p class="empty">No verification reports found in this directory.</p>'

    return (
        "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
        "<title>Mergen verification dashboard</title>"
        f"<style>{_CSS}</style></head><body>"
        "<h1>Mergen verification dashboard</h1>"
        '<p class="sub">Static, offline, generated from verification reports. '
        "A phantom completion is a task claimed done that no lens confirmed.</p>"
        f'<div class="cards">{cards}</div>'
        f"{table}"
        "</body></html>\n"
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Render a static HTML dashboard over a directory of verification reports."
    )
    ap.add_argument("reports_dir", help="directory holding verification-report.json files")
    ap.add_argument("--out", help="write the HTML here (default: stdout)")
    args = ap.parse_args(argv)

    directory = Path(args.reports_dir)
    if not directory.is_dir():
        print(f"error: not a directory: {directory}", file=sys.stderr)
        return 2

    html_text = render_html(load_reports(directory))
    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(html_text.encode("utf-8"))
        print(f"wrote {out_path}", file=sys.stderr)
    else:
        sys.stdout.write(html_text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
