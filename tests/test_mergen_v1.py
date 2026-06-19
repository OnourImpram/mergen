"""Mergen v1.0 tests: the Governor, JSON schemas, the eval evidence metric, the
mneme seam, BOM-safe settings patchers, and the no-reference-text guard.

These complement test_hook (the effort hook) and test_renders (the renderers and
drift gate). dist/ and scripts/ modules are loaded by file path. No test touches
the real ~/.claude: the patcher tests use an explicit --settings path under
tmp_path, or redirect home via env.
"""

import importlib.util
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def _load(rel_path: str):
    path = REPO / rel_path
    spec = importlib.util.spec_from_file_location(path.stem.replace("-", "_"), path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# --------------------------------------------------------------------------- #
# Governor
# --------------------------------------------------------------------------- #

def test_govern_command_documents_the_floor():
    text = (REPO / "core" / "commands" / "govern.md").read_text(encoding="utf-8")
    assert "high-trust" in text
    assert "governor-decision.json" in text
    # The deterministic no-downgrade floor is the safety property that matters.
    assert "never lower" in text or "never silently" in text


# --------------------------------------------------------------------------- #
# Schemas
# --------------------------------------------------------------------------- #

def test_schemas_parse():
    for name in ("verification-report", "tasks-state", "governor-decision"):
        data = json.loads((REPO / "core" / "schemas" / f"{name}.schema.json").read_text(encoding="utf-8"))
        assert data["$schema"].startswith("https://json-schema.org/")
        assert "properties" in data


def test_sample_report_carries_confidence_labels():
    rep = json.loads((REPO / "eval" / "sample" / "verification-report.json").read_text(encoding="utf-8"))
    assert rep["schema_version"] == "1.0"
    for task in rep["tasks"]:
        assert task["confidence"] in ("extracted", "inferred", "ambiguous")


# --------------------------------------------------------------------------- #
# Eval evidence metric
# --------------------------------------------------------------------------- #

def test_evidence_metric_work_done(capsys):
    metric = _load("eval/evidence_metric.py")
    rc = metric.main([str(REPO / "eval" / "sample" / "verification-report.json")])
    out = capsys.readouterr().out
    assert rc == 0
    assert "work-done rate:      0.67" in out
    assert "phantom completions: 1" in out
    assert "abstaining on minimal-change" in out


# --------------------------------------------------------------------------- #
# mneme seam
# --------------------------------------------------------------------------- #

def test_mneme_emit_decision_record():
    emit = _load("scripts/mneme_emit.py")
    rep = json.loads((REPO / "eval" / "sample" / "verification-report.json").read_text(encoding="utf-8"))
    md = emit.to_decision_markdown(rep)
    assert "confidence: extracted" in md
    assert "T001" in md and "T003" in md          # proven, with evidence
    assert "unproven tasks: T002" in md            # claimed done but unproven


# --------------------------------------------------------------------------- #
# BOM-safe settings patchers (the inherited defect fix)
# --------------------------------------------------------------------------- #

_BOM = b"\xef\xbb\xbf"


def test_native_patcher_is_bom_safe(tmp_path):
    mod = _load("dist/native/patch_settings_hooks.py")
    settings = tmp_path / "settings.json"
    settings.write_bytes(_BOM + b'{"hooks": {}}\n')
    # load tolerates the BOM and remembers it
    data, had_bom, err = mod.load_settings(settings)
    assert err == "" and had_bom is True and isinstance(data, dict)
    # install writes back and preserves the BOM
    assert mod.main(["--settings", str(settings), "--python", "python"]) == 0
    raw = settings.read_bytes()
    assert raw.startswith(_BOM), "BOM was not preserved"
    json.loads(raw.decode("utf-8-sig"))


def test_effort_patcher_is_bom_safe(tmp_path, monkeypatch):
    mod = _load("effort-mode/scripts/patch_settings.py")
    claude = tmp_path / ".claude"
    claude.mkdir()
    settings = claude / "settings.json"
    settings.write_bytes(_BOM + b'{"hooks": {}}\n')
    # redirect home so the real ~/.claude is never touched
    monkeypatch.setattr(mod.Path, "home", lambda: tmp_path)
    data, had_bom, err = mod._load_settings()
    assert err == "" and had_bom is True
    monkeypatch.setattr(sys, "argv", ["patch_settings.py", "--python", "python"])
    assert mod.main() == 0
    raw = settings.read_bytes()
    assert raw.startswith(_BOM), "BOM was not preserved"
    json.loads(raw.decode("utf-8-sig"))


# --------------------------------------------------------------------------- #
# No reference-prompt text guard
# --------------------------------------------------------------------------- #

def test_no_reference_text_repo_is_clean():
    chk = _load("scripts/check_no_reference_text.py")
    assert chk.main() == 0


def test_no_reference_text_detects_a_fingerprint():
    chk = _load("scripts/check_no_reference_text.py")
    # Build the sample at runtime so no fingerprint literal sits in this test
    # file, which the guard itself scans.
    sample = "a line with " + chk.FINGERPRINTS[0] + " in it"
    assert chk.find_fingerprints(sample) == [chk.FINGERPRINTS[0]]
    assert chk.find_fingerprints("ordinary mergen prose") == []
