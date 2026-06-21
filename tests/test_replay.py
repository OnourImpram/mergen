"""Tests for scripts/replay.py, the replayable execution ledger.

The pure comparison logic is tested directly. The end-to-end record-then-replay
path runs the real verify_core harness against a throwaway git repo, so a
divergence is produced by a genuine tree change (a deleted file), not a mock.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
_TS = "2026-06-21T00:00:00+00:00"
_DEVNULL = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}


def _load():
    spec = importlib.util.spec_from_file_location("replay", REPO / "scripts" / "replay.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


replay = _load()


# --------------------------------------------------------------------------- #
# git helpers for the integration path
# --------------------------------------------------------------------------- #

def _init_repo(path: Path) -> None:
    subprocess.run(["git", "init", str(path)], check=True, **_DEVNULL)  # type: ignore[call-overload]
    subprocess.run(["git", "-C", str(path), "config", "user.email", "t@m.test"], check=True, **_DEVNULL)  # type: ignore[call-overload]
    subprocess.run(["git", "-C", str(path), "config", "user.name", "T"], check=True, **_DEVNULL)  # type: ignore[call-overload]
    subprocess.run(["git", "-C", str(path), "commit", "--allow-empty", "-m", "init"], check=True, **_DEVNULL)  # type: ignore[call-overload]


def _stage(repo: Path, rel: str, content: str) -> None:
    target = repo / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", rel], check=True, **_DEVNULL)  # type: ignore[call-overload]


def _commit(repo: Path) -> None:
    subprocess.run(["git", "-C", str(repo), "commit", "-m", "c"], check=True, **_DEVNULL)  # type: ignore[call-overload]


# --------------------------------------------------------------------------- #
# pure comparison logic
# --------------------------------------------------------------------------- #

def test_replay_matches_when_verdicts_unchanged():
    record = {"run_id": "r", "verdict": "pass",
              "task_verdicts": {"T1": "pass", "T2": "pass"}}
    new = {"summary": {"verdict": "pass"},
           "tasks": [{"task_id": "T1", "verified_status": "pass"},
                     {"task_id": "T2", "verified_status": "pass"}]}
    res = replay.replay(record, new)
    assert res["match"] is True
    assert res["diverged"] == []


def test_replay_diverges_when_a_task_flips():
    record = {"run_id": "r", "verdict": "pass", "task_verdicts": {"T1": "pass"}}
    new = {"summary": {"verdict": "fail"},
           "tasks": [{"task_id": "T1", "verified_status": "fail"}]}
    res = replay.replay(record, new)
    assert res["match"] is False
    assert res["diverged"] == [{"task_id": "T1", "old": "pass", "new": "fail"}]
    assert res["verdict_old"] == "pass" and res["verdict_new"] == "fail"


def test_replay_flags_appeared_and_vanished_tasks():
    record = {"run_id": "r", "verdict": "pass",
              "task_verdicts": {"T1": "pass", "T2": "pass"}}
    new = {"summary": {"verdict": "pass"},
           "tasks": [{"task_id": "T1", "verified_status": "pass"},
                     {"task_id": "T3", "verified_status": "pass"}]}
    diverged = {d["task_id"]: (d["old"], d["new"]) for d in replay.replay(record, new)["diverged"]}
    assert diverged["T2"] == ("pass", "absent")
    assert diverged["T3"] == ("absent", "pass")


def test_run_id_is_stable_and_commit_scoped():
    assert replay.run_id_for("abc", "c1") == replay.run_id_for("abc", "c1")
    assert replay.run_id_for("abc", "c1") != replay.run_id_for("abc", "c2")
    assert replay.run_id_for("abc", None) != replay.run_id_for("abc", "c1")


def test_make_run_record_reads_provenance():
    report = {"feature_id": "f", "summary": {"verdict": "pass"},
              "tasks": [{"task_id": "T1", "verified_status": "pass"}],
              "provenance": {"tasks_state_sha256": "abc", "source_commit": "c1"}}
    state = {"feature_id": "f", "tasks": [{"id": "T1", "status": "done"}]}
    rec = replay.make_run_record(report, state)
    assert rec["tasks_state_sha256"] == "abc"
    assert rec["source_commit"] == "c1"
    assert rec["verdict"] == "pass"
    assert rec["task_verdicts"] == {"T1": "pass"}
    assert rec["tasks_state"] == state
    assert rec["run_id"] == replay.run_id_for("abc", "c1")


def test_make_run_record_falls_back_without_provenance_hash():
    rec = replay.make_run_record(
        {"feature_id": "f", "summary": {"verdict": "pass"}, "tasks": []}, {"tasks": []})
    assert rec["tasks_state_sha256"]  # derived from content, non-empty
    assert rec["source_commit"] is None


def test_load_runs_idempotent(tmp_path):
    runs = tmp_path / "runs.jsonl"
    rec = {"run_id": "r1", "verdict": "pass", "task_verdicts": {}}
    replay.write_run(runs, rec, _TS)
    replay.write_run(runs, rec, _TS)
    assert list(replay.load_runs(runs)) == ["r1"]


# --------------------------------------------------------------------------- #
# end-to-end: record a real run, replay it, then make the tree diverge
# --------------------------------------------------------------------------- #

def test_record_then_replay_match_then_divergence(tmp_path, capsys):
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    _stage(repo, "src/m.py", "x = 1\n")
    _commit(repo)

    verify_core = replay._load("verify_core")
    state = {"schema_version": "1.0", "feature_id": "f",
             "tasks": [{"id": "T1", "status": "done", "files": ["src/m.py"]}]}
    report, _ = verify_core.build_report(state, repo)
    assert report["summary"]["verdict"] == "pass"

    rec = replay.make_run_record(report, state)
    runs = tmp_path / "runs.jsonl"
    replay.write_run(runs, rec, _TS)

    # Same tree: a clean match, exit 0.
    assert replay.main(["run", rec["run_id"], "--runs", str(runs), "--root", str(repo)]) == 0
    capsys.readouterr()  # clear the match output before the divergence run

    # Delete the verified file so the file-exists lens now fails: divergence, exit 1.
    (repo / "src" / "m.py").unlink()
    assert replay.main(["run", rec["run_id"], "--runs", str(runs), "--root", str(repo)]) == 1
    out = json.loads(capsys.readouterr().out)
    assert any(d["task_id"] == "T1" and d["new"] == "fail" for d in out["diverged"])


def test_cli_record_and_list(tmp_path):
    report = {"feature_id": "f", "summary": {"verdict": "pass"},
              "tasks": [{"task_id": "T1", "verified_status": "pass"}],
              "provenance": {"tasks_state_sha256": "abc", "source_commit": "c1"}}
    state = {"feature_id": "f", "tasks": [{"id": "T1", "status": "done"}]}
    rp = tmp_path / "report.json"
    rp.write_text(json.dumps(report), encoding="utf-8")
    sp = tmp_path / "tasks-state.json"
    sp.write_text(json.dumps(state), encoding="utf-8")
    runs = tmp_path / "runs.jsonl"
    assert replay.main(["record", "--report", str(rp), "--tasks-state", str(sp),
                        "--runs", str(runs)]) == 0
    assert replay.main(["list", "--runs", str(runs)]) == 0


def test_cli_run_unknown_returns_2(tmp_path):
    runs = tmp_path / "runs.jsonl"
    runs.write_text("", encoding="utf-8")
    assert replay.main(["run", "nope", "--runs", str(runs)]) == 2


def test_cli_record_missing_file_returns_2(tmp_path):
    runs = tmp_path / "runs.jsonl"
    assert replay.main(["record", "--report", str(tmp_path / "no.json"),
                        "--tasks-state", str(tmp_path / "no2.json"), "--runs", str(runs)]) == 2


# --------------------------------------------------------------------------- #
# review follow-ups: verdict-only divergence, missing state, build crash, BOM
# --------------------------------------------------------------------------- #

def test_replay_flags_verdict_only_change():
    # A verdict can move with no individual task flipping. match is False, the
    # diverged list is empty, and verdict_changed carries the signal.
    rec = {"run_id": "r", "verdict": "conditional_pass", "task_verdicts": {"T1": "pass"}}
    new = {"summary": {"verdict": "pass"},
           "tasks": [{"task_id": "T1", "verified_status": "pass"}]}
    res = replay.replay(rec, new)
    assert res["match"] is False
    assert res["diverged"] == []
    assert res["verdict_changed"] is True


def test_cli_run_missing_tasks_state_returns_2(tmp_path):
    runs = tmp_path / "runs.jsonl"
    rec = {"run_id": "r1", "verdict": "pass", "task_verdicts": {"T1": "pass"},
           "tasks_state": None}  # no usable stored input
    replay.write_run(runs, rec, _TS)
    assert replay.main(["run", "r1", "--runs", str(runs), "--root", str(tmp_path)]) == 2


def test_cli_run_build_crash_returns_2(tmp_path, monkeypatch):
    runs = tmp_path / "runs.jsonl"
    rec = {"run_id": "r1", "verdict": "pass", "task_verdicts": {"T1": "pass"},
           "tasks_state": {"tasks": []}}
    replay.write_run(runs, rec, _TS)

    class _Boom:
        @staticmethod
        def build_report(state, root):
            raise RuntimeError("boom")

    # setitem is reverted by monkeypatch after the test, so the cache stays clean.
    monkeypatch.setitem(replay._MODS, "verify_core", _Boom)
    assert replay.main(["run", "r1", "--runs", str(runs), "--root", str(tmp_path)]) == 2


def test_cli_record_tolerates_bom(tmp_path):
    report = {"feature_id": "f", "summary": {"verdict": "pass"}, "tasks": [],
              "provenance": {"tasks_state_sha256": "abc", "source_commit": "c1"}}
    state = {"tasks": []}
    rp = tmp_path / "report.json"
    rp.write_bytes(b"\xef\xbb\xbf" + json.dumps(report).encode("utf-8"))
    sp = tmp_path / "state.json"
    sp.write_bytes(b"\xef\xbb\xbf" + json.dumps(state).encode("utf-8"))
    runs = tmp_path / "runs.jsonl"
    assert replay.main(["record", "--report", str(rp), "--tasks-state", str(sp),
                        "--runs", str(runs)]) == 0
