#!/usr/bin/env python3
"""mergen trends: cross-run verification trends and per-task churn.

Where `mergen dashboard` is a snapshot, one row per report, this is the cross-run
dimension. It reads the same directory of verification-report.json files, orders
them by verification time, and answers two questions a single report cannot.

  trends  how phantom completions, work-done rate, and ambiguity move across the
          run history. The cross-run view the snapshot dashboard cannot give.
  churn   which tasks are re-queued or reverted most often across runs, the spec
          patterns that reliably produce verifier failures. A task's churn is its
          count of verified-status flips plus the runs it was a phantom.

Tier 0: pure standard library, no Claude Code, no network, no model. The HTML
page is self-contained, inline CSS, an inline SVG sparkline, no JavaScript, no
external asset. --json emits the same metrics as a machine-readable export, the
honest observability seam. An external collector can ingest that JSON, and mergen
core still takes no telemetry dependency and makes no network call of its own.

Metrics are computed from each report's tasks array, the schema-required surface
(task_id, claimed_status, verified_status, confidence), not from the optional
summary counters, so the numbers hold for any conforming report.

Exit codes: 0 on success, 2 when the path is not a directory.
"""

from __future__ import annotations

import argparse
import html
import json
import sys
from pathlib import Path
from typing import Any

_VERDICT_CLASS = {"pass": "ok", "conditional_pass": "warn", "fail": "bad"}
_DEFAULT_TOP = 20  # churn leaderboard rows shown before truncation is announced


def load_runs(directory: Path) -> list[tuple[str, dict[str, Any]]]:
    """Read every verification-report-shaped JSON under directory, time-ordered.

    utf-8-sig tolerates a BOM. A file that does not parse, or carries no tasks
    array, is skipped with a note rather than crashing the run. Runs are ordered
    by verified_at so the series reads oldest to newest, with the filename as a
    deterministic tiebreaker when a timestamp is absent or shared.
    """
    runs: list[tuple[str, dict[str, Any]]] = []
    for f in sorted(directory.glob("*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8-sig"))
        except Exception as exc:  # noqa: BLE001 - skip and report, never crash
            print(f"skip {f.name}: {exc}", file=sys.stderr)
            continue
        if isinstance(data, dict) and isinstance(data.get("tasks"), list):
            runs.append((f.name, data))

    def _key(nr: tuple[str, dict[str, Any]]) -> tuple[str, str]:
        # Order by the ISO verified_at, with the filename as a deterministic
        # tiebreak. A missing or non-string timestamp (load_runs tolerates
        # malformed reports) sorts to the front as an unknown time rather than by
        # some incidental decimal repr.
        ts = nr[1].get("verified_at")
        return (ts if isinstance(ts, str) else "", nr[0])

    runs.sort(key=_key)
    return runs


def _is_phantom(task: dict[str, Any]) -> bool:
    """A phantom is a task claimed done that verification failed."""
    return task.get("claimed_status") == "done" and task.get("verified_status") == "fail"


def run_metrics(name: str, report: dict[str, Any]) -> dict[str, Any]:
    """Reduce one report to the per-run trend row, computed from its tasks array."""
    tasks = [t for t in report.get("tasks", []) if isinstance(t, dict)]
    claimed_done = sum(1 for t in tasks if t.get("claimed_status") == "done")
    passed = sum(1 for t in tasks if t.get("verified_status") == "pass")
    phantoms = sum(1 for t in tasks if _is_phantom(t))
    ambiguous = sum(1 for t in tasks if t.get("confidence") == "ambiguous")
    done_confirmed = claimed_done - phantoms
    # Of the tasks claimed done, the fraction a lens confirmed. None when nothing
    # was claimed done, so a caller abstains rather than render a misleading 0 or
    # divide by zero.
    work_done_rate = (done_confirmed / claimed_done) if claimed_done else None
    summary = report.get("summary")
    verdict = str(summary.get("verdict", "unknown")) if isinstance(summary, dict) else "unknown"
    return {
        "file": name,
        "feature_id": str(report.get("feature_id", "unknown")),
        "verified_at": str(report.get("verified_at", "")),
        "verdict": verdict,
        "total": len(tasks),
        "claimed_done": claimed_done,
        "passed": passed,
        "phantoms": phantoms,
        "ambiguous": ambiguous,
        "work_done_rate": work_done_rate,
    }


