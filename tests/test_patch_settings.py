"""Unit tests for effort-mode/scripts/patch_settings.py."""

import importlib
import json
import sys
from pathlib import Path


def _run_patcher(home_dir: Path, args: list) -> int:
    """Run patch_settings.main() with the given CLI args. Returns exit code."""
    import scripts.patch_settings as ps
    importlib.reload(ps)

    old_argv = sys.argv
    sys.argv = ["patch_settings.py"] + args
    try:
        return ps.main()
    finally:
        sys.argv = old_argv


def _settings_path(home_dir: Path) -> Path:
    return home_dir / ".claude" / "settings.json"


def _has_hook_entry(home_dir: Path) -> bool:
    p = _settings_path(home_dir)
    if not p.is_file():
        return False
    data = json.loads(p.read_text())
    for entry in data.get("hooks", {}).get("UserPromptSubmit", []):
        for h in entry.get("hooks", []):
            if "mergen_prompt_hook.py" in (h.get("command") or ""):
                return True
    return False


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_fresh_install_creates_settings(home_dir):
    """Fresh install (no settings.json) creates file with hook entry."""
    rc = _run_patcher(home_dir, ["--python", sys.executable])
    assert rc == 0
    assert _settings_path(home_dir).is_file()
    assert _has_hook_entry(home_dir)


def test_idempotent_double_install(home_dir):
    """Running install twice does not duplicate the hook entry."""
    _run_patcher(home_dir, ["--python", sys.executable])
    _run_patcher(home_dir, ["--python", sys.executable])

    data = json.loads(_settings_path(home_dir).read_text())
    ups = data.get("hooks", {}).get("UserPromptSubmit", [])
    mergen_entries = [
        e for e in ups
        if any("mergen_prompt_hook.py" in (h.get("command") or "")
               for h in e.get("hooks", []))
    ]
    assert len(mergen_entries) == 1


def test_install_then_remove(home_dir):
    """Install then remove: entry gone, empty containers pruned."""
    _run_patcher(home_dir, ["--python", sys.executable])
    assert _has_hook_entry(home_dir)

    _run_patcher(home_dir, ["--remove"])
    assert not _has_hook_entry(home_dir)

    data = json.loads(_settings_path(home_dir).read_text())
    assert "hooks" not in data or not data["hooks"]


def test_existing_other_hooks_untouched(home_dir):
    """Install does not remove other hook entries."""
    existing = {
        "hooks": {
            "UserPromptSubmit": [
                {"hooks": [{"type": "command", "command": "other_tool.py", "timeout": 5}]}
            ]
        }
    }
    _settings_path(home_dir).write_text(json.dumps(existing), encoding="utf-8")

    _run_patcher(home_dir, ["--python", sys.executable])

    data = json.loads(_settings_path(home_dir).read_text())
    ups = data["hooks"]["UserPromptSubmit"]
    commands = [
        h.get("command", "")
        for e in ups
        for h in e.get("hooks", [])
    ]
    assert any("other_tool.py" in c for c in commands), "Other hook was removed"
    assert any("mergen_prompt_hook.py" in c for c in commands), "Mergen hook missing"


def test_invalid_json_aborts(home_dir):
    """Invalid JSON in settings.json -> exits 1, file unchanged."""
    bad_content = "NOT JSON {{{"
    _settings_path(home_dir).write_text(bad_content, encoding="utf-8")

    rc = _run_patcher(home_dir, ["--python", sys.executable])
    assert rc == 1
    assert _settings_path(home_dir).read_text() == bad_content


def test_non_dict_root_aborts(home_dir):
    """settings.json root is a list -> exits 1."""
    _settings_path(home_dir).write_text("[]", encoding="utf-8")
    rc = _run_patcher(home_dir, ["--python", sys.executable])
    assert rc == 1


def test_status_exits_0_when_installed(home_dir):
    """--status exits 0 when hook entry is present."""
    _run_patcher(home_dir, ["--python", sys.executable])
    rc = _run_patcher(home_dir, ["--status"])
    assert rc == 0


def test_status_exits_1_when_not_installed(home_dir):
    """--status exits 1 when hook entry is absent."""
    rc = _run_patcher(home_dir, ["--status"])
    assert rc == 1


def test_effort_patcher_is_bom_safe(home_dir):
    """A UTF-8 BOM in settings.json is tolerated on read and preserved on write.

    The effort-mode half of the inherited Wave-E defect fix; the native half is
    in test_patch_settings_hooks.
    """
    import scripts.patch_settings as ps
    importlib.reload(ps)
    bom = b"\xef\xbb\xbf"
    settings = _settings_path(home_dir)
    settings.write_bytes(bom + b'{"hooks": {}}\n')
    data, had_bom, err = ps._load_settings()
    assert err == "" and had_bom is True
    assert _run_patcher(home_dir, ["--python", "python"]) == 0
    raw = settings.read_bytes()
    assert raw.startswith(bom), "BOM was not preserved"
    json.loads(raw.decode("utf-8-sig"))
