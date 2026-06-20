# mergen as a Superset of GitHub Spec Kit

**Scope.** This document makes the honest, rigorous case that mergen's SDD layer is a structural superset of GitHub Spec Kit and addresses Spec Kit's own reported failure modes. It is organized in four parts: what Spec Kit does, what it does not do (per its own reported issues), how mergen's architecture answers each gap, and a command-level parity table.

**Affiliation notice.** mergen is an independent community tool. It is not affiliated with, endorsed by, or sponsored by GitHub or Anthropic. "Spec Kit" is a project of GitHub, Inc. (MIT License). "Claude" and "Claude Code" are trademarks of Anthropic. Vendored Spec Kit material is MIT-attributed in `ATTRIBUTION.md` and `NOTICE`.

---

## 1. What Spec Kit Does and How It Is Designed

GitHub Spec Kit is a spec-driven development (SDD) framework for Claude Code. It introduces a structured documentation lifecycle: a feature spec (`spec.md`), an implementation plan (`plan.md`), a task checklist (`tasks.md`), and a project constitution (`constitution.md`). Helper scripts bootstrap the directory structure, and a set of slash commands walk Claude Code through each stage.

The design premise is that giving a language model structured documents to follow reduces drift, phantom completions, and under-specified acceptance criteria compared to freeform prompting. The model operates in a single Claude Code context and is instructed to read and follow the documents at each stage.

Spec Kit ships the following core commands: `speckit.constitution`, `speckit.specify`, `speckit.clarify`, `speckit.checklist`, `speckit.plan`, `speckit.tasks`, `speckit.analyze`, and `speckit.implement`. These are invocable slash commands in Claude Code. The framework also defines a preset and extension system that allows community tooling to override or extend the stock commands.

---

## 2. Spec Kit's Own Reported Failure Modes

The following failure modes are documented in Spec Kit's own issue tracker and community discussions. They are stated here as Spec Kit's reported issues, not as fabricated claims.

**Phantom completions.** Tasks in `tasks.md` are marked `[X]` without any file having been created or modified and without any test having been run. The `[X]` mark itself is treated as evidence of completion. There is no independent check against the filesystem or test runner before the mark is applied.

**No task parallelism.** `speckit.implement` runs tasks sequentially in a single context. There is no mechanism to execute independent tasks in parallel Workflow lanes. Long task lists saturate the context window and produce progressively degraded output from later tasks.

**Context decay.** Over a long `speckit.implement` run, earlier decisions, architectural constraints, and accepted criteria recede from the model's effective context. Tasks near the end of a long list are implemented with less fidelity to the original spec than tasks near the beginning. The model cannot be reliably reminded of the constitution and task requirements without manual intervention.

**No verification gate.** After `speckit.implement` runs, there is no mandatory command that independently re-checks every `[X]` task against the filesystem and tests. Verification is optional and depends on the user remembering to run a check.

**No adversarial review during specification.** `speckit.specify` produces a spec in a single context from a single perspective. There is no parallel judge-panel that generates competing drafts, no adversarial reviewer that actively tries to find untestable or contradictory acceptance criteria, and no synthesis step that resolves findings from multiple lenses before the spec is written.

**TDD not enforced.** The tasks command documents a test-first ordering convention, but there is no mechanism that requires a test task to exist and fail before an implementation task can begin. The ordering is advisory.

---

## 3. mergen's Structural Answers

mergen runs the same SDD lifecycle as Spec Kit but under what this document calls the "ultracode-like substrate": a combination of maximum reasoning effort and standing Workflow orchestration, applied at every command. Each Spec Kit failure mode has a named structural answer in mergen's architecture.

### 3.1 The ultracode-like substrate

Claude Code's compiled binary offers two separate settings: an effort level (low through max) and a boolean ultracode flag (standing Workflow orchestration). The binary does not allow `max` effort and the orchestration flag to be set simultaneously. Selecting `ultracode` forces the effort value to `xhigh`, and selecting any plain effort level disables the orchestration flag. Neither `max` nor `ultracode` can be persisted in `settings.json`. Both are session-scoped.

