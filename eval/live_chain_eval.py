#!/usr/bin/env python3
"""Live-chain eval skeleton: the protocol for the measurements only a live tool chain can make.

The deterministic benchmark (eval/benchmark.py) and EvalOps (eval/evalops.py) measure the verify
harness over a fixed corpus with no model in the loop. Two of the four north-star metrics cannot
be measured that way, because they are properties of a real agent running a real tool chain:

  metric 2  parallel speedup: how much faster the wave-parallel implement pipeline completes a
            feature than a serial baseline, on the same task graph.
  metric 4  over-build: how much code an agent writes beyond what the spec required, the lazy
            ladder's restraint discipline made measurable.

Measuring either needs a real Claude Code binary, a live model, and the network. This module does
NOT measure them. It is a skeleton: it states the protocol as structured data, and it refuses to
emit any metric number on its own, because a number produced without the live run would be
fabricated. The real run is the operator's live-environment job, named here rather than faked.

How a real run plugs in: the operator supplies a runner, a callable (or a subprocess command) that
executes one scenario against the live tool chain and returns its measured outcome. This module
defines the scenario shape and the metric definitions the runner must fill; it provides no runner,
so an autonomous invocation produces the protocol, never a result. See docs/LIVE-CHAIN-EVAL.md.

Tier 0 by construction: with no runner there is no network and no model here. The honest boundary
is the point: this file holds the protocol, not the numbers.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Callable

_LIVE_ENV = "MERGEN_LIVE_EVAL"


def protocol() -> dict[str, Any]:
    """Return the live-chain eval protocol as structured data. No numbers, only the method."""
    return {
        "schema": "mergen-live-chain-eval/1.0",
        "honest_scope": (
            "These metrics require a live Claude Code binary, a model, and the network. This "
            "module measures none of them. It states the protocol and refuses to emit a number "
            "without a real run, which is the operator's live-environment job."
        ),
        "metrics": [
            {
                "id": "parallel_speedup",
                "north_star": 2,
                "definition": (
                    "wall-clock to complete a feature with the wave-parallel implement pipeline, "
                    "divided by the wall-clock of a serial baseline on the same task graph"
                ),
                "method": (
                    "run the same task graph twice on the live tool chain, once parallel once "
                    "serial, hold the model and the graph fixed, report the ratio with both raw "
                    "times so the number is auditable"
                ),
                "requires": ["live Claude Code", "live model", "network"],
            },
            {
                "id": "over_build",
                "north_star": 4,
                "definition": (
                    "lines of code or files an agent produced beyond what the spec and tasks "
                    "required, normalized by the required size"
                ),
                "method": (
                    "run a labelled spec whose required surface is known, diff the agent's output "
                    "against the required surface, count the surplus, report against the baseline "
                    "agent without the lazy-ladder discipline"
                ),
                "requires": ["live Claude Code", "live model", "network", "labelled spec corpus"],
            },
        ],
        "scenario_shape": {
            "id": "a stable scenario name",
            "spec": "the spec or task graph the agent is given",
            "required_surface": "the files and tests the spec genuinely requires (the over-build baseline)",
            "arms": ["parallel", "serial", "baseline-no-discipline"],
        },
        "runner_contract": (
            "the operator supplies runner(scenario, arm) -> {wall_clock_s, files_written, "
            "lines_written, passed}; this module provides no runner, so it cannot fabricate one"
        ),
    }


def run(scenarios: list[dict[str, Any]], runner: Callable[[dict[str, Any], str], dict[str, Any]] | None) -> dict[str, Any]:
    """Run the protocol against a live runner. Without a runner it refuses, it does not fake.

    runner is the operator's bridge to the live tool chain. When it is None, this raises rather
    than returning a result, because the only honest output with no live run is no number at all.
    """
    if runner is None:
        raise RuntimeError(
            "no live runner supplied: the live-chain eval cannot produce a number autonomously. "
            "Wire a runner that executes each scenario arm against the real tool chain. See "
            "docs/LIVE-CHAIN-EVAL.md."
        )
    results: list[dict[str, Any]] = []
    for scenario in scenarios:
        for arm in scenario.get("arms", []):
            measured = runner(scenario, arm)
            results.append({"scenario": scenario.get("id"), "arm": arm, "measured": measured})
    return {"schema": "mergen-live-chain-eval-result/1.0", "results": results}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="live-chain-eval", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("protocol", help="print the eval protocol as JSON (no numbers, the method only)")
    sub.add_parser("run", help="refuses without a live runner, it never fabricates a number")
    args = parser.parse_args(argv)

    if args.command == "protocol":
        print(json.dumps(protocol(), indent=2))
        return 0
    # The run path has no bundled runner. It states why it cannot proceed and exits non-zero, so
    # an automated caller can never mistake silence for a passing measurement.
    print("live-chain eval needs a live runner and a real tool chain; none is bundled. This "
          "skeleton refuses to emit a fabricated number. See docs/LIVE-CHAIN-EVAL.md for how to "
          "wire a runner in a live environment.", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
