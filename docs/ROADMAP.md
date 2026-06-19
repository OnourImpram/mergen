# Roadmap

This document records what shipped in v1.0.0, where the boundaries of that release are, and what is planned next. It is written to be honest rather than promotional.

---

## 1. Shipped in v1.0.0

### Effort mode (half A)

The effort-mode layer reconstructs "max reasoning effort plus standing Workflow orchestration." It consists of:

- **`effort-mode/commands/mergen.md`** is the `/mergen` command. It arms or disarms the mode and prints the `/effort max` line for the user to paste once. The arm/disarm toggle writes a marker to `~/.claude/mergen.json`.
- **`effort-mode/hooks/mergen_prompt_hook.py`** is a `UserPromptSubmit` hook that injects the standing Workflow-orchestration directive on every turn while the mode is armed. The hook is fail-soft. It exits `0` and no-ops when the marker is absent or unreadable.
- **`effort-mode/scripts/patch_settings.py`** is an idempotent, corruption-safe patcher for `settings.json`. It supports `--status`, `--remove`, and `--python` flags. The patcher is BOM-safe and preserves all unrelated settings.
- **`effort-mode/install.sh`** and **`effort-mode/install.ps1`** are cross-platform install scripts. `install.sh` uses `bash` as its interpreter (not `sh`) so process substitution and other bash features are available. Both scripts carry correct executable bits.
- **`docs/HOW-IT-WORKS.md`** is a write-up of the mechanism, including the honest note that `/effort max` requires one manual paste by the user. A hook cannot flip the live effort value. The user performs that step once per session.

### SDD layer, single-source core (half B)

Fourteen command files in `core/commands/`, each defining a named Workflow-tool pattern:

| File | Pattern summary |
|---|---|
| `constitution.md` | Author or update the project constitution and keep dependent templates in sync. |
| `specify.md` | Judge-panel: N spec drafts, adversarial reviewer, synthesized output. |
| `clarify.md` | Targeted question loop, maximum 5 questions. |
| `checklist.md` | Requirements-quality checklist (unit tests for requirements). |
| `plan.md` | Multi-approach generation plus a refute-biased architecture critic. |
| `tasks.md` | Loop-until-dry completeness critic. Emits `tasks-dag.json` with wave id, file list, parallel flag, dependency links, and test-task marker. |
| `analyze.md` | Parallel cross-artifact consistency checkers with deduplication. |
| `implement.md` | Wave-parallel pipeline: isolated max-effort implementer per task, then a separate-context refute-biased verifier that checks filesystem and tests before marking `[X]`. Re-queues on failure. A final verify gate the pipeline will not skip, scoped honestly in section 2. |
| `verify.md` | Parallel multi-lens check (file-exists, spec-match, tests-pass, git-consistent). Majority-or-FAIL result. Reverts unverified `[X]` markers to `[ ]`. Emits `verification-report.json` and `tasks-state.json` (schemas in `core/schemas/`), each task carrying a confidence label. |
| `rollup.md` | Synthesis of all feature specs into canonical `.specify/memory/project-state.md`. |
| `go.md` | Complexity router that directs a request to the appropriate SDD tier. |
| `lean.md` | Over-engineering review: parallel per-file reviewers against the lazy ladder, deduplicated ranked delete-list. Complexity only, never correctness. |
| `debt.md` | Harvests `mergen:` deferred-shortcut comments into a risk-banded ledger. Gate mode fails on unceiled shortcuts. |
| `govern.md` | The Governor. Classifies a task into tiny, standard, spec, or high-trust and sets memory scope, workflow depth, evidence standard, and human-approval threshold. Deterministic high-trust floor: can be raised by explicit configuration, never silently lowered. The wisdom organ that precedes routing. `/mergen.go` executes the chosen tier. |

Seven template files in `core/templates/`:

- `spec-template.md`, `plan-template.md`, `tasks-template.md`, `checklist-template.md`, `constitution-template.md` are vendored from the Spec Kit project (MIT, attributed in `ATTRIBUTION.md` and `NOTICE`).
- `verification-template.md` and `project-state-template.md` are mergen additions.

