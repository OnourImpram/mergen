# Roadmap

This document records what shipped in v1.0.0, where the boundaries of that release are, and what is planned next. It is written to be honest rather than promotional.

---

## 1. Shipped in v1.0.0

### Effort mode (half A)

The effort-mode layer reconstructs "max reasoning effort plus standing Workflow orchestration." It consists of:

- **`effort-mode/commands/mergen.md`** is the `/mergen` command. It arms or disarms the mode and prints the `/effort max` line for the user to paste once. The arm/disarm toggle writes a marker to `~/.claude/mergen.json`.
- **`effort-mode/hooks/mergen_prompt_hook.py`** is a `UserPromptSubmit` hook that injects the standing Workflow-orchestration directive on every turn while the mode is armed. The hook is fail-soft. It exits `0` and no-ops when the marker is absent or unreadable.
- **`effort-mode/scripts/patch_settings.py`** is an idempotent, corruption-safe patcher for `settings.json`. It supports `--status`, `--remove`, and `--python` flags.
- **`effort-mode/install.sh`** and **`effort-mode/install.ps1`** are cross-platform install scripts.
- **`docs/HOW-IT-WORKS.md`** is a write-up of the mechanism, including the honest note that `/effort max` requires one manual paste by the user. A hook cannot flip the live effort value. The user performs that step once per session.

### SDD layer, single-source core (half B)

Eleven command files in `core/commands/`, each defining a named Workflow-tool pattern:

| File | Pattern summary |
|---|---|
| `constitution.md` | Author or update the project constitution and keep dependent templates in sync. |
| `specify.md` | Judge-panel: N spec drafts, adversarial reviewer, synthesized output. |
| `clarify.md` | Targeted question loop, maximum 5 questions. |
| `checklist.md` | Requirements-quality checklist (unit tests for requirements). |
| `plan.md` | Multi-approach generation plus a refute-biased architecture critic. |
| `tasks.md` | Loop-until-dry completeness critic. Emits `tasks-dag.json` with wave id, file list, parallel flag, dependency links, and test-task marker. |
| `analyze.md` | Parallel cross-artifact consistency checkers with deduplication. |
| `implement.md` | Wave-parallel pipeline: isolated max-effort implementer per task, then a separate-context refute-biased verifier that checks filesystem and tests before marking `[X]`. Re-queues on failure. Non-bypassable final verify gate. |
| `verify.md` | Parallel multi-lens check (file-exists, spec-match, tests-pass, git-consistent). Majority-or-FAIL result. Reverts unverified `[X]` markers to `[ ]`. |
| `rollup.md` | Synthesis of all feature specs into canonical `.specify/memory/project-state.md`. |
| `go.md` | Complexity router that directs a request to the appropriate SDD tier. |

Seven template files in `core/templates/`:

- `spec-template.md`, `plan-template.md`, `tasks-template.md`, `checklist-template.md`, `constitution-template.md` are vendored from the Spec Kit project (MIT, attributed in `ATTRIBUTION.md` and `NOTICE`).
- `verification-template.md` and `project-state-template.md` are mergen additions.

Vendored MIT helper scripts from Spec Kit in `core/scripts/`:
`bash/`: `check-prerequisites.sh`, `common.sh`, `create-new-feature.sh`, `setup-plan.sh`, `setup-tasks.sh`.
`powershell/`: the same five scripts as `.ps1` files.

Two hooks in `core/hooks/`:

- **`verify_gate.py`** (`PostToolUse` on `Write`, `Edit`, `MultiEdit`): when `tasks.md` gains an `[X]` entry, it injects an `additionalContext` reminder to run `/mergen.verify`. Fail-soft. Exits `0` when not applicable.
- **`constitution_inject.py`** (`UserPromptSubmit`): injects the section headings of `.specify/memory/constitution.md` at the start of each prompt. Fail-soft. Exits `0` when the file is absent.

Both hooks are reinforcement nudges, not enforcement mechanisms. The real enforcement is the `/implement` pipeline's adversarial verify stage, which runs in a separate context and refuses to mark `[X]` until filesystem and tests confirm the task.

`core/CONVENTIONS.md` documents the single-source / two-renderer contract.

### Native renderer

**`dist/native/build_native.py`** with two subcommands:

