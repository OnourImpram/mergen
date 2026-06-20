#!/usr/bin/env python3
"""Deterministic validator for a tasks-dag.json (roadmap 1.3).

/mergen.tasks emits a wave-ordered dependency DAG and describes an adversarial
verifier lane that checks it. This module is the code form of that lane, so the
check is a tool that proves rather than a prompt that asks. It enforces the
invariants the schema cannot express:

  - every task id is unique across the whole DAG
  - every depends_on reference points to a real task id
  - the dependency graph has no cycle
  - every dependency appears in an earlier wave than the task that needs it

Returns {"pass": bool, "errors": [...]} and, under --gate, exits non-zero when
the DAG is invalid. Stdlib only, deterministic, no side effects.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def _find_cycle(deps: dict[str, list[str]]) -> list[str] | None:
    """Return one cycle as a list of ids (closed loop), or None when acyclic."""
    white, gray, black = 0, 1, 2
    color: dict[str, int] = {node: white for node in deps}
    stack: list[str] = []

    def visit(node: str) -> list[str] | None:
        color[node] = gray
        stack.append(node)
        for nxt in deps.get(node, []):
            if nxt not in color:
                continue  # unknown reference; reported separately
            if color[nxt] == gray:
                return stack[stack.index(nxt):] + [nxt]
            if color[nxt] == white:
                found = visit(nxt)
                if found is not None:
                    return found
        stack.pop()
        color[node] = black
        return None

    for node in deps:
        if color[node] == white:
            found = visit(node)
            if found is not None:
                return found
    return None


def validate(dag: Any) -> dict[str, Any]:
    """Validate a tasks-dag structure. Returns {"pass": bool, "errors": [...]}"""
    errors: list[str] = []

    if not isinstance(dag, list):
        return {"pass": False, "errors": ["top level must be an array of waves"]}

    id_to_wave: dict[str, int] = {}
    duplicates: list[str] = []

    for wave_index, wave in enumerate(dag):
        if not isinstance(wave, list):
            errors.append(f"wave {wave_index} is not an array")
            continue
        for task in wave:
            if not isinstance(task, dict):
                errors.append(f"wave {wave_index} contains a non-object task")
                continue
            task_id = task.get("id")
            if not isinstance(task_id, str) or not task_id:
                errors.append(f"wave {wave_index} has a task with a missing or non-string id")
                continue
            if task_id in id_to_wave:
                duplicates.append(task_id)
            else:
                id_to_wave[task_id] = wave_index

    for dup in sorted(set(duplicates)):
        errors.append(f"duplicate task id: {dup}")

    # Build the dependency map from every well-formed task.
    deps: dict[str, list[str]] = {}
    for wave in dag:
        if not isinstance(wave, list):
            continue
        for task in wave:
            if not isinstance(task, dict):
                continue
            task_id = task.get("id")
            if not isinstance(task_id, str) or not task_id:
                continue
            raw = task.get("depends_on", [])
            deps.setdefault(task_id, [])
            if isinstance(raw, list):
                deps[task_id] = [d for d in raw if isinstance(d, str)]

    known = set(id_to_wave)
    for task_id, dep_list in deps.items():
        for dep in dep_list:
            if dep not in known:
                errors.append(f"task {task_id} depends on unknown task {dep}")
                continue
            if id_to_wave[dep] >= id_to_wave.get(task_id, -1):
                errors.append(
                    f"task {task_id} (wave {id_to_wave.get(task_id)}) depends on {dep} "
                    f"(wave {id_to_wave[dep]}), which is not an earlier wave"
                )

    cycle = _find_cycle(deps)
    if cycle is not None:
        errors.append("dependency cycle: " + " -> ".join(cycle))

    return {"pass": not errors, "errors": errors}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Validate a tasks-dag.json: unique ids, resolvable refs, "
                    "no cycles, dependencies in earlier waves."
    )
    ap.add_argument("--file", metavar="FILE", default=None,
                    help="path to tasks-dag.json (default: read stdin)")
    ap.add_argument("--gate", action="store_true",
                    help="exit non-zero when the DAG is invalid (for CI)")
    args = ap.parse_args(argv)

    text = Path(args.file).read_text(encoding="utf-8") if args.file else sys.stdin.read()
    try:
        dag = json.loads(text)
    except Exception as exc:  # noqa: BLE001
        result: dict[str, Any] = {"pass": False, "errors": [f"invalid JSON: {exc}"]}
    else:
        result = validate(dag)

    print(json.dumps(result, indent=2))
    if args.gate:
        return 0 if result["pass"] else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
