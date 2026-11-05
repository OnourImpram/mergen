"""Hermes adapter behavior at the public host boundary."""
from __future__ import annotations

import importlib.util
import json
import shlex
from pathlib import Path

import pytest

PLUGIN = Path(__file__).resolve().parents[1] / "integrations" / "hermes"


class Host:
    def __init__(self, response='{"output":"report","exit_code":0}'):
        self.response = response
        self.tools = {}
        self.calls = []
        self.skills = []

    def register_tool(self, **kwargs):
        self.tools[kwargs["name"]] = kwargs

    def register_skill(self, name, path, description=""):
        self.skills.append((name, path, description))

    def dispatch_tool(self, name, args, **kwargs):
        self.calls.append((name, args, kwargs))
        return self.response


@pytest.fixture
def host():
    assert (PLUGIN / "__init__.py").exists(), "Native Hermes adapter has not been implemented"
    spec = importlib.util.spec_from_file_location("mergen_hermes_test", PLUGIN / "__init__.py")
    plugin = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(plugin)
    ctx = Host()
    plugin.register(ctx)
    return ctx


def invoke(host, name="mergen_verify", args=None, **kwargs):
    return host.tools[name]["handler"](args or {"root": "/workspace/project", "tasks_state": "tasks.json"}, **kwargs)


def test_native_entrypoint_exists():
    assert (PLUGIN / "__init__.py").is_file(), "Native Hermes adapter has not been implemented"


def test_registers_tools_and_skill_without_executing(host):
    assert set(host.tools) == {"mergen_verify", "mergen_supervise"}
    assert host.calls == []
    assert len(host.skills) == 1
    assert host.skills[0][0] == "verify-completion"
    assert Path(host.skills[0][1]).is_file()
    for name, tool in host.tools.items():
        assert tool["schema"]["name"] == name
        assert tool["schema"]["description"]
        assert tool["toolset"] == "mergen"


def test_verify_builds_fixed_strict_command_and_forwards_context(host):
    result = invoke(host, task_id="task-12", session_id="session-9", unrelated="ignored")
    assert result == host.response
    name, args, context = host.calls[0]
    assert name == "terminal"
    assert shlex.split(args["command"]) == [
        "mergen", "verify", "--root", "/workspace/project", "--tasks-state",
        "/workspace/project/tasks.json", "--test-timeout", "120", "--strict", "--json",
    ]
    assert args["workdir"] == "/workspace/project"
    assert args["timeout"] == 180
    assert args["background"] is False
    assert context == {"task_id": "task-12", "session_id": "session-9"}


def test_shell_punctuation_is_quoted_as_data(host):
    root = "/workspace/project space'$(touch marker);"
    tasks = "inputs/tasks 'quoted'; $HOME.json"
    invoke(host, args={"root": root, "tasks_state": tasks})
    tokens = shlex.split(host.calls[0][1]["command"])
    assert tokens[3] == root
    assert tokens[5] == root + "/" + tasks


@pytest.mark.parametrize("changes", [
    {"root": "relative"}, {"root": "/"}, {"root": "/work/../etc"},
    {"root": "C:\\repo"}, {"root": "/work\nnext"}, {"tasks_state": "../secret"},
    {"tasks_state": "/etc/passwd"}, {"tasks_state": ""}, {"tasks_state": "a\\b"},
    {"tasks_state": "\x00"}, {"tasks_state": None}, {"tasks_state": "-option"},
    {"test_timeout": 0}, {"test_timeout": 301}, {"test_timeout": True},
    {"test_timeout": "120"}, {"timeout": 0}, {"timeout": 301}, {"timeout": 1.5},
    {"extra": "shell injection"},
])
def test_invalid_arguments_fail_before_execution(host, changes):
    args = {"root": "/workspace/project", "tasks_state": "tasks.json", **changes}
    result = json.loads(invoke(host, args=args))
    assert result["error"]
    assert host.calls == []


@pytest.mark.parametrize("args", [{}, {"root": "/workspace/project"}, [], None])
def test_missing_or_nonobject_arguments_fail(host, args):
    result = json.loads(host.tools["mergen_verify"]["handler"](args))
    assert result["error"]
    assert host.calls == []


def test_supervise_preserves_reproduction_and_has_no_output_writes(host):
    invoke(host, "mergen_supervise", {
        "root": "/workspace/project", "tasks_state": "tasks.json", "report": "report.json",
    })
    assert shlex.split(host.calls[0][1]["command"]) == [
        "env", "-u", "MERGEN_SIGNING_KEY", "-u", "MERGEN_ACK_TOKEN",
        "mergen-supervise", "--root", "/workspace/project", "--tasks-state",
        "/workspace/project/tasks.json", "--report", "/workspace/project/report.json",
    ]


def test_supervise_rejects_missing_report(host):
    assert "error" in json.loads(invoke(host, "mergen_supervise"))
    assert host.calls == []


@pytest.mark.parametrize("response", [
    '{"error":"denied"}', '{"status":"pending_approval"}',
    '{"session_id":"background-1","status":"running"}',
    '{"error":"timeout"}', '{"output":"mergen: command not found","exit_code":127}',
    'unparseable host response',
])
def test_host_outcomes_remain_unchanged_and_are_not_retried(host, response):
    host.response = response
    assert invoke(host) == response
    assert len(host.calls) == 1


def test_dispatch_failure_is_not_retried_or_claimed_as_pass(host):
    def unavailable(*args, **kwargs):
        raise RuntimeError("terminal unavailable")
    host.dispatch_tool = unavailable
    result = json.loads(invoke(host))
    assert result["error"] == "Terminal dispatch failed; execution outcome is unknown. Inspect Hermes before retrying."
    assert "verdict" not in result


def test_supervision_does_not_inherit_ambient_mergen_approval_secrets(host):
    invoke(host, "mergen_supervise", {
        "root": "/workspace/project", "tasks_state": "tasks.json", "report": "report.json",
    })
    assert shlex.split(host.calls[0][1]["command"])[:5] == [
        "env", "-u", "MERGEN_SIGNING_KEY", "-u", "MERGEN_ACK_TOKEN",
    ]
