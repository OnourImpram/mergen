#!/usr/bin/env python3
"""spec-kit (B-shell) renderer for mergen's SDD layer.

Single source -> two shells (see core/CONVENTIONS.md). This is the SPEC-KIT
renderer. It packages the same `core/commands/<name>.md` single source into two
Spec Kit artifacts:

  preset/mergen/      Overrides Spec Kit's own core commands with the
                         mergen-powered versions. Installed with
                         `specify preset add --dev <path>`. Each command
                         `replaces:` the stock speckit.<name>.

  extensions/mergen/  Adds the commands Spec Kit does not have (verify,
                         rollup, go) as namespaced `speckit.mergen.<cmd>`,
                         and wires the verify gate as a non-bypassable
                         `after_implement` hook.

Why this is mostly copy + manifest generation: the single-source command files
are authored in Spec Kit's own SOURCE convention (bare `scripts/bash/...` in
frontmatter, which Spec Kit prefixes with `.specify/` at install time; `.specify/`
body paths). So the B-shell command file IS the core file, renamed. Only the
NATIVE renderer transforms (adds skill keys, prefixes scripts). Here we copy
verbatim and generate the manifests.

The generated tree under dist/speckit/ is committed (it is the shippable B-shell
adapter), so users installing via Spec Kit do not need to run this generator.
Stdlib only.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
COMMANDS_DIR = REPO / "core" / "commands"

# Spec Kit HAS these; the preset overrides them with mergen-powered versions.
PRESET_CMDS = ["constitution", "specify", "clarify", "checklist",
               "plan", "tasks", "analyze", "implement"]
# Spec Kit LACKS these; the extension adds them.
EXT_CMDS = ["verify", "rollup", "go", "lean", "debt"]

EXT_ID = "mergen"
AUTHOR = "TheGoatPsy"
REPO_URL = "https://github.com/TheGoatPsy/mergen"
LICENSE = "Apache-2.0"
SPECKIT_REQ = ">=0.6.0"


def read_description(path: Path) -> str:
    """Extract the frontmatter `description:` value (unquoted)."""
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return ""
    lines = text.splitlines()
    for i in range(1, len(lines)):
        ln = lines[i]
        if ln.strip() == "---":
            break
        if ln.startswith("description:"):
            val = ln.split(":", 1)[1].strip()
            if len(val) >= 2 and val[0] == val[-1] and val[0] in ("'", '"'):
                val = val[1:-1]
            return val
    return ""


def _yaml_dq(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def build_preset_yaml(descs: dict[str, str]) -> str:
    lines = [
        'schema_version: "1.0"',
        "",
        "preset:",
        '  id: "mergen"',
        '  name: "Mergen SDD"',
        '  version: "1.1.0"',
        '  description: "Max-effort, Workflow-orchestrated, adversarially-verified, '
        'minimal-by-default replacements for the core Spec Kit commands."',
        f'  author: "{AUTHOR}"',
        f'  repository: "{REPO_URL}"',
        f'  license: "{LICENSE}"',
        "",
        "requires:",
        f'  speckit_version: "{SPECKIT_REQ}"',
        "",
        "provides:",
        "  templates:",
    ]
    for name in PRESET_CMDS:
        lines += [
            '    - type: "command"',
            f'      name: "speckit.{name}"',
            f'      file: "commands/speckit.{name}.md"',
            f"      description: {_yaml_dq(descs[name])}",
            f'      replaces: "speckit.{name}"',
            "",
        ]
    lines += [
        "tags:",
        '  - "mergen"',
        '  - "max-effort"',
        '  - "workflow"',
        '  - "verified"',
        '  - "adversarial"',
        "",
    ]
    return "\n".join(lines)


def build_extension_yaml(descs: dict[str, str]) -> str:
    lines = [
        'schema_version: "1.0"',
        "",
        "extension:",
        f'  id: "{EXT_ID}"',
        '  name: "Mergen (mergen verification and minimalism)"',
        '  version: "1.1.0"',
        '  description: "Adds adversarial verification, canonical project-state '
        'rollup, a complexity router, an over-engineering review, and a '
        'deferred-shortcut debt ledger to Spec Kit, and wires a non-bypassable '
        'verify gate after implement."',
        f'  author: "{AUTHOR}"',
        f'  repository: "{REPO_URL}"',
        f'  license: "{LICENSE}"',
        "",
        "requires:",
        f'  speckit_version: "{SPECKIT_REQ}"',
        "",
        "provides:",
        "  commands:",
    ]
    for name in EXT_CMDS:
        lines += [
            f'    - name: "speckit.{EXT_ID}.{name}"',
            f'      file: "commands/speckit.{EXT_ID}.{name}.md"',
            f"      description: {_yaml_dq(descs[name])}",
        ]
    lines += [
        "",
        "hooks:",
        "  after_implement:",
        f'    command: "speckit.{EXT_ID}.verify"',
        "    optional: false",
        '    description: "Independently verify every [X] task against the '
        'filesystem and tests before completion is claimed."',
        "",
        "tags:",
        '  - "mergen"',
        '  - "verification"',
        '  - "adversarial"',
        "",
    ]
    return "\n".join(lines)


def cmd_build(out_dir: Path, dry_run: bool) -> int:
    missing = [c for c in (PRESET_CMDS + EXT_CMDS)
               if not (COMMANDS_DIR / f"{c}.md").is_file()]
    if missing:
        print(f"ERROR: missing source commands: {missing}", file=sys.stderr)
        return 1

    descs = {c: read_description(COMMANDS_DIR / f"{c}.md")
             for c in (PRESET_CMDS + EXT_CMDS)}
    empty = [c for c, d in descs.items() if not d]
    if empty:
        print(f"ERROR: commands with empty description: {empty}", file=sys.stderr)
        return 1

    preset_dir = out_dir / "preset" / "mergen"
    ext_dir = out_dir / "extensions" / EXT_ID

    actions: list[tuple[str, Path]] = []
    # Preset command files (verbatim copies, renamed speckit.<n>.md).
    for name in PRESET_CMDS:
        actions.append((str(COMMANDS_DIR / f"{name}.md"),
                        preset_dir / "commands" / f"speckit.{name}.md"))
    # Extension command files (verbatim, renamed speckit.mergen.<cmd>.md).
    for name in EXT_CMDS:
        actions.append((str(COMMANDS_DIR / f"{name}.md"),
                        ext_dir / "commands" / f"speckit.{EXT_ID}.{name}.md"))

    if dry_run:
        for src, dst in actions:
            print(f"[dry-run] copy {Path(src).name} -> {dst}")
        print(f"[dry-run] write {preset_dir / 'preset.yml'}")
        print(f"[dry-run] write {ext_dir / 'extension.yml'}")
        return 0

    for src, dst in actions:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
    (preset_dir / "preset.yml").write_text(build_preset_yaml(descs),
                                           encoding="utf-8", newline="\n")
    (ext_dir / "extension.yml").write_text(build_extension_yaml(descs),
                                           encoding="utf-8", newline="\n")

    print(f"preset 'mergen': {len(PRESET_CMDS)} command override(s) -> {preset_dir}")
    print(f"extension '{EXT_ID}': {len(EXT_CMDS)} command(s) + after_implement hook -> {ext_dir}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="mergen spec-kit (B-shell) renderer")
    ap.add_argument("--out", default=str(REPO / "dist" / "speckit"),
                    help="output dir (default: dist/speckit in the repo)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    return cmd_build(Path(args.out), args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
