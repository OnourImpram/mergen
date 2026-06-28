"""Tests for scripts/spec_verify.py.

The script is a security gate: it AST-scans the critical-path hooks and fails
if any imports a forbidden network or LLM client library. These tests pin the
detection surface so a future edit cannot silently reopen a blind spot. The
regression that motivated the test: the bare dotted forms ``import
urllib.request`` and ``from urllib import request`` were once missed while the
``from urllib.request import X`` form was caught.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Allow importing from scripts/ without installing the package.
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import spec_verify  # noqa: E402
from spec_verify import _scan  # noqa: E402


def _scan_src(tmp_path: Path, src: str) -> list[spec_verify.Violation]:
    hook = tmp_path / "hook.py"
    hook.write_text(src, encoding="utf-8")
    return _scan("test-hook", hook)


# --- Forbidden imports: every form must be caught. ------------------------- #

FORBIDDEN_FORMS = [
    "import requests",
    "import requests as r",
    "import urllib.request",            # bare dotted form (the BLOCKER regression)
    "import urllib3",
    "import aiohttp",
    "from anthropic import Anthropic",
    "from openai import OpenAI",
    "from urllib.request import urlopen",
    "from urllib import request",        # submodule form (the MAJOR regression)
    "import os\nif True:\n    import httpx",  # nested under a conditional
]


@pytest.mark.parametrize("src", FORBIDDEN_FORMS)
def test_forbidden_import_is_caught(tmp_path: Path, src: str) -> None:
    assert _scan_src(tmp_path, src), f"forbidden import not caught: {src!r}"


# --- Safe imports: must NOT be flagged. ------------------------------------ #

SAFE_FORMS = [
    "import urllib.parse",
    "import urllib.error",
    "from urllib.parse import quote",
    "from urllib import parse",
    "import os",
    "import json\nimport re\nfrom pathlib import Path",
]


@pytest.mark.parametrize("src", SAFE_FORMS)
def test_safe_import_is_not_flagged(tmp_path: Path, src: str) -> None:
    assert _scan_src(tmp_path, src) == [], f"safe import wrongly flagged: {src!r}"


# --- Pragma suppression. --------------------------------------------------- #


def test_pragma_suppresses_a_forbidden_import(tmp_path: Path) -> None:
    src = "import requests  # pragma: no cover (offline-only)\n"
    assert _scan_src(tmp_path, src) == []


def test_pragma_does_not_suppress_a_different_line(tmp_path: Path) -> None:
    src = "import requests\nx = 1  # pragma: no cover (offline-only)\n"
    assert _scan_src(tmp_path, src)


# --- Graceful handling of unparseable / missing files. --------------------- #


def test_syntax_error_file_is_skipped_not_crashed(tmp_path: Path) -> None:
    src = "def broken(\n"  # unterminated
    assert _scan_src(tmp_path, src) == []


def test_missing_file_returns_no_violations(tmp_path: Path) -> None:
    assert _scan("absent", tmp_path / "nope.py") == []


# --- CLI: exit codes against the real repo hooks. -------------------------- #


def test_main_passes_on_the_real_hooks(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    # The shipped hooks are clean; the gate must exit 0 and say so. argv is
    # isolated from pytest's own so argparse sees only the program name.
    monkeypatch.setattr(sys, "argv", ["spec_verify.py", "--gate"])
    rc = spec_verify.main()
    assert rc == 0
    assert "spec_verify PASSED" in capsys.readouterr().out
