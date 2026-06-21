"""Tests for the no-reference-text guard (scripts/check_no_reference_text.py):
the repo is clean of reference-prompt fingerprints, and the detector flags one
when it is present.

Loaded by file path because scripts/ is not an importable package.
"""

import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def _load(rel_path: str):
    path = REPO / rel_path
    spec = importlib.util.spec_from_file_location(path.stem.replace("-", "_"), path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_no_reference_text_repo_is_clean():
    chk = _load("scripts/check_no_reference_text.py")
    assert chk.main() == 0


def test_no_reference_text_detects_a_fingerprint():
    chk = _load("scripts/check_no_reference_text.py")
    # Build the sample at runtime so no fingerprint literal sits in this test
    # file, which the guard itself scans.
    sample = "a line with " + chk.FINGERPRINTS[0] + " in it"
    assert chk.find_fingerprints(sample) == [chk.FINGERPRINTS[0]]
    assert chk.find_fingerprints("ordinary mergen prose") == []


def test_disavowed_phrase_detected_case_insensitively():
    chk = _load("scripts/check_no_reference_text.py")
    # Build the sample from the list entry so the literal does not sit in this
    # test file (the guard scans this file too, and it is not allowlisted).
    phrase = chk.DISAVOWED[0]
    assert chk.find_disavowed("wires a " + phrase + " verify gate") == [phrase]
    assert chk.find_disavowed("wires a " + phrase.upper() + " verify gate") == [phrase]
    assert chk.find_disavowed("an honestly scoped guarantee") == []


def test_lineage_docs_are_allowed_to_name_the_disavowed_phrase():
    # The retraction records (CHANGELOG.md, docs/ROADMAP.md) intentionally name
    # the phrase. The whole-repo scan must still pass because they are allowlisted.
    chk = _load("scripts/check_no_reference_text.py")
    assert "CHANGELOG.md" in chk.DISAVOWED_ALLOWED
    assert "docs/ROADMAP.md" in chk.DISAVOWED_ALLOWED
    assert chk.main() == 0
