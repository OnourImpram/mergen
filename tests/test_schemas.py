"""Schema and sample-artifact checks: the three JSON schemas parse as JSON Schema,
and the committed sample verification-report carries calibrated confidence labels.

Split out of the former test_mergen_v1 grab-bag so each concern has a focused
home (C4, the inverted test strategy).
"""

import importlib.util
import json
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def _schema(name: str) -> dict:
    return json.loads(
        (REPO / "core" / "schemas" / f"{name}.schema.json").read_text(encoding="utf-8")
    )


def _load_verify_core():
    spec = importlib.util.spec_from_file_location(
        "verify_core", REPO / "scripts" / "verify_core.py"
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_schemas_parse():
    for name in ("verification-report", "tasks-state", "governor-decision"):
        data = _schema(name)
        assert data["$schema"].startswith("https://json-schema.org/")
        assert "properties" in data


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


def test_policy_results_shape_is_shared_across_schemas():
    # The "unify policy_results" guarantee: the Governor decision and the
    # verification report use one policy-result item shape and one vocabulary.
    gov_item = _schema("governor-decision")["properties"]["policy_results"]["items"]
    ver_item = _schema("verification-report")["properties"]["policy_results"]["items"]
    assert set(gov_item["properties"]) == set(ver_item["properties"])
    assert gov_item["properties"]["result"]["enum"] == ver_item["properties"]["result"]["enum"]


def test_governor_decision_policy_results_is_optional():
    gov = _schema("governor-decision")
    assert "policy_results" in gov["properties"]
    assert "policy_results" not in gov["required"]
