#!/usr/bin/env python3
"""Cross-agent (passive-rule) renderer for mergen's minimalism discipline.

mergen's full value is the Workflow-orchestrated SDD engine, which is Claude
Code specific and does not port. But ONE part of it is portable to any coding
agent that reads a passive rule file: the lazy ladder (`core/lazy-ladder.md`).
This renderer turns that single source into the rule-file format each agent
expects, so the "think exhaustively, build minimally" discipline travels even
where the orchestration cannot.

Honest scope: this ports the minimalism discipline ONLY. It does not port, and
does not claim to port, the `/mergen.*` command suite, the verify gate, or
the wave-parallel implement pipeline. Each rendered file states this.

Targets (each agent's documented passive-rule location):

  AGENTS.md                         generic AGENTS.md convention (root)
  .cursor/rules/lazy-ladder.mdc     Cursor project rules (MDC, alwaysApply)
  .windsurf/rules/lazy-ladder.md    Windsurf workspace rules
  .clinerules/lazy-ladder.md        Cline rules
  .github/copilot-instructions.md   GitHub Copilot repository instructions
  .kiro/steering/lazy-ladder.md     Kiro steering (inclusion: always)

Single source -> many shells (see core/CONVENTIONS.md). The discipline is
authored once in core/lazy-ladder.md, and this renderer reads it at build time so
the rendered rules can never drift from the source. `scripts/check_sync.py`
asserts the rendered output still embeds the canonical ladder.

Cross-agent rendering pattern adapted from ponytail (DietrichGebert/ponytail,
MIT, attributed in ATTRIBUTION.md).

Stdlib only.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
LADDER = REPO / "core" / "lazy-ladder.md"

PROVENANCE = (
    "<!-- Generated from mergen core/lazy-ladder.md by dist/agents/build_agents.py. "
    "Do not edit here. Edit the source and re-render. -->"
)

SCOPE_NOTE = (
    "> This file ports mergen's minimalism discipline only. mergen's "
    "Workflow-orchestrated spec-driven-development engine (the `/mergen.*` "
    "commands, the adversarial verify gate, the wave-parallel implement pipeline) "
    "is Claude Code specific and is not included here."
)


def portable_discipline(ladder_text: str) -> str:
    """Return the agent-portable body of the lazy ladder.

    Drops the Claude-specific "How the lifecycle uses the ladder" section and
    rewrites the one sentence that references the `/mergen.debt` command, so
    a non-Claude agent gets clean, applicable guidance.
    """
    body = ladder_text
    # Drop the Claude-Code-specific lifecycle section and anything after it.
    marker = "## How the lifecycle uses the ladder"
    idx = body.find(marker)
    if idx != -1:
        body = body[:idx]
    # Rewrite any sentence that references a `/mergen.<cmd>` command into a
    # portable instruction (robust to wording changes in the source).
    body = re.sub(
        r"`/mergen\.\w+`[^\n]*",
        "Track these comments so deferred work stays visible.",
        body,
    )
    return body.rstrip() + "\n"


def render_targets(ladder_text: str) -> dict[str, str]:
    """Return {relative_path: file_content} for every agent target."""
    discipline = portable_discipline(ladder_text)
    plain = f"{PROVENANCE}\n\n{discipline}\n{SCOPE_NOTE}\n"

    cursor = (
        "---\n"
        'description: "mergen lazy ladder: reason exhaustively, build the minimum that works."\n'
        "alwaysApply: true\n"
        "---\n\n"
        f"{plain}"
    )
    kiro = "---\ninclusion: always\n---\n\n" + plain

    return {
        "AGENTS.md": plain,
        ".cursor/rules/lazy-ladder.mdc": cursor,
        ".windsurf/rules/lazy-ladder.md": plain,
        ".clinerules/lazy-ladder.md": plain,
        ".github/copilot-instructions.md": plain,
        ".kiro/steering/lazy-ladder.md": kiro,
    }


def cmd_build(target: Path, dry_run: bool, force: bool) -> int:
    if not LADDER.is_file():
        print(f"ERROR: missing source {LADDER}", file=sys.stderr)
        return 1
    targets = render_targets(LADDER.read_text(encoding="utf-8"))
    skipped: list[str] = []
    for rel, content in targets.items():
        dst = target / rel
        if dry_run:
            if dst.exists() and PROVENANCE not in dst.read_text(encoding="utf-8"):
                print(f"[dry-run] would skip {dst} (user file, no provenance marker; use --force to overwrite)")
            else:
                print(f"[dry-run] would write {dst} ({len(content)} bytes)")
            continue
        if dst.exists() and PROVENANCE not in dst.read_text(encoding="utf-8"):
            if not force:
                skipped.append(rel)
                continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(content, encoding="utf-8", newline="\n")
        print(f"rendered {rel} -> {dst}")
    if skipped:
        print(f"\nWARNING: {len(skipped)} file(s) were NOT overwritten because they exist "
              "and do not contain the mergen PROVENANCE marker (they appear to be user files):")
        for rel in skipped:
            print(f"  {target / rel}")
        print("To overwrite them, re-run with --force.")
    rendered = len(targets) - len(skipped)
    print(f"\n{len(targets)} cross-agent rule file(s) "
          f"{'planned' if dry_run else f'rendered: {rendered}, skipped: {len(skipped)}'} "
          f"under {target}.")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="render mergen's lazy ladder into cross-agent passive rule files")
    ap.add_argument("target", nargs="?", default=".",
                    help="target project directory (default: cwd)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true",
                    help="overwrite existing files even when they lack the provenance marker")
    args = ap.parse_args(argv)
    return cmd_build(Path(args.target).resolve(), args.dry_run, args.force)


if __name__ == "__main__":
    raise SystemExit(main())
