"""Test that the native settings patcher (dist/native/patch_settings_hooks.py) is
BOM-safe: it tolerates a UTF-8 BOM in settings.json and preserves it on write.

This is one half of the inherited Wave-E defect fix. The other half, the
effort-mode patcher, is covered in test_patch_settings.

Loaded by file path because dist/native/ is not an importable package.
"""

import importlib.util
import json
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
_BOM = b"\xef\xbb\xbf"


def _load(rel_path: str):
    path = REPO / rel_path
    spec = importlib.util.spec_from_file_location(path.stem.replace("-", "_"), path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_native_patcher_is_bom_safe(tmp_path):
    mod = _load("dist/native/patch_settings_hooks.py")
    settings = tmp_path / "settings.json"
    settings.write_bytes(_BOM + b'{"hooks": {}}\n')
    # load tolerates the BOM and remembers it
    data, had_bom, err = mod.load_settings(settings)
    assert err == "" and had_bom is True and isinstance(data, dict)
    # install writes back and preserves the BOM
    assert mod.main(["--settings", str(settings), "--python", "python"]) == 0
    raw = settings.read_bytes()
    assert raw.startswith(_BOM), "BOM was not preserved"
    json.loads(raw.decode("utf-8-sig"))
