#!/usr/bin/env python3
"""Fail the build if reference-prompt fingerprints appear in the repository.

Mergen's operating principles were informed by a reference system prompt but
reproduce no proprietary text (see MERGEN.md and MERGEN_PRINCIPLES.md). This
guard makes that promise testable rather than asserted. It scans tracked text
for a few structural fingerprints that are unique to the reference prompt, its
distinctive XML section tags and product identifiers, which would only appear
through an accidental paste. It does not store the reference prose. The
fingerprints are short structural markers, not creative expression.

Stdlib only. Exit 0 if clean, 1 if any fingerprint is found.
"""

from __future__ import annotations

import sys
from collections.abc import Iterator
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SELF = Path(__file__).resolve()

# Structural markers unique to the reference prompt, never legitimate in this
# repository. Deliberately short and non-prose.
FINGERPRINTS = [
    "<budget:token_budget>",
    "<critical_child_safety_instructions>",
    "<voice_note>",
    "long_conversation_reminder",
    "Mythos-class",
]

TEXT_EXT = {".md", ".py", ".sh", ".ps1", ".toml", ".yml", ".yaml", ".json", ".txt", ".mdc"}
SKIP_DIRS = {".git", ".pytest_cache", "__pycache__", ".specify", "node_modules"}
EXTRA_NAMES = {"NOTICE", "LICENSE"}


def find_fingerprints(text: str) -> list[str]:
    """Return the fingerprints present in text (empty list when clean)."""
    return [fp for fp in FINGERPRINTS if fp in text]


def iter_text_files(root: Path) -> Iterator[Path]:
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.resolve() == SELF:
            continue
        if path.suffix.lower() in TEXT_EXT or path.name in EXTRA_NAMES:
            yield path


def main() -> int:
    hits = []
    for path in iter_text_files(REPO):
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            continue
        for fp in find_fingerprints(text):
            hits.append((path.relative_to(REPO), fp))
    if hits:
        print("reference-prompt fingerprint found (verbatim reference text must not be committed):",
              file=sys.stderr)
        for rel, fp in hits:
            print(f"  {rel}: {fp!r}", file=sys.stderr)
        return 1
    print("no-reference-text check: clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())
