#!/usr/bin/env python3
"""Idempotently register, remove, or check mergen's SDD hooks in settings.json.

Registers two hooks (see core/hooks/):
  - verify_gate.py        -> PostToolUse (matcher: Write|Edit|MultiEdit)
  - constitution_inject.py -> UserPromptSubmit

Safety properties (mirrors effort-mode/scripts/patch_settings.py, the proven
pattern):
  - Creates settings.json if missing.
  - Never clobbers other hooks or unrelated settings.
  - Idempotent: re-running install does not create duplicate entries (it drops
    any prior entry for the same hook basename before re-adding).
  - Refuses to write if the existing file is not valid JSON (avoids corruption).
  - Matches entries by hook script BASENAME substring, so the python path can
    change between installs without leaving duplicates behind.

This patcher is deliberately decoupled from the live ~/.claude/settings.json via
--settings, so it can be tested against a throwaway file.

Usage:
  patch_settings_hooks.py --python "/path/to/python"        # install both hooks
  patch_settings_hooks.py --remove                           # uninstall both
  patch_settings_hooks.py --status                           # exit 0 iff BOTH present
  patch_settings_hooks.py --settings /tmp/s.json [...]       # operate on a custom file
  patch_settings_hooks.py --dry-run [...]                    # print result, do not write
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# event -> matcher (None means no matcher field, applies to all)
HOOKS = [
    {"basename": "verify_gate.py", "event": "PostToolUse", "matcher": "Write|Edit|MultiEdit"},
    {"basename": "constitution_inject.py", "event": "UserPromptSubmit", "matcher": None},
]


def hook_command(python_exe: str, basename: str) -> str:
    py = python_exe.replace("\\", "/")
    hk = str(Path.home() / ".claude" / "hooks" / basename).replace("\\", "/")
    return f'"{py}" "{hk}"'


def entry_has_basename(entry: dict, basename: str) -> bool:
    if not isinstance(entry, dict):
        return False
    for h in entry.get("hooks", []) or []:
        if isinstance(h, dict) and basename in (h.get("command") or ""):
            return True
    return False


def _read_text_bom(path: Path):
    """Read text, tolerating and remembering a UTF-8 BOM (Claude Code on Windows
    sometimes writes one). Returns (text, had_bom)."""
    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw[3:].decode("utf-8"), True
    return raw.decode("utf-8"), False


def load_settings(path: Path):
    """Return (data, had_bom, error_message). error_message is empty on success."""
    if not path.is_file():
        return {}, False, ""
    try:
        text, had_bom = _read_text_bom(path)
        data = json.loads(text)
    except Exception as exc:
        return None, False, f"{path} is not valid JSON ({exc})"
    if not isinstance(data, dict):
        return None, False, "settings.json root is not a JSON object"
    return data, had_bom, ""


def status(path: Path) -> int:
    data, _had_bom, err = load_settings(path)
    if err:
        print(f"absent (could not read settings: {err})")
        return 1
    hooks = data.get("hooks", {}) if isinstance(data.get("hooks"), dict) else {}
    all_present = True
    for spec in HOOKS:
        lst = hooks.get(spec["event"], [])
        present = isinstance(lst, list) and any(
            entry_has_basename(e, spec["basename"]) for e in lst
        )
        print(f"{'present' if present else 'absent '}: {spec['basename']} on {spec['event']}")
        all_present = all_present and present
    return 0 if all_present else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--python", default="python3", help="python executable to run the hooks")
    ap.add_argument("--remove", action="store_true", help="remove the hooks instead of adding")
    ap.add_argument("--status", action="store_true", help="read-only: exit 0 iff both hooks present")
    ap.add_argument("--settings", default=str(Path.home() / ".claude" / "settings.json"),
                    help="settings.json path (default: ~/.claude/settings.json)")
    ap.add_argument("--dry-run", action="store_true", help="print the result, do not write")
    args = ap.parse_args(argv)

    settings_path = Path(args.settings)

    if args.status:
        return status(settings_path)

    data, had_bom, err = load_settings(settings_path)
    if err:
        print(f"ERROR: {err}. Aborting so your settings are not corrupted.", file=sys.stderr)
        return 1

    hooks = data.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        print("ERROR: settings.json 'hooks' is not an object. Aborting.", file=sys.stderr)
        return 1

    for spec in HOOKS:
        event, basename, matcher = spec["event"], spec["basename"], spec["matcher"]
        lst = hooks.setdefault(event, [])
        if not isinstance(lst, list):
            print(f"ERROR: settings.json 'hooks.{event}' is not an array. Aborting.", file=sys.stderr)
            return 1
        # Drop prior entries for this hook (idempotent install, clean uninstall).
        lst[:] = [e for e in lst if not entry_has_basename(e, basename)]
        if not args.remove:
            entry = {"hooks": [{"type": "command",
                                "command": hook_command(args.python, basename),
                                "timeout": 5}]}
            if matcher is not None:
                entry = {"matcher": matcher, **entry}
            lst.append(entry)
        if not lst:
            hooks.pop(event, None)

    if not hooks:
        data.pop("hooks", None)

    rendered = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    if had_bom:
        rendered = chr(0xFEFF) + rendered
    if args.dry_run:
        print(rendered, end="")
        return 0

    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(rendered, encoding="utf-8")
    print(f"{'removed' if args.remove else 'installed'} mergen SDD hooks in {settings_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
