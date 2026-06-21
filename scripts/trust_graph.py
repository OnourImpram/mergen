#!/usr/bin/env python3
"""mergen trust graph: a typed, append-only provenance graph over the ledger.

Where `scripts/ledger.py` is a flat append-only event log, the Trust Graph adds
typed nodes and typed edges, so the history records not just what happened but how
the facts relate. A verification report verified that tasks-state, which was
produced under this Governor decision, which cited those policy results. Given any
artifact the graph answers "what proved this, and what did that proof depend on"
without reading the artifacts themselves.

The design keeps the ledger's guarantees. Every node and every edge is one
append-only JSONL line written through `ledger.append_event`, so the JSONL stays
the single source of truth. The graph in memory is a rebuildable projection: a
node index and forward and reverse edge indexes derived by scanning the events.
Nothing is stored that the JSONL does not already hold.

A node id is a content hash of the node's stable identity (a report's sha256, a
tasks-state's sha256, a commit), so the same artifact always maps to the same
node and re-ingesting a report is idempotent. Edges are also content-addressed by
their endpoints and type, so a repeated edge does not double-count.

Tier 0: pure standard library, no network, no model, no third-party dependency.
Deterministic, the timestamp is injected by the caller exactly as the ledger
requires. Exit codes: 0 on success, 2 when the graph file is not readable or an
artifact id is unknown.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

#: The event kind every trust-graph line carries in the ledger envelope, so the
#: graph can share a ledger file with other event kinds and still be filtered out.
GRAPH_KIND = "trust-graph"

#: The node kinds the graph understands. A node of an unknown kind still loads (the
#: graph never refuses data it can read), these are the kinds the ingest bridge and
#: the queries reason about.
NODE_KINDS: tuple[str, ...] = (
    "verification-report",
    "tasks-state",
    "governor-decision",
    "policy-result",
    "plan",
    "commit",
)

#: The edge types, each read "from <type> to": a report verified a tasks-state, a
#: tasks-state was produced-by a plan, a report was decided-under a governor
#: decision, a decision cited a policy-result, a tasks-state sits at-commit.
EDGE_TYPES: tuple[str, ...] = (
    "verified",
    "produced-by",
    "decided-under",
    "cited",
    "at-commit",
)


_LEDGER_MOD: Any = None


def _load_ledger() -> Any:
    """Load scripts/ledger.py by path and cache it (scripts/ is not a package).

    Cached at module scope so a batch ingest does not re-exec the ledger module on
    every append, which would be one module load per node and per edge.
    """
    global _LEDGER_MOD
    if _LEDGER_MOD is not None:
        return _LEDGER_MOD
    repo = Path(__file__).resolve().parent
    spec = importlib.util.spec_from_file_location("ledger", repo / "ledger.py")
    if spec is None or spec.loader is None:  # pragma: no cover - import wiring
        raise ImportError("cannot load ledger")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    _LEDGER_MOD = mod
    return mod


def node_id(kind: str, identity: str) -> str:
    """A stable content-addressed id for a node.

    The same (kind, identity) always hashes to the same id, so re-ingesting an
    artifact reuses its node rather than creating a duplicate. A null byte
    separates the fields so ("a", "bc") and ("ab", "c") cannot collide.
    """
    digest = hashlib.sha256(f"{kind}\x00{identity}".encode("utf-8")).hexdigest()
    return digest[:16]


def edge_id(from_id: str, to_id: str, edge_type: str) -> str:
    """A stable content-addressed id for an edge, so a repeated edge is one edge."""
    raw = f"{from_id}\x00{to_id}\x00{edge_type}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def add_node(path: str | Path, kind: str, identity: str,
             attrs: dict[str, Any], timestamp: str) -> str:
    """Append a node event and return its content-addressed id."""
    nid = node_id(kind, identity)
    payload = {"g": "node", "id": nid, "kind": kind, "identity": identity, "attrs": attrs}
    _load_ledger().append_event(payload, path, kind=GRAPH_KIND, timestamp=timestamp)
    return nid


def add_edge(path: str | Path, from_id: str, to_id: str,
             edge_type: str, timestamp: str) -> str:
    """Append an edge event and return its content-addressed id."""
    eid = edge_id(from_id, to_id, edge_type)
    payload = {"g": "edge", "id": eid, "from": from_id, "to": to_id, "type": edge_type}
    _load_ledger().append_event(payload, path, kind=GRAPH_KIND, timestamp=timestamp)
    return eid


# --------------------------------------------------------------------------- #
# The rebuildable in-memory projection
# --------------------------------------------------------------------------- #


class Graph:
    """The derived projection over the trust-graph events.

    nodes maps a node id to its record. out maps a node id to its outgoing edges,
    inc to its incoming edges. All three are rebuilt from the JSONL on every load,
    so the events stay the single source of truth and the projection can never
    drift from them. A plain class, not a dataclass, so the module loads cleanly
    under importlib (the way tests and sibling scripts import it) where a
    dataclass with string annotations cannot resolve its own module.
    """

    def __init__(self) -> None:
        self.nodes: dict[str, dict[str, Any]] = {}
        self.out: dict[str, list[dict[str, Any]]] = {}
        self.inc: dict[str, list[dict[str, Any]]] = {}
        self._edges: set[str] = set()

    def referenced_ids(self) -> set[str]:
        """Every node id named by an edge endpoint, present as a node or not."""
        ids: set[str] = set()
        for edges in self.out.values():
            for e in edges:
                ids.add(e["from"])
                ids.add(e["to"])
        return ids


def load_graph(path: str | Path) -> Graph:
    """Read the trust-graph events and build the projection.

    A node id seen twice keeps the latest record (idempotent re-ingest, last write
    wins on attrs). An edge id seen twice is recorded once. Non-graph events in the
    same ledger file are ignored, so the graph can share a file with other kinds.
    """
    graph = Graph()
    for event in _load_ledger().read_events(path):
        if event.get("kind") != GRAPH_KIND:
            continue
        payload = event.get("payload")
        if not isinstance(payload, dict):
            continue
        if payload.get("g") == "node" and isinstance(payload.get("id"), str):
            graph.nodes[payload["id"]] = payload
        elif payload.get("g") == "edge" and isinstance(payload.get("id"), str):
            eid = payload["id"]
            if eid in graph._edges:
                continue
            graph._edges.add(eid)
            frm, to = payload.get("from"), payload.get("to")
            if isinstance(frm, str) and isinstance(to, str):
                graph.out.setdefault(frm, []).append(payload)
                graph.inc.setdefault(to, []).append(payload)
    return graph


def proof_chain(graph: Graph, start_id: str, max_depth: int = 16) -> dict[str, Any]:
    """The provenance subgraph that proves start_id and what that proof depends on.

    Walks incoming edges (what proved or produced this node) and, from each prover,
    its outgoing edges (what that proof in turn depended on), breadth first and
    cycle safe. Returns the reachable nodes and edges without reading any artifact,
    only the graph's own records. A node id with no node record still appears in
    the edge list as a dangling endpoint, which the dashboard surfaces as broken
    lineage.
    """
    seen_nodes: dict[str, dict[str, Any]] = {}
    seen_edges: dict[str, dict[str, Any]] = {}
    frontier: list[tuple[str, int]] = [(start_id, 0)]
    visited: set[str] = set()
    while frontier:
        nid, depth = frontier.pop(0)
        if nid in visited:
            continue
        visited.add(nid)
        if nid in graph.nodes:
            seen_nodes[nid] = graph.nodes[nid]
        # Incoming edges are provers (what proved or produced this node), outgoing
        # edges are dependencies (what this node cited or sat at). For each, the
        # neighbour is the other endpoint.
        for e in graph.inc.get(nid, []) + graph.out.get(nid, []):
            other = e["from"] if e["to"] == nid else e["to"]
            if depth < max_depth:
                # Within budget: traverse to the neighbour and keep the edge.
                seen_edges[e["id"]] = e
                frontier.append((other, depth + 1))
            elif other in visited:
                # At the depth boundary, keep only edges that close back onto a
                # node already in the result, so no edge ever points outside it.
                seen_edges[e["id"]] = e
    return {
        "root": start_id,
        "nodes": list(seen_nodes.values()),
        "edges": list(seen_edges.values()),
    }


def dangling_edges(graph: Graph) -> list[dict[str, Any]]:
    """Edges with a missing node at either endpoint, the broken-lineage signal.

    A referenced id at either endpoint with no node record means a proof points at
    or comes from something the graph never recorded, so a lineage cannot be walked
    to the end. Deterministically ordered.
    """
    bad: list[dict[str, Any]] = []
    for edges in graph.out.values():
        for e in edges:
            if e["from"] not in graph.nodes or e["to"] not in graph.nodes:
                bad.append(e)
    bad.sort(key=lambda e: e["id"])
    return bad


def unsigned_high_trust(graph: Graph) -> list[dict[str, Any]]:
    """High-trust nodes that carry no recorded sign-off.

    A node is unsigned high trust when its attrs say risk_level high-trust and
    human_review_required, but the recorded human-review status is not approved.
    This is the graph's view of the same invariant the gate enforces: a high-trust
    change must not be trusted without a recorded human approval. Deterministic.
    """
    flagged: list[dict[str, Any]] = []
    for nid in sorted(graph.nodes):
        attrs = graph.nodes[nid].get("attrs")
        if not isinstance(attrs, dict):
            continue
        if attrs.get("risk_level") != "high-trust":
            continue
        if not attrs.get("human_review_required"):
            continue
        if attrs.get("human_review_status") != "approved":
            flagged.append(graph.nodes[nid])
    return flagged


# --------------------------------------------------------------------------- #
# The ingest bridge: build the graph from an existing verification report
# --------------------------------------------------------------------------- #


def ingest_report(path: str | Path, report: dict[str, Any],
                  timestamp: str, *, report_sha256: str | None = None) -> str:
    """Record one verification report into the graph and return its node id.

    Builds the report node, the tasks-state node it verified, an optional commit
    node, and a node per policy result, with the typed edges between them. The
    report identity is its sha256 (the same hash mneme records and the manifest
    sidecar carries), so the graph node, the mneme lineage, and the sidecar all
    name the same artifact. Pass report_sha256 from the report file bytes whenever
    a file exists (the CLI does). When it is not supplied the hash is derived from
    verify_core's own on-disk serialization (json.dumps indent 2), so a report
    that verify_core wrote resolves to the same id. A report serialized differently
    must pass its own report_sha256, or its node id will not match the sidecar.
    """
    summary = report.get("summary")
    summary = summary if isinstance(summary, dict) else {}
    provenance = report.get("provenance")
    provenance = provenance if isinstance(provenance, dict) else {}
    review = summary.get("human_review")
    review = review if isinstance(review, dict) else {}

    if report_sha256 is None:
        # Mirror verify_core's on-disk serialization exactly (json.dumps with
        # indent 2, the default ensure_ascii), so the fallback hash equals the
        # sha256 of the file verify_core would write and stays consistent with the
        # manifest sidecar and the mneme report-sha256.
        serialized = json.dumps(report, indent=2).encode("utf-8")
        report_sha256 = hashlib.sha256(serialized).hexdigest()

    report_attrs = {
        "feature_id": report.get("feature_id"),
        "verdict": summary.get("verdict"),
        "risk_level": summary.get("risk_level"),
        "human_review_required": bool(summary.get("human_review_required")),
        "human_review_status": review.get("status"),
        "verified_at": report.get("verified_at"),
    }
    report_node = add_node(path, "verification-report", report_sha256, report_attrs, timestamp)

    tasks_sha = provenance.get("tasks_state_sha256")
    if isinstance(tasks_sha, str) and tasks_sha:
        ts_node = add_node(path, "tasks-state", tasks_sha,
                           {"feature_id": report.get("feature_id")}, timestamp)
        add_edge(path, report_node, ts_node, "verified", timestamp)
        commit = provenance.get("source_commit")
        if isinstance(commit, str) and commit:
            commit_node = add_node(path, "commit", commit, {}, timestamp)
            add_edge(path, ts_node, commit_node, "at-commit", timestamp)

    policy_results = report.get("policy_results")
    if isinstance(policy_results, list):
        for pr in policy_results:
            if not isinstance(pr, dict):
                continue
            pid = pr.get("policy_id")
            if not isinstance(pid, str) or not pid:
                continue
            pr_node = add_node(path, "policy-result", pid,
                               {"result": pr.get("result"), "reason": pr.get("reason")}, timestamp)
            add_edge(path, report_node, pr_node, "cited", timestamp)

    return report_node


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def _now() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _cmd_ingest(args: argparse.Namespace) -> int:
    report_path = Path(args.report)
    if not report_path.is_file():
        print(f"error: report not found: {report_path}", file=sys.stderr)
        return 2
    try:
        raw = report_path.read_bytes()
        report = json.loads(raw.decode("utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"error: cannot read report: {exc}", file=sys.stderr)
        return 2
    if not isinstance(report, dict):
        print("error: report is not a JSON object", file=sys.stderr)
        return 2
    sha = hashlib.sha256(raw).hexdigest()
    nid = ingest_report(args.graph, report, _now(), report_sha256=sha)
    print(f"ingested report node {nid} into {args.graph}")
    return 0


def _cmd_chain(args: argparse.Namespace) -> int:
    graph = load_graph(args.graph)
    if args.node not in graph.nodes and args.node not in graph.referenced_ids():
        print(f"error: unknown node id: {args.node}", file=sys.stderr)
        return 2
    if args.node not in graph.nodes:
        print(f"note: {args.node} is a dangling reference with no node record, "
              "returning the provenance edges that point at it", file=sys.stderr)
    print(json.dumps(proof_chain(graph, args.node), indent=2))
    return 0


def _cmd_audit(args: argparse.Namespace) -> int:
    graph = load_graph(args.graph)
    report = {
        "nodes": len(graph.nodes),
        "edges": len(graph._edges),
        "dangling_edges": dangling_edges(graph),
        "unsigned_high_trust": unsigned_high_trust(graph),
    }
    print(json.dumps(report, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Typed, append-only provenance graph over the mergen ledger.")
    sub = ap.add_subparsers(dest="command", required=True)

    p_ing = sub.add_parser("ingest", help="record a verification-report.json into the graph")
    p_ing.add_argument("--graph", required=True, help="path to the trust-graph JSONL file")
    p_ing.add_argument("report", help="path to a verification-report.json")
    p_ing.set_defaults(func=_cmd_ingest)

    p_ch = sub.add_parser("chain", help="print the provenance chain that proves a node")
    p_ch.add_argument("--graph", required=True, help="path to the trust-graph JSONL file")
    p_ch.add_argument("node", help="a node id (see ingest output, or audit)")
    p_ch.set_defaults(func=_cmd_chain)

    p_au = sub.add_parser("audit", help="report node and edge counts, broken lineage, unsigned high-trust")
    p_au.add_argument("--graph", required=True, help="path to the trust-graph JSONL file")
    p_au.set_defaults(func=_cmd_audit)

    args = ap.parse_args(argv)
    result: int = args.func(args)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
