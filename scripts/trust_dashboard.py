#!/usr/bin/env python3
"""mergen trust dashboard: an offline view of the trust graph.

Where `scripts/dashboard.py` is a snapshot over a directory of reports, this reads
the trust graph (scripts/trust_graph.py) and shows the connected picture: which
report proved which tasks-state, at which commit, citing which policy results,
where a lineage is broken (an edge that points at an unrecorded node), and where a
high-trust node carries no recorded sign-off.

Still one self-contained HTML page. No network, no JavaScript, every value passed
through html.escape, so a crafted attribute cannot break out of the markup. The
class on a verdict tag is a controlled constant, never the raw verdict string.

Tier 0: pure standard library. The dashboard reflects only what the graph records.
A gap the graph does not capture is a gap the dashboard cannot show, so the graph's
completeness is the real work. It mirrors lineage, it does not judge correctness.

Exit codes: 0 on success, 2 when the graph file is not a readable file.
"""

from __future__ import annotations

import argparse
import html
import importlib.util
import sys
from pathlib import Path
from typing import Any

_VERDICT_CLASS = {"pass": "ok", "conditional_pass": "warn", "fail": "bad"}

_CSS = """
body { font: 15px/1.5 system-ui, sans-serif; margin: 2rem; color: #1c2128; background: #fff; }
h1 { font-size: 1.4rem; margin: 0 0 .25rem; }
h2 { font-size: 1.05rem; margin: 1.75rem 0 .5rem; }
.sub { color: #57606a; margin: 0 0 1.5rem; }
.cards { display: flex; gap: 1rem; flex-wrap: wrap; margin-bottom: 1rem; }
.card { border: 1px solid #d0d7de; border-radius: 8px; padding: .75rem 1rem; min-width: 7rem; }
.card .n { font-size: 1.6rem; font-weight: 600; }
.card .l { color: #57606a; font-size: .85rem; }
.card.alert .n { color: #cf222e; }
table { border-collapse: collapse; width: 100%; }
th, td { text-align: left; padding: .5rem .6rem; border-bottom: 1px solid #d0d7de; }
th { color: #57606a; font-weight: 600; font-size: .85rem; }
.tag { display: inline-block; padding: .1rem .5rem; border-radius: 99px; font-size: .8rem; font-weight: 600; }
.ok { background: #dafbe1; color: #1a7f37; }
.warn { background: #fff8c5; color: #7d4e00; }
.bad { background: #ffebe9; color: #cf222e; }
.muted { color: #8c959f; }
.mono { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: .85rem; }
.empty { color: #57606a; padding: 1rem 0; }
.note { color: #57606a; font-size: .85rem; margin: .5rem 0 0; }
""".strip()


def _load_trust_graph() -> Any:
    """Load scripts/trust_graph.py by path (scripts/ is not a package)."""
    repo = Path(__file__).resolve().parent
    spec = importlib.util.spec_from_file_location("trust_graph", repo / "trust_graph.py")
    if spec is None or spec.loader is None:  # pragma: no cover - import wiring
        raise ImportError("cannot load trust_graph")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _identity(graph: Any, node_id: str) -> str:
    """The short stable identity of a node (a sha or commit), or the node id."""
    node = graph.nodes.get(node_id)
    if isinstance(node, dict):
        ident = node.get("identity")
        if isinstance(ident, str) and ident:
            return ident[:12]
    return node_id[:12]


def lineage_rows(graph: Any) -> list[dict[str, Any]]:
    """One provenance row per verification-report node, deterministically ordered.

    Derived purely from the graph edges: the tasks-state the report verified, the
    commit that state sits at, and how many policy results the report cited. This
    is the connected picture, which proof depends on which, without reading an
    artifact.
    """
    rows: list[dict[str, Any]] = []
    for nid in sorted(graph.nodes):
        node = graph.nodes[nid]
        if node.get("kind") != "verification-report":
            continue
        attrs = node.get("attrs") if isinstance(node.get("attrs"), dict) else {}
        out_edges = graph.out.get(nid, [])
        verified = [e["to"] for e in out_edges if e["type"] == "verified"]
        cited = [e for e in out_edges if e["type"] == "cited"]
        ts_id = verified[0] if verified else None
        commit_id = None
        if ts_id is not None:
            for e in graph.out.get(ts_id, []):
                if e["type"] == "at-commit":
                    commit_id = e["to"]
                    break
        rows.append({
            "feature_id": attrs.get("feature_id"),
            "verdict": attrs.get("verdict"),
            "risk_level": attrs.get("risk_level") or "standard",
            "sign_off": attrs.get("human_review_status") or "none",
            "high_trust_unsigned": (attrs.get("risk_level") == "high-trust"
                                    and bool(attrs.get("human_review_required"))
                                    and attrs.get("human_review_status") != "approved"),
            "tasks_state": _identity(graph, ts_id) if ts_id else "n/a",
            "commit": _identity(graph, commit_id) if commit_id else "n/a",
            "policies": len(cited),
        })
    return rows


