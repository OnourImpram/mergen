"""Test for the mneme seam (scripts/mneme_emit.py): a verification-report renders
to a mneme-ingestable decision-record markdown that tags proven tasks (with
evidence) apart from tasks claimed done but unproven.

Loaded by file path because scripts/ is not an importable package.
"""

import importlib.util
import json
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def _load(rel_path: str):
    path = REPO / rel_path
    spec = importlib.util.spec_from_file_location(path.stem.replace("-", "_"), path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_mneme_emit_decision_record():
    emit = _load("scripts/mneme_emit.py")
    rep = json.loads((REPO / "eval" / "sample" / "verification-report.json").read_text(encoding="utf-8"))
    md = emit.to_decision_markdown(rep)
    assert "confidence: extracted" in md
    assert "T001" in md and "T003" in md          # proven, with evidence
    assert "unproven tasks: T002" in md            # claimed done but unproven


# --------------------------------------------------------------------------- #
# Read direction (Phase 4): parse records back, the bidirectional seam.
# --------------------------------------------------------------------------- #

def _sample_report():
    return json.loads(
        (REPO / "eval" / "sample" / "verification-report.json").read_text(encoding="utf-8")
    )


def test_parse_round_trips_what_emit_writes():
    emit = _load("scripts/mneme_emit.py")
    rep = _sample_report()
    rec = emit.parse_decision_record(emit.to_decision_markdown(rep))
    assert rec["feature_id"] == rep.get("feature_id")
    assert rec["verdict"] == rep["summary"]["verdict"]
    assert "T001" in rec["proven"]
    assert "T002" in rec["unproven"]


def test_read_decision_records_from_a_vault(tmp_path):
    emit = _load("scripts/mneme_emit.py")
    md = emit.to_decision_markdown(_sample_report())
    (tmp_path / "a.md").write_text(md, encoding="utf-8")
    (tmp_path / "b.md").write_text(
        md.replace("# Decision: ", "# Decision: other-", 1), encoding="utf-8"
    )
    records = emit.read_decision_records(tmp_path)
    assert len(records) == 2
    assert any(r["feature_id"].startswith("other-") for r in records)


def test_read_absent_vault_is_empty(tmp_path):
    emit = _load("scripts/mneme_emit.py")
    assert emit.read_decision_records(tmp_path / "nope") == []


def test_prior_decisions_filters_by_feature(tmp_path):
    emit = _load("scripts/mneme_emit.py")
    rep = _sample_report()
    md = emit.to_decision_markdown(rep)
    fid = rep.get("feature_id")
    (tmp_path / "a.md").write_text(md, encoding="utf-8")
    (tmp_path / "b.md").write_text(
        md.replace(f"# Decision: {fid}", "# Decision: zzz", 1), encoding="utf-8"
    )
    recs = emit.prior_decisions_for(tmp_path, fid)
    assert len(recs) == 1
    assert recs[0]["feature_id"] == fid
