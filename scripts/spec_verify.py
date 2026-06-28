#!/usr/bin/env python3
"""Critical-path hook verifier for Mergen.

Mirrors mneme's ``tools/spec_verify.py``: AST-parses every hook module
that runs on the live session path and fails if any imports a forbidden
network or LLM client library without an inline ``# pragma: no cover
(offline-only)`` suppression comment.

Mergen's hooks are reinforcement nudges, not enforcement (the README and
MERGEN.md are explicit about this). But they still run on every
UserPromptSubmit, PostToolUse, Stop, PreCompact, and SessionEnd event.
A hook that secretly imported ``anthropic`` or ``requests`` could leak
session content to a third party or add latency to the critical path.
This script is the CI gate that refuses that drift.

Exit codes:
  0 - all critical hooks clean.
  1 - one or more forbidden imports detected.
  2 - usage error (no hooks directory or unreadable file).

Usage:
  python scripts/spec_verify.py            # verify all critical hooks
  python scripts/spec_verify.py --gate     # same, explicit CI mode

The ``--gate`` flag is accepted for symmetry with mneme but has no
behavioral effect: the script always exits non-zero on a violation.

Scope and known limit: this is a static check. It catches ``import`` and
``from ... import`` statements in every form (bare, dotted, aliased, and
nested inside conditionals, because the AST is walked fully). It does NOT
catch dynamic imports such as ``importlib.import_module("requests")`` or
``__import__("requests")``, which no static parse can resolve in general.
Those are out of scope here by design, not by oversight.
"""

from __future__ import annotations

import argparse
import ast
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# Hooks scanned by this gate. Three run on the live session path: the
# effort-mode mergen_prompt_hook (UserPromptSubmit), verify_gate (PostToolUse),
# and constitution_inject (UserPromptSubmit) -- the last two are the pair the
# installer auto-registers. verify_agent_hook is an opt-in Stop hook (default
# OFF, not auto-registered); it is scanned anyway, conservatively, because a
# user can enable it and it would then run on the critical path.
HOOKS: tuple[tuple[str, Path], ...] = (
    ("effort-mode mergen_prompt_hook", REPO_ROOT / "effort-mode" / "hooks" / "mergen_prompt_hook.py"),
    ("core verify_gate", REPO_ROOT / "core" / "hooks" / "verify_gate.py"),
    ("core constitution_inject", REPO_ROOT / "core" / "hooks" / "constitution_inject.py"),
    ("core verify_agent_hook", REPO_ROOT / "core" / "hooks" / "verify_agent_hook.py"),
)

# Forbidden import roots. A critical-path hook must not reach a network or
# LLM client library. The list is intentionally conservative; adding a
# new client library that the hooks must never reach is a one-line change
# here. ``urllib.request`` is listed by full dotted path because bare
# ``urllib`` also covers ``urllib.parse`` and ``urllib.error`` which are
# stdlib-only and safe.
FORBIDDEN_ROOTS: frozenset[str] = frozenset(
    {
        "anthropic",
        "openai",
        "requests",
        "httpx",
        "urllib.request",
        "urllib3",
        "aiohttp",
    }
)

PRAGMA_TOKEN = "pragma: no cover (offline-only)"


@dataclass
class Violation:
    label: str
    file: Path
    line: int
    name: str


def _read_line(path: Path, lineno: int) -> str:
    try:
        with path.open("r", encoding="utf-8") as fp:
            for i, raw in enumerate(fp, start=1):
                if i == lineno:
                    return raw.rstrip("\n")
    except OSError:
        pass
    return ""


def _has_pragma(path: Path, lineno: int) -> bool:
    return PRAGMA_TOKEN in _read_line(path, lineno)


def _scan(label: str, path: Path) -> list[Violation]:
    found: list[Violation] = []
    if not path.is_file():
        # Missing hook files are reported separately by the main routine.
        return found
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
    except OSError as exc:
        print(f"::error::Unreadable hook file {path}: {exc}", file=sys.stderr)
        return found
    except SyntaxError as exc:
        print(f"::error::Syntax error in hook file {path}: {exc}", file=sys.stderr)
        return found

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                # Match both the bare top-level package (``import requests``)
                # and a full dotted module that is itself forbidden
                # (``import urllib.request``). Checking only the split root
                # would miss the dotted form, because ``urllib.request`` is a
                # forbidden root while bare ``urllib`` is not.
                root = alias.name.split(".")[0]
                if (root in FORBIDDEN_ROOTS or alias.name in FORBIDDEN_ROOTS) and not _has_pragma(
                    path, node.lineno
                ):
                    found.append(Violation(label, path, node.lineno, alias.name))
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            root = module.split(".")[0]
            # Three forms reach a forbidden target here:
            #   from anthropic import X          -> root 'anthropic' forbidden
            #   from urllib.request import Y      -> module 'urllib.request' forbidden
            #   from urllib import request        -> submodule 'urllib.request' forbidden
            # The last is the one a root/module-only check misses: 'urllib' is
            # not forbidden, but the imported name completes a forbidden module.
            submodules = {f"{module}.{alias.name}" for alias in node.names} if module else set()
            forbidden_sub = sorted(submodules & FORBIDDEN_ROOTS)
            if module in FORBIDDEN_ROOTS or root in FORBIDDEN_ROOTS or forbidden_sub:
                if not _has_pragma(path, node.lineno):
                    reported = forbidden_sub[0] if forbidden_sub else module
                    found.append(Violation(label, path, node.lineno, reported))
    return found


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--gate",
        action="store_true",
        help="Explicit CI mode (no behavioral effect; the script always exits non-zero on a violation).",
    )
    parser.parse_args()

    violations: list[Violation] = []
    missing: list[tuple[str, Path]] = []

    for label, path in HOOKS:
        if not path.is_file():
            missing.append((label, path))
            continue
        violations.extend(_scan(label, path))

    if missing:
        for label, path in missing:
            print(f"::error::Critical hook missing: {label} at {path}", file=sys.stderr)
        return 2

    if violations:
        for v in violations:
            print(
                f"::error file={v.file},line={v.line}::"
                f"C3 violation: critical-path hook '{v.label}' imports forbidden module '{v.name}'",
                file=sys.stderr,
            )
        print(
            f"spec_verify FAILED: {len(violations)} forbidden imports "
            f"across {len(HOOKS)} critical hooks.",
            file=sys.stderr,
        )
        return 1

    print(
        f"spec_verify PASSED: {len(HOOKS)} critical hooks scanned "
        f"against {len(FORBIDDEN_ROOTS)} forbidden roots."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
