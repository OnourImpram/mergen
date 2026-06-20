#!/usr/bin/env python3
"""mergen status: a compact, agent-agnostic summary of tasks-state.json.

Reads the machine-readable completion record that /mergen.verify and
/mergen.rollup maintain and reports how many tasks are done versus pending, with
a per-task line. The Spec Kit analog is `specify status`. Pure standard library,
no network, no model.

Exit codes mirror verify_core: 0 on a clean read, 2 when the tasks-state file is
missing or cannot be parsed (so a caller can tell "no state" from "all pending").
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def summarize(state: Any) -> dict[str, Any]:
    """Reduce a tasks-state document to counts and a normalized task list.

    Typed Any rather than dict on purpose. The non-dict fallback below is
    intentional resilience: a malformed JSON top level (a bare list, a string)
    degrades to an empty, unknown-feature summary instead of raising.
    """
    tasks = state.get("tasks", []) if isinstance(state, dict) else []
    tasks = [t for t in tasks if isinstance(t, dict)]
    done = sum(1 for t in tasks if t.get("status") == "done")
    pending = sum(1 for t in tasks if t.get("status") == "pending")
    other = len(tasks) - done - pending
    return {
        "feature_id": state.get("feature_id", "unknown") if isinstance(state, dict) else "unknown",
        "total": len(tasks),
        "done": done,
        "pending": pending,
        "other": other,
        "tasks": tasks,
    }


def render_text(s: dict[str, Any]) -> str:
    head = f"tasks:   {s['done']}/{s['total']} done, {s['pending']} pending"
    if s["other"]:
        head += f", {s['other']} other"
    lines = [f"feature: {s['feature_id']}", head, ""]
    for t in s["tasks"]:
        mark = "X" if t.get("status") == "done" else " "
        tid = t.get("id", "?")
        files = ", ".join(t.get("files") or []) or "-"
        verified = t.get("last_verified_at") or "-"
        lines.append(f"  [{mark}] {tid}  files: {files}  verified: {verified}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Summarize a mergen tasks-state.json")
    ap.add_argument("tasks_state", help="path to tasks-state.json")
    ap.add_argument("--json", action="store_true", help="emit the summary counts as JSON")
    args = ap.parse_args(argv)

    path = Path(args.tasks_state)
    if not path.is_file():
        print(f"error: tasks-state not found: {path}", file=sys.stderr)
        return 2
    try:
        state = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"error: could not read tasks-state {path}: {exc}", file=sys.stderr)
        return 2

    s = summarize(state)
    if args.json:
        counts = {k: s[k] for k in ("feature_id", "total", "done", "pending", "other")}
        print(json.dumps(counts, indent=2))
    else:
        print(render_text(s))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
