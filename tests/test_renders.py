"""Render and single-source-sync tests for the SDD layer (v1.1.0).

These cover the renderers and the drift gate, which the hook tests do not touch:
- the native renderer parses every core command, including lean and debt,
- the spec-kit renderer ships lean and debt in the extension,
- the committed dist/speckit output is in sync with core/ (no drift),
- the cross-agent renderer ports the lazy ladder faithfully.

Modules under dist/ and scripts/ are loaded by file path (they are distribution
sources, not an installed package). No test touches the real ~/.claude.
"""

import contextlib
import importlib.util
import io
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CORE_COMMANDS = REPO / "core" / "commands"


def _load(rel_path: str):
    path = REPO / rel_path
    spec = importlib.util.spec_from_file_location(path.stem, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# --------------------------------------------------------------------------- #
# Native renderer
# --------------------------------------------------------------------------- #

def test_native_parses_every_command_including_lean_and_debt():
    build_native = _load("dist/native/build_native.py")
    command_files = sorted(CORE_COMMANDS.glob("*.md"))
    names = []
    for path in command_files:
        cmd = build_native.parse_command(path)  # raises on malformed frontmatter
        assert cmd.description, f"{path.name} has an empty description"
        names.append(cmd.name)
    assert "lean" in names
    assert "debt" in names
    assert "govern" in names
    # 11 original commands + lean + debt + govern.
    assert len(names) == 14, f"expected 14 commands, got {len(names)}: {sorted(names)}"


# --------------------------------------------------------------------------- #
# Spec-kit renderer
# --------------------------------------------------------------------------- #

def test_speckit_ext_cmds_include_lean_and_debt():
    build_speckit = _load("dist/speckit/build_speckit.py")
    assert "lean" in build_speckit.EXT_CMDS
    assert "debt" in build_speckit.EXT_CMDS


def test_committed_extension_yaml_lists_lean_and_debt():
    ext_yaml = (REPO / "dist" / "speckit" / "extensions" / "mergen"
                / "extension.yml").read_text(encoding="utf-8")
    assert "speckit.mergen.lean" in ext_yaml
    assert "speckit.mergen.debt" in ext_yaml
    assert 'version: "1.1.0"' in ext_yaml


def test_committed_command_files_exist():
    cmds_dir = REPO / "dist" / "speckit" / "extensions" / "mergen" / "commands"
    for name in ("lean", "debt"):
        assert (cmds_dir / f"speckit.mergen.{name}.md").is_file()


# --------------------------------------------------------------------------- #
# Single-source drift gate
# --------------------------------------------------------------------------- #

def test_check_sync_reports_no_drift():
    check_sync = _load("scripts/check_sync.py")
    with contextlib.redirect_stdout(io.StringIO()):
        speckit_problems = check_sync.check_speckit_drift()
        agent_problems = check_sync.check_agents_consistency()
    assert speckit_problems == [], f"speckit drift: {speckit_problems}"
    assert agent_problems == [], f"cross-agent inconsistency: {agent_problems}"


# --------------------------------------------------------------------------- #
# Cross-agent renderer
# --------------------------------------------------------------------------- #

def test_build_agents_renders_all_targets():
    build_agents = _load("dist/agents/build_agents.py")
    ladder = build_agents.LADDER.read_text(encoding="utf-8")
    targets = build_agents.render_targets(ladder)
    expected = {
        "AGENTS.md",
        ".cursor/rules/lazy-ladder.mdc",
        ".windsurf/rules/lazy-ladder.md",
        ".clinerules/lazy-ladder.md",
        ".github/copilot-instructions.md",
        ".kiro/steering/lazy-ladder.md",
    }
    assert set(targets) == expected


def test_build_agents_discipline_is_portable():
    build_agents = _load("dist/agents/build_agents.py")
    ladder = build_agents.LADDER.read_text(encoding="utf-8")
    discipline = build_agents.portable_discipline(ladder)
    # The portable body must not instruct a non-Claude agent to run /mergen.*
    # commands, and must not carry the Claude-specific lifecycle section.
    assert "/mergen." not in discipline
    assert "How the lifecycle uses the ladder" not in discipline
    # But it must keep the ladder itself.
    assert "need to be built at all" in discipline
    assert "minimum code that works" in discipline