- `build` renders each `core/commands/<name>.md` to `~/.claude/skills/mergen-<name>/SKILL.md`. It adds frontmatter (`name: mergen.<name>`, `user-invocable: true`, `disable-model-invocation: false`) and prefixes the vendored scripts path to `.specify/scripts/`. Skills are invoked in Claude Code as `/mergen.<name>`. Supports `--skills-dir` and `--dry-run`.
- `init [project]` bootstraps `<project>/.specify/` (copies scripts and templates, creates `memory/`). Supports `--dry-run`.

Built on the Python standard library only.

**`dist/native/patch_settings_hooks.py`** is an idempotent, corruption-safe register, remove, and status tool for the two SDD hooks in `settings.json`. It maps `verify_gate` to a `PostToolUse` matcher on `Write|Edit|MultiEdit` and `constitution_inject` to `UserPromptSubmit`. It matches by hook basename so re-installation does not duplicate entries. It preserves all unrelated settings. Supports `--python`, `--remove`, `--status`, `--settings`, and `--dry-run`.

### Spec-kit renderer (preset and extension)

**`dist/speckit/build_speckit.py`** renders the same `core/commands/` source into spec-kit-compatible artifacts committed under `dist/speckit/`. Supports `--out` and `--dry-run`.

**Preset** (`dist/speckit/preset/mergen/`, declared in `preset.yml`):
Overrides 8 stock Spec Kit commands via `provides.templates` entries of type `command` with `replaces`:
`speckit.constitution`, `speckit.specify`, `speckit.clarify`, `speckit.checklist`, `speckit.plan`, `speckit.tasks`, `speckit.analyze`, `speckit.implement`.

**Extension** (`dist/speckit/extensions/mergen/`, declared in `extension.yml`):
Adds 3 new commands not present in stock Spec Kit:
`speckit.mergen.verify`, `speckit.mergen.rollup`, `speckit.mergen.go`.
Wires `hooks.after_implement -> speckit.mergen.verify` with `optional: false`, making this a non-bypassable gate in the Spec Kit flow.

---

## 1.1. Shipped in v1.1.0 (minimalism layer)

v1.1.0 adds a minimalism discipline so that max effort does not become over-building. It is derived from `DietrichGebert/ponytail` (MIT, attributed in `ATTRIBUTION.md` and `NOTICE`). The thesis: think exhaustively, build minimally, verify it works and that it is minimal.

