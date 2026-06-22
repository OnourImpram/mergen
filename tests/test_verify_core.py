from __future__ import annotations

import hashlib
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
# calibrate(): the pure evidence-strength scorer, no filesystem needed.
# ---------------------------------------------------------------------------


def test_calibrate_all_pass_is_executed_at_full_strength() -> None:
    strength, tier = verify_core.calibrate(
        {"file_exists": "pass", "tests_pass": "pass", "git_consistent": "pass"})
    assert tier == "executed"
    assert strength == 1.0


def test_calibrate_test_only_is_executed_at_half_strength() -> None:
    # A passing test alone is the strong tier, but only 3 of 6 total lens weight.
    strength, tier = verify_core.calibrate(
        {"file_exists": "na", "tests_pass": "pass", "git_consistent": "na"})
    assert tier == "executed"
    assert strength == 0.5


def test_calibrate_static_only_is_corroborated() -> None:
    strength, tier = verify_core.calibrate(
        {"file_exists": "pass", "tests_pass": "na", "git_consistent": "pass"})
    assert tier == "corroborated"
    assert strength == 0.5  # (file 1 + git 2) / 6


def test_calibrate_no_pass_is_none_at_zero() -> None:
    strength, tier = verify_core.calibrate(
        {"file_exists": "na", "tests_pass": "na", "git_consistent": "na"})
    assert tier == "none"
    assert strength == 0.0


def test_calibrate_failing_test_earns_no_weight_and_no_executed_tier() -> None:
    # A failing test is not an executed pass: it contributes zero weight and the
    # tier falls to whatever static lens passed.
    strength, tier = verify_core.calibrate(
        {"file_exists": "pass", "tests_pass": "fail", "git_consistent": "pass"})
    assert tier == "corroborated"
    assert strength == 0.5  # the failed test earns nothing, (1 + 2) / 6


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
    # A test ran and passed, so this is the strongest evidence tier at full strength.
    assert item["evidence_tier"] == "executed"
    assert item["evidence_strength"] == 1.0

    # Summary counts must be coherent.
    s = report["summary"]
    assert s["total_done_tasks"] == 1
    assert s["mechanically_passed"] == 1
    assert s["mechanically_failed"] == 0
    assert s["untested_passes"] == 0  # the pass was test-backed


# ---------------------------------------------------------------------------
# Calibration: a pass with no executed test is corroborated, not executed.
# ---------------------------------------------------------------------------