Vendored MIT helper scripts from Spec Kit in `core/scripts/`:
`bash/`: `check-prerequisites.sh`, `common.sh`, `create-new-feature.sh`, `setup-plan.sh`, `setup-tasks.sh`.
`powershell/`: the same five scripts as `.ps1` files.

Two hooks in `core/hooks/`:

- **`verify_gate.py`** (`PostToolUse` on `Write`, `Edit`, `MultiEdit`): when `tasks.md` gains an `[X]` entry, it injects an `additionalContext` reminder to run `/mergen.verify`. Fail-soft. Exits `0` when not applicable.
- **`constitution_inject.py`** (`UserPromptSubmit`): injects the section headings of `.specify/memory/constitution.md` at the start of each prompt. Fail-soft. Exits `0` when the file is absent.

Both hooks are reinforcement nudges, not enforcement mechanisms. A prompt protocol asks, a hook nudges, a CI gate refuses. The non-bypassable guarantee is scoped to the spec-kit `after_implement` hook contract plus CI, not an absolute in-session lock. The real in-pipeline enforcement is the `/implement` pipeline's adversarial verify stage, which runs in a separate context and refuses to mark `[X]` until filesystem and tests confirm the task.

`core/CONVENTIONS.md` documents the single-source / two-renderer contract.

### Machine-readable verify output

`/mergen.verify` emits two machine-readable files alongside the human-readable `verification-report.md`:

- **`verification-report.json`**: the full per-task verdict with evidence arrays and failure lists.
- **`tasks-state.json`**: a compact per-task state record, each entry carrying a `confidence` label (`high`, `medium`, `low`, `unverified`).

Schemas for both files live in `core/schemas/`. The JSON output is the input consumed by `eval/evidence_metric.py`.

### The Governor (`/mergen.govern`)

The Governor classifies an incoming task into one of four tiers (tiny, standard, spec, high-trust) and sets memory scope, workflow depth, evidence standard, and human-approval threshold for that tier. A deterministic high-trust floor is always enforced: it can be raised by explicit configuration but is never silently lowered. The Governor is the wisdom organ of the command suite. The `/mergen.go` complexity router then executes the chosen tier.

### Eval evidence metric

`eval/evidence_metric.py` is a minimal honest metric derived from the verify JSON: it reports work-done rate (fraction of tasks with verifier-confirmed evidence) and phantom-completion count (tasks marked `[X]` with no backing artifact). The metric abstains on minimal-change runs that have no lean data rather than reporting a misleading zero. The full benchmark suite stays on the roadmap.

### Verify-gate (CI for your own project)

`eval/evidence_metric.py --gate` exits non-zero when a committed `verification-report.json` shows phantom or unverified work. `eval/ci/verify-gate.yml` is a drop-in GitHub Actions workflow that runs it, documented in `eval/ci/README.md`. This is the layer that refuses for a user project, the one that can block a merge. It reads the committed artifact, so a hand-edited report can still pass, and the deepest guarantee rests on the separate-context verifier that produced the report. Mergen's own CI continues to guard this repository (tests, the drift gate, the no-reference-text gate). It does not run verify against a downstream project, which is exactly what the drop-in gate is for.

### Mneme seam

Mergen is the execution layer and pairs with mneme (the memory layer) across one seam. Mergen stores no memory of its own. `docs/MNEME-SEAM.md` documents the seam contract. `scripts/mneme_emit.py` is the emit hook that writes structured events across the seam. The full mneme writeback adapter is deferred.

### Native renderer

**`dist/native/build_native.py`** with two subcommands:

- `build` renders each `core/commands/<name>.md` to `~/.claude/skills/mergen-<name>/SKILL.md`. It adds frontmatter (`name: mergen.<name>`, `user-invocable: true`, `disable-model-invocation: false`) and prefixes the vendored scripts path to `.specify/scripts/`. Skills are invoked in Claude Code as `/mergen.<name>`. Supports `--skills-dir` and `--dry-run`.
- `init [project]` bootstraps `<project>/.specify/` (copies scripts and templates, creates `memory/`). Supports `--dry-run`.

