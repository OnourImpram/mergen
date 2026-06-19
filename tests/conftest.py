"""Shared pytest fixtures for mergen tests.

The critical fixture is `home_dir`: it monkeypatches pathlib.Path.home()
to return a temporary directory so tests never read from or write to the
real ~/.claude directory.
"""

import sys
from pathlib import Path

import pytest

# After the v1 reorg the effort-mode hook and patcher live under effort-mode/.
# Put that directory on sys.path so `import hooks.mergen_prompt_hook` and
# `import scripts.patch_settings` resolve to the effort-mode copies.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "effort-mode"))


@pytest.fixture()
def home_dir(tmp_path, monkeypatch):
    """Return a tmp_path standing in for Path.home().

    Creates the .claude subdirectory structure expected by both the hook
    and the patcher.  Monkeypatches Path.home() in both modules so the
    real ~/.claude is never touched.
    """
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    (fake_home / ".claude").mkdir()
    (fake_home / ".claude" / "commands").mkdir()
    (fake_home / ".claude" / "hooks").mkdir()

    monkeypatch.setattr(Path, "home", staticmethod(lambda: fake_home))
    return fake_home
