#!/usr/bin/env python3
"""Idempotently add, remove, or check the mergen UserPromptSubmit hook in
~/.claude/settings.json.

- Creates settings.json if missing.
- Never clobbers other hooks or settings.
- Idempotent: re-running install does not create duplicate entries.
- Refuses to write if the existing file is not valid JSON (avoids corruption).

Usage:
  patch_settings.py --python "/path/to/python"   # install
  patch_settings.py --remove                      # uninstall
  patch_settings.py --status                      # read-only: exits 0 if installed, 1 if not
"""

import argparse
import json
import sys
from pathlib import Path

HOOK_BASENAME = "mergen_prompt_hook.py"


def hook_command(python_exe: str) -> str:
    py = python_exe.replace("\\", "/")
    hk = str(Path.home() / ".claude" / "hooks" / "mergen_prompt_hook.py").replace("\\", "/")
    return f'"{py}" "{hk}"'


def is_mergen_entry(entry: dict) -> bool:
    if not isinstance(entry, dict):
        return False
    for h in entry.get("hooks", []):
        if isinstance(h, dict) and HOOK_BASENAME in (h.get("command") or ""):
            return True
    return False


def _read_text_bom(path: Path):
    """Read text, tolerating and remembering a UTF-8 BOM. Returns (text, had_bom)."""
    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw[3:].decode("utf-8"), True
    return raw.decode("utf-8"), False


def _load_settings() -> tuple:
    """Return (parsed_data, had_bom, error_message). error_message is empty on success."""
    settings = Path.home() / ".claude" / "settings.json"
    if not settings.is_file():
        return {}, False, ""
    try:
        text, had_bom = _read_text_bom(settings)
        data = json.loads(text)
    except Exception as exc:
        return None, False, f"{settings} is not valid JSON ({exc})"
    if not isinstance(data, dict):
        return None, False, "settings.json root is not a JSON object"
    return data, had_bom, ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--python", default="python3", help="python executable to run the hook")
    ap.add_argument("--remove", action="store_true", help="remove the hook instead of adding it")
    ap.add_argument("--status", action="store_true", help="read-only check: exits 0 if installed, 1 if not")
    args = ap.parse_args()

    settings_path = Path.home() / ".claude" / "settings.json"

    # --status: read-only inspection
    if args.status:
        data, _had_bom, err = _load_settings()
        if err:
            print(f"absent (could not read settings: {err})")
            return 1
        ups = data.get("hooks", {}).get("UserPromptSubmit", [])
        if any(is_mergen_entry(e) for e in ups):
            print("present: mergen UserPromptSubmit hook is registered")
            return 0
        else:
            print("absent: mergen UserPromptSubmit hook is not registered")
            return 1

    data, had_bom, err = _load_settings()
    if err:
        print(f"ERROR: {err}. Aborting so your settings are not corrupted.", file=sys.stderr)
        return 1

    hooks = data.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        print("ERROR: settings.json 'hooks' is not an object. Aborting.", file=sys.stderr)
        return 1
    ups = hooks.setdefault("UserPromptSubmit", [])
    if not isinstance(ups, list):
        print("ERROR: settings.json 'hooks.UserPromptSubmit' is not an array. Aborting.", file=sys.stderr)
        return 1

    # Drop any prior mergen entries first (makes install idempotent and uninstall clean).
    ups[:] = [e for e in ups if not is_mergen_entry(e)]

    if not args.remove:
        ups.append({"hooks": [{"type": "command", "command": hook_command(args.python), "timeout": 5}]})

    # Prune empty containers we may have created.
    if not ups:
        hooks.pop("UserPromptSubmit", None)
    if not hooks:
        data.pop("hooks", None)

    rendered = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    if had_bom:
        rendered = chr(0xFEFF) + rendered
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(rendered, encoding="utf-8")
    print(f"{'removed' if args.remove else 'installed'} mergen UserPromptSubmit hook in {settings_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
