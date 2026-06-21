"""Tests for scripts/governor_adaptive.py, the Adaptive Governor.

The load-bearing tests are the two invariants. The floor-invariance test proves calibration
cannot mutate a single floor trigger, structurally and after running over an adversarial
history. The floor-dominance test proves that even the most permissive thresholds a caller
could pass cannot lower a tripped content floor. Adaptation is policy. The floor is law.
"""

from __future__ import annotations

import copy
import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, REPO / "scripts" / f"{name}.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ga = _load("governor_adaptive")
# The floor instance govern() actually touches lives in governor_adaptive's own module cache,
# loaded by its _load. Asserting against a separately loaded copy would miss a mutation, since
# each importlib spec yields a distinct module object. Use the instance under test.
gf = ga._load("governor_floor")


# --------------------------------------------------------------------------- #
# Scope classifier
# --------------------------------------------------------------------------- #

def test_classify_scope_bands():
    assert ga.classify_scope(0, 0) == "tiny"
    assert ga.classify_scope(ga.DEFAULT_THRESHOLDS["standard_files"], 0) == "standard"
    assert ga.classify_scope(0, ga.DEFAULT_THRESHOLDS["standard_lines"]) == "standard"
    assert ga.classify_scope(ga.DEFAULT_THRESHOLDS["spec_files"], 0) == "spec"
    assert ga.classify_scope(0, ga.DEFAULT_THRESHOLDS["spec_lines"]) == "spec"


def test_classify_scope_never_emits_high_trust():
    # No size, and no threshold a caller could set, lets the scope classifier emit high-trust.
    aggressive = {"standard_files": 1, "spec_files": 1, "standard_lines": 1, "spec_lines": 1}
    for files in range(0, 500, 25):
        for lines in range(0, 5000, 250):
            assert ga.classify_scope(files, lines, aggressive) in ("tiny", "standard", "spec")


def test_count_changed_lines_ignores_headers():
    diff = "--- a/x\n+++ b/x\n@@ -1 +1 @@\n-old\n+new\n+added\n unchanged\n"
    assert ga.count_changed_lines(diff) == 3


def test_count_changed_lines_counts_content_that_looks_like_a_header():
    # An added line whose own text begins with ++ shows up as "+++content" with no space. The
    # space-delimited header check must count it, not mistake it for a file header.
    diff = "--- a/x\n+++ b/x\n@@ -1 +2 @@\n-old\n+++actual content\n+normal\n"
    assert ga.count_changed_lines(diff) == 3


# --------------------------------------------------------------------------- #
# govern: the floor always dominates
# --------------------------------------------------------------------------- #

def test_govern_scope_raises_tier_on_a_wide_nonsensitive_change():
    paths = [f"docs/page{i}.md" for i in range(ga.DEFAULT_THRESHOLDS["spec_files"])]
    decision = ga.govern(paths)
    assert decision["floor_tier"] == "tiny"   # nothing sensitive
    assert decision["scope_tier"] == "spec"   # but wide
    assert decision["tier"] == "spec"


def test_govern_model_tier_raises_but_never_lowers():
    decision = ga.govern(["docs/readme.md"], model_tier="spec")
    assert decision["tier"] == "spec"          # model read carried through
    assert decision["scope_tier"] == "tiny"    # scope alone would be tiny


def test_govern_floor_forces_high_trust_regardless_of_scope():
    decision = ga.govern(["src/auth/login.py"])
    assert decision["floor_tier"] == "high-trust"
    assert decision["tier"] == "high-trust"
    assert "auth-path" in decision["triggers_matched"]


def test_govern_clamps_caller_thresholds_to_the_safe_band():
    # Thresholds passed straight to govern are clamped, so scope escalation cannot be suppressed
    # below the audited default. A wide change still reaches spec even under huge thresholds.
    permissive = {k: v * 1000 for k, v in ga.DEFAULT_THRESHOLDS.items()}
    paths = [f"docs/p{i}.md" for i in range(ga.DEFAULT_THRESHOLDS["spec_files"])]
    decision = ga.govern(paths, thresholds=permissive)
    assert decision["scope_tier"] == "spec"
    assert decision["floor_tier"] == "tiny"


