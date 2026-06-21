"""Tests for scripts/project_config.py: the mergen.toml reader and the domain
overlay that raises, never lowers, the Governor floor.

The minimal fallback reader is exercised directly so it is covered on every
Python version, not only on 3.9/3.10 where tomllib is absent.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import project_config as pc  # noqa: E402


# --------------------------------------------------------------------------- #
# Loading
# --------------------------------------------------------------------------- #

def test_load_absent_config_is_empty(tmp_path):
    assert pc.load_config(tmp_path / "nope.toml") == {}


def test_load_config_reads_domain_and_paths(tmp_path):
    f = tmp_path / "mergen.toml"
    f.write_text(
        'domain = "clinical"\n[governor]\n'
        'extra_high_trust_paths = ["src/billing/", "*.env"]\n',
        encoding="utf-8",
    )
    cfg = pc.load_config(f)
    assert cfg["domain"] == "clinical"
    assert cfg["governor"]["extra_high_trust_paths"] == ["src/billing/", "*.env"]


def test_minimal_parser_handles_the_fixed_shape():
    cfg = pc._parse_simple_toml(
        '# a comment\ndomain = "clinical"\n\n[governor]\n'
        'extra_high_trust_paths = ["a/", "b/"]\nflag = true\n'
    )
    assert cfg["domain"] == "clinical"
    assert cfg["governor"]["extra_high_trust_paths"] == ["a/", "b/"]
    assert cfg["governor"]["flag"] is True


def test_minimal_parser_strips_wholeline_inline_comment_without_quotes():
    cfg = pc._parse_simple_toml("[governor]\nflag = true  # inline\n")
    assert cfg["governor"]["flag"] is True


# --------------------------------------------------------------------------- #
# Overlay
# --------------------------------------------------------------------------- #

def test_overlay_clinical_floors_any_change_to_high_trust():
    base = {"tier": "tiny", "triggers_matched": []}
    out = pc.apply_overlay(base, {"domain": "clinical"}, ["docs/readme.md"])
    assert out["tier"] == "high-trust"
    assert "domain:clinical" in out["triggers_matched"]
    assert out["domain"] == "clinical"


def test_overlay_clinical_with_no_change_stays_low():
    base = {"tier": "tiny", "triggers_matched": []}
    out = pc.apply_overlay(base, {"domain": "clinical"}, [])
    assert out["tier"] == "tiny"


def test_overlay_protected_path_prefix_forces_high_trust():
    base = {"tier": "tiny", "triggers_matched": []}
    cfg = {"governor": {"extra_high_trust_paths": ["src/billing/"]}}
    out = pc.apply_overlay(base, cfg, ["src/billing/charge.py"])
    assert out["tier"] == "high-trust"
    assert "project-protected-path" in out["triggers_matched"]


def test_overlay_protected_path_glob_forces_high_trust():
    base = {"tier": "tiny", "triggers_matched": []}
    cfg = {"governor": {"extra_high_trust_paths": ["*.env"]}}
    out = pc.apply_overlay(base, cfg, ["config/prod.env"])
    assert out["tier"] == "high-trust"


def test_overlay_no_domain_no_protected_is_unchanged():
    base = {"tier": "tiny", "triggers_matched": []}
    out = pc.apply_overlay(base, {}, ["docs/readme.md"])
    assert out["tier"] == "tiny"
    assert out["triggers_matched"] == []
    assert out["domain"] is None


def test_overlay_never_lowers_existing_high_trust():
    base = {"tier": "high-trust", "triggers_matched": ["auth-path"]}
    out = pc.apply_overlay(base, {}, ["src/auth/login.py"])
    assert out["tier"] == "high-trust"
    assert "auth-path" in out["triggers_matched"]


def test_committed_example_config_parses():
    repo = Path(__file__).resolve().parent.parent
    cfg = pc.load_config(repo / "docs" / "mergen-config.example.toml")
    assert cfg["domain"] == "clinical"
    assert "src/billing/" in cfg["governor"]["extra_high_trust_paths"]


# --------------------------------------------------------------------------- #
# Domain packs (Phase 4): a domain is a shareable data pack, not code.
# --------------------------------------------------------------------------- #

def test_load_committed_clinical_pack():
    pack = pc.load_domain_pack("clinical")
    assert pack.get("floor_all_content_changes") is True
    assert "licensed reviewer" in pack.get("safety_note", "")


def test_load_domain_pack_absent_is_empty(tmp_path):
    assert pc.load_domain_pack("nope", packs_dir=tmp_path) == {}


def test_load_committed_security_pack():
    pack = pc.load_domain_pack("security")
    # Security is path-based, not floor-all, so an ordinary change is untouched.
    assert pack.get("floor_all_content_changes") is False
    assert "security reviewer" in pack.get("safety_note", "")
    paths = pack.get("extra_high_trust_paths", [])
    assert any("auth" in p for p in paths)
    assert any("secret" in p for p in paths)


def test_overlay_security_pack_floors_sensitive_paths_only():
    base = {"tier": "tiny", "triggers_matched": []}
    # An auth-surface change is floored to high-trust and carries the note.
    out1 = pc.apply_overlay(base, {"domain": "security"}, ["src/auth/login.py"])
    assert out1["tier"] == "high-trust"
    assert "project-protected-path" in out1["triggers_matched"]
    assert "security reviewer" in out1.get("safety_note", "")
    # A secret-bearing env file is floored too.
    out2 = pc.apply_overlay(base, {"domain": "security"}, ["config/prod.env"])
    assert out2["tier"] == "high-trust"
    # An unrelated docs change is NOT floored: security floors paths, not all changes.
    out3 = pc.apply_overlay(base, {"domain": "security"}, ["docs/readme.md"])
    assert out3["tier"] == "tiny"


def test_overlay_surfaces_clinical_pack_safety_note():
    base = {"tier": "tiny", "triggers_matched": []}
    out = pc.apply_overlay(base, {"domain": "clinical"}, ["docs/x.md"])
    assert out["tier"] == "high-trust"
    assert "licensed reviewer" in out.get("safety_note", "")


def test_overlay_custom_pack_floors_and_notes(tmp_path):
    d = tmp_path / "finance"
    d.mkdir()
    (d / "pack.toml").write_text(
        'name = "finance"\nfloor_all_content_changes = true\n'
        'safety_note = "Money movement needs review."\n',
        encoding="utf-8",
    )
    base = {"tier": "tiny", "triggers_matched": []}
    out = pc.apply_overlay(base, {"domain": "finance"}, ["src/x.py"], packs_dir=tmp_path)
    assert out["tier"] == "high-trust"
    assert out["safety_note"] == "Money movement needs review."


def test_overlay_pack_extra_paths_are_precise(tmp_path):
    d = tmp_path / "sec"
    d.mkdir()
    (d / "pack.toml").write_text(
        'name = "sec"\nfloor_all_content_changes = false\n'
        'extra_high_trust_paths = ["vault/"]\n',
        encoding="utf-8",
    )
    base = {"tier": "tiny", "triggers_matched": []}
    # A change outside the protected path is not floored (floor_all is false).
    out1 = pc.apply_overlay(base, {"domain": "sec"}, ["docs/x.md"], packs_dir=tmp_path)
    assert out1["tier"] == "tiny"
    # A change inside the protected path is forced to high-trust.
    out2 = pc.apply_overlay(base, {"domain": "sec"}, ["vault/secret.md"], packs_dir=tmp_path)
    assert out2["tier"] == "high-trust"
    assert "project-protected-path" in out2["triggers_matched"]
