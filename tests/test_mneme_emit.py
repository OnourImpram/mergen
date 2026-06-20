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


def test_cli_emits_markdown_for_a_report(capsys):
    emit = _load("scripts/mneme_emit.py")
    sample = str(REPO / "eval" / "sample" / "verification-report.json")
    rc = emit.main([sample])
    out = capsys.readouterr().out
    assert rc == 0
    assert "# Decision:" in out


def test_cli_read_lists_vault_records(tmp_path, capsys):
    emit = _load("scripts/mneme_emit.py")
    (tmp_path / "a.md").write_text(
        emit.to_decision_markdown(_sample_report()), encoding="utf-8"
    )
    rc = emit.main(["--read", str(tmp_path)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "feature_id" in out


def test_cli_reads_report_with_utf8_bom(tmp_path, capsys):
    # The seam reads the same verification-report.json that the evidence metric
    # reads. A BOM-prefixed report (the form PowerShell writes) must parse here
    # too, not crash with "cannot read report".
    emit = _load("scripts/mneme_emit.py")
    raw = (REPO / "eval" / "sample" / "verification-report.json").read_bytes()
    bom_report = tmp_path / "verification-report.json"
    bom_report.write_bytes(b"\xef\xbb\xbf" + raw)
    rc = emit.main([str(bom_report)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "# Decision:" in out


# --------------------------------------------------------------------------- #
# Write-to-vault direction: redaction preflight, duplicate detection, CLI.
# --------------------------------------------------------------------------- #

# An AWS example access key, used to exercise the redaction preflight. It is the
# canonical placeholder from AWS docs, not a real credential.
_AWS_EXAMPLE_KEY = "AKIA" + "IOSFODNN7EXAMPLE"


def _report(feature_id="feat-x", verdict="pass", proven=("T1",), unproven=()):
    return {
        "feature_id": feature_id,
        "verified_at": "2026-06-20T00:00:00Z",
        "summary": {"verdict": verdict, "human_review_required": False},
        "tasks": (
            [{"task_id": t, "verified_status": "pass", "files_checked": ["a.py"]} for t in proven]
            + [{"task_id": t, "verified_status": "fail"} for t in unproven]
        ),
    }


def test_writeback_writes_a_record(tmp_path):
    emit = _load("scripts/mneme_emit.py")
    path, status, findings = emit.write_decision_record(_report(), tmp_path)
    assert status == "written"
    assert path.is_file()
    assert path.read_text(encoding="utf-8") == emit.to_decision_markdown(_report())
    assert findings == []


def test_writeback_is_idempotent_on_substantive_duplicate(tmp_path):
    emit = _load("scripts/mneme_emit.py")
    emit.write_decision_record(_report(), tmp_path)
    # The same decision re-verified later (a different timestamp) is a duplicate.
    later = _report()
    later["verified_at"] = "2026-06-21T12:00:00Z"
    _path, status, _findings = emit.write_decision_record(later, tmp_path)
    assert status == "duplicate"
    assert len(list(tmp_path.glob("decision-*.md"))) == 1


def test_writeback_writes_new_record_when_substance_differs(tmp_path):
    emit = _load("scripts/mneme_emit.py")
    emit.write_decision_record(_report(verdict="pass"), tmp_path)
    emit.write_decision_record(_report(verdict="fail"), tmp_path)
    assert len(list(tmp_path.glob("decision-*.md"))) == 2


def test_writeback_redaction_preflight_blocks_a_secret(tmp_path):
    emit = _load("scripts/mneme_emit.py")
    path, status, findings = emit.write_decision_record(
        _report(feature_id=f"leak-{_AWS_EXAMPLE_KEY}"), tmp_path
    )
    assert status == "blocked"
    assert path is None
    assert findings  # the finding labels the pattern, never echoes the secret
    assert _AWS_EXAMPLE_KEY not in " ".join(findings)
    assert not list(tmp_path.glob("decision-*.md"))


def test_writeback_force_overrides_preflight(tmp_path):
    emit = _load("scripts/mneme_emit.py")
    path, status, _findings = emit.write_decision_record(
        _report(feature_id=f"leak-{_AWS_EXAMPLE_KEY}"), tmp_path, force=True
    )
    assert status == "written"
    assert path.is_file()


def test_cli_write_creates_a_record(tmp_path, capsys):
    emit = _load("scripts/mneme_emit.py")
    report = tmp_path / "verification-report.json"
    report.write_text(json.dumps(_report()), encoding="utf-8")
    out = tmp_path / "vault"
    rc = emit.main([str(report), "--write", str(out)])
    assert rc == 0
    assert list(out.glob("decision-*.md"))


def test_cli_write_blocks_secret_and_writes_nothing(tmp_path, capsys):
    emit = _load("scripts/mneme_emit.py")
    report = tmp_path / "verification-report.json"
    report.write_text(json.dumps(_report(feature_id=f"leak-{_AWS_EXAMPLE_KEY}")), encoding="utf-8")
    out = tmp_path / "vault"
    rc = emit.main([str(report), "--write", str(out)])
    err = capsys.readouterr().err
    assert rc == 1
    assert "redaction preflight blocked" in err
    assert _AWS_EXAMPLE_KEY not in err  # the block message must not leak the secret
    assert not out.exists() or not list(out.glob("decision-*.md"))
