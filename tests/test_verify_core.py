from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

"""Tests for scripts/verify_core.py.

Each test uses a real throwaway git repo created with subprocess so the
mechanical lenses run against actual filesystem and git state, not mocks.
"""

# Make the scripts package importable when running from the repo root.
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
import verify_core  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_DEVNULL = {
    "stdin": subprocess.DEVNULL,
    "stdout": subprocess.DEVNULL,
    "stderr": subprocess.DEVNULL,
}


def init_git_repo(path: Path) -> None:
    """Create a minimal git repo at path with a committed initial state."""
    subprocess.run(["git", "init", str(path)], check=True, **_DEVNULL)  # type: ignore[call-overload]
    subprocess.run(
        ["git", "-C", str(path), "config", "user.email", "test@mergen.test"],
        check=True,
        **_DEVNULL,  # type: ignore[call-overload]
    )
    subprocess.run(
        ["git", "-C", str(path), "config", "user.name", "Mergen Test"],
        check=True,
        **_DEVNULL,  # type: ignore[call-overload]
    )
    # Initial empty commit so HEAD exists.
    subprocess.run(
        ["git", "-C", str(path), "commit", "--allow-empty", "-m", "init"],
        check=True,
        **_DEVNULL,  # type: ignore[call-overload]
    )


def write_and_stage(repo: Path, rel: str, content: str) -> Path:
    """Write a file inside the repo and stage it."""
    target = repo / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content.encode("utf-8"))
    subprocess.run(
        ["git", "-C", str(repo), "add", rel],
        check=True,
        **_DEVNULL,  # type: ignore[call-overload]
    )
    return target


def commit_all(repo: Path, message: str = "add files") -> None:
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-m", message],
        check=True,
        **_DEVNULL,  # type: ignore[call-overload]
    )


def write_tasks_state(
    path: Path,
    tasks: list[dict],
    feature_id: str = "test-feature",
) -> Path:
    state = {
        "schema_version": "1.0",
        "feature_id": feature_id,
        "tasks": tasks,
    }
    path.write_bytes(json.dumps(state).encode("utf-8"))
    return path


def write_passing_test(repo: Path, rel: str) -> None:
    """Write a pytest file that always passes."""
    content = "def test_pass():\n    assert True\n"
    write_and_stage(repo, rel, content)
    commit_all(repo, "add passing test")


def write_failing_test(repo: Path, rel: str) -> None:
    """Write a pytest file that always fails."""
    content = "def test_fail():\n    assert False, 'deliberate failure'\n"
    write_and_stage(repo, rel, content)
    commit_all(repo, "add failing test")


# ---------------------------------------------------------------------------
# Case (a): done task, file exists, test passes, git knows it.
# ---------------------------------------------------------------------------


