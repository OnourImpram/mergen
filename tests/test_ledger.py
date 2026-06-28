"""Tests for scripts/ledger.py.

All tests inject explicit timestamps so the suite is fully deterministic.
No wall-clock calls are made from test code or from the library functions
under test.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
import pytest
from pathlib import Path

# Allow importing from scripts/ without installing the package.
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import ledger  # noqa: E402
from ledger import append_event, main, read_events, summarize  # noqa: E402


TS1 = "2026-01-01T00:00:00+00:00"
TS2 = "2026-01-02T00:00:00+00:00"
TS3 = "2026-01-03T00:00:00+00:00"


# ---------------------------------------------------------------------------
# Round-trip: append then read.
# ---------------------------------------------------------------------------


def test_append_then_read_single_event(tmp_path: Path) -> None:
    ledger = tmp_path / "events.jsonl"
    payload = {"decision": "approve", "score": 0.95}
    append_event(payload, path=ledger, kind="governor-decision", timestamp=TS1)

    events = read_events(ledger)
    assert len(events) == 1
    ev = events[0]
    assert ev["schema_version"] == "1.0"
    assert ev["kind"] == "governor-decision"
    assert ev["ts"] == TS1
    assert ev["payload"] == payload


def test_append_then_read_multiple_events(tmp_path: Path) -> None:
    ledger = tmp_path / "events.jsonl"
    payloads = [
        {"decision": "approve", "status": "done"},
        {"report": "pass", "status": "pending"},
        {"note": "no status field here"},
    ]
    kinds = ["governor-decision", "verification-report", "audit-note"]
    timestamps = [TS1, TS2, TS3]

    for payload, kind, ts in zip(payloads, kinds, timestamps):
        append_event(payload, path=ledger, kind=kind, timestamp=ts)

    events = read_events(ledger)
    assert len(events) == 3
    for i, ev in enumerate(events):
        assert ev["schema_version"] == "1.0"
        assert ev["kind"] == kinds[i]
        assert ev["ts"] == timestamps[i]
        assert ev["payload"] == payloads[i]


# ---------------------------------------------------------------------------
# Multiple kinds in a single ledger.
# ---------------------------------------------------------------------------


def test_multiple_kinds_are_preserved(tmp_path: Path) -> None:
    ledger = tmp_path / "multi.jsonl"
    append_event({"x": 1}, path=ledger, kind="alpha", timestamp=TS1)
    append_event({"x": 2}, path=ledger, kind="beta", timestamp=TS2)
    append_event({"x": 3}, path=ledger, kind="alpha", timestamp=TS3)

    events = read_events(ledger)
    kinds = [e["kind"] for e in events]
    assert kinds == ["alpha", "beta", "alpha"]


# ---------------------------------------------------------------------------
# Tolerates trailing newline.
# ---------------------------------------------------------------------------


def test_read_tolerates_trailing_newline(tmp_path: Path) -> None:
    ledger = tmp_path / "trail.jsonl"
    append_event({"v": 7}, path=ledger, kind="test-kind", timestamp=TS1)
    # Force an extra trailing newline.
    with ledger.open("ab") as fh:
        fh.write(b"\n")
    events = read_events(ledger)
    assert len(events) == 1


# ---------------------------------------------------------------------------
# Corrupt line raises ValueError with the line number.
# ---------------------------------------------------------------------------


def test_corrupt_line_raises_value_error(tmp_path: Path) -> None:
    ledger = tmp_path / "corrupt.jsonl"
    good_line = json.dumps({"schema_version": "1.0", "kind": "ok", "ts": TS1, "payload": {}})
    with ledger.open("wb") as fh:
        fh.write((good_line + "\n").encode("utf-8"))
        fh.write(b"NOT VALID JSON\n")

    with pytest.raises(ValueError, match=r"line 2"):
        read_events(ledger)


# ---------------------------------------------------------------------------
# summarize: event counts.
# ---------------------------------------------------------------------------


def test_summarize_counts_events_by_kind(tmp_path: Path) -> None:
    ledger = tmp_path / "sum.jsonl"
    append_event({"status": "done"}, path=ledger, kind="governor-decision", timestamp=TS1)
    append_event({"status": "done"}, path=ledger, kind="governor-decision", timestamp=TS2)
    append_event({"status": "pending"}, path=ledger, kind="verification-report", timestamp=TS3)

    events = read_events(ledger)
    result = summarize(events)

    assert result["total_events"] == 3
    assert result["events_by_kind"]["governor-decision"] == 2
    assert result["events_by_kind"]["verification-report"] == 1
    assert result["status_counts"]["done"] == 2
    assert result["status_counts"]["pending"] == 1


def test_summarize_empty_list() -> None:
    result = summarize([])
    assert result["total_events"] == 0
    assert result["events_by_kind"] == {}
    assert result["status_counts"] == {"done": 0, "pending": 0}


def test_summarize_ignores_events_without_status(tmp_path: Path) -> None:
    ledger = tmp_path / "nostatus.jsonl"
    append_event({"note": "no status"}, path=ledger, kind="audit-note", timestamp=TS1)

    events = read_events(ledger)
    result = summarize(events)
    assert result["status_counts"]["done"] == 0
    assert result["status_counts"]["pending"] == 0


# ---------------------------------------------------------------------------
# append_event raises when timestamp is None.
# ---------------------------------------------------------------------------


def test_append_event_requires_timestamp(tmp_path: Path) -> None:
    ledger = tmp_path / "ts.jsonl"
    with pytest.raises(ValueError, match="timestamp must be provided"):
        append_event({"x": 1}, path=ledger, kind="k", timestamp=None)


# ---------------------------------------------------------------------------
# Parent directories are created automatically.
# ---------------------------------------------------------------------------


def test_parent_dirs_created(tmp_path: Path) -> None:
    ledger = tmp_path / "deep" / "nested" / "events.jsonl"
    append_event({"a": 1}, path=ledger, kind="k", timestamp=TS1)
    assert ledger.exists()
    events = read_events(ledger)
    assert len(events) == 1


# ---------------------------------------------------------------------------
# read_events on a missing file returns an empty list.
# ---------------------------------------------------------------------------


def test_read_events_missing_file_returns_empty(tmp_path: Path) -> None:
    led = tmp_path / "nonexistent.jsonl"
    assert read_events(led) == []


# ---------------------------------------------------------------------------
# CLI layer: append, summary, error paths, and subcommand dispatch. These drive
# main() so the entry-point surface is covered, not just the library functions.
# A fixed clock keeps the append path deterministic, honouring the no-wall-clock
# discipline even though the CLI is the layer that injects the default timestamp.
# ---------------------------------------------------------------------------


class _FixedClock:
    @staticmethod
    def now(tz: object = None) -> datetime:
        return datetime(2026, 1, 1, tzinfo=timezone.utc)


def test_cli_append_writes_event(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(ledger, "datetime", _FixedClock)
    led = tmp_path / "cli.jsonl"
    main(["append", "--path", str(led), "--kind", "governor-decision",
          "--json", '{"decision": "approve"}'])
    assert "Appended event" in capsys.readouterr().out
    events = read_events(led)
    assert len(events) == 1
    assert events[0]["kind"] == "governor-decision"
    assert events[0]["ts"] == TS1
    assert events[0]["payload"] == {"decision": "approve"}


def test_cli_append_invalid_json_exits(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    led = tmp_path / "bad.jsonl"
    with pytest.raises(SystemExit) as exc:
        main(["append", "--path", str(led), "--kind", "k", "--json", "not-json"])
    assert exc.value.code == 1
    assert "not valid JSON" in capsys.readouterr().err
    assert not led.exists()


def test_cli_summary_prints_json(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    led = tmp_path / "sum.jsonl"
    append_event({"status": "done"}, path=led, kind="governor-decision", timestamp=TS1)
    append_event({"status": "pending"}, path=led, kind="verification-report", timestamp=TS2)
    main(["summary", "--path", str(led)])
    result = json.loads(capsys.readouterr().out)
    assert result["total_events"] == 2
    assert result["status_counts"] == {"done": 1, "pending": 1}


def test_cli_requires_a_subcommand(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        main([])
