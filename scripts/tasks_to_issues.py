#!/usr/bin/env python3
"""mergen issues: render GitHub issue stubs from a tasks.md checklist.

The Spec Kit analog is taskstoissues. This RENDERS one markdown issue body per
task so you can create them, for example by piping each to `gh issue create`. It
does not create issues itself. Creating an issue is a side effect that needs your
GitHub auth and your decision, which a renderer must not take on your behalf.

It parses the standard mergen and Spec Kit tasks.md line, `- [ ] T001 [P] [US1]
description ...`, and, when a tasks-dag.json is given, annotates each issue with
the task's dependencies. Pure standard library, no network.

Exit codes: 0 on success, 2 when tasks.md is missing, 1 when the file has no
recognizable task lines.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

# - [ ] T001 [P] [US1] description in path/to/file.py
_TASK = re.compile(r"^\s*[-*]\s*\[(?P<mark>[ xX])\]\s*(?P<id>T\d+)\b(?P<rest>.*)$")
# Bracketed labels like [P] or [US1]. Nested brackets are not supported, and the
# canonical mergen and Spec Kit tasks.md line never contains them.
_TAG = re.compile(r"\[[^\]]+\]")


def parse_tasks(md: str) -> list[dict[str, Any]]:
    tasks: list[dict[str, Any]] = []
    for line in md.splitlines():
        m = _TASK.match(line)
        if not m:
            continue
        rest = m.group("rest").strip()
        tags = _TAG.findall(rest)
        description = _TAG.sub("", rest).strip(" -:\t")
        tasks.append(
            {
                "id": m.group("id"),
                "done": m.group("mark").lower() == "x",
                "tags": tags,
                "description": description,
            }
        )
    return tasks


def load_deps(dag_path: str | None) -> dict[str, list[str]]:
    deps: dict[str, list[str]] = {}
    if not dag_path:
        return deps
    try:
        dag = json.loads(Path(dag_path).read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return deps
    if isinstance(dag, list):
        for wave in dag:
            if not isinstance(wave, list):
                continue
            for task in wave:
                if isinstance(task, dict) and task.get("id"):
                    deps[str(task["id"])] = [str(d) for d in (task.get("depends_on") or [])]
    return deps


def render_issue(task: dict[str, Any], deps: dict[str, list[str]]) -> str:
    title = f"{task['id']}: {task['description']}" if task["description"] else str(task["id"])
    lines = [f"### {title}", ""]
    if task["tags"]:
        lines.append(f"Labels from tasks.md: {' '.join(task['tags'])}")
    depends = deps.get(task["id"])
    if depends:
        lines.append(f"Depends on: {', '.join(depends)}")
    lines += [
        "",
        "- [ ] Implemented and verified against the spec",
        "- [ ] Tests pass",
        "",
    ]
    return "\n".join(lines)


def render_all(tasks: list[dict[str, Any]], deps: dict[str, list[str]], include_done: bool) -> str:
    rendered = [t for t in tasks if include_done or not t["done"]]
    out = [
        "<!-- mergen issue stubs, one per task. Create them yourself, for example:",
        "       gh issue create --title '<the ### line>' --body '<the rest>'",
        "     This renderer never creates issues. That side effect is your call. -->",
        f"<!-- {len(rendered)} task(s) rendered out of {len(tasks)} total. -->",
        "",
    ]
    for i, task in enumerate(rendered):
        out.append(render_issue(task, deps))
        if i != len(rendered) - 1:
            out.append("---")  # separator between issues only, never a trailing one
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Render GitHub issue stubs from a tasks.md")
    ap.add_argument("tasks_md", help="path to tasks.md")
    ap.add_argument("--dag", help="optional tasks-dag.json to annotate dependencies")
    ap.add_argument("--include-done", action="store_true", help="also render completed tasks")
    args = ap.parse_args(argv)

    path = Path(args.tasks_md)
    if not path.is_file():
        print(f"error: tasks.md not found: {path}", file=sys.stderr)
        return 2
    tasks = parse_tasks(path.read_text(encoding="utf-8-sig"))
    if not tasks:
        print("no tasks found (expected lines like '- [ ] T001 ...')", file=sys.stderr)
        return 1
    deps = load_deps(args.dag)
    print(render_all(tasks, deps, args.include_done))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
