#!/usr/bin/env python3
"""Reproducible adapter-to-CLI demo, not a live Hermes LLM session."""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]


def _run(argv: list[str], root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, cwd=root, capture_output=True, text=True, timeout=60, check=False)


def _git(root: Path, *args: str) -> None:
    proc = _run(["git", *args], root)
    if proc.returncode:
        raise RuntimeError(proc.stderr)


class DemoHost:
    """Explicit test harness. Real plugin runtime delegates to Hermes instead."""

    def __init__(self) -> None:
        self.handlers: dict[str, Any] = {}

    def register_tool(self, **kwargs: Any) -> None:
        self.handlers[kwargs["name"]] = kwargs["handler"]

    def register_skill(self, name: str, path: Path, description: str = "") -> None:
        if not path.is_file():
            raise ValueError("Bundled skill is absent")

    def dispatch_tool(self, name: str, args: dict[str, Any], **kwargs: Any) -> str:
        if name != "terminal":
            raise ValueError("Demo only accepts terminal dispatch")
        command = shlex.split(args["command"])
        if command[:2] != ["mergen", "verify"]:
            raise ValueError("Demo only accepts the fixed verification command")
        # Run the checked-out CLI through this test's interpreter, not arbitrary PATH content.
        command = [sys.executable, str(REPO / "mergen_cli.py"), *command[1:]]
        proc = _run(command, Path(args["workdir"]))
        return json.dumps({"output": proc.stdout, "stderr": proc.stderr, "exit_code": proc.returncode})


def run_demo(output_dir: Path) -> dict[str, Any]:
    spec = importlib.util.spec_from_file_location("mergen_hermes_demo", REPO / "integrations/hermes/__init__.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("Plugin could not be loaded")
    plugin = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(plugin)
    host = DemoHost()
    plugin.register(host)
    output_dir.mkdir(parents=True, exist_ok=True)
    runs: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="mergen-hermes-demo-") as directory:
        root = Path(directory)
        _git(root, "init", "-q")
        _git(root, "config", "user.name", "Mergen Demo")
        _git(root, "config", "user.email", "demo@example.invalid")
        (root / ".gitignore").write_text("__pycache__/\n.pytest_cache/\n", encoding="utf-8")
        (root / "test_greeting.py").write_text(
            "from greeting import greet\n\ndef test_greeting():\n    assert greet('Hermes') == 'Hello, Hermes!'\n",
            encoding="utf-8",
        )
        (root / "tasks-state.json").write_text(json.dumps({
            "schema_version": "1.0", "feature_id": "hermes-demo",
            "tasks": [{"id": "T001", "status": "done", "files": ["greeting.py"],
                       "test_task": "test_greeting.py"}],
        }), encoding="utf-8")
        _git(root, "add", ".")
        _git(root, "commit", "-qm", "Declare a completion claim with a missing implementation")
        phases = [
            ("missing_file", None, "fail", 1),
            ("failing_test", "def greet(name):\n    return 'Hello!'\n", "fail", 1),
            ("repaired", "def greet(name):\n    return f'Hello, {name}!'\n", "pass", 0),
        ]
        for phase, implementation, expected_verdict, expected_exit in phases:
            if implementation is not None:
                (root / "greeting.py").write_text(implementation, encoding="utf-8")
                _git(root, "add", "greeting.py")
                _git(root, "commit", "-qm", phase)
            response = json.loads(host.handlers["mergen_verify"]({
                "root": str(root), "tasks_state": "tasks-state.json", "test_timeout": 20,
            }))
            report = json.loads(response["output"])
            verdict = report["summary"]["verdict"]
            if verdict != expected_verdict or response["exit_code"] != expected_exit:
                raise RuntimeError(f"Unexpected demo result in {phase}: {response}")
            (output_dir / f"{phase}.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
            runs.append({"phase": phase, "verdict": verdict, "exit_code": response["exit_code"],
                         "failures": report["tasks"][0]["failures"]})
    result = {"scope": "Adapter contract and real Mergen CLI, not a live LLM session.", "runs": runs}
    (output_dir / "summary.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path, help="Directory for synthetic demo reports")
    args = parser.parse_args()
    if os.name == "nt":
        parser.error("POSIX terminal required. Run this demo in WSL, Linux or macOS.")
    # Prevent repository test code from writing Python bytecode in the fixture.
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    print(json.dumps(run_demo(args.out), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
