"""End-to-end planted claims for the Hermes adapter demo."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def test_demo_catches_missing_file_and_failing_test_before_accepting_repair(tmp_path):
    root = Path(__file__).resolve().parents[1]
    script = root / "eval" / "hermes_demo.py"
    assert script.is_file(), "Reproducible Hermes demo has not been implemented"
    proc = subprocess.run([sys.executable, str(script), "--out", str(tmp_path)],
                          capture_output=True, text=True, timeout=90)
    if os.name == "nt":
        assert proc.returncode == 2
        assert "POSIX terminal required" in proc.stderr
        return
    assert proc.returncode == 0, proc.stdout + proc.stderr
    result = json.loads(proc.stdout)
    assert [(item["phase"], item["verdict"], item["exit_code"]) for item in result["runs"]] == [
        ("missing_file", "fail", 1), ("failing_test", "fail", 1), ("repaired", "pass", 0),
    ]
    assert result["scope"] == "Adapter contract and real Mergen CLI, not a live LLM session."
    assert len(list(tmp_path.glob("*.json"))) == 4
