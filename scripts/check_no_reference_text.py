#!/usr/bin/env python3
"""Fail the build if reference-prompt fingerprints or disavowed over-claims
appear in the repository.

Mergen's operating principles were informed by a reference system prompt but
reproduce no proprietary text (see MERGEN.md and MERGEN_PRINCIPLES.md). This
guard makes that promise testable rather than asserted. It scans tracked text
for a few structural fingerprints that are unique to the reference prompt, its
distinctive XML section tags and product identifiers, which would only appear
through an accidental paste. It does not store the reference prose. The
fingerprints are short structural markers, not creative expression.

It also guards a second honesty promise: that an over-claim the project has
explicitly retracted does not creep back into a shipped or source artifact.
The retraction is recorded once in the lineage and correction documents
(CHANGELOG.md and docs/ROADMAP.md), and only those files may name the disavowed
phrase. Everywhere else, especially any rendered, user-facing artifact, the
phrase is a build failure. This puts the "asks, nudges, refuses" honesty
discipline under the same automated check as the IP promise, closing the blind
spot where an over-claim could pass both the drift gate (core and dist would be
wrong together) and the fingerprint gate (no fingerprint involved).

Stdlib only. Exit 0 if clean, 1 if any fingerprint or disavowed phrase is found.
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

# Over-claims the project has explicitly retracted. They must not reappear in
# any source or rendered artifact. Matched case-insensitively.
DISAVOWED = [
    "non-bypassable",
]

# The only files whose job is to RECORD the retraction, so they are allowed to
# name the disavowed phrase. Relative to the repo root, forward-slash form.
DISAVOWED_ALLOWED = {
    "CHANGELOG.md",
    "docs/ROADMAP.md",
}

TEXT_EXT = {".md", ".py", ".sh", ".ps1", ".toml", ".yml", ".yaml", ".json", ".txt", ".mdc"}
SKIP_DIRS = {".git", ".pytest_cache", "__pycache__", ".specify", "node_modules"}
EXTRA_NAMES = {"NOTICE", "LICENSE"}


def find_fingerprints(text: str) -> list[str]:
    """Return the fingerprints present in text (empty list when clean)."""
    return [fp for fp in FINGERPRINTS if fp in text]


def find_disavowed(text: str) -> list[str]:
    """Return the disavowed phrases present in text, case-insensitive."""
    low = text.lower()
    return [phrase for phrase in DISAVOWED if phrase in low]


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
        rel = path.relative_to(REPO)
        rel_str = str(rel).replace("\\", "/")
        for fp in find_fingerprints(text):
            hits.append((rel, f"reference-prompt fingerprint {fp!r}"))
        if rel_str not in DISAVOWED_ALLOWED:
            for phrase in find_disavowed(text):
                hits.append((rel, f"disavowed over-claim {phrase!r}"))
    if hits:
        print("forbidden text found (reference-prompt fingerprints and retracted over-claims "
              "must not be committed outside their lineage records):", file=sys.stderr)
        for rel, what in hits:
            print(f"  {rel}: {what}", file=sys.stderr)
        return 1
    print("no-reference-text check: clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())
