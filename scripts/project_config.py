#!/usr/bin/env python3
"""Per-project mergen config and the domain overlay on the Governor floor.

A project may carry a `.specify/mergen.toml` that raises the deterministic
Governor floor for that project. Two levers:

  domain = "clinical"
      Activates a domain overlay. In a clinical project any change is treated
      as content-bearing and floored to high-trust, mirroring govern.md: a
      domain mode sets the floor to high-trust and the floor is non-downgradable.

  [governor]
  extra_high_trust_paths = ["src/billing/", "*.env"]
      Project-specific paths that force high-trust, beyond the built-in path
      triggers in governor_floor.py.

The overlay can only RAISE the floor, never lower it, exactly like the built-in
classifier. A malformed or absent config yields no overlay, so the built-in
floor still applies. The full TOML grammar is read with tomllib on Python 3.11+.
On 3.9 and 3.10, where tomllib is absent, a deterministic reader for the small
fixed shape above is used instead (string, boolean, number, and single-line array
values, section headers, and whole-line comments).

Stdlib only. Deterministic and side-effect free.
"""

from __future__ import annotations

import fnmatch
from pathlib import Path
from typing import Any

# Domain name -> overlay behavior. A domain that floors all content changes
# raises any non-empty change set to high-trust. New domains are added here.
DOMAIN_OVERLAYS: dict[str, dict[str, Any]] = {
    "clinical": {"floor_all_content_changes": True},
}

# Built-in domain packs live here. A pack is a shareable bundle of a domain's
# floor behavior, protected paths, and safety note, so a domain is data, not
# code. A pack's values take precedence over the built-in DOMAIN_OVERLAYS above.
_PACKS_DIR = Path(__file__).resolve().parents[1] / "domains"


# --------------------------------------------------------------------------- #
# Loading
# --------------------------------------------------------------------------- #

def load_config(path: Path) -> dict[str, Any]:
    """Load a mergen.toml into a dict. Absent or unparseable yields {}.

    Failing safe to {} can only fail to RAISE the floor, never lower it, so a
    broken config cannot weaken protection.
    """
    if not path.is_file():
        return {}
    text = path.read_text(encoding="utf-8")
    try:
        import tomllib  # Python 3.11+
        return tomllib.loads(text)
    except ModuleNotFoundError:
        return _parse_simple_toml(text)
    except Exception:
        return {}


def _parse_simple_toml(text: str) -> dict[str, Any]:
    """Deterministic reader for the small fixed shape mergen.toml uses.

    Handles whole-line comments, [section] headers, and key = value where value
    is a quoted string, a boolean, a bare number, or a single-line array of those.
    Inline comments are stripped only on lines that contain no quote character,
    which is sufficient for this fixed shape. Not a general TOML parser.
    """
    root: dict[str, Any] = {}
    current = root
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if '"' not in line and "'" not in line and "#" in line:
            line = line.split("#", 1)[0].strip()
            if not line:
                continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1].strip()
            current = root.setdefault(section, {})
            if not isinstance(current, dict):
                current = root[section] = {}
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        current[key.strip()] = _parse_value(value.strip())
    return root


def _parse_value(value: str) -> Any:
    if value.startswith("["):
        # An inline comment can follow the closing bracket on an array line. Cut at
        # the last bracket so a single-line array with a trailing comment still
        # parses to a list, rather than degrading to a raw string the overlay would
        # silently ignore (which on 3.9 and 3.10 would mean zero protection).
        rbracket = value.rfind("]")
        if rbracket != -1:
            value = value[: rbracket + 1]
        if value.endswith("]"):
            inner = value[1:-1].strip()
            if not inner:
                return []
            return [_parse_scalar(item.strip()) for item in inner.split(",") if item.strip()]
    return _parse_scalar(value)


