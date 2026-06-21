"""Tests for the cross-run trends and churn analyzer (scripts/trends.py).

Loaded by file path because scripts/ is not an importable package. Reports are
built from the schema-required per-task surface, so the tests prove the metrics
hold without depending on the optional summary counters.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def _load():
    spec = importlib.util.spec_from_file_location("trends", REPO / "scripts" / "trends.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


trends = _load()


def _task(tid, claimed="done", verified="pass", confidence="extracted"):
    return {"task_id": tid, "claimed_status": claimed,
            "verified_status": verified, "confidence": confidence}


def _report(feature, verified_at, tasks):
    phantom = any(t["claimed_status"] == "done" and t["verified_status"] == "fail" for t in tasks)
    return {
        "schema_version": "1.0",
        "feature_id": feature,
        "verified_at": verified_at,
        "summary": {"verdict": "fail" if phantom else "pass", "human_review_required": phantom},
        "tasks": tasks,
    }


def _write(directory, name, report):
    (directory / name).write_text(json.dumps(report), encoding="utf-8")


def _corpus_dir(parent, name):
    d = parent / name
    d.mkdir()
    return d


# --------------------------------------------------------------------------- #
# load_runs
# --------------------------------------------------------------------------- #

def test_load_runs_orders_by_verified_at(tmp_path):
    _write(tmp_path, "b.json", _report("f", "2026-02-01T00:00:00Z", [_task("T1")]))
    _write(tmp_path, "a.json", _report("f", "2026-01-01T00:00:00Z", [_task("T1")]))
    runs = trends.load_runs(tmp_path)
    assert [r[1]["verified_at"] for r in runs] == ["2026-01-01T00:00:00Z", "2026-02-01T00:00:00Z"]


def test_load_runs_skips_non_report_and_bad_json(tmp_path):
    _write(tmp_path, "ok.json", _report("f", "2026-01-01T00:00:00Z", [_task("T1")]))
    (tmp_path / "bad.json").write_text("{ not json", encoding="utf-8")
    (tmp_path / "notreport.json").write_text(json.dumps({"feature_id": "x"}), encoding="utf-8")
    runs = trends.load_runs(tmp_path)
    assert [r[0] for r in runs] == ["ok.json"]


# --------------------------------------------------------------------------- #
# run_metrics
# --------------------------------------------------------------------------- #

def test_run_metrics_counts_from_tasks_array():
    report = _report("f", "2026-01-01T00:00:00Z", [
        _task("T1", "done", "pass", "extracted"),
        _task("T2", "done", "fail", "extracted"),   # phantom
        _task("T3", "done", "pass", "ambiguous"),
    ])
    m = trends.run_metrics("r.json", report)
    assert m["total"] == 3
    assert m["claimed_done"] == 3
    assert m["passed"] == 2
    assert m["phantoms"] == 1
    assert m["ambiguous"] == 1
    assert abs(m["work_done_rate"] - (2 / 3)) < 1e-9
    assert m["verdict"] == "fail"


def test_run_metrics_work_done_rate_none_when_nothing_claimed_done():
    report = _report("f", "2026-01-01T00:00:00Z", [_task("T1", "todo", "fail")])
    m = trends.run_metrics("r.json", report)
    assert m["claimed_done"] == 0
    assert m["work_done_rate"] is None


# --------------------------------------------------------------------------- #
# task_churn
# --------------------------------------------------------------------------- #

def test_task_churn_counts_flips_and_phantoms_and_ranks():
    runs = [
        ("r1.json", _report("f", "2026-01-01T00:00:00Z", [_task("T1", "done", "pass"), _task("T2", "done", "pass")])),
        ("r2.json", _report("f", "2026-01-02T00:00:00Z", [_task("T1", "done", "fail"), _task("T2", "done", "pass")])),
        ("r3.json", _report("f", "2026-01-03T00:00:00Z", [_task("T1", "done", "pass"), _task("T2", "done", "pass")])),
    ]
    churn = trends.task_churn(runs)
    by_id = {c["task_id"]: c for c in churn}
    assert by_id["T1"]["flips"] == 2          # pass -> fail -> pass
    assert by_id["T1"]["phantom_runs"] == 1   # the middle run
    assert by_id["T1"]["runs"] == 3
    assert by_id["T1"]["churn_score"] == 3
    assert by_id["T1"]["last_status"] == "pass"
    assert by_id["T2"]["churn_score"] == 0    # stable, never churns
    # The churny task ranks ahead of the stable one.
    assert churn[0]["task_id"] == "T1"


# --------------------------------------------------------------------------- #
# rendering
# --------------------------------------------------------------------------- #

def test_render_html_has_both_sections_and_a_sparkline():
    runs = [
        ("r1.json", _report("f", "2026-01-01T00:00:00Z", [_task("T1", "done", "fail")])),
        ("r2.json", _report("f", "2026-01-02T00:00:00Z", [_task("T1", "done", "pass")])),
    ]
    out = trends.render_html(runs)
    assert "Mergen verification trends" in out
    assert "Trends across runs" in out
    assert "Task churn leaderboard" in out
    assert "<svg" in out and "polyline" in out
    assert "T1" in out
    assert "<script" not in out  # no JavaScript, ever


def test_render_html_empty_when_no_runs():
    out = trends.render_html([])
    assert "No verification reports with a tasks array" in out
    # Still a well-formed page, not a bare string or a crash swallowed upstream.
    assert out.startswith("<!doctype html")
    assert "Mergen verification trends" in out


def test_render_html_announces_truncation_when_over_top():
    # Three phantom tasks, each churn_score 1. With top=2 the page must say it
    # truncated rather than silently dropping the third.
    runs = [("r.json", _report("f", "2026-01-01T00:00:00Z",
             [_task("T1", "done", "fail"), _task("T2", "done", "fail"), _task("T3", "done", "fail")]))]
    out = trends.render_html(runs, top=2)
    assert "Showing the 2 most churny of 3" in out


def test_render_html_truncation_keeps_highest_scored_task():
    # Differing churn scores across a multi-run history. T1 churns hardest
    # (pass -> fail -> pass: 2 flips + 1 phantom = 3), T2 less (1 flip + 1 phantom
    # = 2), T3 stable (0). With top=2 the page must announce the cut and keep the
    # highest-scored task in the shown slice, proving the sort drives truncation.
    runs = [
        ("r1.json", _report("f", "2026-01-01T00:00:00Z",
            [_task("T1", "done", "pass"), _task("T2", "done", "pass"), _task("T3", "done", "pass")])),
        ("r2.json", _report("f", "2026-01-02T00:00:00Z",
            [_task("T1", "done", "fail"), _task("T2", "done", "pass"), _task("T3", "done", "pass")])),
        ("r3.json", _report("f", "2026-01-03T00:00:00Z",
            [_task("T1", "done", "pass"), _task("T2", "done", "fail"), _task("T3", "done", "pass")])),
    ]
    churn = trends.task_churn(runs)
    assert churn[0]["task_id"] == "T1" and churn[0]["churn_score"] == 3
    out = trends.render_html(runs, top=2)
    assert "Showing the 2 most churny of 3" in out
    assert "T1" in out  # the highest-scored task survives the cut


def test_sparkline_single_value_is_a_dot_and_multi_is_a_line():
    assert "circle" in trends._sparkline([3])
    assert "polyline" in trends._sparkline([1, 2, 3])
    assert trends._sparkline([]) == ""


# --------------------------------------------------------------------------- #
# export and main
# --------------------------------------------------------------------------- #

def test_build_export_shape(tmp_path):
    _write(tmp_path, "r.json", _report("f", "2026-01-01T00:00:00Z", [_task("T1", "done", "fail")]))
    runs = trends.load_runs(tmp_path)
    export = trends.build_export(tmp_path, runs)
    assert export["schema"] == "mergen-trends/1.1"
    assert export["report_count"] == 1
    assert len(export["runs"]) == 1
    assert export["churn"][0]["task_id"] == "T1"
    assert export["feature_churn"][0]["feature_id"] == "f"


# --------------------------------------------------------------------------- #
# feature_churn (spec-pattern clustering)
# --------------------------------------------------------------------------- #

def test_feature_churn_rolls_up_per_feature():
    runs = [
        ("r1.json", _report("auth", "2026-01-01T00:00:00Z", [_task("A1", "done", "pass")])),
        ("r2.json", _report("auth", "2026-01-02T00:00:00Z", [_task("A1", "done", "fail")])),  # flip+phantom
        ("r3.json", _report("pay", "2026-01-03T00:00:00Z", [_task("P1", "done", "fail")])),    # phantom
    ]
    fc = trends.feature_churn(runs)
    by_f = {r["feature_id"]: r for r in fc}
    assert by_f["auth"]["flips"] == 1
    assert by_f["auth"]["phantom_runs"] == 1
    assert by_f["auth"]["churn_score"] == 2
    assert by_f["auth"]["tasks"] == 1
    assert by_f["auth"]["runs"] == 2
    assert by_f["pay"]["churn_score"] == 1
    # The harder-churning spec ranks first.
    assert fc[0]["feature_id"] == "auth"


def test_feature_churn_does_not_pool_task_id_across_features():
    # The same task_id lives in two features. Pooled task churn would merge them
    # (pass->fail->pass->pass = 2 flips + 1 phantom = 3), but the feature is the
    # task's namespace, so per-feature each id is its own task.
    runs = [
        ("r1.json", _report("A", "2026-01-01T00:00:00Z", [_task("T1", "done", "pass")])),
        ("r2.json", _report("A", "2026-01-02T00:00:00Z", [_task("T1", "done", "fail")])),
        ("r3.json", _report("B", "2026-01-03T00:00:00Z", [_task("T1", "done", "pass")])),
        ("r4.json", _report("B", "2026-01-04T00:00:00Z", [_task("T1", "done", "pass")])),
    ]
    by_f = {r["feature_id"]: r for r in trends.feature_churn(runs)}
    assert by_f["A"]["churn_score"] == 2   # A's T1: one flip + one phantom
    assert by_f["B"]["churn_score"] == 0   # B's T1: stable, never churns
    # Proof the namespacing matters: pooled across features it would be 3.
    pooled = trends.task_churn(runs)
    assert pooled[0]["task_id"] == "T1" and pooled[0]["churn_score"] == 3


# --------------------------------------------------------------------------- #
# multi-corpus
# --------------------------------------------------------------------------- #

def test_corpus_summary_aggregates_features_and_rate():
    runs = [
        ("r1.json", _report("auth", "2026-01-01T00:00:00Z",
                            [_task("A1", "done", "pass"), _task("A2", "done", "fail")])),
        ("r2.json", _report("pay", "2026-01-02T00:00:00Z", [_task("P1", "done", "pass")])),
    ]
    s = trends._corpus_summary("lbl", runs)
    assert s["label"] == "lbl"
    assert s["report_count"] == 2
    assert s["features"] == 2
    assert s["latest_verdict"] == "pass"            # r2 is latest, no phantom
    # r1 work-done = 1/2, r2 = 1/1, mean = 0.75.
    assert abs(s["mean_work_done_rate"] - 0.75) < 1e-9


def test_build_multi_export_has_comparison_and_corpora(tmp_path):
    a = _corpus_dir(tmp_path, "a")
    b = _corpus_dir(tmp_path, "b")
    _write(a, "r.json", _report("A", "2026-01-01T00:00:00Z", [_task("T1", "done", "fail")]))
    _write(b, "r.json", _report("B", "2026-01-01T00:00:00Z", [_task("T1", "done", "pass")]))
    export = trends.build_multi_export(trends.load_corpora([a, b]))
    assert export["schema"] == "mergen-trends/1.1"
    assert export["report_count"] == 2
    assert len(export["corpora"]) == 2
    assert {c["label"] for c in export["comparison"]} == {str(a), str(b)}
    assert all("feature_churn" in c for c in export["corpora"])


def test_render_multi_has_comparison_and_per_corpus(tmp_path):
    corpora = [
        (str(tmp_path / "a"),
         [("r.json", _report("A", "2026-01-01T00:00:00Z", [_task("T1", "done", "fail")]))]),
        (str(tmp_path / "b"),
         [("r.json", _report("B", "2026-01-02T00:00:00Z", [_task("T2", "done", "pass")]))]),
    ]
    out = trends.render_multi(corpora)
    assert out.startswith("<!doctype html")
    assert "Corpora compared" in out
    assert "Corpus:" in out
    assert "Trends across runs" in out   # each corpus rendered in full
    assert "<script" not in out


def test_render_html_shows_spec_table_when_multiple_features():
    runs = [
        ("r1.json", _report("auth", "2026-01-01T00:00:00Z", [_task("A1", "done", "fail")])),
        ("r2.json", _report("pay", "2026-01-02T00:00:00Z", [_task("P1", "done", "fail")])),
    ]
    out = trends.render_html(runs)
    assert "Spec churn leaderboard" in out
    assert "auth" in out and "pay" in out


def test_render_html_hides_spec_table_for_single_feature():
    runs = [
        ("r1.json", _report("f", "2026-01-01T00:00:00Z", [_task("T1", "done", "fail")])),
        ("r2.json", _report("f", "2026-01-02T00:00:00Z", [_task("T1", "done", "pass")])),
    ]
    out = trends.render_html(runs)
    assert "Spec churn leaderboard" not in out


def test_main_multi_dir_json_compares_corpora(tmp_path, capsys):
    a = _corpus_dir(tmp_path, "a")
    b = _corpus_dir(tmp_path, "b")
    _write(a, "r.json", _report("A", "2026-01-01T00:00:00Z", [_task("T1", "done", "fail")]))
    _write(b, "r.json", _report("B", "2026-01-01T00:00:00Z", [_task("T1", "done", "pass")]))
    rc = trends.main([str(a), str(b), "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["schema"] == "mergen-trends/1.1"
    assert payload["report_count"] == 2
    assert len(payload["corpora"]) == 2
    assert {c["label"] for c in payload["comparison"]} == {str(a), str(b)}


def test_main_multi_dir_one_bad_returns_2(tmp_path):
    a = _corpus_dir(tmp_path, "a")
    _write(a, "r.json", _report("A", "2026-01-01T00:00:00Z", [_task("T1")]))
    assert trends.main([str(a), str(tmp_path / "nope")]) == 2


def test_main_multi_dir_html_to_stdout(tmp_path, capsys):
    a = _corpus_dir(tmp_path, "a")
    b = _corpus_dir(tmp_path, "b")
    _write(a, "r.json", _report("A", "2026-01-01T00:00:00Z", [_task("T1", "done", "fail")]))
    _write(b, "r.json", _report("B", "2026-01-01T00:00:00Z", [_task("T2", "done", "pass")]))
    rc = trends.main([str(a), str(b)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Corpora compared" in out
    assert "Corpus:" in out


# --------------------------------------------------------------------------- #
# robustness and contract (review follow-ups)
# --------------------------------------------------------------------------- #

def test_feature_churn_missing_feature_id_uses_sentinel_not_unknown():
    # load_runs tolerates a report missing feature_id. Its tasks must not pool with
    # a report that legitimately names its feature "unknown", or one would
    # contaminate the other's churn score.
    no_fid = {
        "schema_version": "1.0", "verified_at": "2026-01-01T00:00:00Z",
        "summary": {"verdict": "fail", "human_review_required": True},
        "tasks": [_task("T1", "done", "fail")],   # a phantom
    }
    runs = [
        ("r1.json", no_fid),
        ("r2.json", _report("unknown", "2026-01-02T00:00:00Z", [_task("T2", "done", "pass")])),
    ]
    by_f = {r["feature_id"]: r for r in trends.feature_churn(runs)}
    assert trends._NO_FEATURE in by_f             # missing feature_id gets its own bucket
    assert "unknown" in by_f                       # the literal "unknown" feature is separate
    assert by_f[trends._NO_FEATURE]["phantom_runs"] == 1
    assert by_f["unknown"]["churn_score"] == 0     # the legit feature is uncontaminated


def test_render_multi_with_one_empty_corpus(tmp_path):
    a = _corpus_dir(tmp_path, "a")
    b = _corpus_dir(tmp_path, "b")  # empty, no reports
    _write(a, "r.json", _report("A", "2026-01-01T00:00:00Z", [_task("T1")]))
    out = trends.render_multi(trends.load_corpora([a, b]))
    assert out.startswith("<!doctype html")
    assert "Corpora compared" in out
    assert "No verification reports" in out        # the empty corpus renders its empty section


def test_render_html_spec_table_announces_truncation():
    # Three single-phantom features, each churn 1. With top=2 the spec table must
    # announce the cut and name "specs", not "tasks".
    runs = [
        ("r1.json", _report("auth", "2026-01-01T00:00:00Z", [_task("A", "done", "fail")])),
        ("r2.json", _report("pay", "2026-01-02T00:00:00Z", [_task("B", "done", "fail")])),
        ("r3.json", _report("core", "2026-01-03T00:00:00Z", [_task("C", "done", "fail")])),
    ]
    out = trends.render_html(runs, top=2)
    assert "Showing the 2 most churny of 3 specs" in out


def test_comparison_churny_tasks_matches_corpus_export(tmp_path):
    # The comparison row's churny_tasks must equal the count of non-zero churn
    # entries in that corpus's own churn list, so the two computations cannot drift.
    a = _corpus_dir(tmp_path, "a")
    b = _corpus_dir(tmp_path, "b")
    _write(a, "r1.json", _report("A", "2026-01-01T00:00:00Z", [_task("T1", "done", "pass")]))
    _write(a, "r2.json", _report("A", "2026-01-02T00:00:00Z", [_task("T1", "done", "fail")]))
    _write(b, "r.json", _report("B", "2026-01-01T00:00:00Z", [_task("T2", "done", "pass")]))
    export = trends.build_multi_export(trends.load_corpora([a, b]))
    by_source = {c["source_dir"]: c for c in export["corpora"]}
    for summary in export["comparison"]:
        corpus = by_source[summary["label"]]
        expected = sum(1 for c in corpus["churn"] if c["churn_score"] > 0)
        assert summary["churny_tasks"] == expected


def test_main_returns_2_on_non_directory(tmp_path):
    assert trends.main([str(tmp_path / "nope")]) == 2


def test_main_json_export_to_stdout(tmp_path, capsys):
    _write(tmp_path, "r.json", _report("f", "2026-01-01T00:00:00Z",
           [_task("T1", "done", "pass"), _task("T2", "done", "fail")]))
    rc = trends.main([str(tmp_path), "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["report_count"] == 1
    assert payload["runs"][0]["phantoms"] == 1


def test_main_writes_html_to_out(tmp_path):
    _write(tmp_path, "r.json", _report("f", "2026-01-01T00:00:00Z", [_task("T1")]))
    out = tmp_path / "trends.html"
    rc = trends.main([str(tmp_path), "--out", str(out)])
    assert rc == 0
    assert out.read_text(encoding="utf-8").startswith("<!doctype html")


def test_main_html_to_stdout_default(tmp_path, capsys):
    _write(tmp_path, "r.json", _report("f", "2026-01-01T00:00:00Z", [_task("T1")]))
    rc = trends.main([str(tmp_path)])
    assert rc == 0
    assert "Mergen verification trends" in capsys.readouterr().out


def test_main_tolerates_bom(tmp_path):
    body = json.dumps(_report("f", "2026-01-01T00:00:00Z", [_task("T1")])).encode("utf-8")
    (tmp_path / "r.json").write_bytes(b"\xef\xbb\xbf" + body)
    assert trends.main([str(tmp_path), "--json"]) == 0