def render_html(graph: Any) -> str:
    """Render the trust graph into one self-contained offline HTML page."""
    tg = _load_trust_graph()
    dangling = tg.dangling_edges(graph)
    unsigned = tg.unsigned_high_trust(graph)
    rows = lineage_rows(graph)
    n_reports = sum(1 for n in graph.nodes.values() if n.get("kind") == "verification-report")

    def esc(value: Any) -> str:
        return html.escape(str(value))

    cards = "".join(
        f'<div class="card{cls}"><div class="n">{esc(n)}</div><div class="l">{esc(label)}</div></div>'
        for n, label, cls in (
            (len(graph.nodes), "nodes", ""),
            (len(graph._edges), "edges", ""),
            (n_reports, "reports", ""),
            (len(dangling), "broken lineage", " alert" if dangling else ""),
            (len(unsigned), "unsigned high-trust", " alert" if unsigned else ""),
        )
    )

    if dangling:
        dl = "".join(
            "<tr>"
            f"<td>{esc(e['type'])}</td>"
            f'<td class="mono">{esc(e["from"][:12])}</td>'
            f'<td class="mono">{esc(e["to"][:12])}</td>'
            f"<td>{'from' if e['from'] not in graph.nodes else ''}"
            f"{' and ' if e['from'] not in graph.nodes and e['to'] not in graph.nodes else ''}"
            f"{'to' if e['to'] not in graph.nodes else ''}</td>"
            "</tr>"
            for e in dangling
        )
        broken = ("<table><thead><tr><th>edge</th><th>from</th><th>to</th>"
                  "<th>missing endpoint</th></tr></thead><tbody>" + dl + "</tbody></table>")
    else:
        broken = '<p class="empty">No broken lineage. Every edge endpoint has a recorded node.</p>'

    if unsigned:
        ul = "".join(
            "<tr>"
            f"<td>{esc((n.get('attrs') or {}).get('feature_id'))}</td>"
            f'<td><span class="tag {_VERDICT_CLASS.get(str((n.get("attrs") or {}).get("verdict")), "muted")}">'
            f'{esc((n.get("attrs") or {}).get("verdict"))}</span></td>'
            f'<td class="muted">{esc((n.get("attrs") or {}).get("human_review_status") or "none")}</td>'
            f'<td class="mono">{esc(n["id"][:12])}</td>'
            "</tr>"
            for n in unsigned
        )
        unsigned_tbl = ("<table><thead><tr><th>feature</th><th>verdict</th>"
                        "<th>sign-off</th><th>node</th></tr></thead><tbody>" + ul + "</tbody></table>")
    else:
        unsigned_tbl = '<p class="empty">No unsigned high-trust nodes. Every high-trust report carries a sign-off.</p>'

    if rows:
        lr = "".join(
            "<tr>"
            f"<td>{esc(r['feature_id'])}</td>"
            f'<td><span class="tag {_VERDICT_CLASS.get(r["verdict"], "muted")}">{esc(r["verdict"])}</span></td>'
            f"<td>{esc(r['risk_level'])}</td>"
            f'<td class="{"bad" if r["high_trust_unsigned"] else "muted"}">{esc(r["sign_off"])}</td>'
            f'<td class="mono">{esc(r["tasks_state"])}</td>'
            f'<td class="mono">{esc(r["commit"])}</td>'
            f"<td>{esc(r['policies'])}</td>"
            "</tr>"
            for r in rows
        )
        lineage = ("<table><thead><tr><th>feature</th><th>verdict</th><th>risk</th>"
                   "<th>sign-off</th><th>verified state</th><th>commit</th>"
                   "<th>policies cited</th></tr></thead><tbody>" + lr + "</tbody></table>")
    else:
        lineage = '<p class="empty">No verification-report nodes in this graph yet. Ingest a report.</p>'

    return (
        "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
        "<title>Mergen trust graph dashboard</title>"
        f"<style>{_CSS}</style></head><body>"
        "<h1>Mergen trust graph dashboard</h1>"
        '<p class="sub">Static, offline, generated from the trust graph. It shows the '
        "connected provenance: which report proved which state, where a lineage is "
        "broken, and where a high-trust change carries no sign-off. It mirrors "
        "lineage, it does not judge correctness.</p>"
        f'<div class="cards">{cards}</div>'
        "<h2>Broken lineage</h2>"
        f"{broken}"
        "<h2>Unsigned high-trust</h2>"
        f"{unsigned_tbl}"
        "<h2>Provenance</h2>"
        f"{lineage}"
        "</body></html>\n"
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Offline HTML dashboard over a mergen trust graph JSONL file.")
    ap.add_argument("graph", help="path to a trust-graph JSONL file")
    ap.add_argument("--out", help="write the HTML here (default: stdout)")
    args = ap.parse_args(argv)

    graph_path = Path(args.graph)
    if not graph_path.is_file():
        print(f"error: not a file: {graph_path}", file=sys.stderr)
        return 2

    graph = _load_trust_graph().load_graph(graph_path)
    page = render_html(graph)
    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(page.encode("utf-8"))
        print(f"wrote {out_path}", file=sys.stderr)
    else:
        sys.stdout.write(page)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
