"""Contract and packaging tests for the milestone supervisor."""

from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent


def _load_supervisor():
    spec = importlib.util.spec_from_file_location(
        "mergen_supervise_contract",
        REPO / "mergen_supervise.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _schema() -> dict:
    return json.loads(
        (REPO / "core" / "schemas" / "milestone-decision.schema.json").read_text(
            encoding="utf-8"
        )
    )


def test_milestone_schema_parses_and_uses_current_version():
    schema = _schema()
    assert schema["$schema"].startswith("https://json-schema.org/")
    assert schema["properties"]["schema_version"]["const"] == "1.1"
    assert set(schema["properties"]["verdict"]["enum"]) == {
        "pass",
        "conditional_pass",
        "fail",
        "unverifiable",
    }
    assert set(schema["properties"]["advancement_action"]["enum"]) == {
        "advance",
        "hold",
        "return_for_remediation",
        "human_review_required",
    }


def test_schema_accepts_each_decision_mapping():
    jsonschema = pytest.importorskip("jsonschema")
    validator = jsonschema.Draft202012Validator(_schema())
    supervisor = _load_supervisor()
    cases = {
        "pass": "pass",
        "conditional_pass": "unverifiable",
        "fail": "fail",
        "unverifiable": "unverifiable",
    }
    for expected, check_result in cases.items():
        checks = [supervisor._check("fixture", check_result, "fixture")]
        if expected == "conditional_pass":
            checks = [
                supervisor._check(
                    "human-approval",
                    "unverifiable",
                    "approval required",
                    "unavailable",
                )
            ]
        decision = supervisor._decision("M001", checks, {}, None)
        assert decision["verdict"] == expected
        assert validator.is_valid(decision), list(validator.iter_errors(decision))


def test_schema_refuses_advance_for_non_pass():
    jsonschema = pytest.importorskip("jsonschema")
    validator = jsonschema.Draft202012Validator(_schema())
    supervisor = _load_supervisor()
    decision = supervisor._decision(
        "M001",
        [supervisor._check("fixture", "fail", "fixture")],
        {},
        None,
    )
    decision["advancement_action"] = "advance"
    assert not validator.is_valid(decision)


def test_packaging_installs_supervisor_entry_point_and_module():
    text = (REPO / "pyproject.toml").read_text(encoding="utf-8")
    assert 'mergen-supervise = "mergen_supervise:main"' in text
    match = re.search(r"(?ms)^\[tool\.setuptools\]\s*(.*?)(?=^\[)", text + "\n[")
    assert match is not None
    assert "mergen_supervise" in match.group(1)


def test_readme_version_stamp_and_product_boundary_are_present():
    text = (REPO / "README.md").read_text(encoding="utf-8")
    assert "Status: v2.0.0" in text
    assert "External workflow owns" in text
    assert "Mergen owns" in text
    assert "mergen-supervise" in text
    assert "does not claim universal truth" in text.lower()
