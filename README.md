# mergen

**Max reasoning effort plus standing dynamic-workflow orchestration for Claude Code, extended with a verified, minimal-by-default parallel spec-driven development (SDD) layer.**

`mergen` is two things shipped together: an effort mode that reconstructs the `max + orchestration` combination the Claude Code binary does not expose natively, and an SDD command suite that runs the same lifecycle as GitHub Spec Kit but under an adversarially verified, wave-parallel substrate. Each half is independently useful. Together they form a coherent engineering posture for hard, multi-step work.

> Status: v1.1.0, experimental. Built entirely from public Claude Code extension points (slash commands, hooks, `settings.json`). Does not patch or modify the Claude Code binary.

Not affiliated with Anthropic or GitHub. "Claude" and "Claude Code" are trademarks of Anthropic. "Spec Kit" is a project of GitHub, Inc. (MIT License). Vendored Spec Kit material is attributed in [ATTRIBUTION.md](ATTRIBUTION.md) and [NOTICE](NOTICE).

---

## What it is

### Half A: effort mode

Claude Code's compiled binary exposes an `/effort` ladder: `low`, `medium`, `high`, `xhigh`, `max`, and a special `ultracode` mode. `ultracode` means `xhigh` effort plus a standing directive to orchestrate every substantive task with the Workflow tool. It is excellent, but it is deliberately pinned to `xhigh`. There is no native way to combine `max` effort with that standing orchestration: selecting `ultracode` forces the value to `xhigh`, and selecting `max` disables the orchestration flag.

`mergen` reconstructs the combination from two supported, independent mechanisms:

- **Standing orchestration** via a `UserPromptSubmit` hook that injects the directive on every turn while the mode is armed.
- **Max effort** via the native `/effort max` command. A hook cannot flip the live effort value. The `/mergen` command prints the line for you to paste once. This single paste is irreducible.

Honest: `/effort max` requires one manual paste per session. No full automation claim is made.

Full mechanism in [docs/HOW-IT-WORKS.md](docs/HOW-IT-WORKS.md).

### Half B: SDD layer (superset of Spec Kit)

Thirteen command files in `core/commands/` define the full SDD lifecycle, each as a named Workflow-tool pattern. A single-source renderer produces two distribution shells: a native Claude Code skills install (invoked as `/mergen.*`) and a Spec Kit preset plus extension (invoked as `speckit.*` or `speckit.mergen.*`). The thesis: Spec Kit prompt-suggests structured documents and relies on a single context to follow them. mergen runs the same lifecycle under max effort plus Workflow orchestration, where each command is a multi-agent pattern, tasks run wave-parallel from a dependency DAG, and a separate-context adversarial verifier must confirm filesystem and tests before any task is marked complete. Each command also runs to a minimalism discipline, the lazy ladder: reason exhaustively, build the minimum that works, never cutting validation, security, or accessibility.

Details and the full parity table in [docs/SDD-SUPERSET.md](docs/SDD-SUPERSET.md).

---

## Quickstart (native install)

Requirements: Claude Code, Python 3.8+ on `PATH`.

```bash
git clone https://github.com/TheGoatPsy/mergen.git
cd mergen
./install.sh               # macOS / Linux / Git Bash
```

On Windows PowerShell:

```powershell
.\install.ps1
```

The installer runs three steps in order:

1. `effort-mode/install.sh` (or `.ps1`) installs the `/mergen` command and the `UserPromptSubmit` effort hook.
2. `python dist/native/build_native.py build` renders the 13 `/mergen.*` skills to `~/.claude/skills/`.
3. `python dist/native/patch_settings_hooks.py` registers the two SDD hooks in `~/.claude/settings.json` (idempotent, corruption-safe).

After install, restart Claude Code or run `/hooks` to load the new hooks.

### Arm effort mode

```
/mergen            arm the mode, then paste the /effort max line it prints
/mergen off        disarm
```

### Bootstrap SDD in a project

```bash
./install.sh --init <project-dir>
```

This creates `<project-dir>/.specify/` with scripts, templates, and a `memory/` directory. Then use the commands below.

### Regenerate the Spec Kit preset and extension

```bash
./install.sh --speckit
```

This renders `core/commands/` into `dist/speckit/` and prints the Spec Kit install commands.

---

## The 13 /mergen.* commands

