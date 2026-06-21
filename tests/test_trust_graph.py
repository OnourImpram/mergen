"""Tests for scripts/trust_graph.py, the typed append-only provenance graph.

Loaded by file path because scripts/ is not an importable package. The graph is
exercised against a real JSONL file on disk so the append-only and rebuildable
projection guarantees are tested, not mocked. The timestamp is injected, matching
the ledger's deterministic contract.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
_TS = "2026-06-21T00:00:00+00:00"


def _load():
    spec = importlib.util.spec_from_file_location("trust_graph", REPO / "scripts" / "trust_graph.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


tg = _load()


def _report(*, tasks_sha="ts-abc", commit="c0ffee", verdict="pass",
            risk=None, human_required=False, human_status=None, policy=None):
    summary = {"verdict": verdict, "human_review_required": human_required}
    if risk is not None:
        summary["risk_level"] = risk
    if human_status is not None:
        summary["human_review"] = {"status": human_status}
    report = {
        "schema_version": "1.0", "feature_id": "feat-x",
        "verified_at": "2026-06-20T00:00:00Z", "summary": summary,
        "tasks": [], "provenance": {"tasks_state_sha256": tasks_sha, "source_commit": commit},
    }
    if policy is not None:
        report["policy_results"] = policy
    return report


# --------------------------------------------------------------------------- #
# content-addressed ids
# --------------------------------------------------------------------------- #

def test_node_id_is_stable_and_field_separated():
    assert tg.node_id("commit", "abc") == tg.node_id("commit", "abc")
    # The null separator prevents ("a","bc") from colliding with ("ab","c").
    assert tg.node_id("a", "bc") != tg.node_id("ab", "c")


def test_edge_id_is_stable_per_endpoints_and_type():
    a = tg.edge_id("n1", "n2", "verified")
    assert a == tg.edge_id("n1", "n2", "verified")
    assert a != tg.edge_id("n1", "n2", "cited")
    assert a != tg.edge_id("n2", "n1", "verified")


# --------------------------------------------------------------------------- #
# append + projection
# --------------------------------------------------------------------------- #

def test_add_node_and_edge_build_projection(tmp_path):
    g = tmp_path / "graph.jsonl"
    a = tg.add_node(g, "verification-report", "rep1", {"verdict": "pass"}, _TS)
    b = tg.add_node(g, "tasks-state", "ts1", {}, _TS)
    tg.add_edge(g, a, b, "verified", _TS)
    graph = tg.load_graph(g)
    assert a in graph.nodes and b in graph.nodes
    assert graph.out[a][0]["to"] == b
    assert graph.inc[b][0]["from"] == a


def test_reingest_is_idempotent_on_nodes_and_edges(tmp_path):
    g = tmp_path / "graph.jsonl"
    rep = _report()
    tg.ingest_report(g, rep, _TS, report_sha256="sha-1")
    tg.ingest_report(g, rep, _TS, report_sha256="sha-1")  # same report twice
    graph = tg.load_graph(g)
    # report + tasks-state + commit = 3 nodes, no duplicates.
    assert len(graph.nodes) == 3
    # verified + at-commit = 2 edges, deduped despite the double ingest.
    assert len(graph._edges) == 2


# --------------------------------------------------------------------------- #
# proof_chain
# --------------------------------------------------------------------------- #

def test_proof_chain_walks_report_to_state_to_commit(tmp_path):
    g = tmp_path / "graph.jsonl"
    tg.ingest_report(g, _report(tasks_sha="ts-1", commit="c-1"), _TS, report_sha256="rep-1")
    graph = tg.load_graph(g)
    ts_node = tg.node_id("tasks-state", "ts-1")
    chain = tg.proof_chain(graph, ts_node)
    kinds = {n["kind"] for n in chain["nodes"]}
    # From the tasks-state we reach the report that verified it (incoming) and the
    # commit it sits at (outgoing), without reading any artifact.
    assert kinds == {"verification-report", "tasks-state", "commit"}
    edge_types = {e["type"] for e in chain["edges"]}
    assert edge_types == {"verified", "at-commit"}


def test_proof_chain_includes_cited_policy_results(tmp_path):
    g = tmp_path / "graph.jsonl"
    rep = _report(policy=[{"policy_id": "secrets", "result": "fail", "reason": "x"}])
    rid = tg.ingest_report(g, rep, _TS, report_sha256="rep-2")
    graph = tg.load_graph(g)
    chain = tg.proof_chain(graph, rid)
    assert any(n["kind"] == "policy-result" for n in chain["nodes"])
    assert any(e["type"] == "cited" for e in chain["edges"])


def test_proof_chain_is_cycle_safe(tmp_path):
    g = tmp_path / "graph.jsonl"
    a = tg.add_node(g, "plan", "p", {}, _TS)
    b = tg.add_node(g, "tasks-state", "t", {}, _TS)
    tg.add_edge(g, a, b, "verified", _TS)
    tg.add_edge(g, b, a, "produced-by", _TS)  # a cycle
    graph = tg.load_graph(g)
    chain = tg.proof_chain(graph, a)  # must terminate
    assert {n["id"] for n in chain["nodes"]} == {a, b}


# --------------------------------------------------------------------------- #
# audit queries
# --------------------------------------------------------------------------- #

def test_dangling_edges_flags_a_missing_endpoint(tmp_path):
    g = tmp_path / "graph.jsonl"
    a = tg.add_node(g, "verification-report", "rep", {}, _TS)
    tg.add_edge(g, a, tg.node_id("tasks-state", "never-added"), "verified", _TS)
    graph = tg.load_graph(g)
    dangling = tg.dangling_edges(graph)
    assert len(dangling) == 1
    assert dangling[0]["type"] == "verified"


def test_unsigned_high_trust_flags_unapproved_and_clears_on_approval(tmp_path):
    g = tmp_path / "graph.jsonl"
    tg.ingest_report(g, _report(risk="high-trust", human_required=True), _TS,
                     report_sha256="unsigned")
    flagged = tg.unsigned_high_trust(tg.load_graph(g))
    assert len(flagged) == 1

    g2 = tmp_path / "graph2.jsonl"
    tg.ingest_report(g2, _report(risk="high-trust", human_required=True, human_status="approved"),
                     _TS, report_sha256="signed")
    assert tg.unsigned_high_trust(tg.load_graph(g2)) == []


def test_standard_risk_is_never_unsigned_high_trust(tmp_path):
    g = tmp_path / "graph.jsonl"
    tg.ingest_report(g, _report(risk="standard", human_required=True), _TS, report_sha256="std")
    assert tg.unsigned_high_trust(tg.load_graph(g)) == []


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def _write_report(tmp_path, report, name="verification-report.json"):
    p = tmp_path / name
    p.write_text(json.dumps(report), encoding="utf-8")
    return p


def test_cli_ingest_then_audit(tmp_path, capsys):
    rep = _write_report(tmp_path, _report())
    g = tmp_path / "graph.jsonl"
    assert tg.main(["ingest", "--graph", str(g), str(rep)]) == 0
    capsys.readouterr()
    assert tg.main(["audit", "--graph", str(g)]) == 0
    audit = json.loads(capsys.readouterr().out)
    assert audit["nodes"] == 3
    assert audit["edges"] == 2
    assert audit["dangling_edges"] == []


def test_cli_chain_unknown_node_returns_2(tmp_path):
    g = tmp_path / "graph.jsonl"
    tg.add_node(g, "plan", "p", {}, _TS)
    assert tg.main(["chain", "--graph", str(g), "deadbeefdeadbeef"]) == 2


def test_cli_ingest_missing_report_returns_2(tmp_path):
    g = tmp_path / "graph.jsonl"
    assert tg.main(["ingest", "--graph", str(g), str(tmp_path / "nope.json")]) == 2


def test_cli_ingest_tolerates_bom(tmp_path):
    p = tmp_path / "verification-report.json"
    p.write_bytes(b"\xef\xbb\xbf" + json.dumps(_report()).encode("utf-8"))
    g = tmp_path / "graph.jsonl"
    assert tg.main(["ingest", "--graph", str(g), str(p)]) == 0


# --------------------------------------------------------------------------- #
# review follow-ups: hash alignment, depth boundary, graceful degrade
# --------------------------------------------------------------------------- #

def test_ingest_fallback_hash_matches_verify_core_serialization(tmp_path):
    # When report_sha256 is not supplied, the fallback must hash the exact bytes
    # verify_core writes (json.dumps indent 2), so the graph node id resolves to
    # the same artifact the manifest sidecar and mneme name. A sort_keys canonical
    # form would silently diverge.
    g = tmp_path / "graph.jsonl"
    rep = _report()
    rid = tg.ingest_report(g, rep, _TS)  # no report_sha256, exercise the fallback
    expected = tg.node_id(
        "verification-report",
        hashlib.sha256(json.dumps(rep, indent=2).encode("utf-8")).hexdigest())
    assert rid == expected


def test_proof_chain_depth_boundary_has_no_orphan_edges(tmp_path):
    g = tmp_path / "graph.jsonl"
    tg.ingest_report(g, _report(tasks_sha="ts-d", commit="c-d"), _TS, report_sha256="rep-d")
    graph = tg.load_graph(g)
    ts_node = tg.node_id("tasks-state", "ts-d")
    # max_depth 0 returns only the start node and no edges pointing outside it.
    chain0 = tg.proof_chain(graph, ts_node, max_depth=0)
    assert {n["id"] for n in chain0["nodes"]} == {ts_node}
    assert chain0["edges"] == []
    # At any depth, every edge endpoint that has a node record is in the result.
    chain1 = tg.proof_chain(graph, ts_node, max_depth=1)
    node_ids = {n["id"] for n in chain1["nodes"]}
    for e in chain1["edges"]:
        for endpoint in (e["from"], e["to"]):
            assert endpoint in node_ids or endpoint not in graph.nodes


def test_cli_chain_dangling_start_returns_0_with_note(tmp_path, capsys):
    g = tmp_path / "graph.jsonl"
    a = tg.add_node(g, "verification-report", "rep", {}, _TS)
    dangling = tg.node_id("tasks-state", "never-recorded")
    tg.add_edge(g, a, dangling, "verified", _TS)
    rc = tg.main(["chain", "--graph", str(g), dangling])
    assert rc == 0
    assert "dangling reference" in capsys.readouterr().err


def test_reingest_with_changed_attrs_keeps_latest(tmp_path):
    g = tmp_path / "graph.jsonl"
    tg.ingest_report(g, _report(risk=None), _TS, report_sha256="same")
    tg.ingest_report(g, _report(risk="high-trust", human_required=True), _TS,
                     report_sha256="same")
    graph = tg.load_graph(g)
    rid = tg.node_id("verification-report", "same")
    # Last write wins on attrs, so the projection reflects the second ingest.
    assert graph.nodes[rid]["attrs"]["risk_level"] == "high-trust"


def test_ingest_report_without_tasks_state_sha_makes_only_report_node(tmp_path):
    g = tmp_path / "graph.jsonl"
    rep = {"schema_version": "1.0", "feature_id": "f", "verified_at": "t",
           "summary": {"verdict": "pass", "human_review_required": False},
           "tasks": [], "provenance": {"verifier_version": "1.1"}}  # no tasks_state_sha256
    tg.ingest_report(g, rep, _TS, report_sha256="r")
    graph = tg.load_graph(g)
    assert len(graph.nodes) == 1  # only the report node, no tasks-state or commit
    assert len(graph._edges) == 0


def test_ingest_minimal_report_is_one_node_zero_edges(tmp_path):
    g = tmp_path / "graph.jsonl"
    rep = {"schema_version": "1.0", "feature_id": "f", "verified_at": "t",
           "summary": {"verdict": "pass", "human_review_required": False}, "tasks": []}
    tg.ingest_report(g, rep, _TS, report_sha256="r")
    graph = tg.load_graph(g)
    assert len(graph.nodes) == 1
    assert len(graph._edges) == 0