def task_churn(runs: list[tuple[str, dict[str, Any]]]) -> list[dict[str, Any]]:
    """Per-task churn across the ordered runs.

    Walks runs in chronological order tracking each task's verified_status
    history. A flip is a change in verified_status between two consecutive
    appearances (a re-queue or a revert). phantom_runs counts runs where the task
    was claimed done but failed. churn_score is flips plus phantom_runs, the
    combined "this task keeps fighting the verifier" signal.
    """
    history: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for _name, report in runs:
        for t in report.get("tasks", []):
            if not isinstance(t, dict):
                continue
            tid = t.get("task_id")
            if not isinstance(tid, str):
                continue
            status = t.get("verified_status")
            h = history.get(tid)
            if h is None:
                h = {"runs": 0, "phantom_runs": 0, "flips": 0, "last": None}
                history[tid] = h
                order.append(tid)
            h["runs"] += 1
            if _is_phantom(t):
                h["phantom_runs"] += 1
            if h["last"] is not None and status != h["last"]:
                h["flips"] += 1
            h["last"] = status
    rows = [
        {
            "task_id": tid,
            "runs": history[tid]["runs"],
            "phantom_runs": history[tid]["phantom_runs"],
            "flips": history[tid]["flips"],
            "last_status": history[tid]["last"],
            "churn_score": history[tid]["flips"] + history[tid]["phantom_runs"],
        }
        for tid in order
    ]
    # Most churny first. Ties broken by phantom_runs then task_id so the order is
    # stable and reproducible across runs of this tool.
    rows.sort(key=lambda r: (-r["churn_score"], -r["phantom_runs"], r["task_id"]))
    return rows


def build_export(directory: Path, runs: list[tuple[str, dict[str, Any]]]) -> dict[str, Any]:
    """The machine-readable metrics export, the observability seam (--json)."""
    metrics = [run_metrics(name, rep) for name, rep in runs]
    return {
        "schema": "mergen-trends/1.0",
        "source_dir": str(directory),
        "report_count": len(runs),
        "runs": metrics,
        "churn": task_churn(runs),
    }


# --------------------------------------------------------------------------- #
# HTML rendering (self-contained, inline CSS and SVG, no JavaScript)
# --------------------------------------------------------------------------- #

_CSS = """
body { font: 15px/1.5 system-ui, sans-serif; margin: 2rem; color: #1c2128; background: #fff; }
h1 { font-size: 1.4rem; margin: 0 0 .25rem; }
h2 { font-size: 1.05rem; margin: 1.75rem 0 .5rem; }
.sub { color: #57606a; margin: 0 0 1.5rem; }
.cards { display: flex; gap: 1rem; flex-wrap: wrap; margin-bottom: 1rem; }
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
.spark { vertical-align: middle; }
.spark polyline { stroke: #cf222e; }
.spark circle { fill: #cf222e; }
.note { color: #57606a; font-size: .85rem; margin: .5rem 0 0; }
""".strip()


def _sparkline(values: list[int], width: int = 240, height: int = 36) -> str:
    """An inline SVG polyline of integer values. Pure markup, no script."""
    if not values:
        return ""
    lo, hi = min(values), max(values)
    span = (hi - lo) or 1
    if len(values) == 1:
        return (f'<svg class="spark" width="{width}" height="{height}" '
                f'viewBox="0 0 {width} {height}" role="img" aria-label="phantom history">'
                f'<circle cx="{width / 2:.1f}" cy="{height / 2:.1f}" r="2.5"/></svg>')
    step = width / (len(values) - 1)
    pts = []
    for i, v in enumerate(values):
        x = i * step
        # Higher value sits higher on the page (smaller y), so a rising line means
        # more phantoms, which is the direction a reader expects to read as worse.
        y = height - ((v - lo) / span) * (height - 6) - 3
        pts.append(f"{x:.1f},{y:.1f}")
    return (f'<svg class="spark" width="{width}" height="{height}" '
            f'viewBox="0 0 {width} {height}" role="img" '
            f'aria-label="phantom completions across runs">'
            f'<polyline fill="none" stroke-width="2" points="{" ".join(pts)}"/></svg>')


def _rate(value: Any) -> str:
    return "n/a" if value is None else f"{value * 100:.0f}%"


