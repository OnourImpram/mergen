#!/usr/bin/env python3
"""PostToolUse hook: reinforce the verify-gate when tasks.md gains an [X] mark.

This is a REINFORCEMENT nudge, not the enforcement mechanism. Real enforcement
is the /mergen.implement pipeline's adversarial verify stage: a separate
context that checks the filesystem and tests before any task is marked [X], plus
the non-bypassable final verify gate. A PostToolUse hook cannot itself run a
project's tests to prove completion, so it does not pretend to. What it does is
re-surface the discipline at the exact moment a task box is checked, so a
single-context shortcut cannot quietly mark work done without the reminder.

Registered as a PostToolUse hook on Write/Edit/MultiEdit. PostToolUse is the
correct event because it is the only tool-use hook in this build that supports
injecting additionalContext into the model's context.

Fail-soft: any error, or any call that is not a tasks.md edit introducing an
[X] mark, exits 0 with no output (true no-op).
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
        if not path.endswith("tasks.md"):
            return 0

        # Collect the text this call added, to see if it introduced an [X] mark.
        if tool == "Write":
            added = tool_input.get("content", "") or ""
        elif tool == "Edit":
            added = tool_input.get("new_string", "") or ""
        else:  # MultiEdit
            added = "\n".join(
                (e or {}).get("new_string", "") for e in (tool_input.get("edits") or [])
            )

        if not _CHECKED.search(added):
            return 0

        msg = (
            "verify-gate reminder: a task in tasks.md was just marked [X]. "
            "Per mergen's verify-gate protocol, a task is complete only when an "
            "independent verifier confirms it against the FILESYSTEM and TESTS: the "
            "named file exists and changed as specified, the acceptance criteria are "
            "met, the task's tests pass, and git state is consistent. If you have not "
            "run that check, run /mergen.verify (or /speckit.mergen.verify) before "
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
