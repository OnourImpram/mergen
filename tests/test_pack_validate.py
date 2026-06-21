"""Tests for scripts/pack_validate.py, the Policy Pack SDK conformance check.

The two committed packs (clinical, security) are exercised as worked examples that
must pass. The negative cases build throwaway packs in a temp dir, including the
dominant defect: a multi-line extra_high_trust_paths array that the 3.9 and 3.10
fallback reader cannot recover.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DOMAINS = REPO / "domains"


def _load():
    spec = importlib.util.spec_from_file_location("pack_validate", REPO / "scripts" / "pack_validate.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


pv = _load()


def _pack(tmp_path, name, body):
    d = tmp_path / name
    d.mkdir()
    (d / "pack.toml").write_text(body, encoding="utf-8")
    return d


# --------------------------------------------------------------------------- #
# conformance: the committed packs are valid
# --------------------------------------------------------------------------- #

def test_clinical_pack_is_valid():
    assert pv.validate_pack(DOMAINS / "clinical")["pass"] is True


def test_security_pack_is_valid():
    result = pv.validate_pack(DOMAINS / "security")
    assert result["pass"] is True, result["errors"]


# --------------------------------------------------------------------------- #
# negative cases
# --------------------------------------------------------------------------- #

def test_name_must_match_directory(tmp_path):
    d = _pack(tmp_path, "alpha", 'name = "beta"\n')
    result = pv.validate_pack(d)
    assert result["pass"] is False
    assert any("does not match" in e for e in result["errors"])


def test_missing_name_fails(tmp_path):
    d = _pack(tmp_path, "alpha", 'safety_note = "x"\n')
    result = pv.validate_pack(d)
    assert result["pass"] is False
    assert any("name" in e for e in result["errors"])


def test_unknown_field_is_rejected(tmp_path):
    d = _pack(tmp_path, "alpha", 'name = "alpha"\nlower_floor = true\n')
    result = pv.validate_pack(d)
    assert result["pass"] is False
    assert any("unknown field" in e for e in result["errors"])


def test_wrong_type_for_floor_all_fails(tmp_path):
    d = _pack(tmp_path, "alpha", 'name = "alpha"\nfloor_all_content_changes = "yes"\n')
    result = pv.validate_pack(d)
    assert result["pass"] is False
    assert any("boolean" in e for e in result["errors"])


def test_multiline_array_is_rejected(tmp_path):
    # The dominant defect: a multi-line array parses to zero paths on 3.9 and 3.10,
    # silently providing no protection. validate must refuse it on every host.
    body = (
        'name = "alpha"\n'
        "extra_high_trust_paths = [\n"
        '  "**/auth*",\n'
        '  "**/secret*",\n'
        "]\n"
    )
    d = _pack(tmp_path, "alpha", body)
    result = pv.validate_pack(d)
    assert result["pass"] is False
    assert any("multiple lines" in e for e in result["errors"])


def test_single_line_array_is_accepted(tmp_path):
    d = _pack(tmp_path, "alpha",
              'name = "alpha"\nextra_high_trust_paths = ["**/auth*", "**/secret*"]\n')
    assert pv.validate_pack(d)["pass"] is True


def test_missing_pack_toml_fails(tmp_path):
    d = tmp_path / "alpha"
    d.mkdir()
    result = pv.validate_pack(d)
    assert result["pass"] is False
    assert any("no pack.toml" in e for e in result["errors"])


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def test_cli_validate_pass_returns_0():
    assert pv.main(["validate", str(DOMAINS / "security")]) == 0


def test_cli_validate_fail_returns_1(tmp_path):
    d = _pack(tmp_path, "alpha", 'name = "beta"\n')
    assert pv.main(["validate", str(d)]) == 1


def test_cli_non_directory_returns_2(tmp_path):
    assert pv.main(["validate", str(tmp_path / "nope")]) == 2


# --------------------------------------------------------------------------- #
# review follow-ups: inline comment, parser fix, raise-only, more negatives
# --------------------------------------------------------------------------- #

def test_single_line_array_with_inline_comment_passes(tmp_path):
    # A trailing TOML comment after the closing bracket is legal and must not be
    # mistaken for a multi-line array.
    d = _pack(tmp_path, "alpha",
              'name = "alpha"\nextra_high_trust_paths = ["**/auth*"] # inline comment\n')
    result = pv.validate_pack(d)
    assert result["pass"] is True, result["errors"]


def test_parser_recovers_array_with_inline_comment():
    # The root fix: the 3.9 and 3.10 fallback reader must parse an array even when a
    # comment trails it, or the paths silently degrade to a string the engine drops.
    pc = pv._load("project_config")
    assert pc._parse_simple_toml('x = ["a", "b"] # trailing comment\n')["x"] == ["a", "b"]


def test_validated_pack_only_raises_the_floor(tmp_path):
    # The safety-critical end-to-end invariant: a pack that passes validate, fed to
    # the engine, can only raise the floor, never lower it.
    pc = pv._load("project_config")
    packs = tmp_path / "domains"
    d = packs / "alpha"
    d.mkdir(parents=True)
    (d / "pack.toml").write_text(
        'name = "alpha"\nfloor_all_content_changes = false\n'
        'extra_high_trust_paths = ["**/auth*"]\n', encoding="utf-8")
    assert pv.validate_pack(d)["pass"] is True
    # A high-trust base cannot be lowered by the overlay.
    base_high = pc.apply_overlay({"tier": "high-trust", "triggers_matched": ["auth-path"]},
                                 {"domain": "alpha"}, ["src/auth.py"], packs_dir=packs)
    assert base_high["tier"] == "high-trust"
    # A tiny base with a matching protected path is raised to high-trust.
    raised = pc.apply_overlay({"tier": "tiny", "triggers_matched": []},
                              {"domain": "alpha"}, ["src/auth.py"], packs_dir=packs)
    assert raised["tier"] == "high-trust"


def test_malformed_toml_fails(tmp_path):
    d = _pack(tmp_path, "alpha", 'name = "alpha"\nextra_high_trust_paths = [unclosed\n')
    assert pv.validate_pack(d)["pass"] is False


def test_empty_array_is_accepted(tmp_path):
    d = _pack(tmp_path, "alpha", 'name = "alpha"\nextra_high_trust_paths = []\n')
    assert pv.validate_pack(d)["pass"] is True


def test_non_string_array_item_is_rejected(tmp_path):
    d = _pack(tmp_path, "alpha", 'name = "alpha"\nextra_high_trust_paths = [42, "ok"]\n')
    result = pv.validate_pack(d)
    assert result["pass"] is False
    assert any("non-empty strings" in e for e in result["errors"])


def test_is_multiline_array_unit():
    # The sole defense on 3.9 and 3.10, where the cross-check cannot run.
    assert pv._is_multiline_array('x = [\n  "a",\n]\n', "x") is True
    assert pv._is_multiline_array('x = ["a", "b"]\n', "x") is False
    assert pv._is_multiline_array('# x = [\n', "x") is False  # a comment, not an assignment


def test_wrong_type_for_safety_note_fails(tmp_path):
    d = _pack(tmp_path, "alpha", 'name = "alpha"\nsafety_note = 123\n')
    result = pv.validate_pack(d)
    assert result["pass"] is False
    assert any("safety_note" in e for e in result["errors"])
