"""m5: build_native.py honors --hooks-dir so a build can target a sandbox
instead of the real ~/.claude/hooks. This is what lets CI run a real (non-dry)
native build without writing into the runner's home directory."""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "dist" / "native"))

import build_native  # noqa: E402


def test_build_copies_hooks_into_explicit_hooks_dir(tmp_path):
    skills_dir = tmp_path / "skills"
    hooks_dir = tmp_path / "hooks"
    rc = build_native.cmd_build(skills_dir, hooks_dir, dry_run=False)
    assert rc == 0
    # Every source hook landed in the sandbox hooks dir, not in ~/.claude.
    src_hooks = sorted((REPO / "core" / "hooks").glob("*.py"))
    assert src_hooks, "expected at least one source hook to exist"
    for h in src_hooks:
        assert (hooks_dir / h.name).is_file()
    # And the skills were rendered into the sandbox skills dir.
    assert any(skills_dir.glob("mergen-*/SKILL.md"))


def test_dry_run_writes_nothing(tmp_path):
    skills_dir = tmp_path / "skills"
    hooks_dir = tmp_path / "hooks"
    rc = build_native.cmd_build(skills_dir, hooks_dir, dry_run=True)
    assert rc == 0
    assert not any(skills_dir.glob("mergen-*/SKILL.md")) if skills_dir.exists() else True
    assert not hooks_dir.exists()
