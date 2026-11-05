"""Native Hermes adapter for the separately installed Mergen CLI.

Execution belongs to Hermes' terminal tool, never to this module. The terminal
may be local, Docker, or SSH, so paths are lexical POSIX paths in that environment.
"""
from __future__ import annotations

import json
import shlex
from pathlib import Path
from typing import Any

_DEFAULT_TEST_TIMEOUT = 120
_DEFAULT_TIMEOUT = 180
_MAX_TIMEOUT = 300
_CONTEXT_KEYS = ("task_id", "session_id", "parent_agent")


def _path(value: Any, *, root: bool = False) -> str:
    if not isinstance(value, str) or not value or any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
        raise ValueError("Paths must be nonempty strings without control characters.")
    if "\\" in value:
        raise ValueError("Use POSIX paths in the selected Hermes terminal environment.")
    if root:
        if not value.startswith("/") or value.strip("/") == "":
            raise ValueError("root must be an absolute POSIX repository directory, not /.")
        clean = value.rstrip("/")
        parts = clean[1:].split("/")
    else:
        if value.startswith(("/", "-")):
            raise ValueError("Evidence paths must be repository-relative, not absolute paths or options.")
        clean = value
        parts = value.split("/")
    if any(part in ("", ".", "..") for part in parts):
        raise ValueError("Paths cannot contain empty, dot, or parent-directory segments.")
    return clean


def _seconds(args: dict[str, Any], key: str, default: int) -> int:
    value = args.get(key, default)
    if type(value) is not int or not 1 <= value <= _MAX_TIMEOUT:
        raise ValueError(f"{key} must be an integer from 1 to {_MAX_TIMEOUT} seconds.")
    return value


def _terminal_args(args: Any, *, supervise: bool) -> dict[str, Any]:
    if not isinstance(args, dict):
        raise ValueError("Arguments must be an object.")
    allowed = {"root", "tasks_state", "timeout", "report" if supervise else "test_timeout"}
    if set(args) - allowed:
        raise ValueError("Unknown argument. Only the documented fields are accepted.")
    root = _path(args.get("root"), root=True)
    tasks = root + "/" + _path(args.get("tasks_state"))
    timeout = _seconds(args, "timeout", _DEFAULT_TIMEOUT)
    command = (["env", "-u", "MERGEN_SIGNING_KEY", "-u", "MERGEN_ACK_TOKEN", "mergen-supervise"]
               if supervise else ["mergen"])
    if not supervise:
        command.append("verify")
    command.extend(["--root", root, "--tasks-state", tasks])
    if supervise:
        command.extend(["--report", root + "/" + _path(args.get("report"))])
    else:
        command.extend(["--test-timeout", str(_seconds(args, "test_timeout", _DEFAULT_TEST_TIMEOUT)),
                        "--strict", "--json"])
    return {"command": shlex.join(command), "workdir": root, "timeout": timeout, "background": False}


def _handler(ctx: Any, *, supervise: bool) -> Any:
    def run(args: dict[str, Any], **kwargs: Any) -> Any:
        try:
            terminal_args = _terminal_args(args, supervise=supervise)
        except ValueError as exc:
            return json.dumps({"error": str(exc)})
        context = {key: kwargs[key] for key in _CONTEXT_KEYS if key in kwargs}
        try:
            return ctx.dispatch_tool("terminal", terminal_args, **context)
        except Exception:
            # The dispatch may already have started. Do not retry or guess its outcome.
            return json.dumps({
                "error": "Terminal dispatch failed; execution outcome is unknown. Inspect Hermes before retrying."
            })
    return run


def _schema(name: str, *, supervise: bool) -> dict[str, Any]:
    properties: dict[str, Any] = {
        "root": {"type": "string", "description": "Operator-selected absolute POSIX repository root in terminal."},
        "tasks_state": {"type": "string", "description": "Repository-relative Mergen tasks-state JSON path."},
        "timeout": {"type": "integer", "minimum": 1, "maximum": _MAX_TIMEOUT, "default": _DEFAULT_TIMEOUT,
                    "description": "Host terminal wait budget. A background result is pending, never a pass."},
    }
    required = ["root", "tasks_state"]
    if supervise:
        properties["report"] = {
            "type": "string", "description": "Existing repository-relative report with SHA sidecar."
        }
        required.append("report")
        description = (
            "Independently reproduce an existing Mergen milestone report through Hermes terminal. "
            "Requires mergen-verdict 2.1.3 on terminal PATH. May execute project tests. "
            "Does not write decision files or authorize other actions. Return host denials and pending states honestly."
        )
    else:
        properties["test_timeout"] = {
            "type": "integer", "minimum": 1, "maximum": _MAX_TIMEOUT, "default": _DEFAULT_TEST_TIMEOUT,
            "description": "Per declared pytest task deadline. The whole run may take longer.",
        }
        description = (
            "Check declared completion claims against current files, Git and optional pytest tests through Hermes "
            "terminal. Requires mergen-verdict 2.1.3 on terminal PATH. Tests execute project code and may have side "
            "effects. Strict mode stays enabled. JSON report goes to stdout. This is not automatic enforcement."
        )
    return {"name": name, "description": description, "parameters": {
        "type": "object", "properties": properties, "required": required, "additionalProperties": False,
    }}


def register(ctx: Any) -> None:
    """Register only public Hermes surfaces, with no execution during loading."""
    for name, supervise in (("mergen_verify", False), ("mergen_supervise", True)):
        ctx.register_tool(name=name, toolset="mergen", schema=_schema(name, supervise=supervise),
                          handler=_handler(ctx, supervise=supervise))
    ctx.register_skill("verify-completion", Path(__file__).parent / "skills" / "verify-completion" / "SKILL.md",
                       description="Verify completion claims with Mergen and report evidence honestly.")
