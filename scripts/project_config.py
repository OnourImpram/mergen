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
fixed shape above is used instead (string, boolean, and single-line array
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
    is a quoted string, a boolean, or a single-line array of quoted strings.
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
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [_unquote(item.strip()) for item in inner.split(",") if item.strip()]
    if value in ("true", "false"):
        return value == "true"
    return _unquote(value)


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


def apply_overlay(
    base_decision: dict[str, Any],
    config: dict[str, Any],
    changed_paths: list[str],
) -> dict[str, Any]:
    """Raise a base floor decision per the project config. Never lowers it.

    Returns a new decision dict with the possibly-raised tier, the merged
    trigger list, and the active domain (or None).
    """
    triggers = list(base_decision.get("triggers_matched", []))
    base_tier = base_decision.get("tier", "tiny")

    governor = config.get("governor")
    extra_paths = []
    if isinstance(governor, dict):
        candidate = governor.get("extra_high_trust_paths")
        if isinstance(candidate, list):
            extra_paths = [str(p) for p in candidate]

    if extra_paths:
        for raw in changed_paths:
            norm = raw.replace("\\", "/").lower()
            if any(_path_matches(norm, p) for p in extra_paths):
                if "project-protected-path" not in triggers:
                    triggers.append("project-protected-path")
                break

    domain = str(config.get("domain") or "").strip().lower()
    overlay = DOMAIN_OVERLAYS.get(domain)
    if overlay and overlay.get("floor_all_content_changes") and changed_paths:
        tag = f"domain:{domain}"
        if tag not in triggers:
            triggers.append(tag)

    tier = "high-trust" if triggers else base_tier
    return {
        "tier": tier,
        "triggers_matched": triggers,
        "domain": domain or None,
    }
