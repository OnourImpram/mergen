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