- **`core/lazy-ladder.md`** is the single-source discipline: the YAGNI ladder (needed at all, then stdlib, then a native platform feature, then an installed dependency, then one line, then the minimum that works), the "never lazy about" guards (validation, security, accessibility, error handling, tests), and the `mergen:` deferred-shortcut comment convention.
- **`/mergen.lean`** (`core/commands/lean.md`) is an over-engineering review: parallel per-file reviewers against the ladder, deduplicated into a ranked delete-list tagged `delete`/`stdlib`/`native`/`yagni`/`shrink`. Complexity only, never correctness. It lists cuts and never applies them.
- **`/mergen.debt`** (`core/commands/debt.md`) harvests `mergen:` comments into a risk-banded ledger at `.specify/memory/debt.md`. Gate mode fails on any shortcut with no named ceiling and upgrade path.
- **`core/commands/implement.md`** Stage A now builds each task to the ladder, and Stage B rejects a task that is correct but over-built. **`core/commands/plan.md`** prefers stdlib, native, and installed dependencies over new abstractions in its Lean lens. The effort-mode standing directive adds: reason exhaustively, build the minimum that works, never cut validation, security, or accessibility.
- **`dist/agents/build_agents.py`** renders `core/lazy-ladder.md` into passive rule files for non-Claude agents (`AGENTS.md`, `.cursor/rules/`, `.windsurf/rules/`, `.clinerules/`, `.github/copilot-instructions.md`, `.kiro/steering/`). It ports the discipline only, not the SDD engine.
- **`scripts/check_sync.py`** is a single-source drift gate (modeled on ponytail's `check-rule-copies.js`): it re-renders `dist/speckit/` from `core/` and fails if the committed output is stale, and it asserts the cross-agent render embeds the canonical ladder. Wired into CI.
- **`eval/`** gains Metric 4 (over-build rate, the only metric that measures the minimalism layer) and an isolation discipline adapted from ponytail's agentic benchmark harness (headless `claude -p`, `--setting-sources project,local`, one `--plugin-dir` per arm, same agent with the harness disabled as the baseline, median of at least four trials). No numbers are claimed.
- The spec-kit preset and extension are bumped to `1.1.0` and now ship five extension commands (`verify`, `rollup`, `go`, `lean`, `debt`).

---

## 2. Known limits of v1

**Spec-kit renderer is preset plus extension, not full feature parity.**
The spec-kit half (B) ships a preset that replaces 8 commands and an extension that adds 5 commands. Any Spec Kit behavior outside those 13 command surfaces, such as its interactive CLI scaffolding or its own project-bootstrap scripts, is not modified or replicated by this release.

**`/effort max` requires a manual paste.**
The `mergen_prompt_hook.py` hook injects a standing orchestration directive on each turn, but it cannot flip Claude Code's live effort value to `max`. The user must paste the `/effort max` line once after arming the mode. This is documented in `docs/HOW-IT-WORKS.md`.

**Hooks are reinforcement nudges, not enforcement.**
`verify_gate.py` reminds the user to run `/mergen.verify` when `[X]` is written, and `constitution_inject.py` surfaces constitution headings at prompt time. Neither hook can prevent Claude Code from proceeding. Enforcement lives in the `/implement` pipeline's adversarial verify stage: a separate-context verifier checks the filesystem and tests and re-queues any task it cannot confirm.

**Eval has methodology and a reproduce procedure, not yet measured numbers.**
The `eval/` directory defines the evaluation methodology and how to run it. No measured benchmark numbers have been published yet. Any figures shown in supporting documents that are labeled SYNTHETIC or ILLUSTRATIVE are not real measurements and must not be cited as such.

**Templates `verification-template.md` and `project-state-template.md` are self-described by their commands.**
The `/verify` and `/rollup` commands reference these templates and explain their structure. The `build_native.py init` subcommand copies templates into a bootstrapped `.specify/` directory, so a project initialized with `init` will have them present. A project that adopts the spec-kit preset and extension but does not run `init` must copy or create these templates separately, as the spec-kit preset mechanism does not include an `init` equivalent.

---

## 3. Planned next

**Real eval runs with published numbers.**
Execute the methodology in `eval/` against representative codebases, record results (phantom-completion rate, wave-parallel speedup, verification catch rate, and over-build rate), and publish them with reproducible scripts and the exact model versions used.

**Broader spec-kit command coverage.**
The v1 preset covers the 8 core workflow commands. Remaining Spec Kit command surfaces and any new commands Spec Kit ships after this release are candidates for inclusion in a future preset version.

**Additional Workflow patterns.**
The 13 commands in v1.1.0 cover the primary SDD lifecycle. Patterns for common adjacent tasks (incremental re-specification, cross-project dependency tracking, change-impact analysis) are candidates for new commands in a future minor release.

**CI for the SDD layer.**
Partly shipped in v1.1.0: `scripts/check_sync.py` runs in CI and fails when `dist/speckit/` drifts from `core/`, and v1.1.0 adds render tests for the native and spec-kit shells. Remaining: run `build_native.py build` and `build_native.py init` against a fixture project end to end, verify the rendered skill files on disk, and confirm `patch_settings_hooks.py` round-trips cleanly.

**MCP surface (deferred, with reason).**
An MCP server exposing the minimalism discipline to non-Claude hosts was scoped for v1.1.0 and deliberately deferred. The cross-agent renderer (`dist/agents/build_agents.py`) already delivers the discipline to non-Claude agents through the passive rule files those agents read, so an MCP `lazy_ladder` tool would be redundant. A `lean_review` MCP tool cannot faithfully reproduce the Workflow-orchestrated fan-out that makes `/mergen.lean` more than a single-shot review, so shipping it would over-claim. It will be reconsidered only if a concrete non-Claude MCP host needs it and a faithful design exists. Honesty over surface area.

**Spec-kit extension: `init` equivalent.**
A mechanism to bootstrap the `.specify/templates/` directory (including the two mergen-addition templates) into a project that adopts the spec-kit preset, so no manual copy step is required.

---

## Legal notes

Claude Code and Claude are trademarks of Anthropic. Spec Kit is a project of GitHub, Inc., licensed MIT. This project is not affiliated with Anthropic or GitHub. Vendored Spec Kit material is attributed in `ATTRIBUTION.md` and `NOTICE` at the repository root. This project is licensed Apache-2.0.
