"""Tests for the deterministic phantom-detection benchmark (eval/benchmark.py).

The corpus is run once per module (it shells pytest for the test-lens cases), and
the scored result is asserted: the real harness catches every planted phantom by
its expected lens, never false-alarms a genuine completion, and the bare-checkbox
baseline catches nothing. The gate's failure branch is exercised with a synthetic
regressed score so it stays fast.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "eval"))
import benchmark  # noqa: E402


@pytest.fixture(scope="module")
def scored():
    return benchmark.run_all()


def test_phantom_catch_rate_is_perfect(scored):
    assert scored["phantom_catch_rate"] == 1.0
    assert scored["caught"] == scored["total_phantom"] == 5


def test_no_false_alarms_on_genuine_completions(scored):
    assert scored["false_alarm_rate"] == 0.0
    assert scored["false_alarm_cases"] == []
    assert scored["total_real"] == 3


def test_baseline_checkbox_catches_no_phantoms(scored):
    # The bare spec-kit baseline re-checks nothing, so it cannot catch a phantom.
    assert scored["baseline_catch_rate"] == 0.0


def test_every_phantom_caught_by_its_expected_lens(scored):
    assert scored["expected_lens_hit_rate"] == 1.0


def test_no_phantom_is_missed(scored):
    assert scored["missed"] == []


def test_gitignored_file_is_caught_only_by_git_consistent(scored):
    case = next(c for c in scored["cases"] if c["name"] == "phantom_gitignored_file")
    assert case["verdict"] == "fail"
    assert case["failing_lenses"] == ["lens_git_consistent"]


def test_gate_passes_on_healthy_harness(scored):
    assert benchmark.run_gate(scored) == 0


def test_gate_fails_when_a_phantom_is_missed():
    regressed = {
        "phantom_catch_rate": 0.8,
        "false_alarm_rate": 0.0,
        "expected_lens_hit_rate": 1.0,
    }
    assert benchmark.run_gate(regressed) == 1


def test_gate_fails_on_a_false_alarm():
    regressed = {
        "phantom_catch_rate": 1.0,
        "false_alarm_rate": 0.34,
        "expected_lens_hit_rate": 1.0,
    }
    assert benchmark.run_gate(regressed) == 1
