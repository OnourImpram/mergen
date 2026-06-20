#!/usr/bin/env python3
"""feature_ops.py - single Python implementation of all SDD feature helper operations.

All real logic that was spread across five bash scripts and five PowerShell scripts
now lives here. The .sh and .ps1 files are thin shims that delegate here via:

    python <script_dir>/feature_ops.py <subcommand> [flags...]

Subcommands mirror the original script names:
    check-prerequisites   (was check-prerequisites.sh / .ps1)
    setup-plan            (was setup-plan.sh / .ps1)
    setup-tasks           (was setup-tasks.sh / .ps1)
    create-new-feature    (was create-new-feature.sh / .ps1)

m3 fold-in: setup-plan warns (non-fatal, to stderr) when spec.md is absent,
because a plan logically depends on a spec. This is a warning only, not a hard error.

Stdlib only. Python 3.9 compatible.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path


# --------------------------------------------------------------------------- #
# Path resolution (mirrors common.sh / common.ps1 logic exactly)
# --------------------------------------------------------------------------- #

def find_specify_root(start: Path) -> Path | None:
    """Walk upward from start looking for a .specify directory."""
    current = start.resolve()
    prev = None
    while True:
        if (current / ".specify").is_dir():
            return current
        parent = current.parent
        if parent == current or current == prev:
            return None
        prev = current
        current = parent


def get_repo_root(script_dir: Path) -> Path:
    """Return the repository root, preferring the .specify marker."""
    specify_root = find_specify_root(Path.cwd())
    if specify_root is not None:
        return specify_root
    # Fallback: three levels up from script_dir (core/scripts/ -> repo root).
    return (script_dir / ".." / "..").resolve()


def read_feature_json_feature_directory(repo_root: Path) -> str:
    """Read feature_directory from .specify/feature.json. Returns '' on any error."""
    fj = repo_root / ".specify" / "feature.json"
    if not fj.is_file():
        return ""
    try:
        data = json.loads(fj.read_text(encoding="utf-8"))
        return data.get("feature_directory") or ""
    except Exception:
        return ""


def persist_feature_json(repo_root: Path, feature_dir_value: str) -> None:
    """Write feature_directory to .specify/feature.json when the value changes."""
    # Strip repo_root prefix so the stored value is relative.
    repo_prefix = str(repo_root) + os.sep
    if feature_dir_value.startswith(repo_prefix):
        feature_dir_value = feature_dir_value[len(repo_prefix):]
    # Also handle forward-slash separator on Windows.
    repo_prefix_fwd = str(repo_root).replace("\\", "/") + "/"
    fwd = feature_dir_value.replace("\\", "/")
    if fwd.startswith(repo_prefix_fwd):
        feature_dir_value = feature_dir_value[len(repo_prefix_fwd):]

    current = read_feature_json_feature_directory(repo_root)
    if current == feature_dir_value:
        return

    specify_dir = repo_root / ".specify"
    specify_dir.mkdir(parents=True, exist_ok=True)
    fj = specify_dir / "feature.json"
    payload = json.dumps({"feature_directory": feature_dir_value}, ensure_ascii=False)
    fj.write_text(payload + "\n", encoding="utf-8")


def get_feature_paths(repo_root: Path) -> dict[str, str]:
    """Resolve all feature paths from env or .specify/feature.json.

    Returns a dict with keys matching the bash variable names:
    REPO_ROOT, CURRENT_BRANCH, FEATURE_DIR, FEATURE_SPEC, IMPL_PLAN,
    TASKS, RESEARCH, DATA_MODEL, QUICKSTART, CONTRACTS_DIR.
    Raises SystemExit on failure (mirrors set -e behavior).
    """
    current_branch = os.environ.get("SPECIFY_FEATURE", "")

    feature_dir_raw = os.environ.get("SPECIFY_FEATURE_DIRECTORY", "")
    if feature_dir_raw:
        feature_dir = Path(feature_dir_raw)
        if not feature_dir.is_absolute():
            feature_dir = repo_root / feature_dir
        persist_feature_json(repo_root, feature_dir_raw)
    else:
        raw = read_feature_json_feature_directory(repo_root)
        if raw:
            feature_dir = Path(raw)
            if not feature_dir.is_absolute():
                feature_dir = repo_root / feature_dir
        else:
            fj = repo_root / ".specify" / "feature.json"
            if fj.is_file():
                print(
                    "ERROR: Feature directory not found. Set SPECIFY_FEATURE_DIRECTORY"
                    " or ensure .specify/feature.json contains feature_directory.",
                    file=sys.stderr,
                )
            else:
                print(
                    "ERROR: Feature directory not found. Set SPECIFY_FEATURE_DIRECTORY"
                    " or run the specify command to create .specify/feature.json.",
                    file=sys.stderr,
                )
            sys.exit(1)

    fd = str(feature_dir)
    return {
        "REPO_ROOT": str(repo_root),
        "CURRENT_BRANCH": current_branch,
        "FEATURE_DIR": fd,
        "FEATURE_SPEC": str(feature_dir / "spec.md"),
        "IMPL_PLAN": str(feature_dir / "plan.md"),
        "TASKS": str(feature_dir / "tasks.md"),
        "RESEARCH": str(feature_dir / "research.md"),
        "DATA_MODEL": str(feature_dir / "data-model.md"),
        "QUICKSTART": str(feature_dir / "quickstart.md"),
        "CONTRACTS_DIR": str(feature_dir / "contracts"),
    }


# --------------------------------------------------------------------------- #
# Template resolution (mirrors resolve_template in common.sh / common.ps1)
# --------------------------------------------------------------------------- #

def resolve_template(template_name: str, repo_root: Path) -> Path | None:
    """Resolve a template name to a file path using the priority stack.

    Priority:
      1. .specify/templates/overrides/<name>.md
      2. .specify/presets/<id>/templates/<name>.md (sorted by priority)
      3. .specify/extensions/<id>/templates/<name>.md
      4. .specify/templates/<name>.md  (core)
    """
    base = repo_root / ".specify" / "templates"

    # Priority 1: project overrides.
    override = base / "overrides" / f"{template_name}.md"
    if override.is_file():
        return override

    # Priority 2: installed presets sorted by priority.
    presets_dir = repo_root / ".specify" / "presets"
    if presets_dir.is_dir():
        sorted_presets = _sorted_preset_ids(presets_dir)
        for pid in sorted_presets:
            candidate = presets_dir / pid / "templates" / f"{template_name}.md"
            if candidate.is_file():
                return candidate

    # Priority 3: extension-provided templates.
    ext_dir = repo_root / ".specify" / "extensions"
    if ext_dir.is_dir():
        for ext in sorted(ext_dir.iterdir()):
            if not ext.is_dir() or ext.name.startswith("."):
                continue
            candidate = ext / "templates" / f"{template_name}.md"
            if candidate.is_file():
                return candidate

    # Priority 4: core templates.
    core = base / f"{template_name}.md"
    if core.is_file():
        return core

    return None


def _sorted_preset_ids(presets_dir: Path) -> list[str]:
    """Return preset IDs sorted by priority field from .registry, or alphabetically."""
    registry = presets_dir / ".registry"
    if registry.is_file():
        try:
            data = json.loads(registry.read_text(encoding="utf-8"))
            presets = data.get("presets", {})
            enabled = [
                (pid, meta if isinstance(meta, dict) else {})
                for pid, meta in presets.items()
                if not (isinstance(meta, dict) and meta.get("enabled") is False)
            ]
            enabled.sort(key=lambda t: t[1].get("priority", 10))
            return [pid for pid, _ in enabled]
        except Exception:
            pass
    # Fallback: alphabetical.
    return sorted(p.name for p in presets_dir.iterdir() if p.is_dir() and not p.name.startswith("."))


# --------------------------------------------------------------------------- #
# invoke separator (mirrors get_invoke_separator in common.sh / common.ps1)
# --------------------------------------------------------------------------- #

def get_invoke_separator(repo_root: Path) -> str:
    """Read .specify/integration.json and return '.' or '-'."""
    integration_json = repo_root / ".specify" / "integration.json"
    if not integration_json.is_file():
        return "."
    try:
        state = json.loads(integration_json.read_text(encoding="utf-8"))
        key = state.get("default_integration") or state.get("integration") or ""
        settings = state.get("integration_settings")
        if key and isinstance(settings, dict):
            entry = settings.get(key)
            if isinstance(entry, dict) and entry.get("invoke_separator") in (".", "-"):
                return entry["invoke_separator"]
    except Exception:
        pass
    return "."


def format_speckit_command(command_name: str, repo_root: Path) -> str:
    """Return '/speckit<sep><name>' for user-facing error messages."""
    sep = get_invoke_separator(repo_root)
    name = command_name.lstrip("/")
    for prefix in ("speckit.", "speckit-"):
        if name.startswith(prefix):
            name = name[len(prefix):]
            break
    name = name.replace(".", sep)
    return f"/speckit{sep}{name}"


# --------------------------------------------------------------------------- #
# Available-docs helper (shared by check-prerequisites and setup-tasks)
# --------------------------------------------------------------------------- #

def build_available_docs(
    paths: dict[str, str],
    include_tasks: bool = False,
) -> list[str]:
    """Build the list of available optional documents."""
    docs: list[str] = []
    if Path(paths["RESEARCH"]).is_file():
        docs.append("research.md")
    if Path(paths["DATA_MODEL"]).is_file():
        docs.append("data-model.md")
    contracts_dir = Path(paths["CONTRACTS_DIR"])
    if contracts_dir.is_dir() and any(contracts_dir.iterdir()):
        docs.append("contracts/")
    if Path(paths["QUICKSTART"]).is_file():
        docs.append("quickstart.md")
    if include_tasks and Path(paths["TASKS"]).is_file():
        docs.append("tasks.md")
    return docs


# --------------------------------------------------------------------------- #
# JSON output helpers
# --------------------------------------------------------------------------- #

def _emit_json(obj: dict) -> None:
    print(json.dumps(obj, ensure_ascii=False, separators=(",", ":")))


# --------------------------------------------------------------------------- #
# Subcommand: check-prerequisites
# --------------------------------------------------------------------------- #

def cmd_check_prerequisites(argv: list[str], repo_root: Path) -> int:
    """Mirrors check-prerequisites.sh and check-prerequisites.ps1.

    Flags: --json, --require-tasks, --require-spec, --include-tasks,
           --paths-only, --help / -h.
    PowerShell aliases: -Json, -RequireTasks, -RequireSpec, -IncludeTasks,
                        -PathsOnly, -Help.
    """
    p = argparse.ArgumentParser(
        prog="check-prerequisites",
        add_help=False,
    )
    p.add_argument("--json", "-Json", action="store_true", dest="json_mode")
    p.add_argument("--require-tasks", "-RequireTasks", action="store_true", dest="require_tasks")
    p.add_argument("--require-spec", "-RequireSpec", action="store_true", dest="require_spec")
    p.add_argument("--include-tasks", "-IncludeTasks", action="store_true", dest="include_tasks")
    p.add_argument("--paths-only", "-PathsOnly", action="store_true", dest="paths_only")
    p.add_argument("--help", "-h", "-Help", action="store_true", dest="show_help")

    args, unknown = p.parse_known_args(argv)

    if unknown:
        print(
            f"ERROR: Unknown option(s) {unknown}. Use --help for usage information.",
            file=sys.stderr,
        )
        return 1

    if args.show_help:
        print(
            "Usage: check-prerequisites [OPTIONS]\n\n"
            "Consolidated prerequisite checking for Spec-Driven Development workflow.\n\n"
            "OPTIONS:\n"
            "  --json              Output in JSON format\n"
            "  --require-tasks     Require tasks.md to exist (for implementation phase)\n"
            "  --require-spec      Require spec.md to exist (for the clarify phase, before plan)\n"
            "  --include-tasks     Include tasks.md in AVAILABLE_DOCS list\n"
            "  --paths-only        Only output path variables (no prerequisite validation)\n"
            "  --help, -h          Show this help message\n"
        )
        return 0

    paths = get_feature_paths(repo_root)

    if args.paths_only:
        if args.json_mode:
            _emit_json({
                "REPO_ROOT": paths["REPO_ROOT"],
                "BRANCH": paths["CURRENT_BRANCH"],
                "FEATURE_DIR": paths["FEATURE_DIR"],
                "FEATURE_SPEC": paths["FEATURE_SPEC"],
                "IMPL_PLAN": paths["IMPL_PLAN"],
                "TASKS": paths["TASKS"],
            })
        else:
            print(f"REPO_ROOT: {paths['REPO_ROOT']}")
            print(f"BRANCH: {paths['CURRENT_BRANCH']}")
            print(f"FEATURE_DIR: {paths['FEATURE_DIR']}")
            print(f"FEATURE_SPEC: {paths['FEATURE_SPEC']}")
            print(f"IMPL_PLAN: {paths['IMPL_PLAN']}")
            print(f"TASKS: {paths['TASKS']}")
        return 0

    # Validate required directories and files.
    feature_dir = Path(paths["FEATURE_DIR"])
    if not feature_dir.is_dir():
        specify_cmd = format_speckit_command("specify", repo_root)
        print(f"ERROR: Feature directory not found: {feature_dir}", file=sys.stderr)
        print(f"Run {specify_cmd} first to create the feature structure.", file=sys.stderr)
        return 1

    if args.require_spec:
        if not Path(paths["FEATURE_SPEC"]).is_file():
            specify_cmd = format_speckit_command("specify", repo_root)
            print(f"ERROR: spec.md not found in {feature_dir}", file=sys.stderr)
            print(f"Run {specify_cmd} first to create the feature spec.", file=sys.stderr)
            return 1
    else:
        if not Path(paths["IMPL_PLAN"]).is_file():
            plan_cmd = format_speckit_command("plan", repo_root)
            print(f"ERROR: plan.md not found in {feature_dir}", file=sys.stderr)
            print(f"Run {plan_cmd} first to create the implementation plan.", file=sys.stderr)
            return 1
        if args.require_tasks and not Path(paths["TASKS"]).is_file():
            tasks_cmd = format_speckit_command("tasks", repo_root)
            print(f"ERROR: tasks.md not found in {feature_dir}", file=sys.stderr)
            print(f"Run {tasks_cmd} first to create the task list.", file=sys.stderr)
            return 1

    docs = build_available_docs(paths, include_tasks=args.include_tasks)

    if args.json_mode:
        _emit_json({"FEATURE_DIR": paths["FEATURE_DIR"], "AVAILABLE_DOCS": docs})
    else:
        print(f"FEATURE_DIR:{paths['FEATURE_DIR']}")
        print("AVAILABLE_DOCS:")
        for name, path_key in (
            ("research.md", "RESEARCH"),
            ("data-model.md", "DATA_MODEL"),
        ):
            mark = "✓" if Path(paths[path_key]).is_file() else "✗"
            print(f"  {mark} {name}")
        contracts_dir = Path(paths["CONTRACTS_DIR"])
        has_contracts = contracts_dir.is_dir() and any(contracts_dir.iterdir())
        print(f"  {'✓' if has_contracts else '✗'} contracts/")
        mark = "✓" if Path(paths["QUICKSTART"]).is_file() else "✗"
        print(f"  {mark} quickstart.md")
        if args.include_tasks:
            mark = "✓" if Path(paths["TASKS"]).is_file() else "✗"
            print(f"  {mark} tasks.md")
    return 0


# --------------------------------------------------------------------------- #
# Subcommand: setup-plan
# --------------------------------------------------------------------------- #

def cmd_setup_plan(argv: list[str], repo_root: Path) -> int:
    """Mirrors setup-plan.sh and setup-plan.ps1.

    Flags: --json, --help / -h.
    PowerShell aliases: -Json, -Help.

    m3 fold-in: warns (non-fatal, to stderr) when spec.md is absent.
    """
    p = argparse.ArgumentParser(prog="setup-plan", add_help=False)
    p.add_argument("--json", "-Json", action="store_true", dest="json_mode")
    p.add_argument("--help", "-h", "-Help", action="store_true", dest="show_help")

    args, unknown = p.parse_known_args(argv)
    if args.show_help:
        print("Usage: setup-plan [--json] [--help]")
        print("  --json    Output results in JSON format")
        print("  --help    Show this help message")
        return 0

    paths = get_feature_paths(repo_root)
    feature_dir = Path(paths["FEATURE_DIR"])
    feature_dir.mkdir(parents=True, exist_ok=True)

    impl_plan = Path(paths["IMPL_PLAN"])
    if impl_plan.is_file():
        msg = f"Plan already exists at {impl_plan}, skipping template copy"
        if args.json_mode:
            print(msg, file=sys.stderr)
        else:
            print(msg)
    else:
        template = resolve_template("plan-template", repo_root)
        if template is not None and template.is_file():
            shutil.copy2(str(template), str(impl_plan))
            msg = f"Copied plan template to {impl_plan}"
            if args.json_mode:
                print(msg, file=sys.stderr)
            else:
                print(msg)
        else:
            msg = "Warning: Plan template not found"
            if args.json_mode:
                print(msg, file=sys.stderr)
            else:
                print(msg)
            impl_plan.touch()

    # m3: warn when spec.md is absent (non-fatal).
    if not Path(paths["FEATURE_SPEC"]).is_file():
        print(
            "Warning: spec.md not found in the feature directory. "
            "A plan logically depends on a spec. "
            "Consider running the specify command first.",
            file=sys.stderr,
        )

    if args.json_mode:
        _emit_json({
            "FEATURE_SPEC": paths["FEATURE_SPEC"],
            "IMPL_PLAN": paths["IMPL_PLAN"],
            "SPECS_DIR": paths["FEATURE_DIR"],
            "BRANCH": paths["CURRENT_BRANCH"],
        })
    else:
        print(f"FEATURE_SPEC: {paths['FEATURE_SPEC']}")
        print(f"IMPL_PLAN: {paths['IMPL_PLAN']}")
        print(f"SPECS_DIR: {paths['FEATURE_DIR']}")
        print(f"BRANCH: {paths['CURRENT_BRANCH']}")
    return 0


# --------------------------------------------------------------------------- #
# Subcommand: setup-tasks
# --------------------------------------------------------------------------- #

def cmd_setup_tasks(argv: list[str], repo_root: Path) -> int:
    """Mirrors setup-tasks.sh and setup-tasks.ps1.

    Flags: --json, --help / -h.
    PowerShell aliases: -Json, -Help.
    """
    p = argparse.ArgumentParser(prog="setup-tasks", add_help=False)
    p.add_argument("--json", "-Json", action="store_true", dest="json_mode")
    p.add_argument("--help", "-h", "-Help", action="store_true", dest="show_help")

    args, unknown = p.parse_known_args(argv)
    if args.show_help:
        print("Usage: setup-tasks [--json] [--help]")
        return 0

    paths = get_feature_paths(repo_root)

    impl_plan = Path(paths["IMPL_PLAN"])
    if not impl_plan.is_file():
        plan_cmd = format_speckit_command("plan", repo_root)
        print(f"ERROR: plan.md not found in {paths['FEATURE_DIR']}", file=sys.stderr)
        print(f"Run {plan_cmd} first to create the implementation plan.", file=sys.stderr)
        return 1

    feature_spec = Path(paths["FEATURE_SPEC"])
    if not feature_spec.is_file():
        specify_cmd = format_speckit_command("specify", repo_root)
        print(f"ERROR: spec.md not found in {paths['FEATURE_DIR']}", file=sys.stderr)
        print(f"Run {specify_cmd} first to create the feature structure.", file=sys.stderr)
        return 1

    docs = build_available_docs(paths, include_tasks=False)

    tasks_template = resolve_template("tasks-template", repo_root)
    if tasks_template is None or not tasks_template.is_file():
        print(
            f"ERROR: Could not resolve required tasks-template from the template"
            f" override stack for {repo_root}",
            file=sys.stderr,
        )
        print(
            "Template 'tasks-template' was not found in any supported location"
            " (overrides, presets, extensions, or shared core). Add an override at"
            " .specify/templates/overrides/tasks-template.md, or run 'specify init'"
            " / reinstall shared infra to restore the core"
            " .specify/templates/tasks-template.md template.",
            file=sys.stderr,
        )
        return 1

    tasks_template_path = str(tasks_template.resolve())

    if args.json_mode:
        _emit_json({
            "FEATURE_DIR": paths["FEATURE_DIR"],
            "AVAILABLE_DOCS": docs,
            "TASKS_TEMPLATE": tasks_template_path,
        })
    else:
        print(f"FEATURE_DIR: {paths['FEATURE_DIR']}")
        print(f"TASKS_TEMPLATE: {tasks_template_path}")
        print("AVAILABLE_DOCS:")
        for name, path_key in (
            ("research.md", "RESEARCH"),
            ("data-model.md", "DATA_MODEL"),
        ):
            mark = "✓" if Path(paths[path_key]).is_file() else "✗"
            print(f"  {mark} {name}")
        contracts_dir = Path(paths["CONTRACTS_DIR"])
        has_contracts = contracts_dir.is_dir() and any(contracts_dir.iterdir())
        print(f"  {'✓' if has_contracts else '✗'} contracts/")
        mark = "✓" if Path(paths["QUICKSTART"]).is_file() else "✗"
        print(f"  {mark} quickstart.md")
    return 0


# --------------------------------------------------------------------------- #
# Feature-name generation helpers (mirrors create-new-feature.sh / .ps1)
# --------------------------------------------------------------------------- #

_STOP_WORDS = frozenset({
    "i", "a", "an", "the", "to", "for", "of", "in", "on", "at", "by",
    "with", "from", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "should",
    "could", "can", "may", "might", "must", "shall", "this", "that",
    "these", "those", "my", "your", "our", "their", "want", "need",
    "add", "get", "set",
})


def clean_branch_name(name: str) -> str:
    """Lowercase, replace non-alphanumerics with hyphens, collapse duplicates."""
    s = re.sub(r"[^a-z0-9]", "-", name.lower())
    s = re.sub(r"-+", "-", s)
    return s.strip("-")


def generate_branch_name(description: str) -> str:
    """Generate a 3-4 word slug from description, filtering stop words."""
    clean = re.sub(r"[^a-z0-9\s]", " ", description.lower())
    words = clean.split()
    meaningful: list[str] = []
    for word in words:
        if not word:
            continue
        if word in _STOP_WORDS:
            continue
        if len(word) >= 3:
            meaningful.append(word)
        elif re.search(r"\b" + word.upper() + r"\b", description):
            meaningful.append(word)

    if meaningful:
        max_words = 4 if len(meaningful) == 4 else 3
        return "-".join(meaningful[:max_words])

    # Fallback: use clean_branch_name and take first 3 tokens.
    parts = [p for p in clean_branch_name(description).split("-") if p]
    return "-".join(parts[:3])


def get_highest_from_specs(specs_dir: Path) -> int:
    """Return the highest sequential numeric prefix found in specs_dir."""
    highest = 0
    if not specs_dir.is_dir():
        return 0
    for entry in specs_dir.iterdir():
        if not entry.is_dir():
            continue
        name = entry.name
        # Match sequential prefixes (>=3 digits) but not timestamp dirs.
        if re.match(r"^\d{3,}-", name) and not re.match(r"^\d{8}-\d{6}-", name):
            m = re.match(r"^(\d+)", name)
            if m:
                n = int(m.group(1))
                if n > highest:
                    highest = n
    return highest


# --------------------------------------------------------------------------- #
# Subcommand: create-new-feature
# --------------------------------------------------------------------------- #

def cmd_create_new_feature(argv: list[str], repo_root: Path) -> int:
    """Mirrors create-new-feature.sh and create-new-feature.ps1.

    Flags: --json, --dry-run, --allow-existing-branch, --short-name <name>,
           --number N, --timestamp, --help / -h.
    PowerShell aliases: -Json, -DryRun, -AllowExistingBranch, -ShortName,
                        -Number, -Timestamp, -Help.
    """
    p = argparse.ArgumentParser(prog="create-new-feature", add_help=False)
    p.add_argument("--json", "-Json", action="store_true", dest="json_mode")
    p.add_argument("--dry-run", "-DryRun", action="store_true", dest="dry_run")
    p.add_argument(
        "--allow-existing-branch", "-AllowExistingBranch",
        action="store_true", dest="allow_existing",
    )
    p.add_argument("--short-name", "-ShortName", dest="short_name", default="")
    p.add_argument("--number", "-Number", dest="number", default="0")
    p.add_argument("--timestamp", "-Timestamp", action="store_true", dest="use_timestamp")
    p.add_argument("--help", "-h", "-Help", action="store_true", dest="show_help")
    # Positional: feature description (remaining args).
    p.add_argument("description", nargs="*")

    args, unknown = p.parse_known_args(argv)
    # Absorb unknown positionals into description.
    all_desc = args.description + unknown

    if args.show_help:
        print(
            "Usage: create-new-feature [--json] [--dry-run] [--allow-existing-branch]"
            " [--short-name <name>] [--number N] [--timestamp] <feature_description>"
        )
        print("")
        print("Options:")
        print("  --json              Output in JSON format")
        print("  --dry-run           Compute feature name and paths without creating files")
        print("  --allow-existing-branch  Reuse an existing feature directory if it exists")
        print("  --short-name <name> Provide a custom short name (2-4 words) for the feature")
        print("  --number N          Specify branch number manually (overrides auto-detection)")
        print("  --timestamp         Use timestamp prefix (YYYYMMDD-HHMMSS) instead of sequential")
        print("  --help, -h          Show this help message")
        return 0

    feature_description = " ".join(all_desc).strip()
    if not feature_description:
        print(
            "Usage: create-new-feature [--json] [--dry-run] [--allow-existing-branch]"
            " [--short-name <name>] [--number N] [--timestamp] <feature_description>",
            file=sys.stderr,
        )
        return 1

    feature_description = re.sub(r"^\s+|\s+$", "", feature_description)
    if not feature_description:
        print("Error: Feature description cannot be empty or contain only whitespace", file=sys.stderr)
        return 1

    # Generate branch suffix.
    if args.short_name:
        branch_suffix = clean_branch_name(args.short_name)
    else:
        branch_suffix = generate_branch_name(feature_description)

    # Parse number (allow "0" default meaning auto).
    try:
        branch_number = int(args.number)
    except (TypeError, ValueError):
        branch_number = 0

    # Warn if both --number and --timestamp are given.
    if args.use_timestamp and branch_number != 0:
        print("[specify] Warning: --number is ignored when --timestamp is used", file=sys.stderr)
        branch_number = 0

    specs_dir = repo_root / "specs"
    if not args.dry_run:
        specs_dir.mkdir(parents=True, exist_ok=True)

    if args.use_timestamp:
        feature_num = datetime.now().strftime("%Y%m%d-%H%M%S")
        branch_name = f"{feature_num}-{branch_suffix}"
    else:
        if branch_number == 0:
            branch_number = get_highest_from_specs(specs_dir) + 1
        feature_num = f"{branch_number:03d}"
        branch_name = f"{feature_num}-{branch_suffix}"

    # GitHub enforces a 244-byte limit on branch names.
    max_branch_length = 244
    if len(branch_name) > max_branch_length:
        prefix_length = len(feature_num) + 1
        max_suffix_length = max_branch_length - prefix_length
        truncated_suffix = branch_suffix[:max_suffix_length].rstrip("-")
        original_branch_name = branch_name
        branch_name = f"{feature_num}-{truncated_suffix}"
        print("[specify] Warning: Branch name exceeded GitHub's 244-byte limit", file=sys.stderr)
        print(f"[specify] Original: {original_branch_name} ({len(original_branch_name)} bytes)", file=sys.stderr)
        print(f"[specify] Truncated to: {branch_name} ({len(branch_name)} bytes)", file=sys.stderr)

    feature_dir = specs_dir / branch_name
    spec_file = feature_dir / "spec.md"

    if not args.dry_run:
        if feature_dir.is_dir() and not args.allow_existing:
            if args.use_timestamp:
                print(
                    f"Error: Feature directory '{feature_dir}' already exists."
                    " Rerun to get a new timestamp or use a different --short-name.",
                    file=sys.stderr,
                )
            else:
                print(
                    f"Error: Feature directory '{feature_dir}' already exists."
                    " Please use a different feature name or specify a different number with --number.",
                    file=sys.stderr,
                )
            return 1

        feature_dir.mkdir(parents=True, exist_ok=True)

        if not spec_file.is_file():
            template = resolve_template("spec-template", repo_root)
            if template is not None and template.is_file():
                shutil.copy2(str(template), str(spec_file))
            else:
                print("Warning: Spec template not found; created empty spec file", file=sys.stderr)
                spec_file.touch()

        persist_feature_json(repo_root, str(feature_dir))

        print(f"# To persist: export SPECIFY_FEATURE={branch_name!r}", file=sys.stderr)
        print(f"#              export SPECIFY_FEATURE_DIRECTORY={str(feature_dir)!r}", file=sys.stderr)

    if args.json_mode:
        obj: dict = {
            "BRANCH_NAME": branch_name,
            "SPEC_FILE": str(spec_file),
            "FEATURE_NUM": feature_num,
        }
        if args.dry_run:
            obj["DRY_RUN"] = True
        _emit_json(obj)
    else:
        print(f"BRANCH_NAME: {branch_name}")
        print(f"SPEC_FILE: {spec_file}")
        print(f"FEATURE_NUM: {feature_num}")
        if not args.dry_run:
            print(f"# To persist in your shell: export SPECIFY_FEATURE={branch_name!r}")
            print(f"#                           export SPECIFY_FEATURE_DIRECTORY={str(feature_dir)!r}")
    return 0


# --------------------------------------------------------------------------- #
# Dispatch
# --------------------------------------------------------------------------- #

_SUBCOMMANDS: dict[str, object] = {
    "check-prerequisites": cmd_check_prerequisites,
    "setup-plan": cmd_setup_plan,
    "setup-tasks": cmd_setup_tasks,
    "create-new-feature": cmd_create_new_feature,
}


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]

    if not argv or argv[0] in ("-h", "--help"):
        print("Usage: feature_ops.py <subcommand> [options]")
        print("")
        print("Subcommands:")
        for name in _SUBCOMMANDS:
            print(f"  {name}")
        return 0

    subcommand = argv[0]
    rest = argv[1:]

    handler = _SUBCOMMANDS.get(subcommand)
    if handler is None:
        print(f"ERROR: Unknown subcommand '{subcommand}'", file=sys.stderr)
        return 1

    # Resolve repo root relative to this script's own directory (core/scripts/).
    script_dir = Path(__file__).resolve().parent
    repo_root = get_repo_root(script_dir)

    return handler(rest, repo_root)  # type: ignore[operator]


if __name__ == "__main__":
    sys.exit(main())
