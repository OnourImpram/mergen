"""Append-only event ledger for the mergen governor pipeline.

Every event is stored as one JSON object per line (JSONL). Each line
carries a standard envelope plus an arbitrary payload dict.

CLI usage:
    python scripts/ledger.py append --path p --kind k --json '{"a":1}'
    python scripts/ledger.py summary --path p
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "1.0"


# ---------------------------------------------------------------------------
# Core library functions (pure, no wall-clock calls).
# ---------------------------------------------------------------------------


def append_event(
    record: dict,
    path: str | Path,
    kind: str,
    timestamp: str | None = None,
) -> None:
    """Append one event envelope to the JSONL file at path.

    Parameters
    ----------
    record:
        Arbitrary payload dict stored under the "payload" key.
    path:
        Destination file path. Parent directories are created when missing.
    kind:
        Event kind string, e.g. "governor-decision" or "verification-report".
    timestamp:
        ISO-8601 timestamp string. Callers MUST supply this value so the
        function stays deterministic. The CLI layer provides a default from
        datetime.now(tz=timezone.utc) when the user omits the flag.
    """
    if timestamp is None:
        raise ValueError(
            "timestamp must be provided to append_event. "
            "The CLI supplies a default; tests must inject an explicit value."
        )
    envelope: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": kind,
        "ts": timestamp,
        "payload": record,
    }
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(envelope, ensure_ascii=False) + "\n"
    with p.open("ab") as fh:
        fh.write(line.encode("utf-8"))


def read_events(path: str | Path) -> list[dict]:
    """Read all events from a JSONL file and return them as a list of dicts.

    Tolerates a trailing newline. Raises ValueError with the line number on
    any corrupt (non-JSON) line.
    """
    p = Path(path)
    if not p.exists():
        return []
    events: list[dict] = []
    with p.open("r", encoding="utf-8") as fh:
        for lineno, raw in enumerate(fh, start=1):
            stripped = raw.rstrip("\n")
            if stripped == "":
                continue
            try:
                events.append(json.loads(stripped))
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"Corrupt JSON on line {lineno}: {exc}"
                ) from exc
    return events


def summarize(events: list[dict]) -> dict:
    """Return a summary dict useful as a dashboard seed.

    Keys returned:

    total_events
        Total number of events in the list.
    events_by_kind
        Dict mapping each kind string to its count.
    status_counts
        Tallies of "done" vs "pending" across payloads that carry a
        top-level "status" key. Events without a "status" key are ignored.
    """
    by_kind: dict[str, int] = {}
    done = 0
    pending = 0
    for event in events:
        kind = event.get("kind", "unknown")
        by_kind[kind] = by_kind.get(kind, 0) + 1
        payload = event.get("payload", {})
        status = payload.get("status") if isinstance(payload, dict) else None
        if status == "done":
            done += 1
        elif status == "pending":
            pending += 1
    return {
        "total_events": len(events),
        "events_by_kind": by_kind,
        "status_counts": {"done": done, "pending": pending},
    }


# ---------------------------------------------------------------------------
# CLI entry point.
# ---------------------------------------------------------------------------


def _cli_append(args: argparse.Namespace) -> None:
    try:
        payload = json.loads(args.json)
    except json.JSONDecodeError as exc:
        print(f"Error: --json argument is not valid JSON: {exc}", file=sys.stderr)
        sys.exit(1)
    ts = datetime.now(tz=timezone.utc).isoformat()
    append_event(payload, path=args.path, kind=args.kind, timestamp=ts)
    print(f"Appended event kind={args.kind!r} to {args.path}")


def _cli_summary(args: argparse.Namespace) -> None:
    events = read_events(args.path)
    result = summarize(events)
    print(json.dumps(result, indent=2))


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Append-only event ledger for the mergen governor pipeline."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    ap = sub.add_parser("append", help="Append a new event to the ledger.")
    ap.add_argument("--path", required=True, help="Path to the JSONL ledger file.")
    ap.add_argument("--kind", required=True, help="Event kind string.")
    ap.add_argument("--json", required=True, help="JSON payload object as a string.")

    sp = sub.add_parser("summary", help="Print a summary of ledger events.")
    sp.add_argument("--path", required=True, help="Path to the JSONL ledger file.")

    parsed = parser.parse_args(argv)
    if parsed.command == "append":
        _cli_append(parsed)
    elif parsed.command == "summary":
        _cli_summary(parsed)


if __name__ == "__main__":
    main()
