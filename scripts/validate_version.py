#!/usr/bin/env python3
"""Version-consistency validator for Mergen.

Asserts that the version stamp in every declared source agrees with the
canonical version in ``pyproject.toml``. This structurally prevents the
docs-drift class where a release bumps ``pyproject.toml`` but misses
``CITATION.cff``, ``CHANGELOG.md``, or ``README.md``.

Pure standard library and 3.9-safe by construction: every source is read
with a scoped regex rather than a TOML parser, so this runs on the same
Python floor (3.9+) that the rest of Mergen promises. (The runtime modules
that genuinely need the full TOML grammar -- pack_validate, project_config --
use ``tomllib`` on 3.11+ with a deterministic fallback; a single version
field does not, so the simpler portable read is the right tool here.)

Exit codes:
  0 - all version sources agree.
  1 - a source disagrees, OR a prose source (CITATION.cff, CHANGELOG.md,
      README.md) is missing or its version cannot be read.
  2 - usage error: pyproject.toml is missing or its [project].version cannot
      be read, so the canonical version is unavailable and no comparison is
      possible.

Usage:
  python scripts/validate_version.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _canonical_version() -> str:
    """Return the version from pyproject.toml [project].version.

    The version is read with a regex scoped to the ``[project]`` table so a
    ``version = ...`` line in any other table (or a dependency specifier)
    cannot be mistaken for it. No TOML parser, so this stays 3.9-safe.
    """
    pyproject = REPO_ROOT / "pyproject.toml"
    if not pyproject.is_file():
        print(f"::error::pyproject.toml not found at {pyproject}", file=sys.stderr)
        sys.exit(2)
    text = _read(pyproject)
    # Capture the [project] table body: from its header to the next top-level
    # table header. The trailing sentinel guarantees a terminating match. If the
    # [project] table is absent, fail rather than fall back to a whole-file
    # search, which could pick up a version = in some [tool.*] table and report
    # the wrong canonical version.
    section = re.search(r"(?ms)^\[project\]\s*\n(.*?)(?=^\[)", text + "\n[")
    if not section:
        print("::error::pyproject.toml has no [project] table", file=sys.stderr)
        sys.exit(2)
    match = re.search(r'(?m)^\s*version\s*=\s*"([^"]+)"', section.group(1))
    if not match:
        print("::error::pyproject.toml [project].version is missing or empty", file=sys.stderr)
        sys.exit(2)
    return match.group(1).strip()


def _check_citation_cff(expected: str) -> str | None:
    """Return an error message if CITATION.cff disagrees, else None."""
    citation = REPO_ROOT / "CITATION.cff"
    if not citation.is_file():
        return "CITATION.cff not found"
    match = re.search(r'^version:\s*"?([^"\n]+)"?\s*$', _read(citation), re.MULTILINE)
    if not match:
        return "CITATION.cff version: line not found"
    declared = match.group(1).strip()
    if declared != expected:
        return f"CITATION.cff is {declared} but pyproject.toml is {expected}"
    return None


def _check_changelog(expected: str) -> str | None:
    """Return an error message if CHANGELOG.md's latest version disagrees."""
    changelog = REPO_ROOT / "CHANGELOG.md"
    if not changelog.is_file():
        return "CHANGELOG.md not found"
    # The first "## [X.Y.Z]" heading is the latest release.
    match = re.search(r"^##\s*\[(\d+\.\d+\.\d+)\]", _read(changelog), re.MULTILINE)
    if not match:
        return "CHANGELOG.md has no '## [X.Y.Z]' version heading"
    declared = match.group(1)
    if declared != expected:
        return f"CHANGELOG.md latest is {declared} but pyproject.toml is {expected}"
    return None


def _check_readme(expected: str) -> str | None:
    """Return an error message if README.md's status-line version disagrees.

    Anchored to the ``Status:`` line (the README's current-version line)
    rather than the first ``vX.Y.Z`` anywhere in the file, so a historical
    version in a later provenance note cannot be mistaken for the current one.
    """
    readme = REPO_ROOT / "README.md"
    if not readme.is_file():
        return "README.md not found"
    match = re.search(r"(?m)^>?\s*[Ss]tatus:.*?\bv(\d+\.\d+\.\d+)", _read(readme))
    if not match:
        return "README.md has no 'Status:' line with a vX.Y.Z version"
    declared = match.group(1)
    if declared != expected:
        return f"README.md status line is v{declared} but pyproject.toml is {expected}"
    return None


def main() -> int:
    canonical = _canonical_version()

    checks = (
        ("CITATION.cff", _check_citation_cff),
        ("CHANGELOG.md", _check_changelog),
        ("README.md", _check_readme),
    )

    errors = [f"{label}: {msg}" for label, check in checks if (msg := check(canonical)) is not None]

    if errors:
        print("validate_version FAILED:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1

    print(f"validate_version PASSED: {1 + len(checks)} version sources agree at {canonical}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