def test_even_the_most_permissive_thresholds_cannot_lower_the_floor():
    # A caller passes thresholds far more permissive than calibration could ever produce.
    permissive = {k: v * 1000 for k, v in ga.DEFAULT_THRESHOLDS.items()}
    decision = ga.govern(["src/auth/login.py"], thresholds=permissive)
    assert decision["tier"] == "high-trust"
    decision2 = ga.govern([], diff_text="api_key = 'AKIAIOSFODNN7EXAMPLE'", thresholds=permissive)
    assert decision2["tier"] == "high-trust"


def test_govern_rejects_an_unknown_model_tier():
    # A bad tier is rejected with a clear message rather than crashing opaquely in combine().
    import pytest
    with pytest.raises(ValueError, match="model_tier"):
        ga.govern(["docs/x.md"], model_tier="invalid-tier")


def test_govern_rejects_a_negative_line_count():
    import pytest
    with pytest.raises(ValueError, match="non-negative"):
        ga.govern(["docs/x.md"], line_count=-1)


def test_govern_line_count_zero_disables_line_based_scope():
    # An explicit line_count overrides the diff. Zero asserts no changed lines, so a 400-line
    # diff escalates by lines normally but not when the caller overrides the count to zero.
    big = "\n".join("+line" for _ in range(400))
    assert ga.govern(["docs/x.md"], diff_text=big)["scope_tier"] == "spec"
    assert ga.govern(["docs/x.md"], diff_text=big, line_count=0)["scope_tier"] == "tiny"


# --------------------------------------------------------------------------- #
# Recording round-trip
# --------------------------------------------------------------------------- #

def test_record_and_collect_round_trip(tmp_path):
    led = tmp_path / "ledger.jsonl"
    d = ga.govern([f"src/x{i}.py" for i in range(4)])
    ga.record_decision(d, "run-1", led, "2026-06-21T00:00:00Z")
    ga.record_outcome("run-1", True, led, "2026-06-21T01:00:00Z", note="reverted")
    samples = ga.collect_samples(led)
    assert len(samples) == 1
    assert samples[0]["regressed"] is True
    assert samples[0]["file_count"] == 4
    assert samples[0]["tier"] == d["scope_tier"]


def test_collect_treats_unannotated_decision_as_not_regressed(tmp_path):
    led = tmp_path / "ledger.jsonl"
    ga.record_decision(ga.govern(["a.py"]), "run-2", led, "2026-06-21T00:00:00Z")
    samples = ga.collect_samples(led)
    assert samples[0]["regressed"] is False


def test_duplicate_run_id_contaminates_only_conservatively(tmp_path):
    # A reused run_id is a reporting error. One regressing outcome marks every decision that
    # shares the id as regressed. This only ever makes calibration MORE conservative (it can add
    # a false regressor, never remove a real one), so it cannot weaken the floor.
    led = tmp_path / "ledger.jsonl"
    ga.record_decision(ga.govern(["a.py", "b.py", "c.py", "d.py", "e.py"]), "dup", led, "2026-06-21T00:00:00Z")
    ga.record_decision(ga.govern(["x.py"]), "dup", led, "2026-06-21T00:00:00Z")
    ga.record_outcome("dup", True, led, "2026-06-21T01:00:00Z")
    samples = ga.collect_samples(led)
    assert all(s["regressed"] for s in samples)  # both inherit the one outcome


# --------------------------------------------------------------------------- #
# Calibration
# --------------------------------------------------------------------------- #

def test_calibrate_unchanged_below_minimum_samples():
    new, rationale = ga.calibrate([{"tier": "tiny", "file_count": 1, "line_count": 1, "regressed": True}])
    assert new == ga.DEFAULT_THRESHOLDS
    assert any("insufficient signal" in r for r in rationale)


def test_calibrate_tightens_standard_band_for_tiny_regressors():
    samples = [{"tier": "tiny", "file_count": 2, "line_count": 10, "regressed": True} for _ in range(6)]
    new, rationale = ga.calibrate(samples)
    assert new["standard_files"] == 2     # dropped from default 3 to the regressor size
    assert new["standard_lines"] == 10
    assert any("standard_files" in r for r in rationale)


def test_calibrate_tightens_spec_band_for_standard_regressors():
    samples = [{"tier": "standard", "file_count": 5, "line_count": 100, "regressed": True} for _ in range(6)]
    new, _ = ga.calibrate(samples)
    assert new["spec_files"] == 5
    assert new["spec_lines"] == 100


