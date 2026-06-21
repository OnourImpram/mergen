#!/usr/bin/env python3
"""PostToolUse hook: reinforce the verify-gate when tasks.md gains an [X] mark.

This is a REINFORCEMENT nudge, not the enforcement mechanism. Real enforcement
is the /mergen-implement pipeline's adversarial verify stage: a separate
context that checks the filesystem and tests before any task is marked [X], plus
the final verify gate the pipeline will not skip. A PostToolUse hook cannot itself run a
project's tests to prove completion, so it does not pretend to. What it does is
re-surface the discipline at the exact moment a task box is checked, so a
single-context shortcut cannot quietly mark work done without the reminder.

Registered as a PostToolUse hook on Write/Edit/MultiEdit. PostToolUse is the
correct event because it is the only tool-use hook in this build that supports
injecting additionalContext into the model's context.

Fail-soft: any error, or any call that does not raise the [X] count of a Mergen
tasks.md, exits 0 with no output (true no-op). For Edit and MultiEdit the count
is measured against the replaced text, so the nudge is precise to a newly
introduced mark. For Write, a full-file rewrite, a PostToolUse hook cannot see
the prior content, so the nudge fires on any [X] in the written content.
"""

from __future__ import annotations

import json
import re
import sys

_CHECKED = re.compile(r"-\s*\[[xX]\]")


def main() -> int:
    try:
        data = json.load(sys.stdin)
    except Exception:
        return 0
    try:
        tool = data.get("tool_name", "")
        if tool not in ("Edit", "Write", "MultiEdit"):
            return 0

        tool_input = data.get("tool_input", {}) or {}
        path = (tool_input.get("file_path") or "").replace("\\", "/")
        # Scope to a Mergen SDD tasks file, not any tasks.md in any project.
        if not (path.endswith("tasks.md") and ".specify/" in path):
            return 0

        # Collect the text added and the text replaced. For Edit and MultiEdit
        # the old_string gives a true baseline, so the nudge fires only when this
        # call INTRODUCES a new [X] rather than touching one already there. Write
        # is a full-file rewrite seen by a PostToolUse hook, which runs AFTER the
        # write, so the prior content is already gone and cannot be diffed. For
        # Write the baseline is therefore empty and the nudge fires whenever the
        # written content contains an [X], which may include marks that already
        # existed. A reminder that occasionally over-fires on a full rewrite is
        # the safer default for a fail-soft gate than silently missing one.
        if tool == "Write":
            added = tool_input.get("content", "") or ""
            removed = ""
        elif tool == "Edit":
            added = tool_input.get("new_string", "") or ""
            removed = tool_input.get("old_string", "") or ""
        else:  # MultiEdit
            edits = tool_input.get("edits") or []
            added = "\n".join((e or {}).get("new_string", "") for e in edits)
            removed = "\n".join((e or {}).get("old_string", "") for e in edits)

        if len(_CHECKED.findall(added)) <= len(_CHECKED.findall(removed)):
            return 0

        msg = (
            "verify-gate reminder: a task in tasks.md was just marked [X]. "
            "Per mergen's verify-gate protocol, a task is complete only when an "
            "independent verifier confirms it against the FILESYSTEM and TESTS: the "
            "named file exists and changed as specified, the acceptance criteria are "
            "met, the task's tests pass, and git state is consistent. If you have not "
            "run that check, run /mergen-verify (or /speckit.mergen.verify) before "
            "claiming completion. The [X] mark itself is not evidence."
        )
        out = {
            "hookSpecificOutput": {
                "hookEventName": "PostToolUse",
                "additionalContext": msg,
            }
        }
        print(json.dumps(out))
    except Exception:
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
