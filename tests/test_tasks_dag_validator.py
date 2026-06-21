"""Tests for scripts/tasks_dag_validator.py (roadmap 1.3): the deterministic
tasks-dag checker (unique ids, resolvable refs, no cycles, earlier-wave deps).
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import tasks_dag_validator as tdv  # noqa: E402

_VALID = [
    [{"id": "T001", "files": ["a.py"], "parallel": True, "depends_on": [], "test_task": "T010"}],
    [{"id": "T002", "files": ["b.py"], "parallel": False, "depends_on": ["T001"], "test_task": None}],
]


def test_valid_dag_passes():
    result = tdv.validate(_VALID)
    assert result["pass"] is True
    assert result["errors"] == []


def test_duplicate_id_fails():
    dag = [
        [{"id": "T1", "files": [], "parallel": True, "depends_on": []}],
        [{"id": "T1", "files": [], "parallel": True, "depends_on": []}],
    ]
    result = tdv.validate(dag)
    assert not result["pass"]
    assert any("duplicate" in e for e in result["errors"])


def test_broken_reference_fails():
    dag = [[{"id": "T1", "files": [], "parallel": True, "depends_on": ["TX"]}]]
    result = tdv.validate(dag)
    assert not result["pass"]
    assert any("unknown task TX" in e for e in result["errors"])


def test_cycle_fails():
    dag = [[
        {"id": "T1", "files": [], "parallel": True, "depends_on": ["T2"]},
        {"id": "T2", "files": [], "parallel": True, "depends_on": ["T1"]},
    ]]
    result = tdv.validate(dag)
    assert not result["pass"]
    assert any("cycle" in e for e in result["errors"])


def test_dependency_in_same_wave_fails():
    dag = [[
        {"id": "T1", "files": [], "parallel": True, "depends_on": []},
        {"id": "T2", "files": [], "parallel": True, "depends_on": ["T1"]},
    ]]
    result = tdv.validate(dag)
    assert not result["pass"]
    assert any("not an earlier wave" in e for e in result["errors"])


def test_dependency_in_later_wave_fails():
    dag = [
        [{"id": "T1", "files": [], "parallel": True, "depends_on": ["T2"]}],
        [{"id": "T2", "files": [], "parallel": True, "depends_on": []}],
    ]
    result = tdv.validate(dag)
    assert not result["pass"]
    assert any("not an earlier wave" in e for e in result["errors"])


def test_non_array_top_level_fails():
    result = tdv.validate({"not": "a list"})
    assert not result["pass"]


def test_cli_gate_passes_on_valid(tmp_path, capsys):
    f = tmp_path / "dag.json"
    f.write_text(json.dumps(_VALID), encoding="utf-8")
    assert tdv.main(["--file", str(f), "--gate"]) == 0


def test_cli_gate_fails_on_invalid(tmp_path, capsys):
    f = tmp_path / "dag.json"
    f.write_text(
        json.dumps([[{"id": "T1", "files": [], "parallel": True, "depends_on": ["TX"]}]]),
        encoding="utf-8",
    )
    assert tdv.main(["--file", str(f), "--gate"]) == 1


def test_cli_gate_fails_on_invalid_json(tmp_path, capsys):
    f = tmp_path / "dag.json"
    f.write_text("not json at all", encoding="utf-8")
    assert tdv.main(["--file", str(f), "--gate"]) == 1


def test_committed_schema_parses():
    repo = Path(__file__).resolve().parent.parent
    schema = json.loads(
        (repo / "core" / "schemas" / "tasks-dag.schema.json").read_text(encoding="utf-8")
    )
    assert schema["$schema"].startswith("https://json-schema.org/")
    assert schema["type"] == "array"
