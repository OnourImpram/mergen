"""Tests for eval/evalops.py and the externalized corpus under eval/corpus/.

The corpus drift test is load-bearing: it proves the committed file corpus is identical to the
benchmark's embedded CASES, so externalizing the corpus to data files cannot silently diverge
from the bench. The gate tests pin the floor plus the trend-regression guard, and the trend
round-trip pins the recorded time series.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def _load(rel: str):
    path = REPO / rel
    spec = importlib.util.spec_from_file_location(path.stem, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


evalops = _load("eval/evalops.py")
benchmark = _load("eval/benchmark.py")


def _scored(catch=1.0, fa=0.0, lens=1.0, missed=None, fa_cases=None, corpus_size=8):
    return {
        "phantom_catch_rate": catch, "false_alarm_rate": fa, "expected_lens_hit_rate": lens,
        "missed": missed or [], "false_alarm_cases": fa_cases or [],
        "total_phantom": 5, "total_real": 3, "cases": [], "corpus_size": corpus_size,
    }


# --------------------------------------------------------------------------- #
# Corpus: externalized and faithful
# --------------------------------------------------------------------------- #

def test_corpus_is_identical_to_the_embedded_bench():
    # The externalized data corpus and the in-code CASES must describe the same scenarios, or
    # the bench and EvalOps would measure different things.
    assert benchmark.load_corpus() == benchmark.CASES


def test_corpus_keeps_a_floor_of_phantom_scenarios():
    # An independent floor so a corpus weakening that is mirrored in BOTH the files and CASES
    # (which the drift test alone would pass) still fails: the corpus must keep enough phantoms
    # to be a real test of detection.
    corpus = benchmark.load_corpus()
    assert sum(1 for c in corpus if c["truth"] == "phantom") >= 5
    assert sum(1 for c in corpus if c["truth"] == "real") >= 3


def test_corpus_files_are_well_formed():
    files = sorted((REPO / "eval" / "corpus").glob("*.json"))
    assert len(files) >= 5
    for path in files:
        case = json.loads(path.read_text(encoding="utf-8"))
        assert case["truth"] in ("real", "phantom")
        assert "task" in case and "name" in case
        # Every required key build_case reads must be present, so a malformed file fails the
        # gate here with a clear diagnostic rather than a KeyError deep in materialization.
        assert "create_files" in case and "test_files" in case and "expect_lens" in case


def test_load_corpus_raises_on_a_missing_directory(tmp_path):
    import pytest
    with pytest.raises(FileNotFoundError):
        benchmark.load_corpus(tmp_path / "no_such_corpus")


# --------------------------------------------------------------------------- #
# Scoring (runs the real harness over the corpus)
# --------------------------------------------------------------------------- #

def test_score_corpus_catches_every_phantom_with_no_false_alarm():
    scored = evalops.score_corpus()
    assert scored["phantom_catch_rate"] == 1.0
    assert scored["false_alarm_rate"] == 0.0
    assert scored["expected_lens_hit_rate"] == 1.0
    assert scored["corpus_size"] == len(benchmark.load_corpus())


# --------------------------------------------------------------------------- #
# Trend recording
# --------------------------------------------------------------------------- #

def test_trend_entry_is_deterministic_and_carries_the_timestamp():
    entry = evalops.trend_entry(_scored(), "2026-06-21T00:00:00Z")
    assert entry["ts"] == "2026-06-21T00:00:00Z"
    assert entry["schema_version"] == evalops.EVALOPS_SCHEMA
    assert entry["corpus_size"] == 8
    assert entry["phantom_catch_rate"] == 1.0


def test_append_and_load_trend_round_trip(tmp_path):
    hist = tmp_path / "trend.jsonl"
    evalops.append_trend(hist, evalops.trend_entry(_scored(catch=1.0), "2026-06-20T00:00:00Z"))
    evalops.append_trend(hist, evalops.trend_entry(_scored(catch=1.0), "2026-06-21T00:00:00Z"))
    rows = evalops.load_trend(hist)
    assert len(rows) == 2
    assert [r["ts"] for r in rows] == ["2026-06-20T00:00:00Z", "2026-06-21T00:00:00Z"]


def test_load_trend_absent_is_empty(tmp_path):
    assert evalops.load_trend(tmp_path / "nope.jsonl") == []


# --------------------------------------------------------------------------- #
# Gate
# --------------------------------------------------------------------------- #

def test_gate_passes_a_clean_score():
    ok, reasons = evalops.gate(_scored(), [])
    assert ok and reasons == []


def test_gate_fails_a_missed_phantom():
    ok, reasons = evalops.gate(_scored(catch=0.5, missed=["phantom_x"]), [])
    assert not ok
    assert any("catch rate" in r and "phantom_x" in r for r in reasons)


def test_gate_fails_a_false_alarm():
    ok, reasons = evalops.gate(_scored(fa=0.33, fa_cases=["real_y"]), [])
    assert not ok
    assert any("false-alarm" in r for r in reasons)


def test_gate_flags_a_corpus_that_shrank_below_the_recorded_best():
    # The genuinely independent trend guard: the floor passes a shrunken corpus trivially, so a
    # removed scenario is caught here, not by the floor.
    history = [{"corpus_size": 8, "phantom_catch_rate": 1.0}]
    ok, reasons = evalops.gate(_scored(catch=1.0, corpus_size=5), history)
    assert not ok
    assert any("corpus shrank" in r for r in reasons)


def test_gate_does_not_flag_a_corpus_that_held_its_size():
    ok, reasons = evalops.gate(_scored(corpus_size=8), [{"corpus_size": 8, "phantom_catch_rate": 1.0}])
    assert ok and reasons == []


def test_gate_names_an_empty_corpus_distinctly():
    ok, reasons = evalops.gate(_scored(catch=0.0, lens=0.0, corpus_size=0), [])
    assert not ok
    assert reasons == ["corpus is empty: no scenarios were loaded from eval/corpus"]


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def test_cli_score_and_gate_pass():
    assert evalops.main(["score"]) == 0
    assert evalops.main(["gate"]) == 0


def test_cli_record_writes_a_trend_row(tmp_path):
    hist = tmp_path / "trend.jsonl"
    rc = evalops.main(["record", "--history", str(hist), "--timestamp", "2026-06-21T00:00:00Z"])
    assert rc == 0
    rows = evalops.load_trend(hist)
    assert len(rows) == 1 and rows[0]["ts"] == "2026-06-21T00:00:00Z"
