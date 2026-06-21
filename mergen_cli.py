#!/usr/bin/env python3
"""mergen: one cross-platform install / doctor / uninstall / upgrade CLI.

A single Python entry point that replaces the shell installers' orchestration.
It renders the SDD skills from this repo's core/, registers the runtime hooks,
checks the install honestly, and can remove it. Unlike install.sh it runs the
same way on Windows, macOS, and Linux, because it drives the in-repo Python
helpers directly rather than shelling bash.

It is exposed as the `mergen` command through pyproject's [project.scripts] when
installed with `pip install -e .` or `pipx install -e .` from a clone. The
editable/clone install is the supported path on purpose: mergen renders from
this repo's core/ tree, so the command has to be able to find it. A fully
standalone wheel that bundles core/ as package data is on the roadmap.

The verbs:

  install    copy the effort command and hook, register the effort hook, render
             the 14 SDD skills, and register the two SDD hooks. Idempotent.
  doctor     read-only health probe. Reports what is present, what is missing,
             and the honest caveats (the /effort max manual paste, and that the
             hooks are reinforcement nudges, not enforcement).
  uninstall  remove every artifact install created. Idempotent.
  upgrade    re-render the skills from the current core/ and re-register the
             hooks. Use after pulling a new version of the repo.
  verify     run the deterministic verify harness on any project. This verb is
             agent agnostic. It forwards to scripts/verify_core.py, which is pure
             standard library and needs no Claude Code, no network, and no model.
  verify-lint
             refuse a verification report that is not a clean, proven pass
             (proofless pass, ambiguous pass, summary fail, conditional, unsigned
             high-trust). Stdlib enforcement of the verification-report schema.
  dashboard  render a static HTML dashboard over a directory of verification
             reports. Agent agnostic, pure standard library, no network.
  status     summarize a tasks-state.json (done versus pending, per task). Agent
             agnostic. The Spec Kit analog is `specify status`.
  issues     render GitHub issue stubs from a tasks.md. It renders, it does not
             create. Agent agnostic. The Spec Kit analog is taskstoissues.
  trends     cross-run verification trends and per-task churn over a directory of
             reports, with a per-feature spec churn rollup, and a side-by-side
             comparison when several directories are passed. Where dashboard is a
             snapshot, this is the time dimension. Agent agnostic, pure standard
             library, no network.
  graph      typed provenance graph over the ledger: ingest a verification report,
             walk the proof chain that justifies an artifact, audit broken lineage
             and unsigned high-trust nodes. Agent agnostic, pure standard library.
  replay     record a deterministic verification run and replay it against the
             current tree, reporting match or divergence. The recorded input is the
             tasks-state, the variable is the tree. Agent agnostic, pure stdlib.
  impacted   continuous verification: from a diff and the tasks DAG, re-verify only
             the impacted slice and flag any task that flips pass to fail against a
             prior report. Agent agnostic, pure standard library.
  pack       validate a domain policy pack: the name matches its directory, only the
             raise-only fields appear, and the path list is a single-line array the
             3.9 and 3.10 fallback reader can recover. Agent agnostic, pure stdlib.
  calibrate  the Adaptive Governor: compute review-scope thresholds from the recorded
             governor history, bounded so adaptation can never weaken the floor. Use
             classify to show one decision. Agent agnostic, pure standard library.
  adapter    the Adapter SDK: validate the per-host capability manifests, print the
             generated capability matrix, or check whether a host provides a capability
             so a renderer refuses to overclaim. Agent agnostic, pure standard library.
  sign       bind a pre-action authorization token to an artifact's exact bytes (HMAC
             under a local key), or verify one, so an acknowledgement cannot be copied
             onto a different change. Agent agnostic, pure standard library.

install, uninstall, and upgrade act on the real ~/.claude. doctor takes optional
directory flags so it can inspect any tree, which is also how it is tested.
verify, dashboard, status, issues, trends, graph, replay, impacted, pack, calibrate,
adapter, and sign act on whatever project paths the forwarded flags name.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parent

# In-repo helpers the CLI orchestrates.
_BUILD_NATIVE = _REPO / "dist" / "native" / "build_native.py"
_PATCH_HOOKS = _REPO / "dist" / "native" / "patch_settings_hooks.py"
_VERIFY_CORE = _REPO / "scripts" / "verify_core.py"
_VERIFY_LINT = _REPO / "scripts" / "verify_report_lint.py"
_DASHBOARD = _REPO / "scripts" / "dashboard.py"
_STATUS = _REPO / "scripts" / "tasks_status.py"
_ISSUES = _REPO / "scripts" / "tasks_to_issues.py"
_TRENDS = _REPO / "scripts" / "trends.py"
_GRAPH = _REPO / "scripts" / "trust_graph.py"
_REPLAY = _REPO / "scripts" / "replay.py"
_IMPACTED = _REPO / "scripts" / "impacted.py"
_PACK = _REPO / "scripts" / "pack_validate.py"
_CALIBRATE = _REPO / "scripts" / "governor_adaptive.py"
_ADAPTER = _REPO / "scripts" / "adapter_sdk.py"
_SIGN = _REPO / "scripts" / "preaction_sign.py"
_SCHEMAS_DIR = _REPO / "core" / "schemas"
_EFFORT_PATCH = _REPO / "effort-mode" / "scripts" / "patch_settings.py"
_EFFORT_CMD = _REPO / "effort-mode" / "commands" / "mergen.md"
_EFFORT_HOOK = _REPO / "effort-mode" / "hooks" / "mergen_prompt_hook.py"
_COMMANDS_SRC = _REPO / "core" / "commands"

# Files install copies into ~/.claude/hooks (the two SDD hooks are copied there
# by build_native, the effort hook is copied by this CLI).
_SDD_HOOK_FILES = ("verify_gate.py", "constitution_inject.py")
_EFFORT_HOOK_FILE = "mergen_prompt_hook.py"
_ALL_HOOK_FILES = (*_SDD_HOOK_FILES, _EFFORT_HOOK_FILE)

_SKILL_PREFIX = "mergen"  # skill dirs are mergen-<name>


# --------------------------------------------------------------------------- #
# Path defaults
# --------------------------------------------------------------------------- #

def _claude_home() -> Path:
    return Path.home() / ".claude"


def expected_skill_names() -> list[str]:
    """Skill names the native renderer would produce, derived from core/commands."""
    return sorted(p.stem for p in _COMMANDS_SRC.glob("*.md"))


# --------------------------------------------------------------------------- #
# Subprocess helper
# --------------------------------------------------------------------------- #

def _run(script: Path, *args: str, dry_run: bool = False) -> int:
    """Run an in-repo python helper with the current interpreter."""
    cmd = [sys.executable, str(script), *args]
    if dry_run:
        print(f"[dry-run] would run: {' '.join(cmd)}")
        return 0
    proc = subprocess.run(cmd)
    return proc.returncode


# --------------------------------------------------------------------------- #
# Settings inspection (read-only, BOM tolerant)
# --------------------------------------------------------------------------- #

def _load_settings(settings_path: Path) -> dict[str, Any]:
    if not settings_path.is_file():
        return {}
    try:
        data = json.loads(settings_path.read_text(encoding="utf-8-sig"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _hook_registered(settings: dict[str, Any], basename: str) -> bool:
    hooks = settings.get("hooks")
    if not isinstance(hooks, dict):
        return False
    for entries in hooks.values():
        if not isinstance(entries, list):
            continue
        for entry in entries:
            for h in entry.get("hooks", []) if isinstance(entry, dict) else []:
                if basename in (h.get("command") or ""):
                    return True
    return False


# --------------------------------------------------------------------------- #
# doctor
# --------------------------------------------------------------------------- #

def doctor(
    skills_dir: Path,
    hooks_dir: Path,
    commands_dir: Path,
    settings_path: Path,
    schemas_dir: Path = _SCHEMAS_DIR,
) -> int:
    """Read-only health probe. Return 0 if the core install is intact, else 1."""
    ok = True
    print("mergen doctor")
    print("")

    # Python version. The repo floor is 3.9.
    v = sys.version_info
    py_ok = (v.major, v.minor) >= (3, 9)
    ok = ok and py_ok
    print(f"  [{'OK ' if py_ok else 'BAD'}] python {v.major}.{v.minor} "
          f"({'>= 3.9' if py_ok else 'mergen needs 3.9 or newer'})")

    # Skills.
    expected = expected_skill_names()
    present = [n for n in expected if (skills_dir / f"{_SKILL_PREFIX}-{n}" / "SKILL.md").is_file()]
    skills_ok = bool(expected) and len(present) == len(expected)
    ok = ok and skills_ok
    print(f"  [{'OK ' if skills_ok else 'BAD'}] skills {len(present)}/{len(expected)} "
          f"rendered under {skills_dir}")
    missing_skills = sorted(set(expected) - set(present))
    if missing_skills:
        print(f"        missing: {', '.join(missing_skills)}")

    # Hook files.
    for fname in _ALL_HOOK_FILES:
        here = (hooks_dir / fname).is_file()
        ok = ok and here
        print(f"  [{'OK ' if here else 'BAD'}] hook file {fname}")

    # Command.
    cmd_here = (commands_dir / "mergen.md").is_file()
    ok = ok and cmd_here
    print(f"  [{'OK ' if cmd_here else 'BAD'}] command mergen.md under {commands_dir}")

    # Shipped schema integrity. The JSON schemas mergen renders and verifies
    # against must be well-formed. doctor renders from this repo, so it checks the
    # source schemas, not an installed copy.
    schema_files = sorted(schemas_dir.glob("*.json"))
    bad_schemas = []
    for sf in schema_files:
        try:
            doc = json.loads(sf.read_text(encoding="utf-8-sig"))
            if not (isinstance(doc, dict) and ("$schema" in doc or "type" in doc)):
                bad_schemas.append(sf.name)
        except Exception:  # noqa: BLE001 - any unreadable or invalid schema counts as bad
            bad_schemas.append(sf.name)
    # A malformed schema is a failure. An empty schemas dir is not: the check asks
    # whether the schemas mergen ships are well-formed, which is vacuously true when
    # there are none to ship, so it must not false-degrade a partial or renamed tree.
    schemas_ok = not bad_schemas
    ok = ok and schemas_ok
    if schema_files:
        print(f"  [{'OK ' if schemas_ok else 'BAD'}] schemas {len(schema_files) - len(bad_schemas)}/"
              f"{len(schema_files)} valid under {schemas_dir}")
    else:
        print(f"  [OK ] schemas none found under {schemas_dir} (nothing to validate)")
    if bad_schemas:
        print(f"        invalid: {', '.join(bad_schemas)}")

    # Settings registrations.
    settings = _load_settings(settings_path)
    for fname in _ALL_HOOK_FILES:
        reg = _hook_registered(settings, fname)
        ok = ok and reg
        print(f"  [{'OK ' if reg else 'BAD'}] {fname} registered in settings.json")

    # Honest caveats (these are not failures, they are how mergen actually works).
    print("")
    print("  notes (by design, not faults):")
    print("    - max effort needs one manual paste of '/effort max' per session. A hook")
    print("      cannot set the live effort value, so install cannot do it for you.")
    print("    - the SDD hooks (verify_gate, constitution_inject) are reinforcement")
    print("      nudges injected via additionalContext. They do not block actions. The")
    print("      real enforcement is the implement pipeline's adversarial verify stage.")
    print("")
    print(f"  result: {'healthy' if ok else 'degraded, run: mergen install'}")
    return 0 if ok else 1


# --------------------------------------------------------------------------- #
# install / uninstall / upgrade
# --------------------------------------------------------------------------- #

def install(python_exe: str, dry_run: bool) -> int:
    """Render skills and register hooks into the real ~/.claude. Idempotent."""
    home = _claude_home()
    commands_dir = home / "commands"
    hooks_dir = home / "hooks"

    print("==> 1/4 effort command + hook")
    if dry_run:
        print(f"[dry-run] would copy {_EFFORT_CMD.name} -> {commands_dir / 'mergen.md'}")
        print(f"[dry-run] would copy {_EFFORT_HOOK.name} -> {hooks_dir / _EFFORT_HOOK_FILE}")
    else:
        commands_dir.mkdir(parents=True, exist_ok=True)
        hooks_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(_EFFORT_CMD, commands_dir / "mergen.md")
        shutil.copy2(_EFFORT_HOOK, hooks_dir / _EFFORT_HOOK_FILE)

    print("==> 2/4 register effort hook in settings.json")
    rc = _run(_EFFORT_PATCH, "--python", python_exe, dry_run=dry_run)
    if rc != 0:
        return rc

    print("==> 3/4 render the 14 SDD skills")
    rc = _run(_BUILD_NATIVE, "build", dry_run=dry_run)
    if rc != 0:
        return rc

    print("==> 4/4 register SDD hooks in settings.json")
    rc = _run(_PATCH_HOOKS, "--python", python_exe, dry_run=dry_run)
    if rc != 0:
        return rc

    print("")
    print("mergen installed. Restart Claude Code (or run /hooks) so the hooks load.")
    print("Arm max effort in a session with /mergen, then paste the printed /effort max.")
    return 0


def uninstall(dry_run: bool) -> int:
    """Remove every artifact install created from the real ~/.claude. Idempotent."""
    home = _claude_home()
    skills_dir = home / "skills"
    hooks_dir = home / "hooks"
    commands_dir = home / "commands"

    print("==> 1/4 unregister SDD hooks")
    _run(_PATCH_HOOKS, "--remove", dry_run=dry_run)
    print("==> 2/4 unregister effort hook")
    _run(_EFFORT_PATCH, "--remove", dry_run=dry_run)

    print("==> 3/4 delete rendered skills")
    for name in expected_skill_names():
        d = skills_dir / f"{_SKILL_PREFIX}-{name}"
        if dry_run:
            print(f"[dry-run] would remove {d}")
        elif d.is_dir():
            shutil.rmtree(d)

    print("==> 4/4 delete hook files, command, and marker")
    targets = [hooks_dir / f for f in _ALL_HOOK_FILES]
    targets += [commands_dir / "mergen.md", home / "mergen.json"]
    for t in targets:
        if dry_run:
            print(f"[dry-run] would remove {t}")
        elif t.exists():
            t.unlink()

    print("")
    print("mergen uninstalled. Restart Claude Code (or run /hooks) so the hooks drop.")
    return 0


def upgrade(python_exe: str, dry_run: bool) -> int:
    """Re-render skills from the current core/ and re-register hooks. Idempotent."""
    print("==> 1/2 re-render skills from current core/")
    rc = _run(_BUILD_NATIVE, "build", dry_run=dry_run)
    if rc != 0:
        return rc
    print("==> 2/2 re-register hooks (idempotent)")
    rc = _run(_PATCH_HOOKS, "--python", python_exe, dry_run=dry_run)
    if rc != 0:
        return rc
    print("")
    print("mergen upgraded. Restart Claude Code (or run /hooks) so reloaded hooks apply.")
    return 0


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mergen",
        description="Install, check, upgrade, or remove mergen for Claude Code.",
    )
    sub = parser.add_subparsers(dest="command")

    p_install = sub.add_parser("install", help="render skills and register hooks")
    p_install.add_argument("--python", default=sys.executable,
                           help="python executable the hooks should run (default: this one)")
    p_install.add_argument("--dry-run", action="store_true")

    p_doctor = sub.add_parser("doctor", help="read-only health probe")
    home = _claude_home()
    p_doctor.add_argument("--skills-dir", default=str(home / "skills"))
    p_doctor.add_argument("--hooks-dir", default=str(home / "hooks"))
    p_doctor.add_argument("--commands-dir", default=str(home / "commands"))
    p_doctor.add_argument("--settings", default=str(home / "settings.json"))
    p_doctor.add_argument("--schemas-dir", default=str(_SCHEMAS_DIR),
                          help="schemas to well-formedness check (default: this repo's core/schemas)")

    p_uninstall = sub.add_parser("uninstall", help="remove every installed artifact")
    p_uninstall.add_argument("--dry-run", action="store_true")

    p_upgrade = sub.add_parser("upgrade", help="re-render skills and re-register hooks")
    p_upgrade.add_argument("--python", default=sys.executable)
    p_upgrade.add_argument("--dry-run", action="store_true")

    # verify forwards everything after the verb to scripts/verify_core.py. It is
    # handled before argparse in main() so the forwarded flags are never parsed
    # here. This subparser exists so the verb shows in help.
    sub.add_parser(
        "verify",
        add_help=False,
        help="run the agent-agnostic verify harness (forwards to verify_core.py, "
             "try: mergen verify --help)",
    )

    # verify-lint forwards to the report linter the same way.
    sub.add_parser(
        "verify-lint",
        add_help=False,
        help="refuse a verification report that is not a clean, proven pass "
             "(forwards to verify_report_lint.py, try: mergen verify-lint --help)",
    )

    # dashboard, like verify, forwards everything after the verb to its script.
    sub.add_parser(
        "dashboard",
        add_help=False,
        help="render a static HTML dashboard over verification reports (forwards "
             "to dashboard.py, try: mergen dashboard --help)",
    )

    # status and issues forward to their scripts the same way.
    sub.add_parser(
        "status",
        add_help=False,
        help="summarize a tasks-state.json (forwards to tasks_status.py, try: "
             "mergen status --help)",
    )
    sub.add_parser(
        "issues",
        add_help=False,
        help="render GitHub issue stubs from a tasks.md (forwards to "
             "tasks_to_issues.py, try: mergen issues --help)",
    )
    sub.add_parser(
        "trends",
        add_help=False,
        help="cross-run trends, per-task and per-spec churn over one or more "
             "reports directories (forwards to trends.py, try: mergen trends --help)",
    )
    sub.add_parser(
        "graph",
        add_help=False,
        help="typed provenance graph over the ledger: ingest a report, walk a "
             "proof chain, audit lineage (forwards to trust_graph.py, try: mergen graph --help)",
    )
    sub.add_parser(
        "replay",
        add_help=False,
        help="record a verification run and replay it against the current tree, "
             "reporting match or divergence (forwards to replay.py, try: mergen replay --help)",
    )
    sub.add_parser(
        "impacted",
        add_help=False,
        help="continuous verification: re-verify only the tasks a change impacts and "
             "flag pass-to-fail regressions (forwards to impacted.py, try: mergen impacted --help)",
    )
    sub.add_parser(
        "pack",
        add_help=False,
        help="validate a domain policy pack: name matches directory, raise-only fields, "
             "single-line array (forwards to pack_validate.py, try: mergen pack --help)",
    )
    sub.add_parser(
        "calibrate",
        add_help=False,
        help="Adaptive Governor: compute review-scope thresholds from the governor history, "
             "bounded so adaptation cannot weaken the floor (forwards to governor_adaptive.py, "
             "try: mergen calibrate --help)",
    )
    sub.add_parser(
        "adapter",
        add_help=False,
        help="Adapter SDK: validate per-host capability manifests, print the capability matrix, "
             "or check a host capability (forwards to adapter_sdk.py, try: mergen adapter --help)",
    )
    sub.add_parser(
        "sign",
        add_help=False,
        help="bind or verify a pre-action authorization token over an artifact's bytes "
             "(forwards to preaction_sign.py, try: mergen sign --help)",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    raw = list(sys.argv[1:] if argv is None else argv)

    # verify forwards everything after the verb verbatim to the agent-agnostic
    # harness. Handle it before argparse so flags like --tasks-state are passed
    # through rather than parsed as mergen options.
    if raw and raw[0] == "verify":
        return _run(_VERIFY_CORE, *raw[1:])
    if raw and raw[0] == "verify-lint":
        return _run(_VERIFY_LINT, *raw[1:])
    if raw and raw[0] == "dashboard":
        return _run(_DASHBOARD, *raw[1:])
    if raw and raw[0] == "status":
        return _run(_STATUS, *raw[1:])
    if raw and raw[0] == "issues":
        return _run(_ISSUES, *raw[1:])
    if raw and raw[0] == "trends":
        return _run(_TRENDS, *raw[1:])
    if raw and raw[0] == "graph":
        return _run(_GRAPH, *raw[1:])
    if raw and raw[0] == "replay":
        return _run(_REPLAY, *raw[1:])
    if raw and raw[0] == "impacted":
        return _run(_IMPACTED, *raw[1:])
    if raw and raw[0] == "pack":
        return _run(_PACK, *raw[1:])
    if raw and raw[0] == "calibrate":
        return _run(_CALIBRATE, *raw[1:])
    if raw and raw[0] == "adapter":
        return _run(_ADAPTER, *raw[1:])
    if raw and raw[0] == "sign":
        return _run(_SIGN, *raw[1:])

    parser = build_parser()
    args = parser.parse_args(raw)

    if args.command == "install":
        return install(args.python, args.dry_run)
    if args.command == "doctor":
        return doctor(
            Path(args.skills_dir),
            Path(args.hooks_dir),
            Path(args.commands_dir),
            Path(args.settings),
            Path(args.schemas_dir),
        )
    if args.command == "uninstall":
        return uninstall(args.dry_run)
    if args.command == "upgrade":
        return upgrade(args.python, args.dry_run)

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
