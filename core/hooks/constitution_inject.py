#!/usr/bin/env python3
"""UserPromptSubmit hook: re-surface the project constitution each turn.

Reinforcement, not enforcement. When the current project has a constitution at
.specify/memory/constitution.md (located by walking up from cwd for a .specify
directory, the same way the vendored scripts resolve the project root), this
hook injects the constitution's section headings as a compact standing reminder
so governance constraints stay in view during spec, plan, tasks, and
implementation work. It does not block anything.

Registered as a UserPromptSubmit hook (the proven additionalContext injection
channel, same one the effort-mode hook uses).

Fail-soft: any error, or the absence of a project constitution, exits 0 with no
output (true no-op). It never interrupts a session that has no constitution.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def find_constitution(start: str) -> Path | None:
    try:
        d = Path(start).resolve()
    except Exception:
        return None
    prev = None
    while d != prev:
        candidate = d / ".specify" / "memory" / "constitution.md"
        if candidate.is_file():
            return candidate
        prev = d
        d = d.parent
    return None


def main() -> int:
    try:
        data = json.load(sys.stdin)
    except Exception:
        return 0
    try:
        cwd = data.get("cwd") or os.getcwd()
        con = find_constitution(cwd)
        if con is None:
            return 0

        text = con.read_text(encoding="utf-8", errors="replace")
        # Compact reminder: the section headings (## / ###), not the full body.
        heads = [
            ln.strip().lstrip("#").strip()
            for ln in text.splitlines()
            if ln.strip().startswith("##")
        ]
        heads = [h for h in heads if h]
        if not heads:
            return 0

        compact = "; ".join(heads[:12])
        msg = (
            "Project constitution active (.specify/memory/constitution.md). Honor "
            "these governance sections in spec, plan, tasks, and implementation: "
            f"{compact}. Constraints there override convenience; when a choice "
            "conflicts with the constitution, follow the constitution or surface "
            "the conflict explicitly."
        )
        out = {
            "hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit",
                "additionalContext": msg,
            }
        }
        print(json.dumps(out))
    except Exception:
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
