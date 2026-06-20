"""Runs the committed worked example through the real verify harness.

examples/verify-demo/ is a documentation artifact (README plus a tasks-state and
its files). This test exercises it end to end so the example cannot rot: if a
change broke the harness or the example, the asserts below fail.

The assertions are commit-state independent. file-exists and tests-pass hold
whether or not the demo files are tracked. The git-consistent lens depends on
tracking, so this test does not pin T001's overall verdict on it. T002 is a
planted phantom (a named file that does not exist), so it is always caught.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import verify_core  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
DEMO = REPO / "examples" / "verify-demo"


def _report():
    state = json.loads((DEMO / "tasks-state.json").read_text(encoding="utf-8"))
    return verify_core.build_report(state, DEMO)


def test_demo_exists():
    assert (DEMO / "tasks-state.json").is_file()
    assert (DEMO / "src" / "greeter.py").is_file()
    assert (DEMO / "tests" / "test_greeter.py").is_file()
    # T002's file is the planted phantom and must NOT exist.
    assert not (DEMO / "src" / "teardown.py").exists()


def test_genuine_task_is_confirmed_by_real_evidence():
    report, _ = _report()
    by_id = {t["task_id"]: t for t in report["tasks"]}
    t001 = by_id["T001"]
    # These two lenses are commit-state independent and prove the artifact and
    # its test are real, the genuine-completion half of the demo.
    assert t001["lens_file_exists"] == "pass"
    assert t001["lens_tests_pass"] == "pass"


def test_phantom_task_is_caught():
    report, overall_pass = _report()
    by_id = {t["task_id"]: t for t in report["tasks"]}
    t002 = by_id["T002"]
    assert t002["verified_status"] == "fail"
    assert any("teardown.py" in f for f in t002["failures"])
    # One claimed-done task did not hold up, so the whole run fails.
    assert overall_pass is False
    assert report["summary"]["verdict"] == "fail"
