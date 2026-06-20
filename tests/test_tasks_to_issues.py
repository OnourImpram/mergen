"""Tests for the tasks.md to issue-stub renderer (scripts/tasks_to_issues.py).

Loaded by file path because scripts/ is not an importable package.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def _load():
    spec = importlib.util.spec_from_file_location(
        "tasks_to_issues", REPO / "scripts" / "tasks_to_issues.py"
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


t2i = _load()

_TASKS_MD = (
    "# Tasks\n\n"
    "## Setup\n"
    "- [X] T001 [P] scaffold the package in src/pkg/__init__.py\n"
    "- [ ] T002 [US1] add the parser in src/pkg/parse.py\n"
    "* [ ] T003 wire the CLI in src/pkg/cli.py\n"
    "not a task line\n"
)


def test_parse_extracts_id_state_tags_and_description():
    tasks = t2i.parse_tasks(_TASKS_MD)
    assert [t["id"] for t in tasks] == ["T001", "T002", "T003"]
    assert tasks[0]["done"] is True
    assert tasks[1]["done"] is False
    assert "[P]" in tasks[0]["tags"]
    assert "[US1]" in tasks[1]["tags"]
    # Tags are stripped out of the description text.
    assert tasks[0]["description"] == "scaffold the package in src/pkg/__init__.py"
    assert "[P]" not in tasks[0]["description"]


def test_render_all_skips_done_by_default_and_titles_each_issue():
    out = t2i.render_all(t2i.parse_tasks(_TASKS_MD), {}, include_done=False)
    assert "### T002: add the parser in src/pkg/parse.py" in out
    assert "### T003: wire the CLI in src/pkg/cli.py" in out
    assert "T001" not in out  # done task skipped
    assert "2 task(s) rendered out of 3 total" in out
    # Honest: it renders, it does not create.
    assert "never creates issues" in out


def test_render_all_include_done_shows_completed():
    out = t2i.render_all(t2i.parse_tasks(_TASKS_MD), {}, include_done=True)
    assert "### T001:" in out
    assert "3 task(s) rendered out of 3 total" in out


def test_render_annotates_dependencies_from_a_dag(tmp_path):
    dag = [[{"id": "T002", "files": ["src/pkg/parse.py"], "parallel": False,
             "depends_on": ["T001"]}]]
    dag_path = tmp_path / "tasks-dag.json"
    dag_path.write_text(json.dumps(dag), encoding="utf-8")
    deps = t2i.load_deps(str(dag_path))
    out = t2i.render_all(t2i.parse_tasks(_TASKS_MD), deps, include_done=False)
    assert "Depends on: T001" in out


def test_load_deps_none_and_bad_are_empty(tmp_path):
    assert t2i.load_deps(None) == {}
    bad = tmp_path / "dag.json"
    bad.write_text("{ not json", encoding="utf-8")
    assert t2i.load_deps(str(bad)) == {}


def test_main_renders_to_stdout(tmp_path, capsys):
    md = tmp_path / "tasks.md"
    md.write_text(_TASKS_MD, encoding="utf-8")
    rc = t2i.main([str(md)])
    assert rc == 0
    assert "### T002:" in capsys.readouterr().out


def test_main_missing_file_returns_2(tmp_path):
    assert t2i.main([str(tmp_path / "nope.md")]) == 2


def test_main_no_tasks_returns_1(tmp_path):
    md = tmp_path / "tasks.md"
    md.write_text("# Tasks\n\njust prose, no checklist\n", encoding="utf-8")
    assert t2i.main([str(md)]) == 1