Built on the Python standard library only.

**`dist/native/patch_settings_hooks.py`** is an idempotent, corruption-safe register, remove, and status tool for the two SDD hooks in `settings.json`. It maps `verify_gate` to a `PostToolUse` matcher on `Write|Edit|MultiEdit` and `constitution_inject` to `UserPromptSubmit`. It matches by hook basename so re-installation does not duplicate entries. It preserves all unrelated settings. Supports `--python`, `--remove`, `--status`, `--settings`, and `--dry-run`. The patcher is BOM-safe.

### Spec-kit renderer (preset and extension)

**`dist/speckit/build_speckit.py`** renders the same `core/commands/` source into spec-kit-compatible artifacts committed under `dist/speckit/`. Supports `--out` and `--dry-run`.

**Preset** (`dist/speckit/preset/mergen/`, declared in `preset.yml`):
Overrides 8 stock Spec Kit commands via `provides.templates` entries of type `command` with `replaces`:
`speckit.constitution`, `speckit.specify`, `speckit.clarify`, `speckit.checklist`, `speckit.plan`, `speckit.tasks`, `speckit.analyze`, `speckit.implement`.

**Extension** (`dist/speckit/extensions/mergen/`, declared in `extension.yml`):
Adds 6 new commands not present in stock Spec Kit:
`speckit.mergen.verify`, `speckit.mergen.rollup`, `speckit.mergen.go`, `speckit.mergen.lean`, `speckit.mergen.debt`, `speckit.mergen.govern`.
Wires `hooks.after_implement -> speckit.mergen.verify` with `optional: false`, making verify mandatory in the Spec Kit implement flow. This is the hook contract, reinforced by the drop-in CI verify-gate, not an absolute in-session lock.

### Cross-agent renderer

**`dist/agents/build_agents.py`** renders `core/lazy-ladder.md` into passive rule files for non-Claude agents (`AGENTS.md`, `.cursor/rules/`, `.windsurf/rules/`, `.clinerules/`, `.github/copilot-instructions.md`, `.kiro/steering/`). It ports the minimalism discipline only, not the SDD engine.

### Drift gate and sync check

