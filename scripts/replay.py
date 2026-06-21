#!/usr/bin/env python3
"""mergen replay: a replayable execution ledger for deterministic re-checking.

A verification run is deterministic on its mechanical surface: given the same
tasks-state and the same tree, verify_core rules the same way. This records each
run so a later replay can re-derive the verdict from the recorded input and the
CURRENT tree, and report whether it still matches. A divergence is a signal: the
tree moved (a file was deleted, a test now fails) or a non-deterministic
dependency leaked into the harness.

The recorded input is the tasks-state. The variable is the tree. A run record
carries the tasks-state content (not only its hash), the source commit it was
verified at, and the per-task verdicts the harness reached, so replay re-runs
verify_core on the recorded tasks-state against the current root and diffs the
result. No tasks-state file is needed at replay time, which is what isolates a
tree change from a tasks-state change.

Honest scope: only the deterministic surface replays. The LLM-driven stages (the
implementer, the judge) are not reproduced. A matching replay proves the harness
saw what it claims and would still rule the same way, not that an agent would make
the same choice twice.

Tier 0: pure standard library, no network, no model. Every run record is one
append-only ledger line. Exit codes: 0 a clean match, 1 a divergence, 2 an error
(no such run, unreadable input, no report producible).
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

#: The ledger event kind a run record carries, so runs can share a file.
RUN_KIND = "replay-run"

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


def _task_verdicts(report: dict[str, Any]) -> dict[str, str]:
    """The per-task verified_status map from a report, the comparison surface."""
    out: dict[str, str] = {}
    for item in report.get("tasks", []):
        if not isinstance(item, dict):
            continue
        tid = item.get("task_id")
        status = item.get("verified_status")
        if isinstance(tid, str) and isinstance(status, str):
            out[tid] = status
    return out


def run_id_for(tasks_state_sha256: str, source_commit: str | None) -> str:
    """A stable run id from the recorded input identity.

    Two runs over the same tasks-state at the same commit share an id, so a
    re-record is idempotent. The commit is folded in so the same tasks-state
    verified at two commits is two runs.
    """
    raw = f"{tasks_state_sha256}\x00{source_commit or ''}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def make_run_record(report: dict[str, Any], tasks_state: dict[str, Any]) -> dict[str, Any]:
    """Build a run record from a verification report and the tasks-state it verified.

    The tasks_state_sha256 and source_commit are read from the report's provenance
    so the record names the same input the report names. The tasks-state content is
    stored verbatim so replay needs no external file.
    """
    provenance = report.get("provenance")
    provenance = provenance if isinstance(provenance, dict) else {}
    summary = report.get("summary")
    summary = summary if isinstance(summary, dict) else {}
    tasks_sha = provenance.get("tasks_state_sha256")
    if not isinstance(tasks_sha, str) or not tasks_sha:
        # Without a recorded input hash there is no stable run identity, so derive
        # one from the tasks-state content directly rather than refuse.
        tasks_sha = hashlib.sha256(
            json.dumps(tasks_state, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest()
    commit = provenance.get("source_commit")
    commit = commit if isinstance(commit, str) and commit else None
    return {
        "run_id": run_id_for(tasks_sha, commit),
        "feature_id": report.get("feature_id"),
        "tasks_state_sha256": tasks_sha,
        "source_commit": commit,
        "verdict": summary.get("verdict"),
        "task_verdicts": _task_verdicts(report),
        "tasks_state": tasks_state,
    }


def write_run(path: str | Path, record: dict[str, Any], timestamp: str) -> None:
    """Append one run record to the ledger at path."""
    _load("ledger").append_event(record, path, kind=RUN_KIND, timestamp=timestamp)


def load_runs(path: str | Path) -> dict[str, dict[str, Any]]:
    """Read run records, keyed by run_id with last write winning (idempotent)."""
    runs: dict[str, dict[str, Any]] = {}
    for event in _load("ledger").read_events(path):
        if event.get("kind") != RUN_KIND:
            continue
        payload = event.get("payload")
        if isinstance(payload, dict) and isinstance(payload.get("run_id"), str):
            runs[payload["run_id"]] = payload
    return runs


def replay(record: dict[str, Any], new_report: dict[str, Any]) -> dict[str, Any]:
    """Compare a recorded run to a freshly produced report over the same input.

    Returns a result dict with match True when every recorded task verdict is
    reproduced and the overall verdict is unchanged. diverged lists each task
    whose verified_status changed, plus any task that appeared or vanished, so a
    reader sees exactly what moved.
    """
    old = record.get("task_verdicts") or {}
    new = _task_verdicts(new_report)
    diverged: list[dict[str, Any]] = []
    for tid in sorted(set(old) | set(new)):
        before = old.get(tid, "absent")
        after = new.get(tid, "absent")
        if before != after:
            diverged.append({"task_id": tid, "old": before, "new": after})
    new_summary = new_report.get("summary")
    new_verdict = new_summary.get("verdict") if isinstance(new_summary, dict) else None
    verdict_changed = record.get("verdict") != new_verdict
    return {
        "run_id": record.get("run_id"),
        "match": not diverged and not verdict_changed,
        "verdict_old": record.get("verdict"),
        "verdict_new": new_verdict,
        # A verdict can move with no individual task flipping (an ambiguous task
        # appearing, say), so this is surfaced separately. A reader must not read an
        # empty diverged list as a clean replay without checking it.
        "verdict_changed": verdict_changed,
        "diverged": diverged,
    }


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def _now() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _read_json(path: Path) -> Any:
    return json.loads(path.read_bytes().decode("utf-8-sig"))


def _cmd_record(args: argparse.Namespace) -> int:
    report_path, state_path = Path(args.report), Path(args.tasks_state)
    for p in (report_path, state_path):
        if not p.is_file():
            print(f"error: not a file: {p}", file=sys.stderr)
            return 2
    try:
        report = _read_json(report_path)
        tasks_state = _read_json(state_path)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"error: cannot read input: {exc}", file=sys.stderr)
        return 2
    if not isinstance(report, dict) or not isinstance(tasks_state, dict):
        print("error: report and tasks-state must be JSON objects", file=sys.stderr)
        return 2
    record = make_run_record(report, tasks_state)
    write_run(args.runs, record, _now())
    print(f"recorded run {record['run_id']} ({record.get('verdict')}) to {args.runs}")
    return 0


def _cmd_run(args: argparse.Namespace) -> int:
    try:
        runs = load_runs(args.runs)
    except ValueError as exc:
        print(f"error: corrupt runs ledger: {exc}", file=sys.stderr)
        return 2
    record = runs.get(args.run_id)
    if record is None:
        print(f"error: no such run: {args.run_id}", file=sys.stderr)
        return 2
    tasks_state = record.get("tasks_state")
    if not isinstance(tasks_state, dict):
        print(f"error: run {args.run_id} has no stored tasks_state, so it cannot be "
              "replayed (the record may be corrupt or from an older version)",
              file=sys.stderr)
        return 2
    root = Path(args.root).resolve()
    verify_core = _load("verify_core")
    try:
        new_report, _ = verify_core.build_report(tasks_state, root)
    except Exception as exc:  # noqa: BLE001 - a harness crash is a no-report error
        print(f"error: replay could not build a report: {exc}", file=sys.stderr)
        return 2
    result = replay(record, new_report)
    print(json.dumps(result, indent=2))
    if result["match"]:
        print(f"replay {args.run_id}: MATCH", file=sys.stderr)
        return 0
    print(f"replay {args.run_id}: DIVERGENCE ({len(result['diverged'])} task(s), "
          f"verdict {result['verdict_old']} -> {result['verdict_new']})", file=sys.stderr)
    return 1


def _cmd_list(args: argparse.Namespace) -> int:
    try:
        runs = load_runs(args.runs)
    except ValueError as exc:
        print(f"error: corrupt runs ledger: {exc}", file=sys.stderr)
        return 2
    # Insertion order is the append-only chronology of the ledger, which reads
    # more usefully than a hash sort. load_runs keeps the last record per id.
    listing = [
        {"run_id": r["run_id"], "feature_id": r.get("feature_id"),
         "verdict": r.get("verdict"), "source_commit": r.get("source_commit")}
        for r in runs.values()
    ]
    print(json.dumps(listing, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Record and replay deterministic verification runs.")
    sub = ap.add_subparsers(dest="command", required=True)

    p_rec = sub.add_parser("record", help="record a run from a report and its tasks-state")
    p_rec.add_argument("--report", required=True, help="path to a verification-report.json")
    p_rec.add_argument("--tasks-state", required=True, help="path to the tasks-state.json it verified")
    p_rec.add_argument("--runs", required=True, help="path to the runs JSONL ledger")
    p_rec.set_defaults(func=_cmd_record)

    p_run = sub.add_parser("run", help="replay a recorded run against the current tree")
    p_run.add_argument("run_id", help="the run id to replay (see replay list)")
    p_run.add_argument("--runs", required=True, help="path to the runs JSONL ledger")
    p_run.add_argument("--root", default=".",
                       help="tree to re-verify against (default: cwd, set this to the "
                            "project root for a meaningful replay)")
    p_run.set_defaults(func=_cmd_run)

    p_ls = sub.add_parser("list", help="list recorded runs")
    p_ls.add_argument("--runs", required=True, help="path to the runs JSONL ledger")
    p_ls.set_defaults(func=_cmd_list)

    args = ap.parse_args(argv)
    result: int = args.func(args)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
