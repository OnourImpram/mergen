#!/usr/bin/env python3
"""mergen pack validate: the Policy Pack SDK conformance check.

A domain policy pack (domains/<name>/pack.toml) is policy as data, loaded by the
Governor floor engine, never code it executes. This validates a pack against the
shape core/schemas/policy-pack.schema.json declares and against the invariants a
schema cannot express, so a third party can certify a pack before publishing it.

The checks:
  - name is present and equals the directory name
  - only the known raise-only fields appear, so a pack cannot smuggle a directive
    a future engine might misread as a downgrade (a pack can only RAISE the floor)
  - floor_all_content_changes is a boolean, safety_note a string,
    extra_high_trust_paths an array of non-empty strings
  - extra_high_trust_paths is a SINGLE-LINE array. The standard-library fallback
    reader used on Python 3.9 and 3.10 (where tomllib is absent) parses a
    single-line array only, so a multi-line one silently provides zero protected
    paths on those versions. This is the dominant pack defect, and validate
    refuses it on every host, not only where tomllib is missing.

Reuses scripts/project_config.py for the same fallback reader the engine uses, so
the certification and the runtime cannot disagree on what a pack parses to.

Tier 0: pure standard library. Exit codes: 0 a valid pack, 1 an invalid pack, 2
the target is not a directory.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

#: The only fields a pack may carry. Anything else is rejected, which is the
#: structural form of the raise-only guarantee.
_KNOWN_FIELDS = ("name", "floor_all_content_changes", "safety_note", "extra_high_trust_paths")

_MODS: dict[str, Any] = {}


def _load(name: str) -> Any:
    """Load a sibling scripts/<name>.py by path and cache it (scripts/ not a package)."""
    if name in _MODS:
        return _MODS[name]
    repo = Path(__file__).resolve().parent
    spec = importlib.util.spec_from_file_location(name, repo / f"{name}.py")
    if spec is None or spec.loader is None:  # pragma: no cover - import wiring
        raise ImportError(f"cannot load {name}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    _MODS[name] = mod
    return mod


def _is_multiline_array(text: str, key: str) -> bool:
    """True when key is assigned an array whose opening bracket has no closing one
    on the same line, the multi-line form the fallback reader cannot parse."""
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith(key) and "=" in line:
            value = line.split("=", 1)[1].strip()
            if value.startswith("[") and "]" not in value:
                return True
    return False


def validate_pack(pack_dir: Path) -> dict[str, Any]:
    """Validate one pack directory. Returns {"pass": bool, "errors": [...]}.

    Loads the pack with the same fallback reader the engine uses, and, when tomllib
    is available, cross-checks that the fallback recovers the same protected paths,
    so the single-line-array invariant is enforced on every host.
    """
    errors: list[str] = []
    toml_path = pack_dir / "pack.toml"
    if not toml_path.is_file():
        return {"pass": False, "errors": [f"no pack.toml in {pack_dir}"]}

    text = toml_path.read_text(encoding="utf-8")
    project_config = _load("project_config")
    fallback = project_config._parse_simple_toml(text)
    primary: dict[str, Any] | None
    try:
        import tomllib  # Python 3.11+
        primary = tomllib.loads(text)
    except ModuleNotFoundError:
        primary = None
    except Exception as exc:  # noqa: BLE001 - a malformed pack is an invalid pack
        return {"pass": False, "errors": [f"pack.toml is not valid TOML: {exc}"]}

    parsed = primary if primary is not None else fallback

    name = parsed.get("name")
    if not isinstance(name, str) or not name:
        errors.append("missing or non-string 'name'")
    elif name != pack_dir.name:
        errors.append(f"name {name!r} does not match the directory name {pack_dir.name!r}")

    for key in parsed:
        if key not in _KNOWN_FIELDS:
            errors.append(f"unknown field {key!r} (a pack carries only the raise-only fields)")

    if "floor_all_content_changes" in parsed and not isinstance(
            parsed["floor_all_content_changes"], bool):
        errors.append("floor_all_content_changes must be a boolean")
    if "safety_note" in parsed and not isinstance(parsed["safety_note"], str):
        errors.append("safety_note must be a string")
    if "extra_high_trust_paths" in parsed:
        paths = parsed["extra_high_trust_paths"]
        if not isinstance(paths, list) or not all(isinstance(p, str) and p for p in paths):
            errors.append("extra_high_trust_paths must be an array of non-empty strings")

    # The single-line-array invariant, checked on every host.
    if _is_multiline_array(text, "extra_high_trust_paths"):
        errors.append("extra_high_trust_paths spans multiple lines, which the 3.9 and "
                      "3.10 fallback reader cannot parse (use a single-line array)")
    elif primary is not None and fallback.get("extra_high_trust_paths") != primary.get(
            "extra_high_trust_paths"):
        errors.append("extra_high_trust_paths is not recoverable by the 3.9 and 3.10 "
                      "fallback reader, so it would provide zero protection there")

    return {"pass": not errors, "errors": errors}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Validate a mergen domain policy pack (the Policy Pack SDK check).")
    sub = ap.add_subparsers(dest="command", required=True)
    pv = sub.add_parser("validate", help="validate a domain pack directory")
    pv.add_argument("pack_dir", help="a domains/<name>/ directory containing pack.toml")

    args = ap.parse_args(argv)
    pack_dir = Path(args.pack_dir)
    if not pack_dir.is_dir():
        print(f"error: not a directory: {pack_dir}", file=sys.stderr)
        return 2
    result = validate_pack(pack_dir)
    print(json.dumps(result, indent=2))
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