mergen reconstructs the combination from two supported, independent mechanisms documented in `docs/HOW-IT-WORKS.md`:

**Standing orchestration.** A `UserPromptSubmit` hook (`effort-mode/hooks/mergen_prompt_hook.py`) runs on every turn and injects a standing directive instructing the model to orchestrate every substantive task with the Workflow tool and to adversarially verify before claiming completion. This faithfully reproduces native ultracode's per-turn standing reminder but at the `max` tier rather than `xhigh`. The `additionalContext` injection channel used here is the same documented channel used by other Claude Code hook events.

**Max effort via one paste.** The genuine native `max` tier is only opened by the interactive `/effort max` command. A hook cannot flip the live effort value because the control channel that applies effort is not exposed to hooks. The `/mergen` command (`effort-mode/commands/mergen.md`) arms the mode and prints the `/effort max` line for the user to paste once. This single manual step is irreducible. It is the honest cost of reaching a tier the binary does not let any extension set programmatically.

Together these yield: max reasoning effort, standing per-turn orchestration reminder, and adversarial verification posture. All three are active for the duration of the session.

### 3.2 Commands as named Workflow patterns

Each SDD command in `core/commands/` is not a single-context monologue. It is a named Workflow-tool pattern with specified lane structure, adversarial roles, and explicit mandate text. The following maps each command to its pattern:

**`mergen.specify`: judge-panel.** Three drafting lanes run in parallel: an end-user lens, a senior-architect lens, and a customer-rejection lens. Each lane receives the feature description and independently produces a full draft spec. A fourth lane, the adversarial reviewer, runs after the three drafts return. It scores every acceptance scenario across all three drafts on three axes: missing, contradictory, and untestable. A synthesis step in the original context merges the strongest material from all three drafts, applies mandatory fixes from the adversarial review, and writes the canonical `spec.md`. This directly answers the single-perspective specification failure mode.

**`mergen.clarify`: targeted question loop.** At most five targeted questions. Answers are encoded back into context before any spec work begins. The cap prevents ceremony from exceeding value.

**`mergen.plan`: multi-approach plus architecture-critic.** Two or three candidate-design agents run in parallel, each with a different design lens (lean, conventional, scalable). A separate architecture-critic agent then runs in isolation, with the mandate to find reasons each candidate should be rejected. It delivers a ranked verdict. The synthesis step in the original context selects the recommended candidate or hybrid, populates `plan.md`, and optionally produces `data-model.md` and `contracts/`. An adversarial verifier confirms no requirement from the spec was silently dropped before the plan is accepted.

**`mergen.tasks`: loop-until-dry completeness critic plus DAG emission.** After an initial task draft, a completeness-critic lane is spawned via the Workflow tool. The critic's sole mandate is adversarial: find spec scenarios with no covering task. If it returns gaps, tasks are added and the critic re-runs. The loop continues until the critic returns zero gaps or three iterations are exhausted, with remaining gaps recorded explicitly in `## Known Gaps`. A concurrent DAG-builder lane produces `tasks-dag.json`: an array of waves, each wave an array of task objects with `id`, `files`, `parallel`, `depends_on`, and `test_task` fields. A DAG-consistency verifier checks for duplicate IDs, broken references, cycles, and inconsistent wave ordering before the file is written.

**`mergen.analyze`: parallel cross-artifact consistency checkers.** Four checker lanes run concurrently: spec vs. plan consistency, plan vs. tasks consistency, tasks vs. spec requirements coverage, and constitution and governance compliance. Each lane is adversarially biased. Findings are deduplicated across lanes and sorted by severity. The command is strictly non-destructive. It is run before a single line of code is written, which catches gaps that would otherwise produce task rework or unverified implementation.

**`mergen.implement`: wave-parallel verified pipeline.** This is the core structural answer to phantom completions, no parallelism, context decay, no verify gate, and TDD not enforced. The full mechanism:

The `tasks-dag.json` emitted by `/mergen.tasks` defines execution waves. Within a wave, independent tasks run in parallel Workflow lanes. Between waves there is a barrier: wave N+1 starts only after every wave-N task is verified PASS.

