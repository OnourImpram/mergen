#!/usr/bin/env python3
"""EvalOps: score the verify harness over a committed corpus and record the trend.

The phantom-detection benchmark proves the harness catches planted phantoms on a fixed set of
scenarios. EvalOps turns that single measurement into an operation. It reads the labelled
corpus from eval/corpus/ (committed data, growable a scenario at a time), scores the shipped
harness over it by reusing the benchmark's own machinery, and appends the score to a trend
history. So a change anywhere in the verification surface shows up as a movement in a recorded
time series, not just a one-off pass or fail, and a regression is caught as a DROP from the
best the corpus ever scored rather than only as a breach of an absolute floor.

The gate is two-sided. The absolute floor is unchanged from the benchmark: every phantom must
be caught, no genuine task may false-alarm, and each phantom must trip its expected lens. The
trend guard adds the one check the floor cannot make, because the floor never sees corpus size:
the corpus may not shrink below the largest the history ever recorded. The floor scores a
one-scenario corpus as easily as a hundred-scenario one, so without this a contributor could
quietly delete the hard scenarios and still pass. A catch-rate drop is already a floor breach
at the floor of 1.0, so the guard does not restate it; corpus shrinkage is the genuinely
independent regression it adds.

Honest scope: this is the DETERMINISTIC surface only, the same three mechanical lenses the
benchmark runs. It does not measure a live model or a live tool chain. That live-chain eval
needs a real Claude Code binary, a model, and the network, and stays named on the roadmap, not
faked here.

Tier 0: pure standard library, deterministic (the timestamp is injected by the CLI exactly as
the ledger requires). Exit codes: 0 success or gate pass, 1 a gate failure, 2 a usage error.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
import benchmark  # noqa: E402

EVALOPS_SCHEMA = "mergen-evalops/1.0"


# --------------------------------------------------------------------------- #
# Scoring
# --------------------------------------------------------------------------- #

def score_corpus(corpus_dir: Path | None = None) -> dict[str, Any]:
    """Run the harness over the file corpus and return the benchmark's scored result.

    Reuses benchmark.run_all over the externalized corpus, so the scoring is the one the
    benchmark already proves correct. Adds corpus_size so the trend records how many scenarios
    a score was measured over, since a rate over a growing corpus is only comparable with it.
    """
    corpus = benchmark.load_corpus(corpus_dir)
    scored = benchmark.run_all(corpus)
    scored["corpus_size"] = len(corpus)
    return scored


# --------------------------------------------------------------------------- #
# Trend
# --------------------------------------------------------------------------- #

def trend_entry(scored: dict[str, Any], timestamp: str) -> dict[str, Any]:
    """Build one trend row from a scored result. Deterministic: the timestamp is passed in."""
    return {
        "schema_version": EVALOPS_SCHEMA,
        "ts": timestamp,
        "corpus_size": scored.get("corpus_size", len(scored.get("cases", []))),
        "total_phantom": scored["total_phantom"],
        "total_real": scored["total_real"],
        "phantom_catch_rate": scored["phantom_catch_rate"],
        "false_alarm_rate": scored["false_alarm_rate"],
        "expected_lens_hit_rate": scored["expected_lens_hit_rate"],
    }


def append_trend(history_path: str | Path, entry: dict[str, Any]) -> None:
    """Append one trend row to the history JSONL, creating the file and parents if absent."""
    path = Path(history_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("ab") as fh:
        fh.write((json.dumps(entry, ensure_ascii=False) + "\n").encode("utf-8"))


def load_trend(history_path: str | Path) -> list[dict[str, Any]]:
    """Read the trend history. An absent file yields an empty history, never an error."""
    path = Path(history_path)
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line:
            rows.append(json.loads(line))
    return rows


# --------------------------------------------------------------------------- #
# Gate
# --------------------------------------------------------------------------- #

def gate(scored: dict[str, Any], history: list[dict[str, Any]] | None = None) -> tuple[bool, list[str]]:
    """Return (ok, reasons). The absolute floor plus a corpus-shrink trend guard.

    The floor: every phantom caught, no genuine task false-alarmed, every phantom tripping its
    expected lens. The trend guard checks the one thing the floor cannot see: corpus size. The
    floor scores a one-scenario corpus at 1.0 as easily as a hundred-scenario one, so a
    contributor could quietly delete the hard scenarios and the floor would still pass. The
    trend guard fails when the corpus has shrunk below the largest the history ever recorded, so
    a removed scenario is a regression. This is genuinely independent of the floor, not a
    restatement of it: at the floor of 1.0 a catch-rate drop is already a floor breach, so the
    guard does not re-report it. An empty corpus is named as such rather than scored as a zero.
    A reason names each breach.
    """
    reasons: list[str] = []
    corpus_size = int(scored.get("corpus_size", len(scored.get("cases", []))))
    if corpus_size == 0:
        return False, ["corpus is empty: no scenarios were loaded from eval/corpus"]
    if scored["phantom_catch_rate"] < 1.0:
        reasons.append(
            f"phantom catch rate {scored['phantom_catch_rate']:.2f} below 1.0; "
            f"missed: {', '.join(scored['missed']) or 'none named'}"
        )
    if scored["false_alarm_rate"] > 0.0:
        reasons.append(
            f"false-alarm rate {scored['false_alarm_rate']:.2f} above 0.0; "
            f"false alarms: {', '.join(scored['false_alarm_cases']) or 'none named'}"
        )
    if scored["expected_lens_hit_rate"] < 1.0:
        reasons.append(
            f"expected-lens hit rate {scored['expected_lens_hit_rate']:.2f} below 1.0"
        )
    if history:
        best_corpus = max(int(row.get("corpus_size", 0)) for row in history)
        if corpus_size < best_corpus:
            reasons.append(
                f"corpus shrank to {corpus_size} scenarios from the best recorded {best_corpus}; "
                "a smaller corpus passes the floor trivially, so a removed scenario is a regression"
            )
    return (not reasons), reasons


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def _now() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _cmd_score(args: argparse.Namespace) -> int:
    scored = score_corpus()
    if args.json:
        print(json.dumps(scored, indent=2))
    else:
        benchmark._print_summary(scored)
        print(f"  corpus size: {scored['corpus_size']} scenarios (eval/corpus)")
    return 0


def _cmd_record(args: argparse.Namespace) -> int:
    scored = score_corpus()
    entry = trend_entry(scored, args.timestamp or _now())
    append_trend(args.history, entry)
    print(json.dumps(entry, indent=2))
    return 0


def _cmd_gate(args: argparse.Namespace) -> int:
    scored = score_corpus()
    history = load_trend(args.history) if args.history else []
    ok, reasons = gate(scored, history)
    print(f"EvalOps gate: {'PASS' if ok else 'FAIL'} "
          f"(catch {scored['phantom_catch_rate']:.2f}, "
          f"false-alarm {scored['false_alarm_rate']:.2f}, "
          f"corpus {scored['corpus_size']})")
    for reason in reasons:
        print(f"  - {reason}", file=sys.stderr)
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="evalops", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)

    p_score = sub.add_parser("score", help="score the harness over the committed corpus")
    p_score.add_argument("--json", action="store_true", help="print the scored result as JSON")
    p_score.set_defaults(func=_cmd_score)

    p_rec = sub.add_parser("record", help="score and append the result to a trend history")
    p_rec.add_argument("--history", required=True, metavar="FILE", help="the trend history JSONL")
    p_rec.add_argument("--timestamp", default=None, metavar="ISO",
                       help="ISO timestamp for the row (default: now, set explicitly in tests)")
    p_rec.set_defaults(func=_cmd_record)

    p_gate = sub.add_parser("gate", help="score and exit non-zero on a floor breach or regression")
    p_gate.add_argument("--history", default=None, metavar="FILE",
                        help="a trend history to guard against regression (optional)")
    p_gate.set_defaults(func=_cmd_gate)

    args = parser.parse_args(argv)
    result: int = args.func(args)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
