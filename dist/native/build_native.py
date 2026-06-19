#!/usr/bin/env python3
"""Native (C-shell) renderer for mergen's SDD layer.

Single source -> two shells (see core/CONVENTIONS.md). This is the NATIVE
renderer. It turns each `core/commands/<name>.md` into a Claude Code skill at
`~/.claude/skills/mergen-<name>/SKILL.md`, invoked as `/mergen.<name>`.

Two responsibilities, mirroring how spec-kit splits global commands from a
per-project `.specify/` bootstrap:

  build  (default)  Render the command prompts into global skills under
                    ~/.claude/skills/. Also copies core/hooks/*.py into
                    ~/.claude/hooks/ when present (settings registration is
                    handled separately by the installer).

  init [project]    Bootstrap a project's `.specify/` directory: copy the
                    helper scripts and templates and create the memory dir, so
                    the vendored scripts (which resolve paths by walking up for
                    `.specify/`) work in that project. Mirrors `specify init`.

Why the renderer prefixes the script path: spec-kit's SOURCE command templates
declare scripts as bare `scripts/bash/...`; spec-kit's own release machinery
rewrites them to `.specify/scripts/bash/...` at install time. There is no
spec-kit runtime in native mode, so this renderer performs that exact rewrite.

Stdlib only. No third-party dependency (no PyYAML): the frontmatter these files
use is a small, fixed shape and is parsed deterministically below.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
COMMANDS_DIR = REPO / "core" / "commands"
TEMPLATES_DIR = REPO / "core" / "templates"
SCRIPTS_DIR = REPO / "core" / "scripts"
HOOKS_DIR = REPO / "core" / "hooks"

SKILL_PREFIX = "mergen"  # /mergen.<name>


# --------------------------------------------------------------------------- #
# Frontmatter parsing (minimal, deterministic, matches core/commands/*.md)
# --------------------------------------------------------------------------- #

class Command:
    def __init__(self, name: str, description: str, argument_hint: str | None,
                 scripts: dict[str, str], body: str):
        self.name = name
        self.description = description
        self.argument_hint = argument_hint
        self.scripts = scripts  # {"sh": "...", "ps": "..."} (already prefixed)
        self.body = body


def _strip_quotes(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1]
    return value


def _prefix_script(cmd: str) -> str:
    """Rewrite a bare `scripts/...` invocation to the installed `.specify/` path.

    Only the leading path token is rewritten; trailing flags are preserved.
    Idempotent: an already-prefixed `.specify/scripts/...` is left untouched.
    """
    cmd = cmd.strip()
    if cmd.startswith(".specify/scripts/"):
        return cmd
    if cmd.startswith("scripts/"):
        return ".specify/" + cmd
    return cmd


def parse_command(path: Path) -> Command:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        raise ValueError(f"{path.name}: missing frontmatter")
    # Split into frontmatter and body on the second '---' line.
    parts = text.split("\n")
    if parts[0].strip() != "---":
        raise ValueError(f"{path.name}: frontmatter must open with '---'")
    end = None
    for i in range(1, len(parts)):
        if parts[i].strip() == "---":
            end = i
            break
    if end is None:
        raise ValueError(f"{path.name}: unterminated frontmatter")

    fm_lines = parts[1:end]
    body = "\n".join(parts[end + 1:]).lstrip("\n")

    description = ""
    argument_hint = None
    scripts: dict[str, str] = {}
    in_scripts = False
    for line in fm_lines:
        if not line.strip():
            continue
        if line.startswith(("  ", "\t")) and in_scripts:
            key, _, val = line.strip().partition(":")
            key = key.strip()
            if key in ("sh", "ps") and val.strip():
                scripts[key] = _prefix_script(_strip_quotes(val))
            continue
        in_scripts = False
        key, _, val = line.partition(":")
        key = key.strip()
        if key == "scripts" and not val.strip():
            in_scripts = True
        elif key == "description":
            description = _strip_quotes(val)
        elif key == "argument-hint":
            argument_hint = _strip_quotes(val)
        # Other keys (handoffs, etc.) are intentionally dropped in native mode.

    name = path.stem
    if not description:
        raise ValueError(f"{path.name}: empty description")
    return Command(name, description, argument_hint, scripts, body)


# --------------------------------------------------------------------------- #
# Rendering
# --------------------------------------------------------------------------- #

def _yaml_quote(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def render_skill(cmd: Command) -> str:
    """Render a Command into a Claude Code SKILL.md (frontmatter + body)."""
    lines = ["---"]
    lines.append(f"name: {SKILL_PREFIX}.{cmd.name}")
    lines.append(f"description: {_yaml_quote(cmd.description)}")
    if cmd.argument_hint:
        lines.append(f"argument-hint: {_yaml_quote(cmd.argument_hint)}")
    lines.append("user-invocable: true")
    lines.append("disable-model-invocation: false")
    if cmd.scripts:
        lines.append("scripts:")
        for key in ("sh", "ps"):
            if key in cmd.scripts:
                lines.append(f"  {key}: {cmd.scripts[key]}")
    lines.append("---")
    lines.append("")
    return "\n".join(lines) + "\n" + cmd.body.rstrip("\n") + "\n"


def cmd_build(skills_dir: Path, dry_run: bool) -> int:
    if not COMMANDS_DIR.is_dir():
        print(f"ERROR: no commands dir at {COMMANDS_DIR}", file=sys.stderr)
        return 1
    command_files = sorted(COMMANDS_DIR.glob("*.md"))
    if not command_files:
        print(f"ERROR: no command files in {COMMANDS_DIR}", file=sys.stderr)
        return 1

    rendered = 0
    for path in command_files:
        cmd = parse_command(path)
        content = render_skill(cmd)
        target = skills_dir / f"{SKILL_PREFIX}-{cmd.name}" / "SKILL.md"
        if dry_run:
            print(f"[dry-run] would write {target} "
                  f"({len(content)} bytes, scripts={list(cmd.scripts) or 'none'})")
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            # write_bytes keeps LF cross-platform and is 3.9-safe (write_text
            # gained the newline argument only in 3.10).
            target.write_bytes(content.encode("utf-8"))
            print(f"rendered /{SKILL_PREFIX}.{cmd.name} -> {target}")
        rendered += 1

    # Copy hooks if any exist (settings registration is the installer's job).
    if HOOKS_DIR.is_dir():
        hook_files = sorted(HOOKS_DIR.glob("*.py"))
        if hook_files and not dry_run:
            hooks_target = Path.home() / ".claude" / "hooks"
            hooks_target.mkdir(parents=True, exist_ok=True)
            for h in hook_files:
                shutil.copy2(h, hooks_target / h.name)
                print(f"installed hook {h.name} -> {hooks_target / h.name}")
        elif hook_files:
            print(f"[dry-run] would install {len(hook_files)} hook(s) to ~/.claude/hooks")

    print(f"\n{rendered} skill(s) {'planned' if dry_run else 'rendered'}.")
    return 0


def cmd_init(project: Path, dry_run: bool) -> int:
    """Bootstrap <project>/.specify with scripts, templates, and memory dir."""
    specify = project / ".specify"
    plan = [
        (SCRIPTS_DIR / "bash", specify / "scripts" / "bash"),
        (SCRIPTS_DIR / "powershell", specify / "scripts" / "powershell"),
        (TEMPLATES_DIR, specify / "templates"),
    ]
    for src, dst in plan:
        if not src.is_dir():
            print(f"ERROR: missing source {src}", file=sys.stderr)
            return 1
        if dry_run:
            print(f"[dry-run] would copy {src} -> {dst}")
            continue
        dst.mkdir(parents=True, exist_ok=True)
        for item in sorted(src.iterdir()):
            if item.is_file():
                shutil.copy2(item, dst / item.name)
                if item.suffix == ".sh":
                    os.chmod(dst / item.name, 0o755)
        print(f"copied {src.name} -> {dst}")

    memory = specify / "memory"
    if dry_run:
        print(f"[dry-run] would create {memory}")
    else:
        memory.mkdir(parents=True, exist_ok=True)
        print(f"ensured {memory}")
    print(f"\n.specify bootstrapped at {specify}{' (dry-run)' if dry_run else ''}.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="mergen native renderer")
    sub = parser.add_subparsers(dest="cmd")

    p_build = sub.add_parser("build", help="render command prompts into ~/.claude/skills")
    p_build.add_argument("--skills-dir", default=str(Path.home() / ".claude" / "skills"),
                         help="target skills directory (default: ~/.claude/skills)")
    p_build.add_argument("--dry-run", action="store_true")

    p_init = sub.add_parser("init", help="bootstrap .specify in a project")
    p_init.add_argument("project", nargs="?", default=".",
                        help="project directory (default: cwd)")
    p_init.add_argument("--dry-run", action="store_true")

    args = parser.parse_args(argv)
    if args.cmd == "init":
        return cmd_init(Path(args.project).resolve(), args.dry_run)
    # Default to build (no subcommand or "build").
    skills_dir = getattr(args, "skills_dir", str(Path.home() / ".claude" / "skills"))
    dry_run = getattr(args, "dry_run", False)
    return cmd_build(Path(skills_dir), dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
