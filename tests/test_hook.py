"""Unit tests for effort-mode/hooks/mergen_prompt_hook.py.

All tests monkeypatch Path.home() via the home_dir fixture so the real
~/.claude directory is never touched. Activation is explicit (only the marker,
written by /mergen) and session-scoped (bound to the arming session on first
sight). There is no keyword auto-trigger.
"""

import importlib
import json
import sys
from io import StringIO
from pathlib import Path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run_hook(home_dir, prompt: str = "", session_id: str = "sess-A") -> str:
    """Run the hook main() with the given prompt and session id as stdin."""
    import hooks.mergen_prompt_hook as hook_mod
    importlib.reload(hook_mod)

    stdin_payload = json.dumps({"prompt": prompt, "session_id": session_id})
    _orig_stdin = sys.stdin
    _orig_stdout = sys.stdout
    sys.stdin = StringIO(stdin_payload)
    captured = StringIO()
    sys.stdout = captured
    try:
        hook_mod.main()
    finally:
        sys.stdin = _orig_stdin
        sys.stdout = _orig_stdout
    return captured.getvalue()


def _marker_path(home_dir: Path) -> Path:
    return home_dir / ".claude" / "mergen.json"


def _write_marker(home_dir: Path, payload: dict) -> None:
    _marker_path(home_dir).write_text(json.dumps(payload), encoding="utf-8")


def _read_marker(home_dir: Path) -> dict:
    return json.loads(_marker_path(home_dir).read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Activation gating
# ---------------------------------------------------------------------------

def test_no_marker_no_output(home_dir):
    """No marker file -> hook emits nothing."""
    assert _run_hook(home_dir, prompt="do some work") == ""


def test_active_false_no_output(home_dir):
    """Marker with active: false -> no output."""
    _write_marker(home_dir, {"active": False})
    assert _run_hook(home_dir, prompt="do some work") == ""


def test_armed_marker_emits_default_directive(home_dir):
    """Armed marker (no bound session) -> default DIRECTIVE injected, binds session."""
    import hooks.mergen_prompt_hook as hook_mod
    importlib.reload(hook_mod)

    _write_marker(home_dir, {"active": True})
    stdout = _run_hook(home_dir, prompt="do some work", session_id="sess-A")

    data = json.loads(stdout)
    context = data["hookSpecificOutput"]["additionalContext"]
    assert "maximum reasoning effort" in context
    assert hook_mod.DIRECTIVE == context


def test_armed_marker_custom_directive(home_dir):
    """Marker with custom directive field -> custom string used instead of default."""
    import hooks.mergen_prompt_hook as hook_mod
    importlib.reload(hook_mod)

    custom = "My custom directive: think hard."
    _write_marker(home_dir, {"active": True, "directive": custom})
    stdout = _run_hook(home_dir, prompt="do some work", session_id="sess-A")

    data = json.loads(stdout)
    context = data["hookSpecificOutput"]["additionalContext"]
    assert context == custom
    assert hook_mod.DIRECTIVE not in context


# ---------------------------------------------------------------------------
# No keyword auto-trigger (the behavior change in v1.0.1)
# ---------------------------------------------------------------------------

def test_keyword_does_not_activate(home_dir):
    """Prompt containing 'mergen' with no armed marker -> NO injection.

    The keyword auto-trigger was removed. Only the explicit /mergen command
    (which writes the marker) activates the mode.
    """
    assert _run_hook(home_dir, prompt="use mergen for this task") == ""


# ---------------------------------------------------------------------------
# Session scoping
# ---------------------------------------------------------------------------

def test_first_sight_binds_session(home_dir):
    """Armed marker with no session bound -> injects and binds the current session."""
    _write_marker(home_dir, {"active": True})
    stdout = _run_hook(home_dir, prompt="work", session_id="sess-A")
    assert stdout != ""
    assert _read_marker(home_dir).get("session_id") == "sess-A"


def test_same_session_injects(home_dir):
    """Marker already bound to the current session -> injects."""
    _write_marker(home_dir, {"active": True, "session_id": "sess-A"})
    assert _run_hook(home_dir, prompt="work", session_id="sess-A") != ""


def test_other_session_inert(home_dir):
    """Marker bound to another session -> no injection in a different session."""
    _write_marker(home_dir, {"active": True, "session_id": "sess-A"})
    assert _run_hook(home_dir, prompt="work", session_id="sess-B") == ""


# ---------------------------------------------------------------------------
# Fail-soft
# ---------------------------------------------------------------------------

def test_malformed_stdin_exits_cleanly(home_dir):
    """Malformed stdin JSON -> exits cleanly, no output (no marker armed)."""
    import hooks.mergen_prompt_hook as hook_mod
    importlib.reload(hook_mod)

    _orig_stdin = sys.stdin
    _orig_stdout = sys.stdout
    sys.stdin = StringIO("NOT JSON {{{")
    captured = StringIO()
    sys.stdout = captured
    try:
        hook_mod.main()
    finally:
        sys.stdin = _orig_stdin
        sys.stdout = _orig_stdout
    assert captured.getvalue() == ""


def test_malformed_marker_json_exits_cleanly(home_dir):
    """Marker file contains invalid JSON -> no crash, no output."""
    _marker_path(home_dir).write_text("NOT VALID JSON <<<", encoding="utf-8")
    assert _run_hook(home_dir, prompt="do some work") == ""
