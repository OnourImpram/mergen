"""Tests for scripts/impacted.py, continuous verification over the impacted slice.

The set computation is tested directly. The end-to-end re-verify runs the real
verify_core against a throwaway git repo, so a regression is produced by a genuine
tree change (a deleted file flipping a task from pass to fail), not a mock.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
_DEVNULL = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}


def _load():
    spec = importlib.util.spec_from_file_location("impacted", REPO / "scripts" / "impacted.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


impacted = _load()


def _state(tasks):
    return {"schema_version": "1.0", "feature_id": "f", "tasks": tasks}


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
# set computation
# --------------------------------------------------------------------------- #

def test_direct_impacted_matches_files_and_normalizes_separators():
    state = _state([{"id": "T1", "status": "done", "files": ["src/a.py"]},
                    {"id": "T2", "status": "done", "files": ["src/b.py"]}])
    assert impacted.direct_impacted(state, ["src/a.py"]) == {"T1"}
    assert impacted.direct_impacted(state, ["src\\a.py"]) == {"T1"}  # backslash normalized
    assert impacted.direct_impacted(state, ["src/c.py"]) == set()


def test_reverse_deps_inverts_depends_on():
    dag = [[{"id": "T1"}], [{"id": "T2", "depends_on": ["T1"]}]]
    assert impacted.reverse_deps(dag) == {"T1": {"T2"}}


def test_impacted_set_adds_transitive_dependents_with_dag():
    state = _state([{"id": "T1", "status": "done", "files": ["src/a.py"]},
                    {"id": "T2", "status": "done", "files": ["src/b.py"]}])
    dag = [[{"id": "T1"}], [{"id": "T2", "depends_on": ["T1"]}]]
    # T2 depends on the directly-impacted T1, so it is transitively impacted.
    assert impacted.impacted_set(state, ["src/a.py"], dag) == {"T1", "T2"}
    # Without a DAG, only the direct set.
    assert impacted.impacted_set(state, ["src/a.py"], None) == {"T1"}


def test_impacted_set_is_cycle_safe():
    state = _state([{"id": "T1", "status": "done", "files": ["src/a.py"]},
                    {"id": "T2", "status": "done", "files": ["x"]}])
    dag = [[{"id": "T1", "depends_on": ["T2"]}], [{"id": "T2", "depends_on": ["T1"]}]]
    res = impacted.impacted_set(state, ["src/a.py"], dag)  # must terminate
    assert {"T1", "T2"} <= res


def test_scoped_state_filters_to_impacted():
    state = _state([{"id": "T1", "status": "done"}, {"id": "T2", "status": "done"}])
    scoped = impacted.scoped_state(state, {"T1"})
    assert [t["id"] for t in scoped["tasks"]] == ["T1"]
    assert scoped["feature_id"] == "f"  # the rest of the state is preserved


def test_regressions_flags_only_pass_to_fail():
    prior = {"tasks": [{"task_id": "T1", "verified_status": "pass"},
                       {"task_id": "T2", "verified_status": "fail"}]}
    new = {"tasks": [{"task_id": "T1", "verified_status": "fail"},   # regressed
                     {"task_id": "T2", "verified_status": "fail"},   # already failing
                     {"task_id": "T3", "verified_status": "fail"}]}  # newly appeared
    assert impacted.regressions(prior, new) == [{"task_id": "T1", "old": "pass", "new": "fail"}]


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def test_cli_impacted_lists_with_dag_flag(tmp_path, capsys):
    state = _state([{"id": "T1", "status": "done", "files": ["src/a.py"]}])
    sp = tmp_path / "state.json"
    sp.write_text(json.dumps(state), encoding="utf-8")
    assert impacted.main(["impacted", "--tasks-state", str(sp), "--changed", "src/a.py"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["impacted"] == ["T1"]
    assert out["dag_used"] is False


def test_cli_changed_file_input(tmp_path, capsys):
    state = _state([{"id": "T1", "status": "done", "files": ["src/a.py"]}])
    sp = tmp_path / "state.json"
    sp.write_text(json.dumps(state), encoding="utf-8")
    cf = tmp_path / "changed.txt"
    cf.write_text("src/a.py\nsrc/other.py\n", encoding="utf-8")
    assert impacted.main(["impacted", "--tasks-state", str(sp), "--changed-file", str(cf)]) == 0
    assert json.loads(capsys.readouterr().out)["impacted"] == ["T1"]


def test_cli_verify_flags_a_regression(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    _stage(repo, "src/a.py", "x = 1\n")
    _commit(repo)

    state = _state([{"id": "T1", "status": "done", "files": ["src/a.py"]}])
    prior, _ = impacted._load("verify_core").build_report(state, repo)
    assert prior["summary"]["verdict"] == "pass"

    state_path = tmp_path / "state.json"
    state_path.write_text(json.dumps(state), encoding="utf-8")
    prior_path = tmp_path / "prior.json"
    prior_path.write_text(json.dumps(prior), encoding="utf-8")

    # Delete the verified file so the impacted re-verify flips T1 pass -> fail.
    (repo / "src" / "a.py").unlink()
    rc = impacted.main(["verify", "--tasks-state", str(state_path), "--changed", "src/a.py",
                        "--root", str(repo), "--against", str(prior_path)])
    assert rc == 1


def test_cli_verify_no_regression_when_change_impacts_nothing(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    _stage(repo, "src/a.py", "x = 1\n")
    _commit(repo)
    state = _state([{"id": "T1", "status": "done", "files": ["src/a.py"]}])
    state_path = tmp_path / "state.json"
    state_path.write_text(json.dumps(state), encoding="utf-8")
    # A change to an unrelated path impacts no task, so the slice is empty and
    # there is no regression, exit 0.
    rc = impacted.main(["verify", "--tasks-state", str(state_path), "--changed", "src/unrelated.py",
                        "--root", str(repo)])
    assert rc == 0


def test_cli_missing_tasks_state_returns_2(tmp_path):
    assert impacted.main(["impacted", "--tasks-state", str(tmp_path / "no.json"),
                          "--changed", "x"]) == 2


# --------------------------------------------------------------------------- #
# review follow-ups: ./ prefix, build crash, transitive regression, missing prior
# --------------------------------------------------------------------------- #

def test_direct_impacted_strips_leading_dot_slash():
    # git diff --name-only emits bare paths, but a task may declare ./src/a.py.
    state = _state([{"id": "T1", "status": "done", "files": ["./src/a.py"]}])
    assert impacted.direct_impacted(state, ["src/a.py"]) == {"T1"}
    # and the symmetric case, a changed path carrying the prefix.
    state2 = _state([{"id": "T2", "status": "done", "files": ["src/b.py"]}])
    assert impacted.direct_impacted(state2, ["./src/b.py"]) == {"T2"}


def test_cli_verify_build_crash_returns_2(tmp_path, monkeypatch):
    state = _state([{"id": "T1", "status": "done", "files": ["src/a.py"]}])
    sp = tmp_path / "state.json"
    sp.write_text(json.dumps(state), encoding="utf-8")

    class _Boom:
        @staticmethod
        def build_report(s, r):
            raise RuntimeError("boom")

    monkeypatch.setitem(impacted._MODS, "verify_core", _Boom)
    assert impacted.main(["verify", "--tasks-state", str(sp), "--changed", "src/a.py",
                          "--root", str(tmp_path)]) == 2


def test_cli_verify_transitive_regression_needs_the_dag(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    _stage(repo, "src/a.py", "x = 1\n")
    _stage(repo, "src/b.py", "y = 1\n")
    _commit(repo)

    state = _state([{"id": "TA", "status": "done", "files": ["src/a.py"]},
                    {"id": "TB", "status": "done", "files": ["src/b.py"]}])
    prior, _ = impacted._load("verify_core").build_report(state, repo)
    assert prior["summary"]["verdict"] == "pass"

    sp = tmp_path / "state.json"
    sp.write_text(json.dumps(state), encoding="utf-8")
    pp = tmp_path / "prior.json"
    pp.write_text(json.dumps(prior), encoding="utf-8")
    dag = [[{"id": "TA"}], [{"id": "TB", "depends_on": ["TA"]}]]
    dp = tmp_path / "dag.json"
    dp.write_text(json.dumps(dag), encoding="utf-8")

    # A changed (TA still passes, a.py exists), but its dependent TB broke (b.py
    # deleted). With the DAG, TB is pulled into the slice and the regression shows.
    (repo / "src" / "b.py").unlink()
    assert impacted.main(["verify", "--tasks-state", str(sp), "--dag", str(dp),
                          "--changed", "src/a.py", "--root", str(repo),
                          "--against", str(pp)]) == 1
    # Without the DAG, TB is outside the slice and the transitive regression is
    # missed, which is why the DAG matters.
    assert impacted.main(["verify", "--tasks-state", str(sp),
                          "--changed", "src/a.py", "--root", str(repo),
                          "--against", str(pp)]) == 0


def test_cli_verify_missing_prior_returns_2(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    _stage(repo, "src/a.py", "x = 1\n")
    _commit(repo)
    state = _state([{"id": "T1", "status": "done", "files": ["src/a.py"]}])
    sp = tmp_path / "state.json"
    sp.write_text(json.dumps(state), encoding="utf-8")
    assert impacted.main(["verify", "--tasks-state", str(sp), "--changed", "src/a.py",
                          "--root", str(repo), "--against", str(tmp_path / "nope.json")]) == 2


def test_scoped_verdict_equals_full_verdict_for_a_task(tmp_path):
    # The key property of the scoped re-verify: a task's verdict does not depend on
    # which other tasks share the state, so a scoped run cannot disagree with a full
    # run for the same task.
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    _stage(repo, "src/a.py", "x = 1\n")
    _stage(repo, "src/b.py", "y = 1\n")
    _commit(repo)
    verify_core = impacted._load("verify_core")
    full = _state([{"id": "T1", "status": "done", "files": ["src/a.py"]},
                   {"id": "T2", "status": "done", "files": ["src/b.py"]}])
    full_report, _ = verify_core.build_report(full, repo)
    scoped_report, _ = verify_core.build_report(impacted.scoped_state(full, {"T1"}), repo)
    full_t1 = {t["task_id"]: t["verified_status"] for t in full_report["tasks"]}["T1"]
    scoped_t1 = {t["task_id"]: t["verified_status"] for t in scoped_report["tasks"]}["T1"]
    assert full_t1 == scoped_t1