def _parse_scalar(value: str) -> Any:
    """Type a single TOML scalar the way tomllib would, for the fixed shape.

    A quoted token is a string, true/false is a boolean, a bare numeric token is an
    integer or float, and anything else falls back to the unquoted text. Typing bare
    numbers rather than leaving them as strings keeps this reader faithful to tomllib,
    so a pack validates identically on 3.9 and 3.10 as on 3.11. Without it a numeric
    value would read as a string here and as a number under tomllib, and the conformance
    check would accept on the weakest host what it rejects on the strongest.
    """
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1]
    if value in ("true", "false"):
        return value == "true"
    number = _as_number(value)
    if number is not None:
        return number
    return _unquote(value)


def _as_number(value: str) -> int | float | None:
    """Parse a bare integer or float token, or None when the token is not numeric."""
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        return None


def _unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1]
    return value


# --------------------------------------------------------------------------- #
# Overlay
# --------------------------------------------------------------------------- #

def _path_matches(norm_path: str, pattern: str) -> bool:
    """True when a normalised path matches a pattern by glob or directory prefix."""
    pat = pattern.replace("\\", "/").lower()
    if pat.endswith("/"):
        return norm_path.startswith(pat)
    return fnmatch.fnmatch(norm_path, pat) or norm_path.startswith(pat)


def load_domain_pack(name: str, packs_dir: Path | None = None) -> dict[str, Any]:
    """Load a domain pack (domains/<name>/pack.toml). Absent yields {}."""
    if not name:
        return {}
    base = Path(packs_dir) if packs_dir is not None else _PACKS_DIR
    return load_config(base / name / "pack.toml")


def apply_overlay(
    base_decision: dict[str, Any],
    config: dict[str, Any],
    changed_paths: list[str],
    packs_dir: Path | None = None,
) -> dict[str, Any]:
    """Raise a base floor decision per the project config and its domain pack.

    Never lowers the tier. Returns a new decision dict with the possibly-raised
    tier, the merged trigger list, the active domain (or None), and the domain
    pack's safety note when one applies.
    """
    triggers = list(base_decision.get("triggers_matched", []))
    base_tier = base_decision.get("tier", "tiny")

    domain = str(config.get("domain") or "").strip().lower()
    pack = load_domain_pack(domain, packs_dir) if domain else {}

    # Protected paths come from both the project config and the domain pack.
    extra_paths: list[str] = []
    governor = config.get("governor")
    if isinstance(governor, dict) and isinstance(governor.get("extra_high_trust_paths"), list):
        extra_paths += [str(p) for p in governor["extra_high_trust_paths"]]
    if isinstance(pack.get("extra_high_trust_paths"), list):
        extra_paths += [str(p) for p in pack["extra_high_trust_paths"]]

    if extra_paths:
        for raw in changed_paths:
            norm = raw.replace("\\", "/").lower()
            if any(_path_matches(norm, p) for p in extra_paths):
                if "project-protected-path" not in triggers:
                    triggers.append("project-protected-path")
                break

    # The pack's floor wins; fall back to the built-in overlay for the domain.
    floor_all = bool(pack.get("floor_all_content_changes")) or bool(
        DOMAIN_OVERLAYS.get(domain, {}).get("floor_all_content_changes")
    )
    # A floor-all domain raises any NON-EMPTY change set to high-trust. An empty change set is
    # not a change, so there is nothing to floor and the base tier stands. The gate always
    # classifies a real diff (a non-empty path list), so the empty case is a no-op invocation
    # with no input, not a content change that slips through.
    if domain and floor_all and changed_paths:
        tag = f"domain:{domain}"
        if tag not in triggers:
            triggers.append(tag)

    tier = "high-trust" if triggers else base_tier
    result: dict[str, Any] = {
        "tier": tier,
        "triggers_matched": triggers,
        "domain": domain or None,
    }
    note = pack.get("safety_note")
    if domain and isinstance(note, str) and note:
        result["safety_note"] = note
    return result
