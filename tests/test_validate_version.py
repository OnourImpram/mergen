"""Tests for scripts/validate_version.py.

The validator is an integrity gate: it asserts the version stamp agrees across
pyproject.toml, CITATION.cff, CHANGELOG.md, and README.md. These tests pin its
behaviour so a future edit cannot silently weaken the detection: each source is
driven to disagree and the mismatch must be reported, and the agreeing case
must pass. The functions read from REPO_ROOT, so the tests redirect REPO_ROOT
at a synthetic fixture tree rather than mutating the real repo files.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import validate_version  # noqa: E402


def _write_tree(root: Path, *, pyproject: str, citation: str, changelog: str, readme: str) -> None:
    (root / "pyproject.toml").write_text(pyproject, encoding="utf-8")
    (root / "CITATION.cff").write_text(citation, encoding="utf-8")
    (root / "CHANGELOG.md").write_text(changelog, encoding="utf-8")
    (root / "README.md").write_text(readme, encoding="utf-8")


_GOOD = {
    "pyproject": (
        '[project]\nname = "mergen"\nversion = "2.0.0"\nrequires-python = ">=3.9"\n'
        '\n[tool.x]\nversion = "9.9.9"\n'
    ),
    "citation": 'cff-version: 1.2.0\nversion: "2.0.0"\n',
    "changelog": "# Changelog\n\n## [Unreleased]\n\n## [2.0.0] - 2026-06-28\n\n## [1.0.0] - 2026-06-19\n",
    "readme": "# Mergen\n\nStatus: v2.0.0 beta.\n\nProvenance: forked at v1.0.0.\n",
}


@pytest.fixture
def good_tree(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    _write_tree(tmp_path, **_GOOD)
    monkeypatch.setattr(validate_version, "REPO_ROOT", tmp_path)
    return tmp_path


def test_all_sources_agree_passes(good_tree: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert validate_version.main() == 0
    assert "PASSED" in capsys.readouterr().out


def test_canonical_version_ignores_other_tables(good_tree: Path) -> None:
    # The [tool.x] version 9.9.9 must NOT be picked up; [project] is 2.0.0.
    assert validate_version._canonical_version() == "2.0.0"


def test_citation_mismatch_fails(good_tree: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (good_tree / "CITATION.cff").write_text('cff-version: 1.2.0\nversion: "1.9.9"\n', encoding="utf-8")
    assert validate_version.main() == 1


def test_changelog_mismatch_fails(good_tree: Path) -> None:
    (good_tree / "CHANGELOG.md").write_text("# Changelog\n\n## [1.5.0] - 2026-01-01\n", encoding="utf-8")
    assert validate_version.main() == 1


def test_readme_mismatch_fails(good_tree: Path) -> None:
    (good_tree / "README.md").write_text("# Mergen\n\nStatus: v1.0.0 beta.\n", encoding="utf-8")
    assert validate_version.main() == 1


def test_missing_changelog_fails(good_tree: Path) -> None:
    (good_tree / "CHANGELOG.md").unlink()
    assert validate_version.main() == 1


def test_citation_without_version_line_fails(good_tree: Path) -> None:
    (good_tree / "CITATION.cff").write_text("cff-version: 1.2.0\ntitle: Mergen\n", encoding="utf-8")
    assert validate_version.main() == 1


def test_changelog_without_version_heading_fails(good_tree: Path) -> None:
    (good_tree / "CHANGELOG.md").write_text("# Changelog\n\nNo releases recorded yet.\n", encoding="utf-8")
    assert validate_version.main() == 1


def test_readme_without_status_line_fails(good_tree: Path) -> None:
    (good_tree / "README.md").write_text("# Mergen\n\nNo status line here.\n", encoding="utf-8")
    assert validate_version.main() == 1


def test_missing_pyproject_exits_2(good_tree: Path) -> None:
    (good_tree / "pyproject.toml").unlink()
    with pytest.raises(SystemExit) as exc:
        validate_version.main()
    assert exc.value.code == 2


def test_real_repo_sources_agree(capsys: pytest.CaptureFixture[str]) -> None:
    # Against the actual repo (REPO_ROOT unpatched), the four sources must agree.
    assert validate_version.main() == 0
    assert "PASSED" in capsys.readouterr().out
