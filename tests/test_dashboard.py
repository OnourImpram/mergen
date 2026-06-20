"""Tests for the static verification dashboard (scripts/dashboard.py).

Loaded by file path because scripts/ is not an importable package.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def _load():
    spec = importlib.util.spec_from_file_location("dashboard", REPO / "scripts" / "dashboard.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


dashboard = _load()


def _report(feature_id="feat-x", verdict="pass", passed=2, failed=0, ambiguous=0, done=2):
    return {
        "schema_version": "1.0",
        "feature_id": feature_id,
        "verified_at": "2026-06-20T00:00:00Z",
        "summary": {
            "verdict": verdict, "human_review_required": failed > 0,
            "total_done_tasks": done, "mechanically_passed": passed,
            "mechanically_failed": failed, "ambiguous": ambiguous,
        },
        "tasks": [],
        "provenance": {"source_commit": "abcdef1234567890", "working_tree_clean": True,
                       "verifier_version": "1.0"},
    }


def _write(d: Path, name: str, payload, *, bom: bool = False) -> None:
    raw = json.dumps(payload).encode("utf-8")
    (d / name).write_bytes((b"\xef\xbb\xbf" + raw) if bom else raw)


def test_load_reports_reads_reports_and_skips_non_reports(tmp_path):
    _write(tmp_path, "a.json", _report())
    (tmp_path / "notreport.json").write_text('{"hello": 1}', encoding="utf-8")
    (tmp_path / "bad.json").write_text("{not json", encoding="utf-8")
    reports = dashboard.load_reports(tmp_path)
    assert [n for n, _ in reports] == ["a.json"]


def test_load_reports_tolerates_bom(tmp_path):
    _write(tmp_path, "a.json", _report(), bom=True)
    assert len(dashboard.load_reports(tmp_path)) == 1


def test_render_includes_feature_verdict_and_phantom_count():
    # passed=1, phantoms=3, done=4: distinct values so the phantom cell is pinned.
    out = dashboard.render_html([("a.json", _report(feature_id="alpha", verdict="fail",
                                                    passed=1, failed=3, done=4))])
    assert "alpha" in out
    assert "fail" in out
    assert "phantom completions" in out
    assert "<td>3</td>" in out  # the phantom count cell is rendered


def test_render_html_escapes_malicious_values():
    # A report could carry arbitrary strings. They must not break out of markup.
    out = dashboard.render_html([("x.json", _report(feature_id="<script>alert(1)</script>"))])
    assert "<script>alert(1)</script>" not in out
    assert "&lt;script&gt;" in out


def test_render_is_self_contained_offline():
    out = dashboard.render_html([("a.json", _report())])
    assert "http://" not in out and "https://" not in out
    assert "<script" not in out  # no JavaScript at all
    assert "src=" not in out  # no external asset reference


def test_render_empty_directory_message():
    out = dashboard.render_html([])
    assert "No verification reports found" in out


def test_main_writes_html_file(tmp_path):
    _write(tmp_path, "a.json", _report())
    out = tmp_path / "dash.html"
    rc = dashboard.main([str(tmp_path), "--out", str(out)])
    assert rc == 0
    assert out.is_file()
    assert "<!doctype html>" in out.read_text(encoding="utf-8")


def test_main_missing_directory_returns_2(tmp_path):
    assert dashboard.main([str(tmp_path / "nope")]) == 2