Each command is a named Workflow-tool pattern. All run under the mergen substrate (max reasoning effort, standing orchestration).

| Command | One-line purpose | Workflow pattern |
|---|---|---|
| `/mergen.constitution` | Author or update the project constitution, keep dependent templates in sync. | Author plus adversarial self-check before accepting. |
| `/mergen.specify` | Write a feature spec. | Judge-panel: three parallel drafts (user lens, architect lens, rejection lens) plus an adversarial reviewer, then synthesis. |
| `/mergen.clarify` | Ask targeted questions before spec work. | Targeted question loop, maximum 5 questions, answers encoded back before any spec work. |
| `/mergen.checklist` | Apply a requirements-quality checklist. | Requirements-quality checklist ("unit tests for requirements") before implementation. |
| `/mergen.plan` | Produce an implementation plan. | Multi-approach generation in parallel lanes plus a separate refute-biased architecture critic, then synthesis. |
| `/mergen.tasks` | Break the plan into a verified task list and emit a dependency DAG. | Loop-until-dry completeness critic plus DAG-builder. Outputs `tasks-dag.json` with wave arrays and per-task `id`, `files`, `parallel`, `depends_on`, and `test_task` fields. |
| `/mergen.analyze` | Check cross-artifact consistency before writing code. | Four parallel adversarially-biased checker lanes (spec-plan, plan-tasks, tasks-spec, constitution compliance), deduplicated output. |
| `/mergen.implement` | Execute the task list. | Wave-parallel pipeline from `tasks-dag.json`: isolated implementer per task, then a separate-context refute-biased verifier that checks filesystem and tests before marking `[X]`. Re-queues on failure. Non-bypassable final verify gate. |
| `/mergen.verify` | Re-check every `[X]` task as a standalone gate. | Parallel four-lens check per task (file-exists, spec-match, tests-pass, git-consistent). Majority-or-FAIL verdict. Reverts `[X]` to `[ ]` on failure with guidance. |
| `/mergen.rollup` | Synthesize all feature specs into canonical project state. | Parallel reader lanes plus conflict adjudication plus adversarial self-check, writes `.specify/memory/project-state.md`. |
| `/mergen.go` | Route a request to the right SDD tier. | Complexity router: tinySpec (single file), standard (two to five files), or mergen (multiple subsystems, new public contract, ambiguous). When uncertain, picks the higher tier. |
| `/mergen.lean` | Review the diff or repo for over-engineering. | Parallel per-file reviewers hunting the lazy ladder, deduped into a ranked delete-list (`delete`/`stdlib`/`native`/`yagni`/`shrink`). Complexity only, never correctness. Lists cuts, never applies them. |
| `/mergen.debt` | Track deferred shortcuts. | Harvests `mergen:` comments into `.specify/memory/debt.md` by risk band. Gate mode fails on any shortcut with no named ceiling and upgrade path. |

---

## Full project workflow (native)

```
# 1. Install and bootstrap
git clone https://github.com/TheGoatPsy/mergen.git
cd mergen
./install.sh
./install.sh --init /path/to/your-project

# 2. In Claude Code, arm effort mode
/mergen                  # arm, then paste the /effort max line it prints

# 3. SDD lifecycle (in your project session)
/mergen.constitution     # author or refresh the project constitution
/mergen.go               # router: picks tinySpec, standard, or mergen tier
/mergen.clarify          # optional: targeted clarification questions
/mergen.specify          # write the feature spec (judge-panel pattern)
/mergen.checklist        # requirements-quality checklist
/mergen.plan             # produce the implementation plan
/mergen.tasks            # break into tasks, emit tasks-dag.json
/mergen.analyze          # cross-artifact consistency check
/mergen.implement        # execute wave-parallel with adversarial verification
/mergen.verify           # standalone phantom-completion gate
/mergen.lean             # over-engineering review: ranked delete-list, complexity only
/mergen.rollup           # synthesize project state
/mergen.debt             # harvest mergen: deferred-shortcut comments into a ledger
```

---

## Spec Kit option

If you use GitHub Spec Kit, `./install.sh --speckit` renders a preset and extension under `dist/speckit/` and prints the Spec Kit install commands.

**Preset** (`dist/speckit/preset/mergen/`): overrides 8 stock Spec Kit commands via `preset.yml`.

