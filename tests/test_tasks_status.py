"""Tests for the tasks-state summarizer (scripts/tasks_status.py).

Loaded by file path because scripts/ is not an importable package.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def _load():
    spec = importlib.util.spec_from_file_location("tasks_status", REPO / "scripts" / "tasks_status.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


tasks_status = _load()


def _state(*statuses):
    return {
        "schema_version": "1.0",
        "feature_id": "feat-x",
        "tasks": [
            {"id": f"T{i:03d}", "status": s, "files": [f"src/{i}.py"],
             "last_verified_at": "2026-06-20T00:00:00Z" if s == "done" else None}
            for i, s in enumerate(statuses, start=1)
        ],
    }


def test_summarize_counts_done_and_pending():
    s = tasks_status.summarize(_state("done", "pending", "done"))
    assert s["total"] == 3
    assert s["done"] == 2
    assert s["pending"] == 1
    assert s["other"] == 0
    assert s["feature_id"] == "feat-x"


def test_summarize_names_blocked_and_conditional():
    s = tasks_status.summarize(_state("done", "blocked", "conditional", "pending"))
    assert s["done"] == 1
    assert s["pending"] == 1
    assert s["blocked"] == 1
    assert s["conditional"] == 1
    assert s["other"] == 0


def test_summarize_handles_unknown_status_as_other():
    # A status outside the named set still degrades to "other" rather than vanishing.
    s = tasks_status.summarize(_state("done", "frozen"))
    assert s["done"] == 1
    assert s["pending"] == 0
    assert s["blocked"] == 0
    assert s["conditional"] == 0
    assert s["other"] == 1


def test_render_text_shows_marks_and_files():
    out = tasks_status.render_text(tasks_status.summarize(_state("done", "pending")))
    assert "[X] T001" in out
    assert "[ ] T002" in out
    assert "1/2 done, 1 pending" in out


def test_render_text_appends_other_suffix_when_present():
    # An unrecognized status counts as "other" and the header must say so. Pins the
    # render_text branch that the done/pending-only states never exercise.
    out = tasks_status.render_text(tasks_status.summarize(_state("done", "frozen")))
    assert "1 other" in out


def test_render_text_shows_blocked_and_conditional_in_header_and_marks():
    out = tasks_status.render_text(tasks_status.summarize(_state("done", "blocked", "conditional")))
    assert "1 blocked" in out
    assert "1 conditional" in out
    assert "[!] T002" in out  # blocked mark
    assert "[~] T003" in out  # conditional mark


def test_main_text_on_demo_state(tmp_path, capsys):
    p = tmp_path / "tasks-state.json"
    p.write_text(json.dumps(_state("done", "pending")), encoding="utf-8")
    rc = tasks_status.main([str(p)])
    assert rc == 0
    assert "feature: feat-x" in capsys.readouterr().out


def test_main_json_flag_emits_counts(tmp_path, capsys):
    p = tmp_path / "tasks-state.json"
    p.write_text(json.dumps(_state("done", "done", "pending")), encoding="utf-8")
    rc = tasks_status.main([str(p), "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload == {"feature_id": "feat-x", "total": 3, "done": 2, "pending": 1,
                       "blocked": 0, "conditional": 0, "other": 0}


def test_main_tolerates_bom(tmp_path, capsys):
    p = tmp_path / "tasks-state.json"
    p.write_bytes(b"\xef\xbb\xbf" + json.dumps(_state("done")).encode("utf-8"))
    assert tasks_status.main([str(p)]) == 0


def test_main_missing_file_returns_2(tmp_path, capsys):
    assert tasks_status.main([str(tmp_path / "nope.json")]) == 2


def test_main_unparseable_returns_2(tmp_path, capsys):
    p = tmp_path / "tasks-state.json"
    p.write_text("{ not json", encoding="utf-8")
    assert tasks_status.main([str(p)]) == 2
