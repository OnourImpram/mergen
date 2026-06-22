"""Schema and sample-artifact checks: the three JSON schemas parse as JSON Schema,
and the committed sample verification-report carries calibrated confidence labels.

Split out of the former test_mergen_v1 grab-bag so each concern has a focused
home (C4, the inverted test strategy).
"""

import importlib.util
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent


def _schema(name: str) -> dict:
    return json.loads(
        (REPO / "core" / "schemas" / f"{name}.schema.json").read_text(encoding="utf-8")
    )


def _validator(name: str):
    """A Draft 2020-12 validator for a shipped schema, or skip if jsonschema is absent.

    jsonschema is a dev-only dependency. The shipped linter (verify_report_lint.py)
    enforces these same invariants in pure stdlib, so the runtime never needs it.
    These tests prove the declarative schema's if/then logic is itself correct, so
    a generic validator (a third party's CI) reads the same contract the linter does.
    """
    jsonschema = pytest.importorskip("jsonschema")
    return jsonschema.Draft202012Validator(_schema(name))


def _load_verify_core():
    spec = importlib.util.spec_from_file_location(
        "verify_core", REPO / "scripts" / "verify_core.py"
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_schemas_parse():
    for name in ("verification-report", "tasks-state", "governor-decision", "policy-pack",
                 "adapter-manifest"):
        data = _schema(name)
        assert data["$schema"].startswith("https://json-schema.org/")
        assert "properties" in data


def test_adapter_manifest_schema_requires_a_complete_capability_set():
    # The adapter manifest is the declarative half of the Adapter SDK. It requires a host, a
    # title, and the full capability vocabulary, refuses unknown fields, and the runtime
    # adapter_sdk enforces the same in pure stdlib.
    v = _validator("adapter-manifest")
    caps = {k: False for k in (
        "slash_commands", "command_suite", "lifecycle_hooks", "settings_registration",
        "project_bootstrap", "workflow_orchestration", "verify_gate", "passive_rules")}
    assert v.is_valid({"host": "h", "title": "t", "capabilities": caps})
    assert not v.is_valid({"host": "h", "title": "t", "capabilities": {"slash_commands": True}})
    assert not v.is_valid({"host": "h", "title": "t", "capabilities": caps, "surprise": 1})


def test_policy_pack_schema_is_raise_only_and_name_required():
    # The pack schema is the declarative half of the Policy Pack SDK. It requires a
    # name, refuses unknown fields (the structural raise-only guarantee), and the
    # runtime pack_validate enforces the same in pure stdlib.
    v = _validator("policy-pack")
    assert v.is_valid({"name": "clinical"})
    assert v.is_valid({"name": "security", "floor_all_content_changes": False,
                       "extra_high_trust_paths": ["**/auth*"]})
    assert not v.is_valid({"floor_all_content_changes": True})  # missing name
    assert not v.is_valid({"name": "x", "lower_floor": True})   # unknown field rejected


def test_sample_report_carries_confidence_labels():
    rep = json.loads((REPO / "eval" / "sample" / "verification-report.json").read_text(encoding="utf-8"))
    assert rep["schema_version"] == "1.0"
    for task in rep["tasks"]:
        assert task["confidence"] in ("extracted", "inferred", "ambiguous")


def test_confidence_vocabulary_is_unified_across_code_and_schema():
    # The "unify confidence vocabulary" guarantee: the code mirror and the
    # schema enum hold exactly the same labels, so neither can drift.
    verify_core = _load_verify_core()
    schema_enum = set(
        _schema("verification-report")["properties"]["tasks"]["items"]
        ["properties"]["confidence"]["enum"]
    )
    assert set(verify_core.CONFIDENCE_LABELS) == schema_enum
    assert set(verify_core.CONFIDENCE) == schema_enum  # every label is defined


def test_evidence_tiers_vocabulary_is_unified_across_code_and_schema():
    # The same anti-drift guarantee for the calibration tiers: the code tuple and
    # the schema enum hold exactly the same labels in the same order, so a future
    # editor cannot add a tier to one without the other.
    verify_core = _load_verify_core()
    schema_enum = (
        _schema("verification-report")["properties"]["tasks"]["items"]
        ["properties"]["evidence_tier"]["enum"]
    )
    assert list(verify_core.EVIDENCE_TIERS) == schema_enum


def test_policy_results_shape_is_shared_across_schemas():
    # The "unify policy_results" guarantee: the Governor decision and the
    # verification report use one policy-result item shape and one vocabulary.
    gov_item = _schema("governor-decision")["properties"]["policy_results"]["items"]
    ver_item = _schema("verification-report")["properties"]["policy_results"]["items"]
    assert set(gov_item["properties"]) == set(ver_item["properties"])
    assert gov_item["properties"]["result"]["enum"] == ver_item["properties"]["result"]["enum"]
    # required and additionalProperties must be identical so neither schema
    # silently accepts a weaker shape than the other.
    assert gov_item.get("required") == ver_item.get("required")
    assert gov_item.get("additionalProperties") == ver_item.get("additionalProperties")


def test_governor_decision_policy_results_is_optional():
    gov = _schema("governor-decision")
    assert "policy_results" in gov["properties"]
    assert "policy_results" not in gov["required"]


# --------------------------------------------------------------------------- #
# Schema invariants enforced by if/then (validated with jsonschema when present).
# These pin that the declarative contract refuses what the linter refuses.
# --------------------------------------------------------------------------- #

_GOV_BASE = {
    "schema_version": "1.0", "task": "t", "tier": "standard", "triggers_matched": [],
    "memory_scope": "s", "workflow": "w", "evidence_standard": "e",
    "human_approval_required": False,
}


def test_governor_a_fired_trigger_forces_high_trust():
    v = _validator("governor-decision")
    assert v.is_valid(_GOV_BASE)  # no triggers, standard tier: fine
    # A matched trigger but a non-high-trust tier is a contradiction.
    assert not v.is_valid({**_GOV_BASE, "triggers_matched": ["secrets"], "tier": "standard"})
    # The same trigger at high-trust with a sign-off is valid.
    assert v.is_valid({**_GOV_BASE, "triggers_matched": ["secrets"], "tier": "high-trust",
                       "human_approval_required": True})


def test_governor_high_trust_must_require_human_approval():
    v = _validator("governor-decision")
    assert not v.is_valid({**_GOV_BASE, "tier": "high-trust", "triggers_matched": ["auth"],
                           "human_approval_required": False})


_VER_BASE = {
    "schema_version": "1.0", "feature_id": "f", "verified_at": "2026-06-20T00:00:00Z",
    "summary": {"verdict": "pass", "human_review_required": False},
    "tasks": [],
}


def _task(**over):
    base = {"task_id": "T1", "claimed_status": "done",
            "verified_status": "pass", "confidence": "extracted"}
    base.update(over)
    return base


def test_verification_report_rejects_a_proofless_pass():
    v = _validator("verification-report")
    assert not v.is_valid({**_VER_BASE, "tasks": [_task()]})  # pass, no evidence
    assert v.is_valid({**_VER_BASE, "tasks": [_task(files_checked=["a.py"])]})


def test_verification_report_rejects_an_ambiguous_pass():
    v = _validator("verification-report")
    assert not v.is_valid(
        {**_VER_BASE, "tasks": [_task(confidence="ambiguous", evidence=["x"])]})


def test_verification_report_high_trust_must_flag_review_required():
    # Symmetric with the Governor invariant: a report that classifies itself
    # high-trust must at minimum flag that human review is required.
    v = _validator("verification-report")
    bad = {**_VER_BASE, "tasks": [_task(files_checked=["a.py"])],
           "summary": {"verdict": "pass", "risk_level": "high-trust",
                       "human_review_required": False}}
    assert not v.is_valid(bad)
    ok = {**_VER_BASE, "tasks": [_task(files_checked=["a.py"])],
          "summary": {"verdict": "conditional_pass", "risk_level": "high-trust",
                      "human_review_required": True}}
    assert v.is_valid(ok)


def test_verification_report_approved_review_must_be_complete():
    # A bare {status: approved} is not a sign-off: an approval must record who approved,
    # when, and on what evidence. The linter mirrors this with INCOMPLETE_APPROVAL.
    v = _validator("verification-report")
    bare = {**_VER_BASE, "tasks": [_task(files_checked=["a.py"])],
            "summary": {"verdict": "pass", "risk_level": "high-trust",
                        "human_review_required": True,
                        "human_review": {"status": "approved"}}}
    assert not v.is_valid(bare)
    full = {**_VER_BASE, "tasks": [_task(files_checked=["a.py"])],
            "summary": {"verdict": "pass", "risk_level": "high-trust",
                        "human_review_required": True,
                        "human_review": {"status": "approved", "reviewer": "onour",
                                         "approved_at": "2026-06-20T00:00:00Z",
                                         "evidence": ["manual review of the auth path"]}}}
    assert v.is_valid(full)


def test_verification_report_accepts_the_committed_sample():
    v = _validator("verification-report")
    sample = json.loads(
        (REPO / "eval" / "sample" / "verification-report.json").read_text(encoding="utf-8"))
    assert v.is_valid(sample)


def test_verification_report_evidence_calibration_fields_are_optional_and_enumerated():
    # The calibration fields are additive: a report without them still validates,
    # a valid tier and in-range strength validate, and an out-of-vocabulary tier
    # or out-of-range strength is rejected.
    v = _validator("verification-report")
    assert v.is_valid({**_VER_BASE, "tasks": [_task(files_checked=["a.py"])]})  # absent, fine
    assert v.is_valid({**_VER_BASE, "tasks": [
        _task(files_checked=["a.py"], evidence_tier="corroborated", evidence_strength=0.5)]})
    assert not v.is_valid({**_VER_BASE, "tasks": [
        _task(files_checked=["a.py"], evidence_tier="bogus")]})
    assert not v.is_valid({**_VER_BASE, "tasks": [
        _task(files_checked=["a.py"], evidence_strength=1.5)]})


def test_tasks_state_status_enum_includes_blocked_and_conditional():
    enum = _schema("tasks-state")["properties"]["tasks"]["items"]["properties"]["status"]["enum"]
    assert {"pending", "done", "blocked", "conditional"} == set(enum)


def test_tasks_state_accepts_the_new_statuses():
    v = _validator("tasks-state")
    state = {"schema_version": "1.0", "feature_id": "f",
             "tasks": [{"id": "T1", "status": "blocked"}, {"id": "T2", "status": "conditional"}]}
    assert v.is_valid(state)
