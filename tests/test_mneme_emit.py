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