Each task is a two-stage pipeline in an isolated context:

Stage A (implement): a subagent receives only the task spec, the relevant slice of `plan.md`, `data-model.md`, and `contracts/`, and the constitution clauses relevant to the task's file paths. TDD ordering is enforced via `test_task`: a task cannot enter Stage A until its named test sub-task exists and fails first. The implementer writes the failing test, then the implementation, then makes the test pass.

Stage B (adversarial verify): a verifier runs in a separate context. It receives only the task spec and the resulting diff or file list, never Stage A's reasoning. Its mandate is to disprove completion. It checks against the real filesystem and by running tests: (1) every named file exists and changed as specified, (2) the implementation matches acceptance criteria, (3) the task's tests exist and pass, (4) git state is consistent with the claimed change. It returns `{ "pass": bool, "evidence": [...], "failures": [...] }`. Default is `pass: false` when uncertain.

A task is marked `[X]` in `tasks.md` only when its verifier returns `pass: true` with evidence. On `pass: false`, the task is re-queued with the verifier's failure list appended as guidance. Retries are capped at two. After the cap, the task is left `[ ]`, the failure is recorded, and it is surfaced in the completion report. An unverified task is never silently marked complete.

Before reporting completion, a final verification pass equivalent to `/mergen.verify` re-checks every `[X]` task. This gate is mandatory within the pipeline, which does not mark `[X]` without it, and if any `[X]` task fails it reverts to `[ ]` and is re-queued. A user editing `tasks.md` by hand is outside the pipeline. A CI gate for your own project ships as `eval/ci/verify-gate.yml`. It fails the build when the committed verification report shows phantom or unverified work, and because it reads the committed artifact, the deepest guarantee rests on the verifier that produced it.

**`mergen.verify`: parallel multi-lens phantom-completion gate.** Four independent lanes per task: file-exists, spec-match, tests-pass, git-consistent. Lane 1 (file-exists) is an unconditional FAIL gate: a file that does not exist on the filesystem cannot satisfy any other criterion. Otherwise, a task earns PASS when three or more lenses return `pass: true` with concrete command output as evidence. Assertion without output is not evidence. Default is FAIL when uncertain. Tasks that fail the majority verdict are reverted from `[X]` to `[ ]` with failure guidance appended. The full report, including actual command output from every lens of every task, is written to `FEATURE_DIR/verification-report.md`. Machine-readable output is also emitted as `verification-report.json` and `tasks-state.json` (schemas in `core/schemas/`), each task carrying a confidence label. These JSON files are the input consumed by `eval/evidence_metric.py`.

**`mergen.rollup`: canonical project-state synthesis.** Three parallel reader lanes (requirements, plan and data-model, tasks and contracts) produce a deduplicated, conflict-flagged inventory. A synthesis lane adjudicates conflicts, drops superseded material, and writes `.specify/memory/project-state.md` following the project-state template. An adversarial self-check confirms no requirement dropped silently and no section contains contradictory claims before the file is accepted.

**`mergen.go`: complexity router.** Routes a request to the appropriate SDD tier: tinySpec (single file, one small change), standard (two to five files, full SDD chain without maximum ceremony), or mergen (multiple subsystems, new public contract, safety-critical, ambiguous enough for the judge panel). When uncertain between tiers, the rule is to pick the higher one. The tinySpec path is deliberately lightweight: excessive ceremony is named as its own failure mode.

**`mergen.constitution` and `mergen.checklist`.** The constitution command authors or updates the governance document. The checklist command applies a requirements-quality checklist before any implementation begins.

**`mergen.lean` and `mergen.debt`.** These two commands belong to the minimalism layer described in 3.4. `mergen.lean` runs an over-engineering review (parallel per-file reviewers against the lazy ladder, deduplicated into a ranked delete-list, complexity only and never correctness). `mergen.debt` harvests `mergen:` deferred-shortcut comments into a risk-banded ledger and, in gate mode, fails on any shortcut with no named ceiling and upgrade path.

