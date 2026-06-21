"""Tests for eval/live_chain_eval.py, the live-chain eval skeleton.

The load-bearing property is the honest boundary: the skeleton states the protocol and refuses to
emit any number without a live runner, so it can never fabricate a measurement.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def _load():
    spec = importlib.util.spec_from_file_location("live_chain_eval", REPO / "eval" / "live_chain_eval.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


lce = _load()


def test_protocol_states_the_two_live_only_metrics_without_numbers():
    proto = lce.protocol()
    ids = {m["id"] for m in proto["metrics"]}
    assert ids == {"parallel_speedup", "over_build"}
    # No metric carries a measured value: the protocol is method only.
    blob = json.dumps(proto)
    assert "wall_clock_s" in blob  # named in the runner contract, as a key to fill
    for metric in proto["metrics"]:
        assert "value" not in metric and "result" not in metric


def test_run_refuses_without_a_live_runner():
    import pytest
    with pytest.raises(RuntimeError, match="no live runner"):
        lce.run([{"id": "s1", "arms": ["parallel", "serial"]}], None)


def test_run_uses_a_supplied_runner():
    # With a runner (the operator's bridge), the contract is exercised. The runner here is a stub,
    # proving the shape, not a measurement.
    def runner(scenario, arm):
        return {"wall_clock_s": 1.0, "files_written": 1, "lines_written": 10, "passed": True}

    out = lce.run([{"id": "s1", "arms": ["parallel", "serial"]}], runner)
    assert len(out["results"]) == 2
    assert {r["arm"] for r in out["results"]} == {"parallel", "serial"}


def test_cli_protocol_prints_json():
    assert lce.main(["protocol"]) == 0


def test_cli_run_refuses_and_exits_nonzero():
    # The run path has no bundled runner and must never look like a passing measurement.
    assert lce.main(["run"]) == 2
