# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/), and the project aims to follow
[Semantic Versioning](https://semver.org/).

## [1.1.0] - 2026-06-19

### Added

- Minimalism discipline (the "lazy ladder"), derived from `DietrichGebert/ponytail`
  (MIT, attributed in `ATTRIBUTION.md`). mergen reasons exhaustively and builds
  the minimum that works, never cutting validation, security, or accessibility.
  The thesis: think exhaustively, build minimally, verify it works and that it is
  minimal.
  - `core/lazy-ladder.md`: the canonical ladder, "not lazy about" guards, and the
    `mergen:` deferred-shortcut comment convention.
  - `/mergen.lean` (`core/commands/lean.md`): an over-engineering review that
    returns a tagged delete-list (delete/stdlib/native/yagni/shrink) for the diff
    or whole repo, with lite/full/ultra intensity. Complexity only, never
    correctness. Renders to native and to the spec-kit extension
    (`speckit.mergen.lean`).
  - `/mergen.debt` (`core/commands/debt.md`): harvests `mergen:` comments
    into a risk-banded ledger at `.specify/memory/debt.md`. Gate mode fails on any
    shortcut with no named ceiling and upgrade path. Renders to native and to the
    spec-kit extension (`speckit.mergen.debt`).
  - `/mergen.implement` now builds each task to the ladder (Stage A) and its
    adversarial verifier requires the change to be minimal as well as correct
    (Stage B), flagging over-build with the same taxonomy.
  - `/mergen.plan` prefers stdlib, native features, and installed dependencies
    over new abstractions in its Lean lens.
  - The effort-mode standing directive now states: reason exhaustively, build
    minimally, never cut validation, security, or accessibility.
- `dist/agents/build_agents.py`: renders `core/lazy-ladder.md` into passive rule
  files for non-Claude agents (`AGENTS.md`, `.cursor/rules/`, `.windsurf/rules/`,
  `.clinerules/`, `.github/copilot-instructions.md`, `.kiro/steering/`). It ports
  the discipline only, not the SDD engine.
- `scripts/check_sync.py`: single-source drift gate (modeled on ponytail's
  `check-rule-copies.js`). Re-renders `dist/speckit/` from `core/` and fails on a
  stale committed output, and asserts the cross-agent render embeds the canonical
  ladder. Wired into CI.
- `eval/` gains Metric 4 (over-build rate, the only metric that measures the
  minimalism layer) and an isolation discipline adapted from ponytail's
  agentic benchmark harness (headless `claude -p`, `--setting-sources project,local`,
  one `--plugin-dir` per arm, same agent with the harness disabled as the baseline,
  median of at least four trials). No numbers are claimed.

### Changed

- The spec-kit preset and extension are bumped to `1.1.0`. The extension now ships
  five commands (`verify`, `rollup`, `go`, `lean`, `debt`).

### Deferred to a later release

- An MCP surface for non-Claude hosts. The cross-agent renderer already delivers
  the discipline through the passive rule files those hosts read, so a `lazy_ladder`
  MCP tool would be redundant, and a `lean_review` MCP tool cannot faithfully
  reproduce the Workflow-orchestrated fan-out. Deferring it avoids over-claiming.
  See `docs/ROADMAP.md`.

## [1.0.1] - 2026-06-14

### Changed

- Mergen activation is now session-scoped and explicit. Previously the
  armed marker was user-global and persisted across every session and project
  until `/mergen off`, so arming it once left the standing directive active
  everywhere, including sessions where the user only wanted `/effort max`. Now
  the marker binds to the session where `/mergen` was run (on its first
  prompt) and the directive injects only in that session. A new session starts
  clean until `/mergen` is run again.
- Removed the keyword auto-trigger. A prompt containing the word `mergen` no
  longer activates the mode. Only the explicit `/mergen` command does.

### Fixed

- `/effort max` no longer appeared to carry the mergen directive. The
  directive was never coupled to the effort level. It was the persistent
  user-global marker that kept the mode on across sessions. Session scoping
  removes that surprise.

### Notes

- The hook (`effort-mode/hooks/mergen_prompt_hook.py`) now reads `session_id`
  from the `UserPromptSubmit` payload and binds the marker on first sight.
  Updated the hook unit tests accordingly (18 pass).

## [1.0.0] - 2026-06-13

This release turns mergen from an effort mode into an effort mode plus a
verified, parallel spec-driven-development layer that is a superset of GitHub
Spec Kit. The effort mode (the `/mergen` command and `UserPromptSubmit`
directive from 0.1.0 and 0.2.0) is preserved and now lives under `effort-mode/`.

### Added

- SDD command suite, authored once in `core/commands/` (11 commands):
  `constitution`, `specify`, `clarify`, `checklist`, `plan`, `tasks`,
  `analyze`, `implement`, `verify`, `rollup`, `go`. Each command is a named
  Workflow-tool pattern (judge-panel, multi-approach plus architecture critic,
  loop-until-dry plus dependency DAG, wave-parallel verified pipeline, parallel
  multi-lens verification, and so on) rather than a single-context monologue.
- Single source, two renderers (`core/CONVENTIONS.md`):
  - Native renderer `dist/native/build_native.py`. `build` renders each command
    into `~/.claude/skills/mergen-<name>/SKILL.md` (invoked as
    `/mergen.<name>`) and prefixes the bare `scripts/` frontmatter to
    `.specify/scripts/`. `init` bootstraps a project's `.specify/` directory.
  - spec-kit renderer `dist/speckit/build_speckit.py`. Emits a Spec Kit preset
    `mergen` that overrides 8 stock commands, and an extension `mergen`
    that adds `verify`, `rollup`, and `go` plus a non-bypassable
    `after_implement` verify gate.
- Reinforcement hooks in `core/hooks/`: `verify_gate.py` (PostToolUse, reminds
  to verify when `tasks.md` gains an `[X]`) and `constitution_inject.py`
  (UserPromptSubmit, re-surfaces the project constitution). Both are fail-soft.
  They reinforce the discipline. The real enforcement is the `implement`
  pipeline's adversarial verify stage.
- `dist/native/patch_settings_hooks.py`: idempotent, corruption-safe registrar
  for the two SDD hooks in `settings.json`, with `--remove`, `--status`,
  `--settings`, and `--dry-run`.
- Vendored Spec Kit templates and scripts (MIT) under `core/templates/` and
  `core/scripts/`, attributed in `ATTRIBUTION.md`, plus the mergen-only
  `verification-template.md` and `project-state-template.md`.

## [0.2.0] - 2026-06-13

### Added

- `/mergen status` sub-command: reports whether the mode is armed, the
  `started_at` timestamp, and whether a custom directive is active. No
  file writes required to check mode state.
- Custom directive support: `~/.claude/mergen.json` now accepts an optional
  `"directive"` key. When present, the hook uses that string instead of the
  built-in constant. Customisation survives reinstalls because the installer
  overwrites the hook file but not the marker.
- `patch_settings.py --status` flag: read-only check that exits 0 if the
  mergen hook entry is registered in `settings.json`, 1 if not.
- `install.sh --check` / `install.ps1 -Check`: verifies all three installed
  artefacts (command file, hook file, `settings.json` entry) without
  modifying anything. Useful for post-install verification and after Claude
  Code upgrades.
- Unit test suite (`tests/`): 16 tests covering the hook (8 cases) and the
  settings patcher (8 cases). Uses `tmp_path` + `Path.home()` monkeypatching
  so the real `~/.claude` is never touched. Run with `python -m pytest tests/`.
- `pyproject.toml`: minimal pytest configuration pointing at `tests/`.
- `.github/workflows/ci.yml`: CI matrix running the test suite on
  ubuntu-latest for Python 3.9, 3.11, and 3.12 on every push and PR to main.
- `CONTRIBUTING.md`: development setup, test instructions, CI badge, and PR
  requirements.

## [0.1.0] - 2026-06-13

### Added

- `/mergen` slash command that arms and disarms the mode and prints the
  `/effort max` line to paste.
- `UserPromptSubmit` hook (`mergen_prompt_hook.py`) that injects the
  standing max-reasoning plus dynamic-workflow-orchestration directive every
  turn while armed, with a single-turn keyword opt-in. Fail-soft, no-op when
  disarmed.
- `scripts/patch_settings.py`, an idempotent and corruption-safe
  `settings.json` patcher used for both install and uninstall.
- `install.sh` and `install.ps1` cross-platform installers with an uninstall
  path.
- `docs/HOW-IT-WORKS.md` documenting the native effort coupling and the
  two-halves design.