**`mergen.govern`: the Governor.** Classifies an incoming task into one of four tiers: tiny, standard, spec, or high-trust. For each tier it sets memory scope, workflow depth, evidence standard, and the human-approval threshold. A deterministic high-trust floor is always enforced: the floor can be raised by explicit configuration but is never silently lowered. The Governor is the wisdom organ of the suite. It decides how much ceremony a task warrants. The `/mergen.go` complexity router then executes the chosen tier. Machine-readable verify output (`verification-report.json` and `tasks-state.json`, schemas in `core/schemas/`) carries a confidence label per task and feeds both the Governor's evidence standard and the eval evidence metric in `eval/evidence_metric.py`.

### 3.3 Reinforcement hooks

Two hooks in `core/hooks/` are registered by the SDD installer via `dist/native/patch_settings_hooks.py`.

**`verify_gate.py` (PostToolUse on Write, Edit, MultiEdit).** When `tasks.md` is edited and the change introduces an `[X]` mark, the hook injects an `additionalContext` reminder into the model's context: a task is complete only when an independent verifier has confirmed it against the filesystem and tests. The hook is fail-soft. Any error, or any call that does not introduce an `[X]` mark in `tasks.md`, exits 0 with no output.

**`constitution_inject.py` (UserPromptSubmit).** When the current project has a constitution at `.specify/memory/constitution.md`, the hook injects the constitution's section headings as a compact standing reminder so governance constraints remain visible during spec, plan, tasks, and implementation work. The hook is fail-soft. It is a true no-op when no constitution exists.

**Critical honesty.** Both hooks are reinforcement nudges. They are not enforcement mechanisms and they do not block anything. The real enforcement is the `/mergen.implement` pipeline: a separate-context refute-biased verifier that checks the filesystem and tests before any task is marked `[X]`, plus the final verify gate the pipeline will not skip. A PostToolUse hook cannot itself run a project's test suite to prove completion. What it does is re-surface the discipline at the exact moment a task box is checked, so a single-context shortcut cannot quietly mark work done without the reminder. The hook source code (`core/hooks/verify_gate.py`, line 4) states this explicitly.

### 3.4 Minimalism beyond parity: the lazy ladder

This is not an answer to a Spec Kit failure mode. It answers a failure mode of the substrate itself. Maximum reasoning effort, applied without a counterweight, over-builds: it produces abstractions, dependencies, and boilerplate the task never required. A verified, parallel, adversarially-checked pipeline can still ship more code than a task needs, and every line of that surplus is correct, so the verify gate passes it. Spec Kit does not address this, and neither does an unguarded max-effort harness. mergen adds the counterweight.

The discipline is the lazy ladder (`core/lazy-ladder.md`), derived from `DietrichGebert/ponytail` (MIT, attributed in `ATTRIBUTION.md`). Before writing code, the agent stops at the first rung that holds: is it needed at all, then the standard library, then a native platform feature, then an installed dependency, then one line, then the minimum that works. Validation, security, accessibility, error handling, and tests are explicitly never cut. The discipline enters the lifecycle in four places. `plan` prefers stdlib, native, and installed dependencies over new abstractions. `implement` builds each task to the ladder, and its Stage B verifier rejects a task that is correct but over-built, tagging the surplus `delete`, `stdlib`, `native`, `yagni`, or `shrink`. `lean` reviews a diff or the repo and returns a ranked delete-list. `debt` keeps deferred shortcuts visible. The one-line thesis: think exhaustively, build minimally, verify it works and that it is minimal.

The discipline, and only the discipline, ports to non-Claude agents via `dist/agents/build_agents.py`, which renders `core/lazy-ladder.md` into the passive rule files Cursor, Windsurf, Cline, Copilot, Kiro, and the generic `AGENTS.md` convention read. The Workflow-orchestrated SDD engine does not port and is not claimed to.

---

## 4. Feature and Parity Table

The table below maps each Spec Kit command to its mergen equivalent and describes what mergen adds. The native shell (C) is the full 14-command experience. The spec-kit shell (B) ships a preset that overrides eight stock Spec Kit commands and an extension that adds six commands Spec Kit lacks.

