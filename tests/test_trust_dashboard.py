"""Tests for scripts/trust_dashboard.py, the offline HTML view of the trust graph.

Loaded by file path because scripts/ is not an importable package. Graphs are
built with the real trust_graph module against a JSONL file on disk, so the
dashboard renders what the graph actually records.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
_TS = "2026-06-21T00:00:00+00:00"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, REPO / "scripts" / f"{name}.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


td = _load("trust_dashboard")
tg = _load("trust_graph")


def _report(*, feature="feat-x", tasks_sha="ts-1", commit="c0ffee", verdict="pass",
            risk=None, human_required=False, human_status=None):
    summary = {"verdict": verdict, "human_review_required": human_required}
    if risk is not None:
        summary["risk_level"] = risk
    if human_status is not None:
        summary["human_review"] = {"status": human_status}
    return {
        "schema_version": "1.0", "feature_id": feature,
        "verified_at": "2026-06-20T00:00:00Z", "summary": summary,
        "tasks": [], "provenance": {"tasks_state_sha256": tasks_sha, "source_commit": commit},
    }


def test_render_has_sections_and_no_script(tmp_path):
    g = tmp_path / "graph.jsonl"
    tg.ingest_report(g, _report(feature="auth-feature"), _TS, report_sha256="rep-1")
    out = td.render_html(tg.load_graph(g))
    assert out.startswith("<!doctype html")
    assert "Mergen trust graph dashboard" in out
    assert "Broken lineage" in out
    assert "Unsigned high-trust" in out
    assert "Provenance" in out
    assert "auth-feature" in out
    assert "<script" not in out  # no JavaScript, ever


def test_clean_graph_reports_no_broken_lineage_and_no_unsigned(tmp_path):
    g = tmp_path / "graph.jsonl"
    tg.ingest_report(g, _report(verdict="pass"), _TS, report_sha256="rep-clean")
    out = td.render_html(tg.load_graph(g))
    assert "No broken lineage" in out
    assert "No unsigned high-trust nodes" in out


def test_broken_lineage_surfaces_a_dangling_edge(tmp_path):
    g = tmp_path / "graph.jsonl"
    a = tg.add_node(g, "verification-report", "rep", {}, _TS)
    tg.add_edge(g, a, tg.node_id("tasks-state", "never"), "verified", _TS)
    out = td.render_html(tg.load_graph(g))
    # The dangling-edge table renders, and the missing endpoint is named.
    assert "missing endpoint" in out
    assert "No broken lineage" not in out


def test_unsigned_high_trust_is_flagged(tmp_path):
    g = tmp_path / "graph.jsonl"
    tg.ingest_report(g, _report(risk="high-trust", human_required=True), _TS,
                     report_sha256="rep-ht")
    out = td.render_html(tg.load_graph(g))
    assert "No unsigned high-trust nodes" not in out


def test_provenance_row_shows_verified_state_and_commit(tmp_path):
    g = tmp_path / "graph.jsonl"
    tg.ingest_report(g, _report(tasks_sha="state-sha-here", commit="commit-hash-here"),
                     _TS, report_sha256="rep-prov")
    out = td.render_html(tg.load_graph(g))
    # The verified tasks-state and the commit appear as short identities.
    assert "state-sha-he" in out   # first 12 chars of the tasks-state identity
    assert "commit-hash-" in out   # first 12 chars of the commit identity


def test_hostile_feature_id_is_escaped(tmp_path):
    g = tmp_path / "graph.jsonl"
    tg.ingest_report(g, _report(feature="<script>alert(1)</script>"), _TS, report_sha256="rep-x")
    out = td.render_html(tg.load_graph(g))
    assert "<script>alert(1)</script>" not in out
    assert "&lt;script&gt;" in out


def test_empty_graph_renders_empty_messages(tmp_path):
    g = tmp_path / "graph.jsonl"
    g.write_text("", encoding="utf-8")
    out = td.render_html(tg.load_graph(g))
    assert "No verification-report nodes in this graph yet" in out
    assert out.startswith("<!doctype html")


def test_main_writes_to_out(tmp_path):
    g = tmp_path / "graph.jsonl"
    tg.ingest_report(g, _report(), _TS, report_sha256="rep-o")
    out = tmp_path / "trust.html"
    assert td.main([str(g), "--out", str(out)]) == 0
    assert out.read_text(encoding="utf-8").startswith("<!doctype html")


def test_main_returns_2_on_non_file(tmp_path):
    assert td.main([str(tmp_path / "nope.jsonl")]) == 2


def test_mergen_graph_dashboard_subcommand(tmp_path):
    g = tmp_path / "graph.jsonl"
    tg.ingest_report(g, _report(), _TS, report_sha256="rep-sub")
    out = tmp_path / "d.html"
    # The `mergen graph dashboard` path forwards through trust_graph into the
    # renderer, proving the subcommand wiring.
    assert tg.main(["dashboard", "--graph", str(g), "--out", str(out)]) == 0
    assert out.read_text(encoding="utf-8").startswith("<!doctype html")


# --------------------------------------------------------------------------- #
# review follow-ups: byte stability, na fallback, both-missing label, verdict class
# --------------------------------------------------------------------------- #

def test_render_is_byte_stable(tmp_path):
    # A given graph must render to identical bytes, so no set or dict iteration
    # order leaks into the page.
    g = tmp_path / "graph.jsonl"
    tg.ingest_report(g, _report(feature="s1"), _TS, report_sha256="rep-s1")
    tg.ingest_report(g, _report(feature="s2"), _TS, report_sha256="rep-s2")
    graph = tg.load_graph(g)
    assert td.render_html(graph) == td.render_html(graph)


def test_provenance_row_no_tasks_state_shows_na(tmp_path):
    g = tmp_path / "graph.jsonl"
    rep = {"schema_version": "1.0", "feature_id": "no-ts",
           "verified_at": "2026-06-20T00:00:00Z", "summary": {"verdict": "pass"},
           "tasks": [], "provenance": {}}  # no tasks_state_sha256
    tg.ingest_report(g, rep, _TS, report_sha256="rep-no-ts")
    out = td.render_html(tg.load_graph(g))
    # n/a fills both the verified-state and the commit columns.
    assert out.count(">n/a<") >= 2


def test_dangling_edge_both_endpoints_missing_labels_from_and_to(tmp_path):
    g = tmp_path / "graph.jsonl"
    tg.add_edge(g, "a" * 16, "b" * 16, "verified", _TS)  # neither endpoint recorded
    out = td.render_html(tg.load_graph(g))
    assert "from and to" in out


def test_hostile_verdict_class_stays_a_controlled_constant(tmp_path):
    import re
    g = tmp_path / "graph.jsonl"
    # A verdict crafted to break out of a class attribute if it were not constrained.
    tg.ingest_report(g, _report(verdict='" onmouseover="alert(1)" x="'),
                     _TS, report_sha256="rep-hv")
    out = td.render_html(tg.load_graph(g))
    classes = re.findall(r'class="tag ([^"]+)"', out)
    assert classes  # at least one verdict tag rendered
    assert all(c in {"ok", "warn", "bad", "muted"} for c in classes)
    assert '" onmouseover=' not in out