def render_html(runs: list[tuple[str, dict[str, Any]]], top: int = _DEFAULT_TOP) -> str:
    """Render the cross-run trends and churn leaderboard into one HTML page."""
    metrics = [run_metrics(name, rep) for name, rep in runs]
    churn = task_churn(runs)

    def esc(value: Any) -> str:
        return html.escape(str(value))

    n_runs = len(metrics)
    latest = metrics[-1] if metrics else None
    first = metrics[0] if metrics else None
    phantom_series = [m["phantoms"] for m in metrics]
    delta = (latest["phantoms"] - first["phantoms"]) if latest and first else 0
    delta_str = f"{'+' if delta > 0 else ''}{delta}"
    churny = sum(1 for c in churn if c["churn_score"] > 0)

    cards = "".join(
        f'<div class="card"><div class="n">{esc(n)}</div><div class="l">{esc(label)}</div></div>'
        for n, label in (
            (n_runs, "runs"),
            (latest["verdict"] if latest else "n/a", "latest verdict"),
            (latest["phantoms"] if latest else 0, "latest phantoms"),
            (delta_str, "phantoms vs first run"),
            (churny, "tasks with churn"),
        )
    )

    if metrics:
        trend_parts = []
        for m in metrics:
            # css is a controlled class constant, never the raw report verdict. The
            # verdict string itself only ever reaches the page through esc() as text,
            # so a crafted report value cannot break out of the markup.
            css = _VERDICT_CLASS.get(m["verdict"], "muted")
            trend_parts.append(
                "<tr>"
                f'<td class="muted">{esc(m["verified_at"] or m["file"])}</td>'
                f'<td><span class="tag {css}">{esc(m["verdict"])}</span></td>'
                f"<td>{esc(m['claimed_done'])}</td>"
                f"<td>{esc(m['passed'])}</td>"
                f"<td>{esc(m['phantoms'])}</td>"
                f"<td>{esc(m['ambiguous'])}</td>"
                f"<td>{esc(_rate(m['work_done_rate']))}</td>"
                "</tr>"
            )
        trend_rows = "".join(trend_parts)
        trend_table = (
            f'<p class="note">Phantom completions across runs (rising is worse): {_sparkline(phantom_series)}</p>'
            "<table><thead><tr>"
            "<th>verified at</th><th>verdict</th><th>claimed done</th><th>passed</th>"
            "<th>phantoms</th><th>ambiguous</th><th>work-done rate</th>"
            "</tr></thead><tbody>" + trend_rows + "</tbody></table>"
            '<p class="note">Over-build trend needs lean data, which the verification '
            "report does not carry, so it is not shown here yet.</p>"
        )
    else:
        trend_table = '<p class="empty">No verification reports with a tasks array in this directory.</p>'

    if churn:
        shown = churn[:top]
        churn_rows = "".join(
            "<tr>"
            f"<td>{esc(c['task_id'])}</td>"
            f"<td>{esc(c['churn_score'])}</td>"
            f"<td>{esc(c['flips'])}</td>"
            f"<td>{esc(c['phantom_runs'])}</td>"
            f"<td>{esc(c['runs'])}</td>"
            f'<td class="muted">{esc(c["last_status"])}</td>'
            "</tr>"
            for c in shown
        )
        churn_table = (
            "<table><thead><tr>"
            "<th>task</th><th>churn</th><th>flips</th><th>phantom runs</th>"
            "<th>appearances</th><th>last status</th>"
            "</tr></thead><tbody>" + churn_rows + "</tbody></table>"
        )
        if len(churn) > top:
            churn_table += (
                f'<p class="note">Showing the {top} most churny of {len(churn)} tasks. '
                "Pass --top to widen.</p>"
            )
    else:
        churn_table = '<p class="empty">No tasks seen across the runs.</p>'

    return (
        "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
        "<title>Mergen verification trends</title>"
        f"<style>{_CSS}</style></head><body>"
        "<h1>Mergen verification trends</h1>"
        '<p class="sub">Static, offline, generated from a directory of verification '
        "reports over time. A phantom completion is a task claimed done that no lens "
        "confirmed. Churn is how often a task flips verdict or returns as a phantom.</p>"
        f'<div class="cards">{cards}</div>'
        "<h2>Trends across runs</h2>"
        f"{trend_table}"
        "<h2>Task churn leaderboard</h2>"
        f"{churn_table}"
        "</body></html>\n"
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Cross-run verification trends and per-task churn over a reports directory."
    )
    ap.add_argument("reports_dir", help="directory holding verification-report.json files")
    ap.add_argument("--out", help="write the HTML here (default: stdout)")
    ap.add_argument("--json", action="store_true",
                    help="emit the machine-readable metrics export instead of HTML")
    ap.add_argument("--top", type=int, default=_DEFAULT_TOP,
                    help=f"churn leaderboard rows before truncation (default: {_DEFAULT_TOP})")
    args = ap.parse_args(argv)

    directory = Path(args.reports_dir)
    if not directory.is_dir():
        print(f"error: not a directory: {directory}", file=sys.stderr)
        return 2

    runs = load_runs(directory)

    if args.json:
        sys.stdout.write(json.dumps(build_export(directory, runs), indent=2) + "\n")
        return 0

    html_text = render_html(runs, top=args.top)
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