| Spec Kit command | mergen native equivalent | mergen spec-kit equivalent | What mergen adds |
|---|---|---|---|
| `speckit.constitution` | `/mergen.constitution` | `speckit.constitution` (preset override) | Adversarial self-check before accepting the constitution. Constitution sync across templates. |
| `speckit.specify` | `/mergen.specify` | `speckit.specify` (preset override) | Judge-panel: three parallel spec drafts plus adversarial reviewer. Synthesis resolves mandatory findings before `spec.md` is written. |
| `speckit.clarify` | `/mergen.clarify` | `speckit.clarify` (preset override) | Explicit cap of five questions. Answers encoded into context before spec work begins. |
| `speckit.checklist` | `/mergen.checklist` | `speckit.checklist` (preset override) | Requirements-quality checklist before implementation. Surfaces unresolved gaps in a WARNING blockquote rather than blocking. |
| `speckit.plan` | `/mergen.plan` | `speckit.plan` (preset override) | Multi-approach generation in parallel lanes. Separate architecture-critic with refute mandate. Adversarial verifier confirms no spec requirement dropped before plan is accepted. |
| `speckit.tasks` | `/mergen.tasks` | `speckit.tasks` (preset override) | Loop-until-dry completeness critic. DAG emission (`tasks-dag.json`) with wave arrays and `test_task` fields. DAG consistency verifier before write. |
| `speckit.analyze` | `/mergen.analyze` | `speckit.analyze` (preset override) | Four parallel adversarially-biased checker lanes. Cross-lane deduplication. Run before implementation not after. |
| `speckit.implement` | `/mergen.implement` | `speckit.implement` (preset override) | Wave-parallel execution from DAG. Isolated implementer context per task. Separate-context refute-biased verifier per task. TDD enforced via `test_task`. Re-queue with failure evidence on `pass: false`. Mandatory final verify gate. |
| (not present) | `/mergen.verify` | `speckit.mergen.verify` (extension) | Parallel four-lens phantom-completion gate per `[X]` task. Majority-or-FAIL verdict. Reverts `[X]` to `[ ]` on failure with guidance. Writes evidence-backed report. |
| (not present) | `/mergen.rollup` | `speckit.mergen.rollup` (extension) | Parallel reader lanes over all feature specs. Conflict adjudication. Superseded-material pruning. Adversarial self-check on the synthesized `project-state.md`. |
| (not present) | `/mergen.go` | `speckit.mergen.go` (extension) | Complexity router: tinySpec, standard, or mergen tier. When uncertain, routes to the higher tier. Explicitly names excessive ceremony as a failure mode. |
| (not present) | `/mergen.lean` | `speckit.mergen.lean` (extension) | Over-engineering review: parallel per-file reviewers against the lazy ladder, deduplicated into a ranked delete-list (`delete`/`stdlib`/`native`/`yagni`/`shrink`). Complexity only, never correctness. Lists cuts, never applies them. |
| (not present) | `/mergen.debt` | `speckit.mergen.debt` (extension) | Harvests `mergen:` deferred-shortcut comments into a risk-banded ledger. Gate mode fails on any shortcut with no named ceiling and upgrade path. |
| (not present) | `/mergen.govern` | `speckit.mergen.govern` (extension) | Classifies a task into tiny, standard, spec, or high-trust and sets memory scope, workflow depth, evidence standard, and human approval threshold. Deterministic high-trust floor: the floor can be raised by explicit configuration but is never silently lowered. The wisdom organ that precedes routing. The `/mergen.go` router executes the chosen tier. |

**Scope note.** The native shell installs all 14 commands as Claude Code skills under `~/.claude/skills/mergen-<name>/SKILL.md`, invoked as `/mergen.<name>`, via `dist/native/build_native.py`. The spec-kit shell (`dist/speckit/build_speckit.py`) delivers a preset (`dist/speckit/preset/mergen/`) that overrides eight stock Spec Kit commands and an extension (`dist/speckit/extensions/mergen/`) that adds six commands Spec Kit lacks (`verify`, `rollup`, `go`, `lean`, `debt`, `govern`) as `speckit.mergen.<cmd>`, with the verify gate wired as a mandatory `after_implement` hook (`optional: false`), reinforced in-session and made a true gate by the drop-in project CI check `eval/ci/verify-gate.yml`. The spec-kit shell does not claim to replace Spec Kit's own install tooling or preset infrastructure.