def test_done_task_all_lenses_pass(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    init_git_repo(repo)

    src_file = "src/module.py"
    write_and_stage(repo, src_file, "x = 1\n")
    commit_all(repo)

    test_rel = "tests/test_module.py"
    write_passing_test(repo, test_rel)

    tasks_file = tmp_path / "tasks-state.json"
    write_tasks_state(
        tasks_file,
        [
            {
                "id": "T1",
                "status": "done",
                "files": [src_file],
                "test_task": test_rel,
            }
        ],
    )

    report, overall_pass = verify_core.build_report(
        json.loads(tasks_file.read_text(encoding="utf-8")), repo
    )

    assert overall_pass is True, f"expected overall pass, got report: {report}"

    done_items = [i for i in report["tasks"] if i["claimed_status"] == "done"]
    assert len(done_items) == 1
    item = done_items[0]
    assert item["task_id"] == "T1"
    assert item["verified_status"] == "pass"
    assert item["confidence"] == "extracted"
    assert item["lens_file_exists"] == "pass"
    assert item["lens_tests_pass"] == "pass"
    assert item["lens_git_consistent"] == "pass"

    # Summary counts must be coherent.
    s = report["summary"]
    assert s["total_done_tasks"] == 1
    assert s["mechanically_passed"] == 1
    assert s["mechanically_failed"] == 0


# ---------------------------------------------------------------------------
# Case (b): done task with a missing file => file_exists fail, exit 1.
# ---------------------------------------------------------------------------


def test_done_task_missing_file_fails(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    init_git_repo(repo)

    tasks_file = tmp_path / "tasks-state.json"
    write_tasks_state(
        tasks_file,
        [
            {
                "id": "T2",
                "status": "done",
                "files": ["does/not/exist.py"],
            }
        ],
    )

    report, overall_pass = verify_core.build_report(
        json.loads(tasks_file.read_text(encoding="utf-8")), repo
    )

    assert overall_pass is False

    done_items = [i for i in report["tasks"] if i["claimed_status"] == "done"]
    item = done_items[0]
    assert item["verified_status"] == "fail"
    assert item["lens_file_exists"] == "fail"
    assert any("missing" in f for f in item["failures"])

    s = report["summary"]
    assert s["mechanically_failed"] == 1
    assert report["summary"]["verdict"] == "fail"


# ---------------------------------------------------------------------------
# Case (c): done task whose named test fails => tests_pass fail, exit 1.
# ---------------------------------------------------------------------------


def test_done_task_failing_test(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    init_git_repo(repo)

    test_rel = "tests/test_bad.py"
    write_failing_test(repo, test_rel)

    tasks_file = tmp_path / "tasks-state.json"
    write_tasks_state(
        tasks_file,
        [
            {
                "id": "T3",
                "status": "done",
                "test_task": test_rel,
            }
        ],
    )

    report, overall_pass = verify_core.build_report(
        json.loads(tasks_file.read_text(encoding="utf-8")), repo
    )

    assert overall_pass is False

    done_items = [i for i in report["tasks"] if i["claimed_status"] == "done"]
    item = done_items[0]
    assert item["verified_status"] == "fail"
    assert item["lens_tests_pass"] == "fail"

    s = report["summary"]
    assert s["mechanically_failed"] == 1


# ---------------------------------------------------------------------------
# Case (d): done task with no files and no test => all lenses "na",
#            confidence "ambiguous", NOT counted as a mechanical failure.
# ---------------------------------------------------------------------------


def test_done_task_no_files_no_test_is_ambiguous(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    init_git_repo(repo)

    tasks_file = tmp_path / "tasks-state.json"
    write_tasks_state(
        tasks_file,
        [
            {
                "id": "T4",
                "status": "done",
            }
        ],
    )

    report, overall_pass = verify_core.build_report(
        json.loads(tasks_file.read_text(encoding="utf-8")), repo
    )

    # Ambiguous tasks are not mechanical failures, so overall_pass is True.
    assert overall_pass is True

    done_items = [i for i in report["tasks"] if i["claimed_status"] == "done"]
    item = done_items[0]
    assert item["confidence"] == "ambiguous"
    assert item["lens_file_exists"] == "na"
    assert item["lens_tests_pass"] == "na"
    assert item["lens_git_consistent"] == "na"

    s = report["summary"]
    assert s["ambiguous"] == 1
    assert s["mechanically_failed"] == 0


# ---------------------------------------------------------------------------
# Case (e): emitted JSON has all schema-required task keys and a summary.
# ---------------------------------------------------------------------------


def test_report_has_required_schema_keys(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    init_git_repo(repo)

    src = "src/thing.py"
    write_and_stage(repo, src, "pass\n")
    commit_all(repo)

    tasks_file = tmp_path / "tasks-state.json"
    write_tasks_state(
        tasks_file,
        [
            {"id": "T5", "status": "done", "files": [src]},
            {"id": "T6", "status": "pending"},
        ],
    )

    out_file = tmp_path / "report.json"
    exit_code = verify_core.main(
        [
            "--tasks-state",
            str(tasks_file),
            "--root",
            str(repo),
            "--out",
            str(out_file),
        ]
    )

    assert out_file.exists(), "report file was not written"
    report = json.loads(out_file.read_text(encoding="utf-8"))

    # Top-level schema-required fields.
    for key in ("schema_version", "feature_id", "verified_at", "summary", "tasks"):
        assert key in report, f"missing top-level key: {key}"

    # Summary required fields.
    for key in ("verdict", "human_review_required"):
        assert key in report["summary"], f"missing summary key: {key}"

    # Every tasks item must carry the four schema-required keys.
    for item in report["tasks"]:
        for key in ("task_id", "claimed_status", "verified_status", "confidence"):
            assert key in item, f"task item missing key: {key}"

    # The done task should have passed all applicable lenses.
    done_items = [i for i in report["tasks"] if i["claimed_status"] == "done"]
    assert len(done_items) == 1
    assert done_items[0]["verified_status"] == "pass"

    # Exit code 0 means no mechanical failure.
    assert exit_code == 0
