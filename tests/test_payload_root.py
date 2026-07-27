"""Tests for payload_root, the checkout-first resolver in mergen_cli.

The CLI shells out to scripts/ and reads core/schemas, but those trees are not
imported, so nothing makes the interpreter carry them into a wheel. They are
mapped into the mergen_payload package for that reason, and payload_root picks
between the checkout copy and the installed one.

Getting the precedence backwards is the failure worth guarding: an editable
install that silently ran an older packaged script would verify code nobody is
editing, and it would do it without saying so.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

import mergen_cli  # noqa: E402


def test_checkout_wins_when_the_trees_are_present() -> None:
    """In a checkout every payload root resolves next to mergen_cli.py."""
    for name in ("scripts", "core", "dist", "effort-mode"):
        resolved = mergen_cli.payload_root(name)
        assert resolved == REPO / name
        assert resolved.is_dir()


def test_the_files_the_cli_runs_actually_exist() -> None:
    """The constants built on those roots point at real files, not guesses."""
    assert mergen_cli._VERIFY_CORE.is_file()
    assert mergen_cli._VERIFY_LINT.is_file()
    assert mergen_cli._SCHEMAS_DIR.is_dir()
    assert mergen_cli._EFFORT_PATCH.is_file()
    assert mergen_cli._BUILD_NATIVE.is_file()


def test_falls_back_to_the_packaged_copy_when_the_checkout_has_none(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """With no sibling tree, resolution moves to mergen_payload.

    A wheel install is exactly this case: mergen_cli.py sits in site-packages
    with no scripts/ beside it.
    """
    packaged = tmp_path / "mergen_payload"
    (packaged / "scripts").mkdir(parents=True)
    (packaged / "effort_mode").mkdir()

    monkeypatch.setattr(mergen_cli, "_REPO", tmp_path / "nowhere")
    monkeypatch.setattr(
        "importlib.resources.files", lambda _pkg: packaged, raising=False
    )

    assert mergen_cli.payload_root("scripts") == packaged / "scripts"
    # The hyphen cannot survive as a package name, so the lookup translates it.
    assert mergen_cli.payload_root("effort-mode") == packaged / "effort_mode"


def test_reports_the_repository_path_when_neither_copy_exists(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A broken install names a path under the repository, not site-packages.

    Callers surface this path in their error, and the repository-shaped one is
    the version a reader can do something about.
    """
    missing = tmp_path / "nowhere"
    monkeypatch.setattr(mergen_cli, "_REPO", missing)
    monkeypatch.setattr(
        "importlib.resources.files",
        lambda _pkg: tmp_path / "also-missing",
        raising=False,
    )

    assert mergen_cli.payload_root("scripts") == missing / "scripts"


def test_an_unimportable_payload_package_is_not_fatal(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Resolution degrades to a path instead of raising at import time.

    payload_root runs while mergen_cli is still being imported, so an exception
    here would take down every verb, including the ones that need no payload.
    """

    def _boom(_pkg: str) -> Path:
        raise ModuleNotFoundError("mergen_payload")

    monkeypatch.setattr(mergen_cli, "_REPO", tmp_path / "nowhere")
    monkeypatch.setattr("importlib.resources.files", _boom, raising=False)

    assert mergen_cli.payload_root("scripts") == tmp_path / "nowhere" / "scripts"
