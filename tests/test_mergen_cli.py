"""Tests for the unified mergen CLI (mergen_cli.py).

doctor is exercised against tmp trees so it never reads the real ~/.claude.
install, uninstall, and upgrade are exercised only in --dry-run, so they make
no writes. Their real effects are delegated to already-tested helpers.
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


_DEMO = Path(__file__).resolve().parent.parent / "examples" / "verify-demo"


def test_verify_subcommand_forwards_to_the_harness_and_returns_its_code():
    # The packaged `mergen verify` forwards verbatim to verify_core. The demo
    # carries a planted phantom, so the harness exits 1 and the CLI returns 1.
    rc = mergen_cli.main([
        "verify",
        "--tasks-state", str(_DEMO / "tasks-state.json"),
        "--root", str(_DEMO),
    ])
    assert rc == 1


def test_verify_subcommand_reports_missing_tasks_state():
    # A nonexistent tasks-state makes the harness exit 2, surfaced unchanged.
    rc = mergen_cli.main([
        "verify",
        "--tasks-state", str(_DEMO / "does-not-exist.json"),
        "--root", str(_DEMO),
    ])
    assert rc == 2


def test_dashboard_subcommand_forwards_to_the_generator(tmp_path):
    # `mergen dashboard` forwards verbatim to dashboard.py. An empty dir is valid
    # input: it renders a "no reports" page and exits 0.
    out = tmp_path / "dash.html"
    rc = mergen_cli.main(["dashboard", str(tmp_path), "--out", str(out)])
    assert rc == 0
    assert out.is_file()


def test_status_subcommand_forwards_to_the_summarizer():
    # `mergen status` forwards to tasks_status.py. The demo tasks-state is a valid
    # read, so it exits 0. The dispatch-table test below proves it reaches the right
    # helper with the args passed through, which an exit code alone cannot show.
    rc = mergen_cli.main(["status", str(_DEMO / "tasks-state.json")])
    assert rc == 0


def test_forward_verbs_dispatch_to_the_right_script(monkeypatch):
    # Each forwarding verb must reach its own helper with the trailing args passed
    # through verbatim. Recording _run pins the dispatch table directly,
    # which is stronger than an exit code and answers the "wrong helper, returned 0
    # for an unrelated reason" concern without depending on fd-level capture of a
    # child process (unreliable across platforms).
    seen: dict[str, object] = {}

    def fake_run(script, *args, dry_run=False):
        seen["script"] = script
        seen["args"] = args
        return 0

    monkeypatch.setattr(mergen_cli, "_run", fake_run)
    for verb, target in (
        ("verify", mergen_cli._VERIFY_CORE),
        ("verify-lint", mergen_cli._VERIFY_LINT),
        ("dashboard", mergen_cli._DASHBOARD),
        ("status", mergen_cli._STATUS),
        ("issues", mergen_cli._ISSUES),
        ("trends", mergen_cli._TRENDS),
        ("graph", mergen_cli._GRAPH),
        ("replay", mergen_cli._REPLAY),
    ):
        seen.clear()
        rc = mergen_cli.main([verb, "PASSTHROUGH_ARG", "--flag"])
        assert rc == 0
        assert seen["script"] == target
        assert seen["args"] == ("PASSTHROUGH_ARG", "--flag")


def test_verify_lint_subcommand_forwards_and_returns_its_code():
    # `mergen verify-lint` forwards verbatim to the report linter. The committed
    # sample is a conditional, unsigned high-trust report, so the linter exits 1
    # and the CLI surfaces that unchanged.
    sample = Path(__file__).resolve().parent.parent / "eval" / "sample" / "verification-report.json"
    rc = mergen_cli.main(["verify-lint", str(sample)])
    assert rc == 1


def test_status_subcommand_reports_missing_state():
    rc = mergen_cli.main(["status", str(_DEMO / "does-not-exist.json")])
    assert rc == 2


def test_issues_subcommand_forwards_to_the_renderer(tmp_path):
    # `mergen issues` forwards to tasks_to_issues.py over a tasks.md checklist.
    md = tmp_path / "tasks.md"
    md.write_text("- [ ] T001 [P] do the thing in src/a.py\n", encoding="utf-8")
    rc = mergen_cli.main(["issues", str(md)])
    assert rc == 0


def test_trends_subcommand_forwards_to_the_analyzer(tmp_path):
    # `mergen trends` forwards to trends.py over a reports directory. Writing to a
    # file (like the dashboard test) keeps the forwarded child off the inherited
    # stdout and asserts a real artifact, not just an exit code. An empty dir is
    # valid input: it renders a "no reports" page and exits 0.
    out = tmp_path / "trends.html"
    rc = mergen_cli.main(["trends", str(tmp_path), "--out", str(out)])
    assert rc == 0
    assert out.is_file()


def test_doctor_checks_shipped_schema_validity(tmp_path, capsys):
    # doctor now self-checks the repo's shipped schemas. On a healthy tree the
    # real schemas are valid, so the line reads OK and the result stays healthy.
    skills, hooks, commands, settings = _populate_healthy(tmp_path)
    rc = mergen_cli.doctor(skills, hooks, commands, settings)
    out = capsys.readouterr().out
    assert rc == 0
    assert "schemas" in out
    assert "valid under" in out


def test_doctor_bad_schema_degrades_to_1(tmp_path, capsys):
    # A malformed shipped schema must make doctor report BAD and exit 1 even when
    # the rest of the tree is healthy. schemas_dir is an injectable parameter
    # precisely so this red path is testable without monkeypatching a module global.
    skills, hooks, commands, settings = _populate_healthy(tmp_path)
    schemas = tmp_path / "schemas"
    schemas.mkdir()
    (schemas / "broken.json").write_text("{ not json", encoding="utf-8")
    rc = mergen_cli.doctor(skills, hooks, commands, settings, schemas)
    out = capsys.readouterr().out
    assert rc == 1
    assert "BAD" in out
    assert "broken.json" in out


def test_doctor_empty_schemas_dir_does_not_false_degrade(tmp_path, capsys):
    # An empty schemas dir is "nothing to validate", not a failure. With the rest
    # of the tree healthy, doctor must stay at 0 rather than report a phantom
    # degradation on a partial clone or after a directory rename.
    skills, hooks, commands, settings = _populate_healthy(tmp_path)
    empty = tmp_path / "no-schemas"
    empty.mkdir()
    rc = mergen_cli.doctor(skills, hooks, commands, settings, empty)
    out = capsys.readouterr().out
    assert rc == 0
    assert "none found" in out
