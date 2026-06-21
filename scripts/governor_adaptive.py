#!/usr/bin/env python3
"""mergen calibrate: the Adaptive Governor, where the floor is law and adaptation is policy.

The deterministic floor in governor_floor.py classifies content sensitivity. A change that
touches auth, secrets, payments, or any other guarded surface is forced to high-trust, and
that decision can never be lowered. The floor answers tiny versus high-trust. It says nothing
about the two review tiers between them, standard and spec, which a model assigns and which
therefore have no deterministic, model-free basis.

This module adds that basis without touching the floor. It classifies the review SCOPE of a
change by its size and breadth, a deterministic signal: a wide change deserves at least
standard or spec review even when no sensitive surface is touched. The scope tier is a lower
bound exactly like the floor. govern() takes the highest of the model tier, the scope tier,
and the content floor, so every input can only ever RAISE scrutiny, never lower it.

Calibration tunes the scope thresholds from recorded outcomes. It reads the governor's own
past decisions and whether each later regressed, then tightens a band that let through a
change that regressed. Two properties make this safe to run unattended. First, the floor data
is never read-write here. Only the floor's combine() and tier order are imported, so
calibration structurally cannot mutate a single trigger. Second, a calibrated threshold is
clamped to the band [minimum, shipped default], so the adaptive governor is never more
permissive than the audited default and never weaker than the floor. The floor is law.
Adaptation is policy, and policy is bounded.

Tier 0: pure standard library, deterministic, no network, no model in the loop.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

_MODS: dict[str, Any] = {}


def _load(name: str) -> Any:
    """Load a sibling scripts/<name>.py by path and cache it (scripts/ not a package)."""
    if name in _MODS:
        return _MODS[name]
    repo = Path(__file__).resolve().parent
    spec = importlib.util.spec_from_file_location(name, repo / f"{name}.py")
    if spec is None or spec.loader is None:  # pragma: no cover - import wiring
        raise ImportError(f"cannot load {name}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    _MODS[name] = mod
    return mod


# The shipped scope thresholds. A change reaching a files or lines threshold lands at that
# review tier as a lower bound. These are the audited defaults: calibration may tighten below
# them but is clamped never to relax above them, so the adaptive governor is never more
# permissive than what shipped.
DEFAULT_THRESHOLDS: dict[str, int] = {
    "standard_files": 3,     # this many changed files reaches at least standard
    "spec_files": 12,        # this many changed files reaches at least spec
    "standard_lines": 40,    # this many changed diff lines reaches at least standard
    "spec_lines": 300,       # this many changed diff lines reaches at least spec
}

# A calibrated threshold may tighten down to this floor but never below it, so a minimum of
# review scope always survives even an aggressive regression history.
_MIN_THRESHOLDS: dict[str, int] = {
    "standard_files": 1,
    "spec_files": 3,
    "standard_lines": 5,
    "spec_lines": 40,
}

# Calibration needs at least this many recorded decisions before it tunes, so it never overfits
# to noise. Below the bar the thresholds are returned unchanged.
_MIN_SAMPLES = 5


def _resolve_thresholds(thresholds: dict[str, int] | None) -> dict[str, int]:
    """Overlay caller thresholds on the defaults, clamped to the safe band.

    Every accepted value passes through _clamp, so a threshold can never exceed the shipped
    default (more permissive) or fall below its minimum. This holds for EVERY path that resolves
    thresholds, govern and classify_scope included, not only calibrate, so a caller, a CLI flag,
    or an externally supplied thresholds file can raise scrutiny but can never make the adaptive
    governor more permissive than the audited default. Unknown or non-integer keys are ignored.
    """
    resolved = dict(DEFAULT_THRESHOLDS)
    if thresholds:
        for key, value in thresholds.items():
            if key in resolved and isinstance(value, int) and not isinstance(value, bool):
                resolved[key] = _clamp(key, value)
    return resolved


def _clamp(key: str, value: int) -> int:
    """Clamp a threshold to its [minimum, shipped default] band. This is the load-bearing
    safety bound: every calibrated threshold passes through here, so none can ever exceed the
    audited default (more permissive) or fall below its minimum (no review scope at all)."""
    return max(_MIN_THRESHOLDS[key], min(DEFAULT_THRESHOLDS[key], value))


def classify_scope(file_count: int, line_count: int, thresholds: dict[str, int] | None = None) -> str:
    """Classify the review scope tier from change size. Never returns high-trust.

    Returns spec when the change is wide (files or lines reach the spec threshold), standard
    when it reaches the standard threshold, and tiny otherwise. This is a lower bound on the
    review tier, combined with the content floor by govern(). High-trust is the floor's verdict
    alone, never the scope classifier's, so a size signal can never stand in for a content one.
    """
    resolved = _resolve_thresholds(thresholds)
    if file_count >= resolved["spec_files"] or line_count >= resolved["spec_lines"]:
        return "spec"
    if file_count >= resolved["standard_files"] or line_count >= resolved["standard_lines"]:
        return "standard"
    return "tiny"


def count_changed_lines(diff_text: str) -> int:
    """Count added and removed lines in a unified diff, ignoring the +++/--- file headers.

    A git file header is always "+++ b/path" or "--- a/path" with a space after the marker, so
    requiring that space lets an added content line whose own text begins with ++ or -- (for
    example a "++debug" line, which appears in the diff as "+++debug") still be counted rather
    than mistaken for a header.
    """
    total = 0
    for line in diff_text.splitlines():
        if line.startswith("+++ ") or line.startswith("--- ") or line in ("+++", "---"):
            continue
        if line.startswith("+") or line.startswith("-"):
            total += 1
    return total


def govern(
    changed_paths: list[str],
    diff_text: str = "",
    thresholds: dict[str, int] | None = None,
    model_tier: str = "tiny",
    line_count: int | None = None,
) -> dict[str, Any]:
    """Return the governed decision: the highest of the model, scope, and content-floor tiers.

    The content floor here is the BUILT-IN path and diff classifier (governor_floor.classify_floor)
    only. It forces high-trust on a guarded surface and can never be lowered. The scope tier is a
    deterministic lower bound from change size. The model tier, when supplied, is the model's own
    read. govern() takes the maximum of the three via the floor's own combine(), so each input can
    only RAISE the tier. Even the most permissive thresholds a caller could pass cannot lower a
    tripped floor, because the floor enters the maximum independently of the scope thresholds.

    govern() does NOT apply the per-project domain overlay (project_config.apply_overlay, the
    clinical floor-all and protected-path layer). That overlay is a separate layer the governor
    CLI composes on top with --config, and it too can only raise the tier. A programmatic caller
    that needs the domain overlay composes apply_overlay itself, exactly as governor_floor.main
    does; govern() is the built-in content floor plus the scope tier, not the project overlay.

    Thresholds passed here are clamped to the safe band by _resolve_thresholds, so even a caller
    that supplies raw thresholds (or a CLI thresholds file) can raise scrutiny but can never make
    the scope tier more permissive than the audited default. The scope tier is always a lower
    bound and can never lower the content floor. An explicit line_count overrides the count
    computed from the diff: passing 0 asserts a change with no added or removed lines and so
    disables line-based scope escalation. A negative line_count is rejected, and an unknown
    model_tier is rejected, rather than failing opaquely.
    """
    floor_mod = _load("governor_floor")
    if model_tier not in floor_mod._TIERS:
        raise ValueError(
            f"unknown model_tier {model_tier!r}; valid tiers are {floor_mod._TIERS}"
        )
    if line_count is not None and line_count < 0:
        raise ValueError(f"line_count must be non-negative, got {line_count}")
    floor = floor_mod.classify_floor(changed_paths, diff_text)
    lines = line_count if line_count is not None else count_changed_lines(diff_text)
    scope_tier = classify_scope(len(changed_paths), lines, thresholds)
    tier = floor_mod.combine(floor_mod.combine(model_tier, scope_tier), floor["tier"])
    return {
        "tier": tier,
        "triggers_matched": floor["triggers_matched"],
        "floor_tier": floor["tier"],
        "scope_tier": scope_tier,
        "model_tier": model_tier,
        "file_count": len(changed_paths),
        "line_count": lines,
    }


# --------------------------------------------------------------------------- #
# Recording and calibration
# --------------------------------------------------------------------------- #

def record_decision(decision: dict[str, Any], run_id: str, path: str | Path, timestamp: str) -> None:
    """Append a governor-decision event to the ledger, the trust graph's event source.

    The run_id must be unique per decision. collect_samples joins outcomes to decisions by
    run_id, so a reused run_id would let one outcome annotate several decisions. That can only
    make calibration more conservative, never more permissive, but it is still a reporting error.
    """
    ledger = _load("ledger")
    ledger.append_event({**decision, "run_id": run_id}, path, "governor-decision", timestamp)


def record_outcome(
    run_id: str,
    regressed: bool,
    path: str | Path,
    timestamp: str,
    note: str = "",
) -> None:
    """Append a governor-outcome event that annotates a recorded decision by run_id.

    The outcome is the deterministic, model-free signal calibration learns from: did a change
    governed at a given tier later regress verification. Continuous Verification and Replay
    produce that signal already; this records it back against the decision so calibration can
    read decision and outcome as one history.
    """
    ledger = _load("ledger")
    ledger.append_event(
        {"run_id": run_id, "regressed": bool(regressed), "note": note},
        path,
        "governor-outcome",
        timestamp,
    )


def _as_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def collect_samples(path: str | Path) -> list[dict[str, Any]]:
    """Join governor-decision and governor-outcome events by run_id into calibration samples.

    A sample is {tier, file_count, line_count, regressed}, where tier is the scope tier the
    decision was classified at. A decision with no recorded outcome is treated as not regressed,
    so an unannotated history never fabricates a regression signal. Reads the ledger, the single
    event source.
    """
    ledger = _load("ledger")
    events = ledger.read_events(path)
    outcomes: dict[str, bool] = {}
    for event in events:
        if event.get("kind") != "governor-outcome":
            continue
        payload = event.get("payload") or {}
        run_id = payload.get("run_id")
        if isinstance(run_id, str):
            outcomes[run_id] = bool(payload.get("regressed")) or outcomes.get(run_id, False)
    samples: list[dict[str, Any]] = []
    for event in events:
        if event.get("kind") != "governor-decision":
            continue
        payload = event.get("payload") or {}
        run_id = payload.get("run_id")
        regressed = outcomes.get(run_id, False) if isinstance(run_id, str) else False
        samples.append({
            "tier": str(payload.get("scope_tier") or payload.get("tier") or "tiny"),
            "file_count": _as_int(payload.get("file_count")),
            "line_count": _as_int(payload.get("line_count")),
            "regressed": regressed,
        })
    return samples


def calibrate(
    samples: list[dict[str, Any]],
    thresholds: dict[str, int] | None = None,
) -> tuple[dict[str, int], list[str]]:
    """Compute scope thresholds from recorded samples. Deterministic and bounded.

    The rule is safety-biased and outcome-driven. A change that regressed while being reviewed
    only as tiny means the standard band was too permissive for a change that size, so the
    standard thresholds drop to the regressing change's own size, escalating a similar future
    change. A regressor reviewed only as standard tightens the spec band the same way. A history
    with no regressions and enough evidence relaxes the thresholds one step toward, but never
    above, the shipped default. Relaxation moves one unit per clean call per key, so a key with a
    wide band (spec_lines spans 40 to 300) returns to its default far more slowly than a narrow
    one (standard_files spans 1 to 3): the bias is deliberately toward keeping scrutiny. Every
    written threshold passes through _clamp, so the result is never more permissive than the
    audited default and never weaker than the floor, which govern() enforces separately. Returns
    the new thresholds and a human-readable rationale.

    With fewer than the minimum samples the thresholds are returned unchanged, with a rationale
    saying so, rather than tuning on noise.
    """
    current = _resolve_thresholds(thresholds)
    rationale: list[str] = []
    if len(samples) < _MIN_SAMPLES:
        rationale.append(
            f"insufficient signal: {len(samples)} samples, need {_MIN_SAMPLES}. Thresholds unchanged."
        )
        return dict(current), rationale

    new = dict(current)

    # Tighten the standard band to catch regressors that slipped in below standard (tiny).
    tiny_regressors = [s for s in samples if s["regressed"] and s["tier"] == "tiny"]
    if tiny_regressors:
        min_files = min((s["file_count"] for s in tiny_regressors if s["file_count"] > 0), default=0)
        min_lines = min((s["line_count"] for s in tiny_regressors if s["line_count"] > 0), default=0)
        if min_files:
            new["standard_files"] = _clamp("standard_files", min(new["standard_files"], min_files))
            rationale.append(
                f"{len(tiny_regressors)} regressor(s) reviewed only as tiny; "
                f"standard_files -> {new['standard_files']} to escalate a {min_files}-file change."
            )
        if min_lines:
            new["standard_lines"] = _clamp("standard_lines", min(new["standard_lines"], min_lines))
            rationale.append(
                f"standard_lines -> {new['standard_lines']} to escalate a {min_lines}-line change."
            )

    # Tighten the spec band to catch regressors that slipped in below spec (standard).
    standard_regressors = [s for s in samples if s["regressed"] and s["tier"] == "standard"]
    if standard_regressors:
        min_files = min((s["file_count"] for s in standard_regressors if s["file_count"] > 0), default=0)
        min_lines = min((s["line_count"] for s in standard_regressors if s["line_count"] > 0), default=0)
        if min_files:
            new["spec_files"] = _clamp("spec_files", min(new["spec_files"], min_files))
            rationale.append(
                f"{len(standard_regressors)} regressor(s) reviewed only as standard; "
                f"spec_files -> {new['spec_files']} to escalate a {min_files}-file change."
            )
        if min_lines:
            new["spec_lines"] = _clamp("spec_lines", min(new["spec_lines"], min_lines))
            rationale.append(
                f"spec_lines -> {new['spec_lines']} to escalate a {min_lines}-line change."
            )

    if not any(s["regressed"] for s in samples):
        for key in new:
            if new[key] < DEFAULT_THRESHOLDS[key]:
                new[key] = _clamp(key, new[key] + 1)
        rationale.append(
            f"no regressions across {len(samples)} samples; thresholds relaxed one step toward the default."
        )

    # A regressor already reviewed at spec or high-trust has no scope band left to tighten:
    # spec is the highest scope tier, and high-trust is the floor's own verdict. Name that dead
    # zone explicitly rather than letting it fall into the ambiguous catch-all below.
    spec_regressors = [s for s in samples if s["regressed"] and s["tier"] in ("spec", "high-trust")]
    if spec_regressors and not tiny_regressors and not standard_regressors:
        rationale.append(
            f"{len(spec_regressors)} regressor(s) were already at spec or high-trust; no scope "
            "band remains to tighten. Raise the spec threshold by hand if scrutiny must increase."
        )

    if not rationale:
        rationale.append(
            f"{len(samples)} samples, regressions present but not below a band edge; thresholds unchanged."
        )
    return new, rationale


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def _cmd_classify(argv: list[str]) -> int:
    tiers = _load("governor_floor")._TIERS
    parser = argparse.ArgumentParser(
        prog="mergen calibrate classify",
        description="Show the governed decision (floor + scope) for a change.",
    )
    parser.add_argument("--paths", nargs="*", default=[], metavar="PATH",
                        help="Changed file paths.")
    parser.add_argument("--diff-file", default=None, metavar="FILE",
                        help="A file containing the unified diff to size.")
    parser.add_argument("--thresholds-file", default=None, metavar="FILE",
                        help="A JSON file of scope thresholds to apply.")
    parser.add_argument("--model-tier", default="tiny", choices=tiers,
                        help="The model's own tier, raised by the scope and floor tiers.")
    args = parser.parse_args(argv)

    diff_text = Path(args.diff_file).read_text(encoding="utf-8") if args.diff_file else ""
    thresholds = None
    if args.thresholds_file:
        thresholds = json.loads(Path(args.thresholds_file).read_text(encoding="utf-8"))
    decision = govern(args.paths, diff_text, thresholds, args.model_tier)
    print(json.dumps(decision, indent=2))
    return 0


def _cmd_calibrate(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="mergen calibrate",
        description="Compute scope thresholds from the recorded governor history.",
    )
    parser.add_argument("--ledger", required=True, metavar="FILE",
                        help="The JSONL ledger of governor-decision and governor-outcome events.")
    parser.add_argument("--thresholds-file", default=None, metavar="FILE",
                        help="A JSON file of current thresholds to start from.")
    args = parser.parse_args(argv)

    thresholds = None
    if args.thresholds_file:
        thresholds = json.loads(Path(args.thresholds_file).read_text(encoding="utf-8"))
    samples = collect_samples(args.ledger)
    new, rationale = calibrate(samples, thresholds)
    print(json.dumps({"thresholds": new, "rationale": rationale, "samples": len(samples)}, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    """CLI entry. Default action is calibrate. classify shows a single decision."""
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] == "classify":
        return _cmd_classify(args[1:])
    if args and args[0] == "calibrate":
        args = args[1:]
    return _cmd_calibrate(args)


if __name__ == "__main__":
    raise SystemExit(main())
