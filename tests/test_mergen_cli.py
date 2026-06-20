"""Tests for the unified mergen CLI (mergen_cli.py).

doctor is exercised against tmp trees so it never reads the real ~/.claude.
install, uninstall, and upgrade are exercised only in --dry-run, so they make
no writes; their real effects are delegated to already-tested helpers.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import mergen_cli  # noqa: E402


def _populate_healthy(tmp_path):
    skills = tmp_path / "skills"
    hooks = tmp_path / "hooks"
    commands = tmp_path / "commands"
    for name in mergen_cli.expected_skill_names():
        d = skills / f"mergen-{name}"
        d.mkdir(parents=True)
        (d / "SKILL.md").write_text("x", encoding="utf-8")
    hooks.mkdir(parents=True)
    for f in ("verify_gate.py", "constitution_inject.py", "mergen_prompt_hook.py"):
        (hooks / f).write_text("x", encoding="utf-8")
    commands.mkdir(parents=True)
    (commands / "mergen.md").write_text("x", encoding="utf-8")
    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps({"hooks": {
        "UserPromptSubmit": [
            {"hooks": [{"type": "command", "command": "python hooks/mergen_prompt_hook.py"}]},
            {"hooks": [{"type": "command", "command": "python hooks/constitution_inject.py"}]},
        ],
        "PostToolUse": [
            {"matcher": "Write|Edit",
             "hooks": [{"type": "command", "command": "python hooks/verify_gate.py"}]},
        ],
    }}), encoding="utf-8")
    return skills, hooks, commands, settings


def test_expected_skill_names_nonempty_and_known():
    names = mergen_cli.expected_skill_names()
    assert names
    for known in ("go", "verify", "govern"):
        assert known in names


def test_doctor_healthy_tree_returns_0(tmp_path, capsys):
    skills, hooks, commands, settings = _populate_healthy(tmp_path)
    rc = mergen_cli.doctor(skills, hooks, commands, settings)
    out = capsys.readouterr().out
    assert rc == 0
    assert "healthy" in out


def test_doctor_empty_tree_returns_1(tmp_path, capsys):
    rc = mergen_cli.doctor(
        tmp_path / "s", tmp_path / "h", tmp_path / "c", tmp_path / "settings.json"
    )
    out = capsys.readouterr().out
    assert rc == 1
    assert "degraded" in out


def test_doctor_missing_one_registration_fails(tmp_path):
    skills, hooks, commands, settings = _populate_healthy(tmp_path)
    # Drop verify_gate from the settings registration only.
    settings.write_text(json.dumps({"hooks": {"UserPromptSubmit": [
        {"hooks": [{"command": "python hooks/mergen_prompt_hook.py"}]},
        {"hooks": [{"command": "python hooks/constitution_inject.py"}]},
    ]}}), encoding="utf-8")
    assert mergen_cli.doctor(skills, hooks, commands, settings) == 1


def test_doctor_reports_honest_caveats(tmp_path, capsys):
    skills, hooks, commands, settings = _populate_healthy(tmp_path)
    mergen_cli.doctor(skills, hooks, commands, settings)
    out = capsys.readouterr().out
    assert "/effort max" in out
    assert "nudges" in out


def test_install_dry_run_makes_no_writes(capsys):
    rc = mergen_cli.install("python", dry_run=True)
    out = capsys.readouterr().out
    assert rc == 0
    assert "1/4" in out and "4/4" in out
    assert "[dry-run]" in out


def test_uninstall_dry_run_makes_no_writes(capsys):
    rc = mergen_cli.uninstall(dry_run=True)
    out = capsys.readouterr().out
    assert rc == 0
    assert "[dry-run]" in out


def test_upgrade_dry_run(capsys):
    rc = mergen_cli.upgrade("python", dry_run=True)
    out = capsys.readouterr().out
    assert rc == 0
    assert "1/2" in out


def test_main_dispatches_doctor_on_empty_tree(tmp_path):
    rc = mergen_cli.main([
        "doctor",
        "--skills-dir", str(tmp_path / "s"),
        "--hooks-dir", str(tmp_path / "h"),
        "--commands-dir", str(tmp_path / "c"),
        "--settings", str(tmp_path / "x.json"),
    ])
    assert rc == 1


def test_hook_registered_detects_basename():
    settings = {"hooks": {"PostToolUse": [{"hooks": [{"command": "py verify_gate.py"}]}]}}
    assert mergen_cli._hook_registered(settings, "verify_gate.py")
    assert not mergen_cli._hook_registered(settings, "constitution_inject.py")