| Overridden command |
|---|
| `speckit.constitution` |
| `speckit.specify` |
| `speckit.clarify` |
| `speckit.checklist` |
| `speckit.plan` |
| `speckit.tasks` |
| `speckit.analyze` |
| `speckit.implement` |

**Extension** (`dist/speckit/extensions/mergen/`): adds 5 commands not present in stock Spec Kit.

| Added command | Purpose |
|---|---|
| `speckit.mergen.verify` | Parallel phantom-completion gate |
| `speckit.mergen.rollup` | Canonical project-state synthesis |
| `speckit.mergen.go` | Complexity router |
| `speckit.mergen.lean` | Over-engineering review (delete-list, complexity only) |
| `speckit.mergen.debt` | Deferred-shortcut debt ledger |

The extension also wires `hooks.after_implement -> speckit.mergen.verify` with `optional: false`, making the verify gate a non-bypassable step in the Spec Kit flow.

**Scope note.** The spec-kit half delivers a preset that replaces 8 commands and an extension that adds 5. Any Spec Kit behavior outside those 13 command surfaces is not modified or replicated.

---

## The SDD superset thesis

Spec Kit introduces a structured documentation lifecycle (spec, plan, tasks, constitution) and instructs the model to follow those documents in a single Claude Code context. Its own issue tracker and community discussions report these failure modes: phantom completions (tasks marked `[X]` without any file being created or test being run), no task parallelism (a long task list saturates the single context), context decay (earlier constraints recede from the model's effective context), no verification gate after implement, no adversarial review during specification, and TDD not enforced.

mergen runs the same SDD lifecycle but under what this project calls the ultracode-like substrate: max reasoning effort plus standing Workflow orchestration. Each command is not a single-context monologue but a named Workflow-tool pattern with specified lane structure, adversarial roles, and explicit mandate text. The implement command runs tasks wave-parallel from a dependency DAG where each task is a two-stage isolated pipeline: an implementer in one context, then a separate-context refute-biased verifier that checks the real filesystem and tests. A task is marked `[X]` only when the verifier returns `pass: true` with concrete evidence. On failure the task is re-queued with the failure list appended. The final verify gate is non-bypassable.

The hooks (`verify_gate.py`, `constitution_inject.py`) are reinforcement nudges. They remind at the moment of risk (when a task box is checked, when each prompt turn begins in a project with a constitution). They do not block anything. The real enforcement is the implement pipeline's adversarial verify stage. This distinction is maintained throughout the source code and documentation.

The failure modes above are Spec Kit's reported issues, not fabricated claims. No benchmark numbers are claimed. The `eval/` directory defines the evaluation methodology and a reproduction procedure. Any figures labeled SYNTHETIC or ILLUSTRATIVE in supporting documents are not real measurements.

Full treatment in [docs/SDD-SUPERSET.md](docs/SDD-SUPERSET.md).

---

## Minimalism (the lazy ladder)

Max effort has a failure mode: over-building. A request that should be `<input type="date">` becomes hundreds of lines of hand-rolled date picker. A verified, parallel, adversarially-checked pipeline can still ship more code than a task needs. mergen addresses that failure mode with a minimalism discipline derived from [`DietrichGebert/ponytail`](https://github.com/DietrichGebert/ponytail) (MIT, attributed in [ATTRIBUTION.md](ATTRIBUTION.md)).

The discipline is the lazy ladder in [`core/lazy-ladder.md`](core/lazy-ladder.md). Before writing code, stop at the first rung that holds: is it needed at all, then stdlib, then a native platform feature, then an installed dependency, then one line, then the minimum that works. Validation, security, accessibility, error handling, and tests are never on the chopping block. The thesis in one line: **think exhaustively, build minimally, verify it works and that it is minimal.**

It enters the lifecycle in four places:

- `/mergen.plan` prefers stdlib, native features, and installed dependencies over new abstractions, and its architecture-critic rejects complexity the spec does not require.
- `/mergen.implement` builds each task to the ladder, and its Stage B verifier rejects a task that is correct but over-built, tagging the surplus `delete`/`stdlib`/`native`/`yagni`/`shrink`.
- `/mergen.lean` reviews a diff or the whole repo for over-engineering and returns a ranked delete-list. Complexity only, never correctness.
- `/mergen.debt` harvests `mergen:` deferred-shortcut comments into a ledger, so a simplification with a known ceiling does not become permanent by silence.

The discipline (and only the discipline) ports to non-Claude agents: `python dist/agents/build_agents.py <project>` renders the lazy ladder into `AGENTS.md`, `.cursor/rules/`, `.windsurf/rules/`, `.clinerules/`, `.github/copilot-instructions.md`, and `.kiro/steering/`. The Workflow-orchestrated SDD engine is Claude Code specific and is not ported.

---

## Repository layout

```
effort-mode/
  commands/mergen.md           /mergen slash command (arm, disarm, print /effort max)
  hooks/mergen_prompt_hook.py  UserPromptSubmit hook (fail-soft, no-op when disarmed)
  scripts/patch_settings.py       idempotent settings.json patcher
  install.sh / install.ps1        effort-mode-only cross-platform installers

core/
  commands/                       13 SDD command source files (single source)
  lazy-ladder.md                  the minimalism discipline (single source)
  templates/                      7 templates (5 vendored MIT, 2 mergen additions)
  scripts/bash/ powershell/       vendored MIT helper scripts
  hooks/verify_gate.py            PostToolUse reinforcement nudge (see honesty note above)
  hooks/constitution_inject.py    UserPromptSubmit reinforcement nudge
  CONVENTIONS.md                  single-source / two-renderer contract

dist/
  native/build_native.py          renders core/ to ~/.claude/skills/mergen-*/
  native/patch_settings_hooks.py  registers/removes/status the two SDD hooks
  speckit/build_speckit.py        renders core/ to spec-kit preset + extension
  speckit/preset/mergen/       committed preset output (8 command overrides)
  speckit/extensions/mergen/   committed extension output (5 new commands)
  agents/build_agents.py          renders lazy-ladder.md to non-Claude passive rule files

scripts/check_sync.py             drift gate: committed dist/ matches a fresh render of core/

install.sh / install.ps1          root cross-platform installers (all three steps)

docs/
  HOW-IT-WORKS.md                 effort model internals, two-halves reconstruction
  SDD-SUPERSET.md                 full superset thesis and parity table
  ROADMAP.md                      what shipped in v1.0.0, known limits, planned next

ATTRIBUTION.md                    MIT attribution for vendored Spec Kit material
LICENSE                           Apache-2.0
NOTICE                            required Apache notices
```

---

## Status

v1.1.0, experimental.

- Native shell (half A + half B): full 13 `/mergen.*` commands installed as Claude Code skills, plus the effort-mode hook and command.
- Spec Kit shell (half B): preset overriding 8 commands plus extension adding 5 commands (`verify`, `rollup`, `go`, `lean`, `debt`).
- Minimalism layer: the lazy ladder (`core/lazy-ladder.md`), the `/mergen.lean` review, the `/mergen.debt` ledger, and a cross-agent renderer (`dist/agents/build_agents.py`) that ports the discipline to non-Claude agents.
- No benchmark numbers published yet. Evaluation methodology and a reproduction procedure are in `eval/`.
- `/effort max` requires one manual paste per session. The binary does not expose that control channel to hooks.
- Hooks are reinforcement nudges, not enforcement. Enforcement is the implement pipeline's adversarial verify stage.

Further reading:

- [docs/HOW-IT-WORKS.md](docs/HOW-IT-WORKS.md) - effort model internals and the two-halves design
- [docs/SDD-SUPERSET.md](docs/SDD-SUPERSET.md) - the superset thesis, structural answers, and parity table
- [docs/ROADMAP.md](docs/ROADMAP.md) - known limits of v1 and planned next steps
- [ATTRIBUTION.md](ATTRIBUTION.md) - MIT attribution for vendored Spec Kit material

---

## Not affiliated with Anthropic or GitHub

This is an independent community tool. It is not affiliated with, endorsed by, or sponsored by Anthropic or GitHub, Inc. "Claude" and "Claude Code" are trademarks of Anthropic. "Spec Kit" is a project of GitHub, Inc. Vendored Spec Kit material is MIT-attributed in [ATTRIBUTION.md](ATTRIBUTION.md) and [NOTICE](NOTICE). The behavior described here was observed in a specific Claude Code build and may change in future versions.

## License

Apache License 2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE).
