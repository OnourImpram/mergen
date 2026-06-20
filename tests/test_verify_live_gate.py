"""Tests for the live re-verify gate and its attestation drop-in (A2).

Two honesty claims are pinned here:
  1. Regenerating the report from the live tree catches a phantom regardless of
     any committed report, which is what makes a hand-edited report moot.
  2. The shipped drop-in workflows actually regenerate (verify-gate-live.yml does
     not read a committed report) and attest the FRESH report (verify-attest.yml),
     so the workflow files cannot silently drift back into reading a committed
     artifact or signing the wrong subject.

verify_core is loaded by file path because scripts/ is not an importable package.
"""

from __future__ import annotations

import importlib.util
import re
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CI = REPO / "eval" / "ci"


def _git(root: Path, *args: str) -> None:
    # No commit is needed: the git-consistent lens passes on a tracked (staged)
    # file, so init + add -A is enough and avoids needing a git identity.
    subprocess.run(
        ["git", "-C", str(root), *args],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=True,
    )


def _load(rel_path: str):
    path = REPO / rel_path
    spec = importlib.util.spec_from_file_location(path.stem.replace("-", "_"), path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_live_regeneration_catches_a_phantom_a_committed_report_could_hide(tmp_path):
    # A hand-edited committed report could claim every task passed. The live gate
    # never reads it: it regenerates from the tree. Here T002 names a file that
    # does not exist, so a fresh build_report must mark it failed no matter what a
    # committed report says.
    vc = _load("scripts/verify_core.py")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "real.py").write_text("x = 1\n", encoding="utf-8")
    # A fresh git repo with the genuine file tracked, the way the live gate sees a
    # real checkout. This lets the genuine task pass while the phantom fails, so
    # the test proves the phantom specifically is caught, not that everything fails.
    _git(tmp_path, "init")
    _git(tmp_path, "add", "-A")
    tasks_state = {
        "schema_version": "1.0",
        "feature_id": "demo",
        "tasks": [
            {"id": "T001", "status": "done", "files": ["src/real.py"], "test_task": None},
            {"id": "T002", "status": "done", "files": ["src/missing.py"], "test_task": None},
        ],
    }
    report, overall_pass = vc.build_report(tasks_state, tmp_path)
    assert overall_pass is False  # the phantom fails the fresh verdict
    by_id = {t["task_id"]: t for t in report["tasks"]}
    assert by_id["T001"]["verified_status"] == "pass"  # genuine task, tracked and present
    assert by_id["T002"]["verified_status"] == "fail"  # phantom, file absent
    assert report["summary"]["mechanically_failed"] >= 1


def test_live_regeneration_catches_a_failing_test_task(tmp_path):
    # A tracked, present file whose test suite FAILS is still incomplete work. This
    # covers the tests-pass lens, the axis the file-exists case above does not
    # exercise, so the two together prove the gate catches both failure modes.
    vc = _load("scripts/verify_core.py")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "real.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_real.py").write_text(
        "def test_it():\n    assert False\n", encoding="utf-8"
    )
    _git(tmp_path, "init")
    _git(tmp_path, "add", "-A")
    tasks_state = {
        "schema_version": "1.0",
        "feature_id": "demo",
        "tasks": [
            {"id": "T001", "status": "done", "files": ["src/real.py"],
             "test_task": "tests/test_real.py"},
        ],
    }
    report, overall_pass = vc.build_report(tasks_state, tmp_path)
    assert overall_pass is False
    t1 = report["tasks"][0]
    assert t1["lens_tests_pass"] == "fail"
    assert t1["verified_status"] == "fail"


def test_live_gate_workflow_regenerates_and_does_not_read_a_committed_report():
    text = (CI / "verify-gate-live.yml").read_text(encoding="utf-8")
    # It regenerates with verify_core into a fresh report path.
    assert "verify_core.py" in text
    assert "fresh-verification-report.json" in text
    # It gates the FRESH report.
    assert "evidence_metric.py" in text
    # Strong invariant: outside comments, every mention of the report file must be
    # the fresh one. A regressed step that read a bare committed report path
    # (e.g. "evidence_metric.py verification-report.json --gate") would fail here.
    no_comments = re.sub(r"#[^\n]*", "", text)
    assert not re.search(r"(?<!fresh-)verification-report\.json", no_comments)


def test_attest_workflow_signs_the_fresh_report_with_oidc():
    text = (CI / "verify-attest.yml").read_text(encoding="utf-8")
    assert "actions/attest-build-provenance" in text
    # The OIDC + attestation permissions the hosted signer needs.
    assert "id-token: write" in text
    assert "attestations: write" in text
    # The subject is the regenerated report, never a committed one.
    assert "subject-path: fresh-verification-report.json" in text


def test_committed_report_gate_still_documents_its_narrower_guarantee():
    # The original committed-report gate is still honest about reading a committed
    # report, so the two stronger drop-ins are an addition, not a silent swap.
    text = (CI / "verify-gate.yml").read_text(encoding="utf-8")
    assert "path/to/verification-report.json" in text


def test_unparseable_tasks_state_exits_2_not_1(tmp_path):
    # A malformed tasks-state means no report can be produced. It must exit 2 (a
    # harness error), not 1 (a verdict), so the live gate's vc==2 guard can tell a
    # crash apart from a real failure instead of masking it as an empty report.
    vc = _load("scripts/verify_core.py")
    bad = tmp_path / "tasks-state.json"
    bad.write_text("{ this is not valid json", encoding="utf-8")
    rc = vc.main(["--tasks-state", str(bad), "--root", str(tmp_path)])
    assert rc == 2