**`scripts/check_sync.py`** is a single-source drift gate (modeled on ponytail's `check-rule-copies.js`): it re-renders `dist/speckit/` from `core/` and fails if the committed output is stale, and it asserts the cross-agent render embeds the canonical ladder. Wired into CI.

### Inherited-defect fixes

- `install.sh` uses `bash` as its shebang interpreter. The prior `sh` shebang caused failures on systems where `sh` does not support bash constructs.
- Executable bits are set correctly on all installer scripts.
- Both settings patchers (`effort-mode/scripts/patch_settings.py` and `dist/native/patch_settings_hooks.py`) are BOM-safe: they strip a UTF-8 BOM before parsing and write without BOM.
- The "non-bypassable" language in prior documentation has been corrected. The non-bypassable guarantee is honestly scoped to the spec-kit `after_implement` hook contract plus CI, not an absolute in-session lock. A prompt protocol asks, a hook nudges, a CI gate refuses.

### Promo website

A static promo site for Mergen and the Agent Continuity Stack is published at https://thegoatpsy.github.io/mergen/ . It is served from the `gh-pages` branch, kept separate from the engine source on `main`. It presents the identity, the Governor, the verify gate, and the honest enforcement distinction, and it claims no benchmark numbers. The repository itself stays private for now.

---

## 2. Known limits of v1.0.0

**Spec-kit renderer is preset plus extension, not full feature parity.**
The spec-kit half ships a preset that replaces 8 commands and an extension that adds 6 commands. Any Spec Kit behavior outside those 14 command surfaces, such as its interactive CLI scaffolding or its own project-bootstrap scripts, is not modified or replicated by this release.

**`/effort max` requires a manual paste.**
The `mergen_prompt_hook.py` hook injects a standing orchestration directive on each turn, but it cannot flip Claude Code's live effort value to `max`. The user must paste the `/effort max` line once after arming the mode. This is documented in `docs/HOW-IT-WORKS.md`.

**Hooks are reinforcement nudges, not enforcement.**
`verify_gate.py` reminds the user to run `/mergen.verify` when `[X]` is written, and `constitution_inject.py` surfaces constitution headings at prompt time. Neither hook can prevent Claude Code from proceeding. Enforcement lives in the `/implement` pipeline's adversarial verify stage: a separate-context verifier checks the filesystem and tests and re-queues any task it cannot confirm.

**Eval has methodology and a reproduce procedure, not yet measured numbers.**
The `eval/` directory defines the evaluation methodology and how to run it. `eval/evidence_metric.py` provides a minimal honest metric derived from the verify JSON. No full benchmark numbers have been published yet. Any figures shown in supporting documents that are labeled SYNTHETIC or ILLUSTRATIVE are not real measurements and must not be cited as such.

**Templates `verification-template.md` and `project-state-template.md` are self-described by their commands.**
The `/verify` and `/rollup` commands reference these templates and explain their structure. The `build_native.py init` subcommand copies templates into a bootstrapped `.specify/` directory, so a project initialized with `init` will have them present. A project that adopts the spec-kit preset and extension but does not run `init` must copy or create these templates separately, as the spec-kit preset mechanism does not include an `init` equivalent.

**Mneme writeback adapter is a stub.**
`scripts/mneme_emit.py` and `docs/MNEME-SEAM.md` establish the seam contract and emit structured events. The full writeback adapter that persists those events into a mneme memory store is deferred.

---

## 3. Planned next

**Real eval runs with published numbers.**
Execute the methodology in `eval/` against representative codebases, record results (phantom-completion rate, wave-parallel speedup, verification catch rate, and over-build rate), and publish them with reproducible scripts and the exact model versions used.

**GitHub Action and PR comment bot.**
A CI action that runs `scripts/check_sync.py` and posts a summary comment on pull requests, showing drift status and a diff of any stale rendered output.

**Clinical and security domain packs.**
Preset overlays that add domain-specific constitution clauses, checklist items, and evidence standards for clinical and security contexts.

**Dashboard.**
A local web view over `verification-report.json` and `tasks-state.json` that shows task confidence, phantom-completion history, and over-build trends across runs.

**Churn analytics.**
Track which tasks are most frequently re-queued or reverted across eval runs to identify spec patterns that reliably produce verifier failures.

**Full benchmark suite.**
Extend `eval/evidence_metric.py` into the complete four-metric benchmark with published reproducible results.

**Full mneme writeback adapter.**
A complete adapter that persists structured events from `scripts/mneme_emit.py` into a mneme memory store so that cross-session context is available without manual rollup.

**Broader spec-kit command coverage.**
The v1.0.0 preset covers the 8 core workflow commands. Remaining Spec Kit command surfaces and any new commands Spec Kit ships after this release are candidates for inclusion in a future preset version.

**Additional Workflow patterns.**
The 14 commands in v1.0.0 cover the primary SDD lifecycle. Patterns for common adjacent tasks (incremental re-specification, cross-project dependency tracking, change-impact analysis) are candidates for new commands in a future minor release.

**Spec-kit extension: `init` equivalent.**
A mechanism to bootstrap the `.specify/templates/` directory (including the two mergen-addition templates) into a project that adopts the spec-kit preset, so no manual copy step is required.

---

## Legal notes

Claude Code and Claude are trademarks of Anthropic. Spec Kit is a project of GitHub, Inc., licensed MIT. This project is not affiliated with Anthropic or GitHub. Vendored Spec Kit material is attributed in `ATTRIBUTION.md` and `NOTICE` at the repository root. This project is licensed Apache-2.0.
