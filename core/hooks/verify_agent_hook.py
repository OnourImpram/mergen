#!/usr/bin/env python3
"""Stop hook (OPT-IN, default OFF): re-surface the verification verdict at the end of a turn.

EXPERIMENTAL scaffold. This is reinforcement, not enforcement, and it says so. The real gate is
the CI verification step (eval/ci/verify-gate.yml and the PR Guardian): a step that regenerates
the report from the live tree and fails the build on a phantom or an unsigned high-trust report.
A Stop hook cannot be that gate. It runs inside the very session it would judge, it cannot fail a
build, and it must not run a project's test suite on every turn. So this does less, on purpose,
and is off unless a user asks for it.

Default OFF. With MERGEN_VERIFY_HOOK unset or not truthy this is a true no-op: it reads nothing,
prints nothing, and exits 0. A user opts in by setting MERGEN_VERIFY_HOOK=1 in the environment.

When opted in, it reads any committed .specify/verification-report.json (located by walking up
from the working directory for a .specify directory, the same way the vendored scripts resolve
the project root) READ-ONLY. It does not run verification itself. It surfaces a compact line, the
recorded verdict and how many done tasks went unproven, plus the command to run the real check,
so the session is reminded what the gate will say rather than discovering it in CI. With no report
present it surfaces only the reminder to run the check. The message is always framed as
reinforcement, never as a pass: a green line here is a recorded verdict, not a fresh one.

The forward path, named not built: a fuller version would run the impacted-slice verification
(scripts/impacted.py) over the turn's changed files and surface a freshly computed verdict. That
is heavier and can shell a test suite, which is why it stays opt-in and is not the default even
when this hook is enabled.

Registered as a Stop hook. Fail-soft: any error exits 0 with no output.

Tier 0: pure standard library, deterministic, no network, no model.
"""

from __future__ import annotations

import json
import os
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any

_OPT_IN_ENV = "MERGEN_VERIFY_HOOK"
_TRUTHY = {"1", "true", "on", "yes"}

# A verification report is repository content, and repository content is DATA, never an
# instruction. The hook surfaces a few of its fields into the model's context, so a hostile
# report (one a supply-chain compromise or a malicious CI step could write) must not smuggle a
# newline, a control character, or an oversized payload through them. This mirrors the data-fence
# in constitution_inject.py: strip the dangerous mechanics, the surrounding framing does the rest.
_MAX_FIELD = 200
_MAX_TASK_ID = 80
_MAX_TASKS = 20


def _safe(raw: Any, cap: int = _MAX_FIELD) -> str:
    """Neutralize a report field for display: normalize, strip control and format characters,
    collapse whitespace, and cap length. A field can carry text but never structure or bulk."""
    s = raw if isinstance(raw, str) else str(raw)
    s = unicodedata.normalize("NFKC", s)
    s = "".join(ch for ch in s if not unicodedata.category(ch).startswith("C"))
    s = re.sub(r"\s+", " ", s).strip()
    if len(s) > cap:
        s = s[:cap].rstrip() + "..."
    return s or "(empty)"


def _opted_in() -> bool:
    return os.environ.get(_OPT_IN_ENV, "").strip().lower() in _TRUTHY


def _find_report(start: Path) -> Path | None:
    """Walk up from start for a .specify/verification-report.json. None when not found."""
    for directory in [start, *start.parents]:
        candidate = directory / ".specify" / "verification-report.json"
        if candidate.is_file():
            return candidate
    return None


def _summarize(report: dict[str, Any]) -> str:
    summary = report.get("summary")
    summary = summary if isinstance(summary, dict) else {}
    # Every surfaced field is sanitized: it is data read from a file, not trusted text.
    verdict = _safe(summary.get("verdict", "unknown"))
    feature = _safe(report.get("feature_id", "this feature"))
    tasks = report.get("tasks") if isinstance(report.get("tasks"), list) else []
    unproven = [
        _safe(t.get("task_id", "?"), cap=_MAX_TASK_ID) for t in tasks
        if isinstance(t, dict) and t.get("claimed_status") == "done"
        and t.get("verified_status") != "pass"
    ]
    head = (f"verify-agent-hook (reinforcement, not the gate): recorded verdict for "
            f"'{feature}' is '{verdict}'.")
    if unproven:
        shown = unproven[:_MAX_TASKS]
        more = f" (and {len(unproven) - len(shown)} more)" if len(unproven) > len(shown) else ""
        head += f" {len(unproven)} done task(s) went unproven: {', '.join(shown)}{more}."
    head += (" This is the last recorded report, not a fresh check. Run mergen verify "
             "(or mergen impacted verify) to recompute, and remember the CI gate is the enforcement.")
    return head


def _reminder() -> str:
    return ("verify-agent-hook (reinforcement, not the gate): no verification report was found. "
            "Run mergen verify before claiming completion. The CI verification step is the "
            "enforcement; this hook only reminds.")


def _emit(message: str) -> None:
    out = {"hookSpecificOutput": {"hookEventName": "Stop", "additionalContext": message}}
    print(json.dumps(out))


def main() -> int:
    if not _opted_in():
        return 0
    try:
        json.load(sys.stdin)  # consume the event payload; its contents are not needed here
    except Exception:  # noqa: BLE001 - fail-soft on any malformed input
        pass
    try:
        report_path = _find_report(Path.cwd())
        if report_path is None:
            _emit(_reminder())
            return 0
        try:
            report = json.loads(report_path.read_bytes().decode("utf-8-sig"))
        except (json.JSONDecodeError, UnicodeDecodeError, OSError):
            # A present but unreadable or corrupt report still surfaces the reminder, rather than
            # silently emitting nothing, so the session knows the check did not resolve.
            _emit(_reminder())
            return 0
        _emit(_summarize(report) if isinstance(report, dict) else _reminder())
    except Exception:  # noqa: BLE001 - fail-soft, a hook must never break a turn
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
