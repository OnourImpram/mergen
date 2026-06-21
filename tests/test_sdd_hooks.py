"""Tests for the always-on SDD runtime hooks under core/hooks/: verify_gate (the
nudge to run /mergen-verify when a task is checked off inside .specify) and
constitution_inject (surfacing the project constitution's headings on session
start). Both share the _run_hook driver, so they live in one focused file.

Loaded by file path because core/hooks/ is not an importable package.
"""

import importlib.util
import io
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def _load(rel_path: str):
    path = REPO / rel_path
    spec = importlib.util.spec_from_file_location(path.stem.replace("-", "_"), path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _run_hook(rel_path, payload, monkeypatch, capsys):
    """Run a hook's main() in-process with a crafted stdin, capture stdout.

    In-process rather than subprocess to avoid the Windows subprocess flake seen
    under newer Python, the same reason the BOM patcher tests run in-process.
    """
    mod = _load(rel_path)
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
    rc = mod.main()
    return rc, capsys.readouterr().out


def test_verify_gate_fires_on_new_x_in_specify_tasks(monkeypatch, capsys):
    payload = {
        "tool_name": "Edit",
        "tool_input": {
            "file_path": "/proj/.specify/specs/001-feature/tasks.md",
            "old_string": "- [ ] T001 do the thing",
            "new_string": "- [X] T001 do the thing",
        },
    }
    rc, out = _run_hook("core/hooks/verify_gate.py", payload, monkeypatch, capsys)
    assert rc == 0
    assert "verify-gate reminder" in out
    assert "/mergen-verify" in out


def test_verify_gate_silent_on_tasks_outside_specify(monkeypatch, capsys):
    payload = {
        "tool_name": "Edit",
        "tool_input": {
            "file_path": "/proj/docs/tasks.md",
            "old_string": "- [ ] a",
            "new_string": "- [X] a",
        },
    }
    rc, out = _run_hook("core/hooks/verify_gate.py", payload, monkeypatch, capsys)
    assert rc == 0
    assert out.strip() == ""


def test_verify_gate_silent_when_edit_introduces_no_new_x(monkeypatch, capsys):
    payload = {
        "tool_name": "Edit",
        "tool_input": {
            "file_path": "/proj/.specify/specs/001/tasks.md",
            "old_string": "- [X] T001 done",
            "new_string": "- [X] T001 done and tidied",
        },
    }
    rc, out = _run_hook("core/hooks/verify_gate.py", payload, monkeypatch, capsys)
    assert rc == 0
    assert out.strip() == ""


def test_verify_gate_failsoft_on_garbage_stdin(monkeypatch, capsys):
    mod = _load("core/hooks/verify_gate.py")
    monkeypatch.setattr(sys, "stdin", io.StringIO("not json at all"))
    rc = mod.main()
    assert rc == 0
    assert capsys.readouterr().out.strip() == ""


def test_constitution_inject_surfaces_headings(tmp_path, monkeypatch, capsys):
    con = tmp_path / ".specify" / "memory" / "constitution.md"
    con.parent.mkdir(parents=True)
    con.write_text(
        "# Constitution\n\n## Safety first\n\n## Evidence over assertion\n",
        encoding="utf-8",
    )
    rc, out = _run_hook(
        "core/hooks/constitution_inject.py", {"cwd": str(tmp_path)}, monkeypatch, capsys
    )
    assert rc == 0
    assert "Safety first" in out
    assert "Evidence over assertion" in out


def test_constitution_inject_noop_without_constitution(tmp_path, monkeypatch, capsys):
    rc, out = _run_hook(
        "core/hooks/constitution_inject.py", {"cwd": str(tmp_path)}, monkeypatch, capsys
    )
    assert rc == 0
    assert out.strip() == ""


def test_verify_gate_fires_on_write_tool(monkeypatch, capsys):
    # Write is a full rewrite: a PostToolUse hook has no prior content to diff,
    # so any [X] in the written content fires the nudge. This pins that behavior.
    payload = {
        "tool_name": "Write",
        "tool_input": {
            "file_path": "/proj/.specify/specs/001-feature/tasks.md",
            "content": "- [ ] T001 setup\n- [X] T002 done\n",
        },
    }
    rc, out = _run_hook("core/hooks/verify_gate.py", payload, monkeypatch, capsys)
    assert rc == 0
    assert "verify-gate reminder" in out


def test_verify_gate_fires_on_multiedit_new_x(monkeypatch, capsys):
    payload = {
        "tool_name": "MultiEdit",
        "tool_input": {
            "file_path": "/proj/.specify/specs/001/tasks.md",
            "edits": [
                {"old_string": "- [ ] T001 a", "new_string": "- [X] T001 a"},
                {"old_string": "intro", "new_string": "intro tidy"},
            ],
        },
    }
    rc, out = _run_hook("core/hooks/verify_gate.py", payload, monkeypatch, capsys)
    assert rc == 0
    assert "verify-gate reminder" in out


def test_verify_gate_multiedit_silent_when_no_net_new_x(monkeypatch, capsys):
    # MultiEdit that only reshapes an already-checked line introduces no new [X].
    payload = {
        "tool_name": "MultiEdit",
        "tool_input": {
            "file_path": "/proj/.specify/specs/001/tasks.md",
            "edits": [{"old_string": "- [X] T001 done", "new_string": "- [X] T001 done, tidied"}],
        },
    }
    rc, out = _run_hook("core/hooks/verify_gate.py", payload, monkeypatch, capsys)
    assert rc == 0
    assert out.strip() == ""


def test_constitution_inject_walks_up_from_nested_cwd(tmp_path, monkeypatch, capsys):
    con = tmp_path / ".specify" / "memory" / "constitution.md"
    con.parent.mkdir(parents=True)
    con.write_text("# Constitution\n\n## Alpha rule\n\n## Beta rule\n", encoding="utf-8")
    nested = tmp_path / "sub" / "sub2"
    nested.mkdir(parents=True)
    rc, out = _run_hook(
        "core/hooks/constitution_inject.py", {"cwd": str(nested)}, monkeypatch, capsys
    )
    assert rc == 0
    assert "Alpha rule" in out
    assert "Beta rule" in out


def test_constitution_inject_noop_when_no_subheadings(tmp_path, monkeypatch, capsys):
    con = tmp_path / ".specify" / "memory" / "constitution.md"
    con.parent.mkdir(parents=True)
    # Only a top-level '#' title and prose: no '##' sections to surface.
    con.write_text("# Constitution\n\nJust a paragraph, no sections.\n", encoding="utf-8")
    rc, out = _run_hook(
        "core/hooks/constitution_inject.py", {"cwd": str(tmp_path)}, monkeypatch, capsys
    )
    assert rc == 0
    assert out.strip() == ""


def test_constitution_inject_truncates_at_twelve_headings(tmp_path, monkeypatch, capsys):
    con = tmp_path / ".specify" / "memory" / "constitution.md"
    con.parent.mkdir(parents=True)
    body = "# Constitution\n\n" + "".join(f"## Heading{n:02d}\n\n" for n in range(1, 16))
    con.write_text(body, encoding="utf-8")
    rc, out = _run_hook(
        "core/hooks/constitution_inject.py", {"cwd": str(tmp_path)}, monkeypatch, capsys
    )
    assert rc == 0
    assert "Heading01" in out
    assert "Heading12" in out
    assert "Heading13" not in out  # truncated to the first 12


def test_constitution_inject_uses_cwd_fallback_when_key_absent(tmp_path, monkeypatch, capsys):
    # No 'cwd' key in the payload, so the hook must fall back to os.getcwd().
    # Point getcwd at a tmp dir that DOES carry a constitution and assert its
    # heading surfaces. The real cwd has none, so this passes only if the
    # fallback branch genuinely runs, not by coincidence of an empty result.
    con = tmp_path / ".specify" / "memory" / "constitution.md"
    con.parent.mkdir(parents=True)
    con.write_text("# Constitution\n\n## Fallback rule\n", encoding="utf-8")
    monkeypatch.setattr(os, "getcwd", lambda: str(tmp_path))
    rc, out = _run_hook("core/hooks/constitution_inject.py", {}, monkeypatch, capsys)
    assert rc == 0
    assert "Fallback rule" in out


def test_constitution_inject_failsoft_on_garbage_stdin(monkeypatch, capsys):
    mod = _load("core/hooks/constitution_inject.py")
    monkeypatch.setattr(sys, "stdin", io.StringIO("not json at all"))
    rc = mod.main()
    assert rc == 0
    assert capsys.readouterr().out.strip() == ""