def test_calibrate_relaxes_a_clean_history_toward_default_only():
    start = {"standard_files": 1, "spec_files": 3, "standard_lines": 5, "spec_lines": 40}
    samples = [{"tier": "tiny", "file_count": 1, "line_count": 1, "regressed": False} for _ in range(8)]
    new, _ = ga.calibrate(samples, start)
    # Relaxed one step up, but never above the shipped default.
    assert new["standard_files"] == 2
    for key, value in new.items():
        assert value <= ga.DEFAULT_THRESHOLDS[key]


def test_calibrate_names_the_spec_regressor_dead_zone():
    # Regressors already at spec (or high-trust) leave no scope band to tighten. The rationale
    # must say so explicitly rather than fall into the ambiguous catch-all.
    samples = [{"tier": "spec", "file_count": 100, "line_count": 5000, "regressed": True} for _ in range(6)]
    new, rationale = ga.calibrate(samples)
    assert new == ga.DEFAULT_THRESHOLDS  # nothing tightened
    assert any("no scope band remains" in r for r in rationale)


def test_calibrate_output_is_always_within_the_safe_band():
    # An adversarial history that tries to push every band to an extreme. The clamp must hold:
    # no threshold escapes [minimum, shipped default], so the governor can never become more
    # permissive than the audited default.
    adversarial = (
        [{"tier": "tiny", "file_count": 1, "line_count": 1, "regressed": True} for _ in range(50)]
        + [{"tier": "standard", "file_count": 1, "line_count": 1, "regressed": True} for _ in range(50)]
    )
    new, _ = ga.calibrate(adversarial)
    assert set(new) == set(ga.DEFAULT_THRESHOLDS)
    for key, value in new.items():
        assert ga._MIN_THRESHOLDS[key] <= value <= ga.DEFAULT_THRESHOLDS[key]


# --------------------------------------------------------------------------- #
# The two invariants
# --------------------------------------------------------------------------- #

def test_calibration_never_mutates_the_floor_law():
    seg_before = copy.deepcopy(gf._SEGMENT_EXACT)
    glob_before = copy.deepcopy(gf._PATH_GLOBS)
    diff_before = copy.deepcopy(gf._DIFF_PATTERNS)
    compiled_before = copy.deepcopy(gf._COMPILED_DIFF)

    adversarial = [{"tier": "tiny", "file_count": 1, "line_count": 1, "regressed": True} for _ in range(50)]
    new, _ = ga.calibrate(adversarial)
    # Exercise the full path: govern under the calibrated thresholds on a sensitive change.
    ga.govern(["src/auth/login.py"], thresholds=new)

    assert gf._SEGMENT_EXACT == seg_before
    assert gf._PATH_GLOBS == glob_before
    assert gf._DIFF_PATTERNS == diff_before
    assert gf._COMPILED_DIFF == compiled_before


def test_calibrated_governor_still_floors_every_sensitive_surface():
    # Calibrate to the most permissive thresholds reachable, then prove the floor still fires
    # on every guarded surface. Adaptation cannot open a hole in the floor.
    clean = [{"tier": "tiny", "file_count": 1, "line_count": 1, "regressed": False} for _ in range(20)]
    thresholds, _ = ga.calibrate(clean)
    for sensitive in ["src/auth/x.py", "lib/secrets/y.py", "app/payment/z.py", "core/crypto/k.py"]:
        assert ga.govern([sensitive], thresholds=thresholds)["tier"] == "high-trust"


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def test_cli_calibrate_reads_ledger(tmp_path, capsys):
    led = tmp_path / "ledger.jsonl"
    for i in range(6):
        ga.record_decision(ga.govern(["a.py"]), f"run-{i}", led, "2026-06-21T00:00:00Z")
        ga.record_outcome(f"run-{i}", True, led, "2026-06-21T01:00:00Z")
    assert ga.main(["calibrate", "--ledger", str(led)]) == 0
    out = capsys.readouterr().out
    assert '"thresholds"' in out and '"samples": 6' in out


def test_cli_classify_shows_decision(capsys):
    assert ga.main(["classify", "--paths", "src/auth/login.py"]) == 0
    out = capsys.readouterr().out
    assert '"high-trust"' in out
