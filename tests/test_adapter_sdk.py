"""Tests for scripts/adapter_sdk.py, the per-host capability manifests.

The committed manifests are exercised as worked examples that must validate and must reflect
the renderers honestly. The load-bearing tests are the refusal guard (a host refuses a
capability its manifest denies), the schema-to-code drift gate (the capability vocabulary is
one source), and the doc drift gate (docs/CAPABILITIES.md equals the render of the manifests).
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, REPO / "scripts" / f"{name}.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


sdk = _load("adapter_sdk")


def _manifest(tmp_path, host, caps, **extra):
    full = {k: False for k in sdk.CAPABILITY_KEYS}
    full.update(caps)
    doc = {"host": host, "title": f"{host} title", "capabilities": full}
    doc.update(extra)
    (tmp_path / f"{host}.json").write_text(json.dumps(doc), encoding="utf-8")
    return tmp_path


# --------------------------------------------------------------------------- #
# The committed manifests are valid and honest
# --------------------------------------------------------------------------- #

def test_committed_manifests_validate():
    assert sdk.validate_all() == []


def test_committed_manifests_reflect_the_renderers_honestly():
    native = sdk.load_manifest("native")
    speckit = sdk.load_manifest("speckit")
    agents = sdk.load_manifest("agents")
    # Only the native host runs the Workflow orchestration and lifecycle hooks.
    assert sdk.has_capability(native, "workflow_orchestration")
    assert not sdk.has_capability(speckit, "workflow_orchestration")
    assert not sdk.has_capability(agents, "workflow_orchestration")
    assert sdk.has_capability(native, "lifecycle_hooks")
    assert not sdk.has_capability(speckit, "lifecycle_hooks")
    # Spec Kit carries the command suite and the verify gate; generic agents do not.
    assert sdk.has_capability(speckit, "command_suite") and sdk.has_capability(speckit, "verify_gate")
    assert not sdk.has_capability(agents, "command_suite")
    # Spec Kit does NOT bootstrap a mergen scaffold of its own (build_speckit has no init):
    # only native does, which build_native's cmd_init implements.
    assert sdk.has_capability(native, "project_bootstrap")
    assert not sdk.has_capability(speckit, "project_bootstrap")
    # The generic agents host ports only the passive minimalism discipline.
    assert sdk.has_capability(agents, "passive_rules")
    assert not sdk.has_capability(native, "passive_rules")


# --------------------------------------------------------------------------- #
# The refusal guard
# --------------------------------------------------------------------------- #

def test_require_capability_passes_when_granted():
    sdk.require_capability("native", "workflow_orchestration")  # no raise


def test_require_capability_refuses_when_denied():
    import pytest
    with pytest.raises(sdk.CapabilityError, match="does not provide"):
        sdk.require_capability("agents", "workflow_orchestration")


def test_require_capability_unknown_host_raises_not_found():
    import pytest
    with pytest.raises(FileNotFoundError):
        sdk.require_capability("nope", "slash_commands")


def test_has_capability_rejects_an_unknown_capability():
    import pytest
    with pytest.raises(ValueError, match="unknown capability"):
        sdk.has_capability(sdk.load_manifest("native"), "teleportation")


# --------------------------------------------------------------------------- #
# Validation negatives
# --------------------------------------------------------------------------- #

def test_validate_catches_host_name_mismatch(tmp_path):
    d = _manifest(tmp_path, "alpha", {})
    (d / "beta.json").write_text((d / "alpha.json").read_text(encoding="utf-8"), encoding="utf-8")
    errors = sdk.validate_all(d)
    assert any("does not match the file name" in e for e in errors)


def test_validate_catches_missing_capability(tmp_path):
    doc = {"host": "alpha", "title": "t", "capabilities": {"slash_commands": True}}
    (tmp_path / "alpha.json").write_text(json.dumps(doc), encoding="utf-8")
    errors = sdk.validate_all(tmp_path)
    assert any("missing capability" in e for e in errors)


def test_validate_catches_non_boolean_capability(tmp_path):
    caps = {k: False for k in sdk.CAPABILITY_KEYS}
    caps["slash_commands"] = "yes"
    doc = {"host": "alpha", "title": "t", "capabilities": caps}
    (tmp_path / "alpha.json").write_text(json.dumps(doc), encoding="utf-8")
    errors = sdk.validate_all(tmp_path)
    assert any("must be a boolean" in e for e in errors)


def test_validate_catches_unknown_capability_and_field(tmp_path):
    _manifest(tmp_path, "alpha", {"telepathy": True}, surprise="x")
    errors = sdk.validate_all(tmp_path)
    assert any("unknown capability 'telepathy'" in e for e in errors)
    assert any("unknown top-level field 'surprise'" in e for e in errors)


# --------------------------------------------------------------------------- #
# Drift gates
# --------------------------------------------------------------------------- #

def test_capability_vocabulary_matches_the_schema():
    # The capability vocabulary lives in two places, the code tuple and the schema's required
    # list. This proves they are identical in content and order, so neither can drift.
    schema = json.loads((REPO / "core" / "schemas" / "adapter-manifest.schema.json").read_text(encoding="utf-8"))
    required = schema["properties"]["capabilities"]["required"]
    assert tuple(required) == sdk.CAPABILITY_KEYS
    assert set(schema["properties"]["capabilities"]["properties"]) == set(sdk.CAPABILITY_KEYS)


def test_capabilities_doc_is_in_sync_with_the_manifests():
    # Compare raw bytes decoded as utf-8, the way the --check gate does, so a CRLF doc on
    # Windows cannot mask a drift that a non-Windows CI runner would catch.
    committed = (REPO / "docs" / "CAPABILITIES.md").read_bytes().decode("utf-8")
    rendered = sdk.render_capability_matrix(sdk.load_all_manifests())
    assert committed == rendered


def test_capabilities_doc_has_no_carriage_returns():
    # The committed doc must be LF only, or render --check oscillates across platforms.
    assert b"\r" not in (REPO / "docs" / "CAPABILITIES.md").read_bytes()


def test_matrix_is_deterministic_and_orders_native_first():
    out1 = sdk.render_capability_matrix(sdk.load_all_manifests())
    out2 = sdk.render_capability_matrix(sdk.load_all_manifests())
    assert out1 == out2
    # Most-capable host first: native's title column precedes agents'.
    assert out1.index("Claude Code") < out1.index("Generic agents")


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def test_cli_validate_and_matrix_and_render_check_pass():
    assert sdk.main(["validate"]) == 0
    assert sdk.main(["matrix"]) == 0
    assert sdk.main(["render", "--check"]) == 0


def test_cli_check_returns_0_or_1_by_capability():
    assert sdk.main(["check", "--host", "native", "--capability", "workflow_orchestration"]) == 0
    assert sdk.main(["check", "--host", "agents", "--capability", "workflow_orchestration"]) == 1


def test_cli_render_write_and_check_are_mutually_exclusive():
    import pytest
    with pytest.raises(SystemExit):
        sdk.main(["render", "--write", "--check"])