def test_done_task_files_only_is_corroborated_and_counts_as_untested(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    init_git_repo(repo)
    src = "src/m.py"
    write_and_stage(repo, src, "x = 1\n")
    commit_all(repo)

    tasks_file = tmp_path / "tasks-state.json"
    write_tasks_state(tasks_file, [{"id": "T1", "status": "done", "files": [src]}])

    report, overall_pass = verify_core.build_report(
        json.loads(tasks_file.read_text(encoding="utf-8")), repo
    )

    assert overall_pass is True
    item = [i for i in report["tasks"] if i["claimed_status"] == "done"][0]
    assert item["verified_status"] == "pass"
    # No test ran, so the pass is corroborated by the two static lenses only.
    assert item["evidence_tier"] == "corroborated"
    assert item["evidence_strength"] == 0.5  # (file 1 + git 2) / total 6
    # The report flags that this pass was never exercised by a test.
    assert report["summary"]["untested_passes"] == 1


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
    # The failed hard gate earns no corroboration. Calibration records the
    # weakness, it does not soften the fail.
    assert item["evidence_tier"] == "none"
    assert item["evidence_strength"] == 0.0

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
    # A failing test is not executed evidence: it earns no weight and no tier, and
    # a fail is never counted as an untested pass.
    assert item["evidence_tier"] == "none"
    assert item["evidence_strength"] == 0.0

    s = report["summary"]
    assert s["mechanically_failed"] == 1
    assert s["untested_passes"] == 0


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
    # No lens applied, so there is no corroboration to score.
    assert item["evidence_tier"] == "none"
    assert item["evidence_strength"] == 0.0

    s = report["summary"]
    assert s["ambiguous"] == 1
    assert s["mechanically_failed"] == 0
    assert s["untested_passes"] == 0


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


# ---------------------------------------------------------------------------
# BOM tolerance: Windows PowerShell writes a UTF-8 BOM into JSON files.
# ---------------------------------------------------------------------------


def test_main_reads_tasks_state_with_utf8_bom(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    init_git_repo(repo)

    src_file = "src/module.py"
    write_and_stage(repo, src_file, "x = 1\n")
    commit_all(repo)

    test_rel = "tests/test_module.py"
    write_passing_test(repo, test_rel)

    state = {
        "schema_version": "1.0",
        "feature_id": "bom",
        "tasks": [{"id": "T1", "status": "done", "files": [src_file], "test_task": test_rel}],
    }
    tasks_file = tmp_path / "tasks-state.json"
    # Prepend the UTF-8 BOM. With the old utf-8 read this would crash the verifier.
    tasks_file.write_bytes(b"\xef\xbb\xbf" + json.dumps(state).encode("utf-8"))

    exit_code = verify_core.main(["--tasks-state", str(tasks_file), "--root", str(repo)])
    # The BOM file parsed and the genuine task verified: exit 0, not the
    # file-read error code 2 and not an uncaught BOM decode crash.
    assert exit_code == 0


# ---------------------------------------------------------------------------
# Tamper-evident manifest: provenance, sidecar, check, tamper, staleness.
# ---------------------------------------------------------------------------


def _repo_with_done_task(tmp_path: Path) -> tuple[Path, Path]:
    repo = tmp_path / "repo"
    repo.mkdir()
    init_git_repo(repo)
    write_and_stage(repo, "src/module.py", "x = 1\n")
    commit_all(repo)
    write_passing_test(repo, "tests/test_module.py")
    tasks_file = tmp_path / "tasks-state.json"
    write_tasks_state(
        tasks_file,
        [{"id": "T1", "status": "done", "files": ["src/module.py"],
          "test_task": "tests/test_module.py"}],
    )
    return repo, tasks_file


def test_provenance_records_commit_tree_and_state_hash(tmp_path: Path) -> None:
    repo, tasks_file = _repo_with_done_task(tmp_path)
    out = tmp_path / "report.json"
    rc = verify_core.main(
        ["--tasks-state", str(tasks_file), "--root", str(repo), "--out", str(out)]
    )
    assert rc == 0
    prov = json.loads(out.read_text(encoding="utf-8"))["provenance"]
    assert prov["verifier_version"] == verify_core.VERIFIER_VERSION
    head = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        text=True, check=True,
    ).stdout.strip()
    assert prov["source_commit"] == head
    assert prov["working_tree_clean"] is True
    assert prov["tasks_state_sha256"] == hashlib.sha256(tasks_file.read_bytes()).hexdigest()


def test_provenance_is_null_outside_a_git_repo(tmp_path: Path) -> None:
    # A non-git root still verifies; the staleness signal is just unavailable.
    work = tmp_path / "plain"
    work.mkdir()
    (work / "src").mkdir()
    (work / "src" / "x.py").write_text("x = 1\n", encoding="utf-8")
    tasks_file = tmp_path / "tasks-state.json"
    write_tasks_state(tasks_file, [{"id": "T1", "status": "done", "files": ["src/x.py"]}])
    out = tmp_path / "report.json"
    verify_core.main(["--tasks-state", str(tasks_file), "--root", str(work), "--out", str(out)])
    prov = json.loads(out.read_text(encoding="utf-8"))["provenance"]
    assert prov["source_commit"] is None
    assert prov["working_tree_clean"] is None


def test_out_writes_sidecar_matching_report_bytes(tmp_path: Path) -> None:
    repo, tasks_file = _repo_with_done_task(tmp_path)
    out = tmp_path / "report.json"
    verify_core.main(["--tasks-state", str(tasks_file), "--root", str(repo), "--out", str(out)])
    sidecar = tmp_path / "report.json.sha256"
    assert sidecar.is_file()
    recorded = sidecar.read_text(encoding="utf-8").split()[0]
    assert recorded == hashlib.sha256(out.read_bytes()).hexdigest()


def test_check_manifest_passes_on_intact_report(tmp_path: Path) -> None:
    repo, tasks_file = _repo_with_done_task(tmp_path)
    out = tmp_path / "report.json"
    verify_core.main(["--tasks-state", str(tasks_file), "--root", str(repo), "--out", str(out)])
    assert verify_core.main(["--check-manifest", str(out)]) == 0


def test_check_manifest_detects_tamper(tmp_path: Path) -> None:
    repo, tasks_file = _repo_with_done_task(tmp_path)
    out = tmp_path / "report.json"
    verify_core.main(["--tasks-state", str(tasks_file), "--root", str(repo), "--out", str(out)])
    # Flip the verdict in the written report. The sidecar no longer matches.
    edited = out.read_bytes().replace(b'"verdict": "pass"', b'"verdict": "fail"', 1)
    assert edited != out.read_bytes()
    out.write_bytes(edited)
    assert verify_core.main(["--check-manifest", str(out)]) == 1


def test_check_manifest_require_fresh_detects_stale_commit(tmp_path: Path) -> None:
    repo, tasks_file = _repo_with_done_task(tmp_path)
    out = tmp_path / "report.json"
    verify_core.main(["--tasks-state", str(tasks_file), "--root", str(repo), "--out", str(out)])
    # Fresh right after generation.
    assert verify_core.main(
        ["--check-manifest", str(out), "--root", str(repo), "--require-fresh"]
    ) == 0
    # A new commit moves HEAD, so the report is now stale.
    write_and_stage(repo, "src/extra.py", "y = 2\n")
    commit_all(repo, "move HEAD")
    assert verify_core.main(
        ["--check-manifest", str(out), "--root", str(repo), "--require-fresh"]
    ) == 1


def test_check_manifest_missing_sidecar_returns_2(tmp_path: Path) -> None:
    report = tmp_path / "report.json"
    report.write_text("{}", encoding="utf-8")
    assert verify_core.main(["--check-manifest", str(report)]) == 2


def test_check_manifest_missing_report_returns_2(tmp_path: Path) -> None:
    # The other exit-2 path: the report file itself does not exist.
    assert verify_core.main(["--check-manifest", str(tmp_path / "nope.json")]) == 2


# ---------------------------------------------------------------------------
# Path safety: the test_task / files injection that bypassed the verify chain.
# Each of these earned a pass before the fence existed.
# ---------------------------------------------------------------------------


def test_safe_repo_relative_path_accepts_and_normalizes(tmp_path: Path) -> None:
    root = tmp_path
    assert verify_core.safe_repo_relative_path("tests/test_x.py", root, kind="t") == "tests/test_x.py"
    # Backslashes normalize to POSIX; a dotted filename is not a traversal.
    assert verify_core.safe_repo_relative_path("src\\m.py", root, kind="t") == "src/m.py"
    assert verify_core.safe_repo_relative_path("foo..bar.py", root, kind="t") == "foo..bar.py"


def test_safe_repo_relative_path_rejects_options_and_escapes(tmp_path: Path) -> None:
    root = tmp_path
    for bad in ("--version", "-k name", "../outside/test.py", "sub/../x.py",
                "/abs/test.py", "C:\\tmp\\t.py", "a*b.py", "q[0].py", "", "  "):
        try:
            verify_core.safe_repo_relative_path(bad, root, kind="test_task")
        except verify_core.UnsafePathError:
            continue
        raise AssertionError(f"expected UnsafePathError for {bad!r}")
    # The error never echoes the raw value, so a rejected absolute path cannot leak.
    try:
        verify_core.safe_repo_relative_path("/etc/secret", root, kind="files")
    except verify_core.UnsafePathError as exc:
        assert "/etc/secret" not in str(exc)


def test_test_task_option_injection_cannot_pass(tmp_path: Path) -> None:
    # "--version" makes a raw `pytest --version` exit 0. Before the fence that earned a
    # done verdict with no test ever running. It must now fail.
    repo = tmp_path / "repo"
    repo.mkdir()
    init_git_repo(repo)
    tasks_file = tmp_path / "tasks-state.json"
    write_tasks_state(tasks_file, [{"id": "T1", "status": "done", "test_task": "--version"}])

    report, overall_pass = verify_core.build_report(
        json.loads(tasks_file.read_text(encoding="utf-8")), repo
    )
    assert overall_pass is False
    item = [i for i in report["tasks"] if i["claimed_status"] == "done"][0]
    assert item["verified_status"] == "fail"
    assert item["lens_tests_pass"] == "fail"
    assert any("unsafe test_task" in f for f in item["failures"])
    # The report records the redacted marker, never the raw option.
    assert item["tests_run"] == ["<rejected test_task>"]


def test_test_task_outside_repo_cannot_pass_and_does_not_leak(tmp_path: Path) -> None:
    # A real passing test sitting outside the repo, referenced by traversal. The bypass
    # would run it and pass; the fence rejects the path and leaks no machine-local path.
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "test_ok.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    repo = tmp_path / "repo"
    repo.mkdir()
    init_git_repo(repo)
    tasks_file = tmp_path / "tasks-state.json"
    write_tasks_state(
        tasks_file, [{"id": "T1", "status": "done", "test_task": "../outside/test_ok.py"}]
    )

    report, overall_pass = verify_core.build_report(
        json.loads(tasks_file.read_text(encoding="utf-8")), repo
    )
    assert overall_pass is False
    blob = json.dumps(report)
    assert "../outside" not in blob
    assert str(tmp_path) not in blob


def test_files_traversal_fails_and_does_not_leak(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("top secret\n", encoding="utf-8")
    repo = tmp_path / "repo"
    repo.mkdir()
    init_git_repo(repo)
    tasks_file = tmp_path / "tasks-state.json"
    write_tasks_state(
        tasks_file, [{"id": "T1", "status": "done", "files": ["../outside/secret.txt"]}]
    )

    report, overall_pass = verify_core.build_report(
        json.loads(tasks_file.read_text(encoding="utf-8")), repo
    )
    assert overall_pass is False
    item = [i for i in report["tasks"] if i["claimed_status"] == "done"][0]
    assert item["lens_file_exists"] == "fail"
    assert item["files_checked"] == ["<rejected files>"]
    blob = json.dumps(report)
    assert "../outside" not in blob
    assert str(tmp_path) not in blob


def test_test_task_timeout_is_a_fail(tmp_path: Path) -> None:
    # A hanging test must fail on the timeout, never hang the harness or pass.
    repo = tmp_path / "repo"
    repo.mkdir()
    init_git_repo(repo)
    write_and_stage(repo, "tests/test_slow.py",
                    "import time\n\n\ndef test_slow():\n    time.sleep(60)\n")
    commit_all(repo, "add slow test")
    tasks_file = tmp_path / "tasks-state.json"
    write_tasks_state(
        tasks_file, [{"id": "T1", "status": "done", "test_task": "tests/test_slow.py"}]
    )

    report, overall_pass = verify_core.build_report(
        json.loads(tasks_file.read_text(encoding="utf-8")), repo, test_timeout=2
    )
    assert overall_pass is False
    item = [i for i in report["tasks"] if i["claimed_status"] == "done"][0]
    assert item["lens_tests_pass"] == "fail"
    assert any("timed out" in f for f in item["failures"])


def test_schema_pattern_matches_validator(tmp_path: Path) -> None:
    # The schema pattern is the declarative mirror of safe_repo_relative_path. They must
    # agree on every case, so a generic schema validator and the Python enforcement reject
    # the same paths (no drift).
    import re

    schema_path = Path(__file__).parent.parent / "core" / "schemas" / "tasks-state.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    pattern = schema["properties"]["tasks"]["items"]["properties"]["test_task"]["pattern"]
    rx = re.compile(pattern)
    cases = ["tests/test_x.py", "src/auth.py", "foo..bar.py",
             "--version", "-k name", "../outside/test.py", "sub/../x.py",
             "/abs/t.py", "C:\\tmp\\t.py", "a*b.py", "q[0].py"]
    for c in cases:
        schema_ok = bool(rx.match(c))
        try:
            verify_core.safe_repo_relative_path(c, tmp_path, kind="files")
            validator_ok = True
        except verify_core.UnsafePathError:
            validator_ok = False
        assert schema_ok == validator_ok, f"drift on {c!r}: schema={schema_ok} validator={validator_ok}"


# ---------------------------------------------------------------------------
# --strict exit semantics: the exit code becomes a merge gate. The default exit
# stays back-compatible (mechanical failure only), so existing callers are unaffected.
# ---------------------------------------------------------------------------


def test_strict_exit_zero_on_clean_pass(tmp_path: Path) -> None:
    repo, tasks_file = _repo_with_done_task(tmp_path)
    rc = verify_core.main(
        ["--tasks-state", str(tasks_file), "--root", str(repo), "--strict"]
    )
    assert rc == 0


def test_strict_exit_nonzero_on_ambiguous_but_default_is_zero(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    init_git_repo(repo)
    tasks_file = write_tasks_state(tmp_path / "ts.json", [{"id": "T1", "status": "done"}])
    # Default exit is unchanged: an ambiguous done task is not a mechanical failure.
    assert verify_core.main(["--tasks-state", str(tasks_file), "--root", str(repo)]) == 0
    # Under --strict a conditional_pass (human review required) is not a clean pass.
    assert verify_core.main(
        ["--tasks-state", str(tasks_file), "--root", str(repo), "--strict"]
    ) == 1


def test_strict_exit_nonzero_on_high_trust_pending(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    init_git_repo(repo)
    # An auth-path change trips the Governor high-trust floor: the task mechanically
    # passes, but the report flags that a human sign-off is still outstanding.
    write_and_stage(repo, "src/auth.py", "def login():\n    return True\n")
    commit_all(repo)
    tasks_file = write_tasks_state(
        tmp_path / "ts.json", [{"id": "T1", "status": "done", "files": ["src/auth.py"]}]
    )
    report, _ = verify_core.build_report(
        json.loads(tasks_file.read_text(encoding="utf-8")), repo
    )
    assert report["summary"]["risk_level"] == "high-trust"
    assert report["summary"]["human_review_required"] is True
    # Default exit is 0 (no mechanical failure); --strict refuses the unsigned high-trust.
    assert verify_core.main(["--tasks-state", str(tasks_file), "--root", str(repo)]) == 0
    assert verify_core.main(
        ["--tasks-state", str(tasks_file), "--root", str(repo), "--strict"]
    ) == 1
