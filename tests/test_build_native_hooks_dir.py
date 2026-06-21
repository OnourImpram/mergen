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


def test_cmd_build_with_none_hooks_dir_writes_no_hooks(tmp_path):
    # None means "no hooks target": skills render, hooks are skipped entirely.
    skills_dir = tmp_path / "skills"
    rc = build_native.cmd_build(skills_dir, None, dry_run=False)
    assert rc == 0
    assert any(skills_dir.glob("mergen-*/SKILL.md"))
    assert not (tmp_path / "hooks").exists()


def _patch_home(monkeypatch, fake_home: Path) -> None:
    # Patch the module-local seam, not the global pathlib.Path class, so the mock
    # is confined to build_native and is safe under a parallel test runner.
    monkeypatch.setattr(build_native, "_claude_home", lambda: fake_home / ".claude")


def test_custom_skills_dir_does_not_write_global_hooks(tmp_path, monkeypatch):
    # The Codex P1: `build --skills-dir <scratch>` must not write hooks into the
    # global ~/.claude/hooks. This pins the isolation as a regression test.
    fake_home = tmp_path / "home"
    _patch_home(monkeypatch, fake_home)
    skills = tmp_path / "scratch-skills"
    rc = build_native.main(["build", "--skills-dir", str(skills)])
    assert rc == 0
    assert (skills / "mergen-go" / "SKILL.md").is_file()
    assert not (fake_home / ".claude" / "hooks").exists()


def test_default_build_installs_hooks_globally(tmp_path, monkeypatch):
    # The installer path: a fully-default build still copies hooks to the global
    # ~/.claude/hooks, so isolating a custom skills-dir did not break install.
    fake_home = tmp_path / "home"
    _patch_home(monkeypatch, fake_home)
    rc = build_native.main(["build"])
    assert rc == 0
    hooks = fake_home / ".claude" / "hooks"
    assert hooks.is_dir()
    assert sorted(p.name for p in hooks.glob("*.py"))


def test_explicit_hooks_dir_overrides_isolation(tmp_path, monkeypatch):
    # A custom skills-dir plus an explicit --hooks-dir installs to that hooks
    # dir, and still never touches the global one.
    fake_home = tmp_path / "home"
    _patch_home(monkeypatch, fake_home)
    skills = tmp_path / "s"
    hooks = tmp_path / "h"
    rc = build_native.main(["build", "--skills-dir", str(skills), "--hooks-dir", str(hooks)])
    assert rc == 0
    assert (skills / "mergen-go" / "SKILL.md").is_file()
    assert sorted(p.name for p in hooks.glob("*.py"))
    assert not (fake_home / ".claude" / "hooks").exists()


def test_no_hooks_flag_skips_global_install(tmp_path, monkeypatch):
    # --no-hooks suppresses hooks even on an otherwise-default build.
    fake_home = tmp_path / "home"
    _patch_home(monkeypatch, fake_home)
    rc = build_native.main(["build", "--no-hooks"])
    assert rc == 0
    assert not (fake_home / ".claude" / "hooks").exists()
