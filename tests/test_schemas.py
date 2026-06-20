"""Schema and sample-artifact checks: the three JSON schemas parse as JSON Schema,
and the committed sample verification-report carries calibrated confidence labels.

Split out of the former test_mergen_v1 grab-bag so each concern has a focused
home (C4, the inverted test strategy).
"""

import json
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def test_schemas_parse():
    for name in ("verification-report", "tasks-state", "governor-decision"):
        data = json.loads((REPO / "core" / "schemas" / f"{name}.schema.json").read_text(encoding="utf-8"))
        assert data["$schema"].startswith("https://json-schema.org/")
        assert "properties" in data


def test_sample_report_carries_confidence_labels():
    rep = json.loads((REPO / "eval" / "sample" / "verification-report.json").read_text(encoding="utf-8"))
    assert rep["schema_version"] == "1.0"
    for task in rep["tasks"]:
        assert task["confidence"] in ("extracted", "inferred", "ambiguous")
