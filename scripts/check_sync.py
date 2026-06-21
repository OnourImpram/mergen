#!/usr/bin/env python3
"""Drift gate: assert the committed renderer output matches the single source.

mergen authors everything once in `core/` and renders it into distribution
shells (see `core/CONVENTIONS.md`). The native shell is rendered on install and
never committed, so it cannot drift. The spec-kit shell under `dist/speckit/`
IS committed (it is the shippable adapter), so it can fall out of sync when a
`core/commands/*.md` file changes and nobody re-runs `build_speckit.py`. This
script is the guard against that, modeled on ponytail's `check-rule-copies.js`
single-source drift gate (MIT, attributed in `ATTRIBUTION.md`).

Checks:
  1. spec-kit drift: re-render `dist/speckit/` from `core/` into a temp dir and
     compare the generated `preset/` and `extensions/` trees byte-for-byte
     against what is committed. Any missing, extra, or differing file fails.
  2. cross-agent self-consistency: render the lazy ladder via
     `dist/agents/build_agents.py` and assert the output embeds the canonical
     ladder rungs and leaks no Claude-Code-specific lifecycle text.

Exit 0 when in sync, 1 when drift or inconsistency is found. Stdlib only.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import tempfile
from pathlib import Path
from types import ModuleType

REPO = Path(__file__).resolve().parents[1]
SPECKIT_SRC = REPO / "dist" / "speckit" / "build_speckit.py"
AGENTS_SRC = REPO / "dist" / "agents" / "build_agents.py"
COMMITTED_SPECKIT = REPO / "dist" / "speckit"

# The six rung lead-ins that must survive into every cross-agent rule file.
LADDER_RUNGS = [
    "need to be built at all",
    "standard library",
    "native platform feature",
    "already-installed dependency",
    "one line",
    "minimum code that works",
]


def _load(path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(path.stem, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load module from {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _rel_files(root: Path) -> set[str]:
    return {str(p.relative_to(root)).replace("\\", "/")
            for p in root.rglob("*") if p.is_file()}


def check_speckit_drift() -> list[str]:
    """Re-render speckit into a temp dir, then compare generated trees to committed."""
    problems: list[str] = []
    build_speckit = _load(SPECKIT_SRC)
    with tempfile.TemporaryDirectory() as tmp:
        tmp_out = Path(tmp)
        with contextlib.redirect_stdout(io.StringIO()):
            rc = build_speckit.cmd_build(tmp_out, dry_run=False)
        if rc != 0:
            return [f"build_speckit.py returned {rc}, cannot compare"]
        for sub in ("preset", "extensions"):
            committed = COMMITTED_SPECKIT / sub
            fresh = tmp_out / sub
            if not committed.is_dir():
                problems.append(f"committed dist/speckit/{sub}/ is missing")
                continue
            committed_set = _rel_files(committed)
            fresh_set = _rel_files(fresh)
            for missing in sorted(fresh_set - committed_set):
                problems.append(f"dist/speckit/{sub}/{missing}: not committed (run build_speckit.py)")
            for extra in sorted(committed_set - fresh_set):
                problems.append(f"dist/speckit/{sub}/{extra}: committed but no longer rendered")
            for rel in sorted(committed_set & fresh_set):
                if (committed / rel).read_bytes() != (fresh / rel).read_bytes():
                    problems.append(f"dist/speckit/{sub}/{rel}: stale (differs from a fresh render)")
    return problems


def check_agents_consistency() -> list[str]:
    """Render the cross-agent rules and assert they embed the canonical ladder."""
    if not AGENTS_SRC.is_file():
        return []  # cross-agent renderer is optional
    problems: list[str] = []
    build_agents = _load(AGENTS_SRC)
    ladder_text = build_agents.LADDER.read_text(encoding="utf-8")
    targets = build_agents.render_targets(ladder_text)
    agents_md = targets.get("AGENTS.md", "")
    for rung in LADDER_RUNGS:
        if rung not in agents_md:
            problems.append(f"AGENTS.md render is missing ladder rung: '{rung}'")
    # The discipline body must not instruct the agent to run Claude-Code-only
    # commands. The honest scope note (rendered separately) is allowed to name
    # the excluded `/mergen-*` suite, so check the discipline body, not the
    # whole file. Both the hyphen invocation and a legacy dot count as a leak.
    discipline = build_agents.portable_discipline(ladder_text)
    if "/mergen-" in discipline or "/mergen." in discipline:
        problems.append("portable discipline leaks a Claude-Code-specific /mergen- reference")
    if "How the lifecycle uses the ladder" in discipline:
        problems.append("portable discipline leaks the Claude-Code-specific lifecycle section")
    return problems


def main() -> int:
    speckit_problems = check_speckit_drift()
    agent_problems = check_agents_consistency()
    if speckit_problems or agent_problems:
        print("check_sync: DRIFT DETECTED")
        for p in speckit_problems + agent_problems:
            print(f"  - {p}")
        if speckit_problems:
            print("\nRegenerate speckit with: python dist/speckit/build_speckit.py")
        if agent_problems:
            print("Re-render agents with: python dist/agents/build_agents.py <project>")
        return 1
    print("check_sync: OK (dist/speckit in sync with core/, cross-agent render consistent)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
