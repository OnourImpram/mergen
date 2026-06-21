#!/usr/bin/env python3
"""mergen impacted: continuous verification over the impacted slice of the DAG.

Verification is usually a gate you run over every task. Continuous Verification
re-runs only the slice a change actually touches, so a regression in a
previously-verified task is caught when it is introduced rather than at the next
full gate. The impacted set is computed from the changed paths and the dependency
DAG: a task whose files changed is directly impacted, and a task that depends on
an impacted task is transitively impacted, because its dependency's behaviour may
have moved.

Two inputs name the two relations. The tasks-state (the same file verify_core
reads) maps a task to its files, so a changed path resolves to the directly
impacted tasks. The tasks-dag carries depends_on, so the reverse closure adds the
dependents. Without a DAG the tool runs in direct-impact-only mode and says so.

With a prior report to compare against, mergen impacted verify re-verifies the
impacted slice and flags any task that flips from pass to fail, the regression a
change just introduced. Deterministic and offline. It runs where a change is
observed: a pre-commit hook, a CI step, or an explicit invocation. It does not
watch the filesystem.

Tier 0: pure standard library. Exit codes: 0 no regression, 1 a pass-to-fail
flip, 2 an error (unreadable input, no report producible).
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

_MODS: dict[str, Any] = {}


def _load(name: str) -> Any:
    """Load a sibling scripts/<name>.py by path and cache it (scripts/ not a package)."""
    if name in _MODS:
        return _MODS[name]
    repo = Path(__file__).resolve().parent
    spec = importlib.util.spec_from_file_location(name, repo / f"{name}.py")
    if spec is None or spec.loader is None:  # pragma: no cover - import wiring
        raise ImportError(f"cannot load {name}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    _MODS[name] = mod
    return mod


def _norm(path: str) -> str:
    """Normalize a path for comparison: forward slashes, no surrounding space, no
    leading ./ so a task file declared as ./src/a.py matches the bare src/a.py that
    git diff --name-only emits. Comparison stays case-sensitive, matching POSIX
    filesystems, so a task that names a file in a different case than the changed
    path will not match.
    """
    p = path.replace("\\", "/").strip()
    if p.startswith("./"):
        p = p[2:]
    return p


def direct_impacted(tasks_state: dict[str, Any], changed_paths: list[str]) -> set[str]:
    """Tasks whose declared files intersect the changed paths."""
    changed = {_norm(c) for c in changed_paths if _norm(c)}
    hit: set[str] = set()
    for task in tasks_state.get("tasks", []):
        if not isinstance(task, dict):
            continue
        tid = task.get("id")
        files = task.get("files") or []
        if isinstance(tid, str) and isinstance(files, list):
            if any(isinstance(f, str) and _norm(f) in changed for f in files):
                hit.add(tid)
    return hit


def reverse_deps(dag: Any) -> dict[str, set[str]]:
    """Invert the DAG depends_on edges: a task id to the set that depends on it."""
    rev: dict[str, set[str]] = {}
    if not isinstance(dag, list):
        return rev
    for wave in dag:
        if not isinstance(wave, list):
            continue
        for task in wave:
            if not isinstance(task, dict):
                continue
            tid = task.get("id")
            if not isinstance(tid, str):
                continue
            for dep in task.get("depends_on") or []:
                if isinstance(dep, str):
                    rev.setdefault(dep, set()).add(tid)
    return rev


def impacted_set(tasks_state: dict[str, Any], changed_paths: list[str],
                 dag: Any = None) -> set[str]:
    """The directly impacted tasks plus, when a DAG is given, their dependents.

    The transitive closure follows depends_on in reverse: if A depends on B and B
    is impacted, A is impacted. Cycle-safe via the visited set. Without a DAG the
    result is the direct set only, an honest degraded mode.
    """
    impacted = direct_impacted(tasks_state, changed_paths)
    if dag is None:
        return impacted
    rev = reverse_deps(dag)
    frontier = list(impacted)
    while frontier:
        node = frontier.pop()
        for dependent in rev.get(node, set()):
            if dependent not in impacted:
                impacted.add(dependent)
                frontier.append(dependent)
    return impacted


def scoped_state(tasks_state: dict[str, Any], impacted: set[str]) -> dict[str, Any]:
    """The tasks-state narrowed to the impacted tasks, for a scoped re-verify."""
    tasks = [t for t in tasks_state.get("tasks", [])
             if isinstance(t, dict) and t.get("id") in impacted]
    return {**tasks_state, "tasks": tasks}


def _verdicts(report: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for item in report.get("tasks", []):
        if isinstance(item, dict):
            tid, status = item.get("task_id"), item.get("verified_status")
            if isinstance(tid, str) and isinstance(status, str):
                out[tid] = status
    return out


def regressions(prior_report: dict[str, Any], new_report: dict[str, Any]) -> list[dict[str, str]]:
    """Tasks that were pass in the prior report and are fail in the new one.

    A regression is specifically a pass-to-fail flip, the failure a change just
    introduced into a task that was previously verified. A task that was already
    failing, or that newly appears, is not a regression. Deterministically ordered.
    """
    prior = _verdicts(prior_report)
    new = _verdicts(new_report)
    flips: list[dict[str, str]] = []
    for tid in sorted(new):
        if prior.get(tid) == "pass" and new[tid] == "fail":
            flips.append({"task_id": tid, "old": "pass", "new": "fail"})
    return flips


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def _read_json(path: Path) -> Any:
    return json.loads(path.read_bytes().decode("utf-8-sig"))


def _collect_changed(args: argparse.Namespace) -> list[str]:
    changed: list[str] = list(args.changed or [])
    if args.changed_file:
        text = Path(args.changed_file).read_text(encoding="utf-8-sig")
        changed += [line for line in text.splitlines() if line.strip()]
    return changed


def _load_inputs(args: argparse.Namespace) -> tuple[dict[str, Any], Any] | int:
    state_path = Path(args.tasks_state)
    if not state_path.is_file():
        print(f"error: tasks-state not found: {state_path}", file=sys.stderr)
        return 2
    try:
        tasks_state = _read_json(state_path)
        dag = _read_json(Path(args.dag)) if args.dag else None
    except (OSError, json.JSONDecodeError) as exc:
        print(f"error: cannot read input: {exc}", file=sys.stderr)
        return 2
    if not isinstance(tasks_state, dict):
        print("error: tasks-state must be a JSON object", file=sys.stderr)
        return 2
    return tasks_state, dag


def _cmd_impacted(args: argparse.Namespace) -> int:
    loaded = _load_inputs(args)
    if isinstance(loaded, int):
        return loaded
    tasks_state, dag = loaded
    impacted = impacted_set(tasks_state, _collect_changed(args), dag)
    print(json.dumps({
        "impacted": sorted(impacted),
        "dag_used": dag is not None,
    }, indent=2))
    return 0


def _cmd_verify(args: argparse.Namespace) -> int:
    loaded = _load_inputs(args)
    if isinstance(loaded, int):
        return loaded
    tasks_state, dag = loaded
    impacted = impacted_set(tasks_state, _collect_changed(args), dag)
    scoped = scoped_state(tasks_state, impacted)
    root = Path(args.root).resolve()
    try:
        new_report, _ = _load("verify_core").build_report(scoped, root)
    except Exception as exc:  # noqa: BLE001 - a harness crash is a no-report error
        print(f"error: impacted re-verify could not build a report: {exc}", file=sys.stderr)
        return 2

    flips: list[dict[str, str]] = []
    if args.against:
        against_path = Path(args.against)
        if not against_path.is_file():
            print(f"error: prior report not found: {against_path}", file=sys.stderr)
            return 2
        try:
            prior = _read_json(against_path)
        except (OSError, json.JSONDecodeError) as exc:
            print(f"error: cannot read prior report: {exc}", file=sys.stderr)
            return 2
        if not isinstance(prior, dict):
            print("error: prior report is not a JSON object", file=sys.stderr)
            return 2
        flips = regressions(prior, new_report)

    print(json.dumps({
        "impacted": sorted(impacted),
        "tasks_checked": len(impacted),
        "dag_used": dag is not None,
        "verdict": (new_report.get("summary") or {}).get("verdict"),
        "regressions": flips,
    }, indent=2))
    if not impacted:
        # An empty slice re-verifies nothing, so a green exit must not read as a
        # full verification. The impacted list and tasks_checked say so in the JSON,
        # this says so on the console.
        print("impacted verify: no tasks matched the changed paths, nothing re-verified",
              file=sys.stderr)
    if flips:
        print(f"impacted verify: REGRESSION ({len(flips)} task(s) flipped pass to fail)",
              file=sys.stderr)
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Continuous verification over the impacted slice of the tasks DAG.")
    sub = ap.add_subparsers(dest="command", required=True)

    for name, helptext in (
        ("impacted", "list the tasks a set of changed paths impacts"),
        ("verify", "re-verify the impacted slice and flag pass-to-fail regressions"),
    ):
        p = sub.add_parser(name, help=helptext)
        p.add_argument("--tasks-state", required=True, help="path to the tasks-state.json")
        p.add_argument("--dag", help="path to the tasks-dag.json (adds transitive dependents)")
        p.add_argument("--changed", action="append", metavar="PATH",
                       help="a changed path (repeatable)")
        p.add_argument("--changed-file", metavar="FILE",
                       help="a file of changed paths, one per line (e.g. git diff --name-only)")
        if name == "verify":
            p.add_argument("--root", default=".", help="tree to re-verify against (default: cwd)")
            p.add_argument("--against", metavar="REPORT",
                           help="a prior verification-report.json to flag regressions against")
        p.set_defaults(func=_cmd_impacted if name == "impacted" else _cmd_verify)

    args = ap.parse_args(argv)
    result: int = args.func(args)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