---

## 5. The Two Categorical Wins

**Win 1: prompt-suggests becomes harness-reinforced plus orchestration-verified.**

Spec Kit's governance model relies on the model reading and following structured documents in a single context. There is no mechanism that confirms the model acted on them. mergen adds two independent reinforcement layers and one verification layer. The hooks (reinforcement) re-surface governance constraints at the moment they are most likely to be bypassed: when a task is being marked complete and when each prompt turn begins in a project with a constitution. The implement pipeline (verification) uses a separate-context verifier whose mandate is adversarial and whose inputs are restricted to the task spec and the resulting diff, never the implementer's reasoning. A task cannot be marked `[X]` without that verifier returning `pass: true` with concrete filesystem and test evidence. The distinction between reinforcement (hooks) and verification (implement pipeline) is maintained throughout. This document and the hook source code state explicitly that hooks do not block anything.

**Win 2: hopeful single-context execution becomes verified wave-parallel execution.**

Spec Kit's implement command runs tasks sequentially in a single context. mergen's implement command runs tasks in parallel waves derived from a dependency DAG emitted by `/mergen.tasks`. Each task is an isolated two-stage pipeline with context separation between the implementer and the verifier. Context saturation is structurally eliminated because no single context accumulates the full task list. Each context receives only the inputs relevant to its task. TDD is enforced via the `test_task` field in the DAG, which requires a test sub-task to exist and fail before its implementation task can enter Stage A. Between waves there is a barrier: the next wave cannot begin until every task in the current wave is verifier-confirmed or reported as failing with evidence. "Phantom completion" is structurally harder because the verification check is not a separate optional command but an integral stage inside the implementation pipeline.

---

## Measurements and Evaluation

No benchmark numbers are claimed in this document. The eval directory (`eval/`) contains the evaluation methodology and a reproduction procedure. Any figures obtained by running that procedure should be labeled with the date, model version, and task set. Point measurement readers to `eval/` for current numbers.

---

## References

- `docs/HOW-IT-WORKS.md`: effort model internals and the two-halves reconstruction
- `core/commands/implement.md`: the wave-parallel verified pipeline
- `core/commands/verify.md`: the parallel multi-lens phantom-completion gate
- `core/commands/specify.md`: the judge-panel specification pattern
- `core/commands/tasks.md`: the completeness-critic loop and DAG emission
- `core/commands/plan.md`: the multi-approach plus architecture-critic pattern
- `core/commands/analyze.md`: the parallel cross-artifact consistency checkers
- `core/commands/go.md`: the complexity router
- `core/lazy-ladder.md`: the minimalism discipline (the lazy ladder and the `mergen:` convention)
- `core/commands/lean.md`: the over-engineering review
- `core/commands/debt.md`: the deferred-shortcut ledger
- `dist/agents/build_agents.py`: the cross-agent passive-rule renderer
- `core/hooks/verify_gate.py`: reinforcement hook source with explicit scope comment
- `core/hooks/constitution_inject.py`: constitution reinforcement hook source
- `dist/native/build_native.py`: native shell renderer
- `dist/speckit/build_speckit.py`: spec-kit shell renderer
- `docs/MNEME-SEAM.md`: the single seam between mergen (execution layer) and mneme (memory layer)
- `scripts/mneme_emit.py`: emit hook that writes structured events across the mneme seam
- `eval/evidence_metric.py`: minimal honest eval metric (work-done rate, phantom-completion count) derived from verify JSON
- `core/schemas/verification-report.schema.json`: schema for machine-readable verify output
- `core/schemas/tasks-state.schema.json`: schema for per-task post-verification state (id, status, files, test task, last-verified timestamp)
- `ATTRIBUTION.md`: MIT attribution for vendored Spec Kit material
