"""Mergen v1.0 tests: the Governor, JSON schemas, the eval evidence metric, the
mneme seam, BOM-safe settings patchers, and the no-reference-text guard.

These complement test_hook (the effort hook) and test_renders (the renderers and
drift gate). dist/ and scripts/ modules are loaded by file path. No test touches
the real ~/.claude: the patcher tests use an explicit --settings path under
tmp_path, or redirect home via env.
"""

import importlib.util
import io
import json
import re
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


def test_evidence_metric_gate_fails_on_phantom(capsys):
    metric = _load("eval/evidence_metric.py")
    sample = str(REPO / "eval" / "sample" / "verification-report.json")
    rc = metric.main([sample, "--gate"])
    out = capsys.readouterr().out
    assert rc == 1
    assert "result:              FAIL" in out


def test_evidence_metric_gate_passes_when_tolerant(capsys):
    metric = _load("eval/evidence_metric.py")
    sample = str(REPO / "eval" / "sample" / "verification-report.json")
    rc = metric.main([sample, "--gate", "--max-phantoms", "1", "--min-work-done", "0.6"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "result:              PASS" in out


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


# --------------------------------------------------------------------------- #
# SDD hooks: the always-on runtime surface (verify_gate, constitution_inject)
# --------------------------------------------------------------------------- #

def _run_hook(rel_path, payload, monkeypatch, capsys):
    """Run a hook's main() in-process with a crafted stdin, capture stdout.

    In-process rather than subprocess to avoid the Windows subprocess flake seen
    under newer Python, the same reason the BOM patcher tests run in-process.
    """
    mod = _load(rel_path)
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
    rc = mod.main()
    return rc, capsys.readouterr().out


def test_verify_gate_fires_on_new_x_in_specify_tasks(monkeypatch, capsys):
    payload = {
        "tool_name": "Edit",
        "tool_input": {
            "file_path": "/proj/.specify/specs/001-feature/tasks.md",
            "old_string": "- [ ] T001 do the thing",
            "new_string": "- [X] T001 do the thing",
        },
    }
    rc, out = _run_hook("core/hooks/verify_gate.py", payload, monkeypatch, capsys)
    assert rc == 0
    assert "verify-gate reminder" in out
    assert "/mergen.verify" in out


def test_verify_gate_silent_on_tasks_outside_specify(monkeypatch, capsys):
    payload = {
        "tool_name": "Edit",
        "tool_input": {
            "file_path": "/proj/docs/tasks.md",
            "old_string": "- [ ] a",
            "new_string": "- [X] a",
        },
    }
    rc, out = _run_hook("core/hooks/verify_gate.py", payload, monkeypatch, capsys)
    assert rc == 0
    assert out.strip() == ""


def test_verify_gate_silent_when_edit_introduces_no_new_x(monkeypatch, capsys):
    payload = {
        "tool_name": "Edit",
        "tool_input": {
            "file_path": "/proj/.specify/specs/001/tasks.md",
            "old_string": "- [X] T001 done",
            "new_string": "- [X] T001 done and tidied",
        },
    }
    rc, out = _run_hook("core/hooks/verify_gate.py", payload, monkeypatch, capsys)
    assert rc == 0
    assert out.strip() == ""


def test_verify_gate_failsoft_on_garbage_stdin(monkeypatch, capsys):
    mod = _load("core/hooks/verify_gate.py")
    monkeypatch.setattr(sys, "stdin", io.StringIO("not json at all"))
    rc = mod.main()
    assert rc == 0
    assert capsys.readouterr().out.strip() == ""


def test_constitution_inject_surfaces_headings(tmp_path, monkeypatch, capsys):
    con = tmp_path / ".specify" / "memory" / "constitution.md"
    con.parent.mkdir(parents=True)
    con.write_text(
        "# Constitution\n\n## Safety first\n\n## Evidence over assertion\n",
        encoding="utf-8",
    )
    rc, out = _run_hook(
        "core/hooks/constitution_inject.py", {"cwd": str(tmp_path)}, monkeypatch, capsys
    )
    assert rc == 0
    assert "Safety first" in out
    assert "Evidence over assertion" in out


def test_constitution_inject_noop_without_constitution(tmp_path, monkeypatch, capsys):
    rc, out = _run_hook(
        "core/hooks/constitution_inject.py", {"cwd": str(tmp_path)}, monkeypatch, capsys
    )
    assert rc == 0
    assert out.strip() == ""


# --------------------------------------------------------------------------- #
# Command script-contract gate: every flag a command invokes must be a flag the
# named helper actually accepts. This is the gate that would have caught the
# /clarify --require-spec defect, which the byte-for-byte drift gate could not.
# --------------------------------------------------------------------------- #

def _command_script_invocations():
    out = []
    for cmd in sorted((REPO / "core" / "commands").glob("*.md")):
        text = cmd.read_text(encoding="utf-8")
        for lang, pat in (("sh", r"^\s*sh:\s*(.+)$"), ("ps", r"^\s*ps:\s*(.+)$")):
            m = re.search(pat, text, re.MULTILINE)
            if not m:
                continue
            tokens = m.group(1).strip().split()
            flags = [t for t in tokens[1:] if t.startswith("-")]
            out.append((cmd.name, lang, tokens[0], flags))
    return out


def test_every_command_flag_is_implemented_by_its_script():
    invocations = _command_script_invocations()
    # At least clarify and implement declare script flags; guard against a parser regression.
    assert invocations, "no command declared a sh/ps script invocation"
    failures = []
    for cmd_name, lang, script_rel, flags in invocations:
        script_path = REPO / "core" / script_rel
        if not script_path.is_file():
            failures.append(f"{cmd_name} [{lang}] names a missing script: {script_rel}")
            continue
        script_text = script_path.read_text(encoding="utf-8")
        for flag in flags:
            if lang == "sh":
                accepted = flag in script_text
            else:  # PowerShell: -RequireSpec is implemented as the param $RequireSpec
                accepted = ("$" + flag.lstrip("-")) in script_text
            if not accepted:
                failures.append(
                    f"{cmd_name} [{lang}] invokes {flag} but {script_rel} does not accept it"
                )
    assert not failures, "command/script contract violations:\n" + "\n".join(failures)
