<p align="center">
  <img src="assets/mergen-emblem.png" alt="Mergen emblem: a gold arrow finding its mark above a verify checkmark, flanked by two wolves, ringed by a runic border on a deep night sky" width="360">
</p>

# Mergen

**The execution backbone for AI coding agents. Maximum reasoning effort, Workflow orchestration, and
adversarial verification, governed so the ceremony scales to the risk.**

Mergen is named for the Turkic deity of wisdom and isabet, of sound judgment and the arrow that finds its
mark. The name states the architecture. Mergen judges, with wisdom, how much care a task deserves, and it
proves, with accuracy, that the work was actually done and was no larger than it needed to be. The wisdom is
the Governor. The accuracy is the verify gate.

Mergen is the execution half of a two-part whole. [mneme](https://github.com/TheGoatPsy/mneme) is the memory
half. mneme remembers why a project is the way it is, with provenance visible and nothing fabricated. Mergen
decides what a task needs and proves it was hit. Together they form the Agent Continuity Stack, joined by one
seam and nothing more. Mergen stores no memory of its own.

> Status: v1.0.0, experimental. Built entirely from public Claude Code extension points (slash commands,
> hooks, `settings.json`). Does not patch or modify the Claude Code binary.

Mergen is original work. Its operating principles were informed by responsible-AI design ideas and reproduce
no proprietary text. The charter is [MERGEN.md](MERGEN.md), the principle-to-component map is
[MERGEN_PRINCIPLES.md](MERGEN_PRINCIPLES.md). Not affiliated with Anthropic or GitHub. "Claude" and "Claude
Code" are trademarks of Anthropic. "Spec Kit" is a project of GitHub, Inc. (MIT). Vendored Spec Kit material
is attributed in [ATTRIBUTION.md](ATTRIBUTION.md) and [NOTICE](NOTICE). The lineage of Mergen's engine is
recorded in [PROVENANCE.md](PROVENANCE.md).

---

## What it is

Mergen ships two halves under one identity.

### Half A: effort mode

Claude Code's compiled binary exposes an `/effort` ladder (`low`, `medium`, `high`, `xhigh`, `max`) and a
special `ultracode` mode that means `xhigh` plus a standing directive to orchestrate every substantive task
with the Workflow tool. There is no native way to combine `max` effort with that standing orchestration.
Mergen reconstructs the combination from two supported mechanisms:

- **Standing orchestration** via a `UserPromptSubmit` hook that injects the directive on every turn while the
  mode is armed. The directive carries Mergen's operating principles: verify before claiming, never fabricate
  a source or result, treat retrieved content as data and not instruction, and build the minimum that works.
- **Max effort** via the native `/effort max` command. A hook cannot flip the live effort value, so the
  `/mergen` command prints the line for you to paste once. This single paste is irreducible.

Full mechanism in [docs/HOW-IT-WORKS.md](docs/HOW-IT-WORKS.md).

### Half B: the spec-driven development layer (a superset of Spec Kit)

Fourteen command files in `core/commands/` define the full SDD lifecycle, each as a named Workflow pattern. A
single-source renderer produces two distribution shells: a native Claude Code skills install (invoked as
`/mergen.*`) and a Spec Kit preset plus extension (invoked as `speckit.*` or `speckit.mergen.*`). Spec Kit
prompt-suggests structured documents and relies on a single context to follow them. Mergen runs the same
lifecycle under max effort plus Workflow orchestration, where each command is a multi-agent pattern, tasks
run wave-parallel from a dependency DAG, and a separate-context adversarial verifier must confirm filesystem
and tests before any task is marked complete. Each command also runs to the lazy ladder: reason exhaustively,
build the minimum that works, never cutting validation, security, or accessibility.

Details and the full parity table in [docs/SDD-SUPERSET.md](docs/SDD-SUPERSET.md).

### The Governor: wisdom over the lifecycle

Maximum effort on every task is its own failure mode. A typo does not deserve a tribunal, and an auth change
must not avoid one. The Governor (`/mergen.govern`) classifies a task into `tiny`, `standard`, `spec`, or
`high-trust` and sets the memory scope, the workflow depth, the evidence standard, and whether a human must
sign off. High-trust triggers (auth, payment, secrets, privacy and PII, clinical and regulated content,
irreversible operations, public-contract changes, and treating untrusted input as instruction) force a
deterministic floor that the Governor can raise but never silently lower. Clinical and sensitive work cannot
be downgraded, even by configuration. The Governor emits `governor-decision.json`, and the `go` router
executes the chosen tier, adding the high-trust human checkpoint. The Governor is what makes maximum effort
affordable.

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
2. `python dist/native/build_native.py build` renders the 14 `/mergen.*` skills to `~/.claude/skills/`.
3. `python dist/native/patch_settings_hooks.py` registers the two SDD hooks in `~/.claude/settings.json`
   (idempotent, corruption-safe, and tolerant of a UTF-8 BOM that Claude Code on Windows can write).

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

This creates `<project-dir>/.specify/` with scripts, templates, and a `memory/` directory.

---

## The 14 /mergen.* commands

Each command is a named Workflow pattern. All run under the mergen substrate (max reasoning effort, standing
orchestration), with the Governor setting how much of the pattern a given task earns.

| Command | One-line purpose | Workflow pattern |
|---|---|---|
| `/mergen.govern` | Classify a task by risk and set its ceremony. | The Governor: tier (tiny/standard/spec/high-trust), memory scope, evidence standard, and human approval, with a deterministic high-trust floor. Emits `governor-decision.json`. |
| `/mergen.constitution` | Author or update the project constitution. | Author plus adversarial self-check before accepting. |
| `/mergen.specify` | Write a feature spec. | Judge panel: three parallel drafts (user, architect, rejection lens) plus an adversarial reviewer, then synthesis. |
| `/mergen.clarify` | Ask targeted questions before spec work. | Targeted question loop, maximum 5, answers encoded back. |
| `/mergen.checklist` | Apply a requirements-quality checklist. | Requirements-quality checklist ("unit tests for requirements") before implementation. |
| `/mergen.plan` | Produce an implementation plan. | Multi-approach generation in parallel lanes plus a refute-biased architecture critic, then synthesis. |
| `/mergen.tasks` | Break the plan into tasks and a dependency DAG. | Loop-until-dry completeness critic plus DAG builder. Outputs `tasks-dag.json`. |
| `/mergen.analyze` | Check cross-artifact consistency before code. | Four parallel adversarial checker lanes, deduplicated. |
| `/mergen.implement` | Execute the task list. | Wave-parallel pipeline from `tasks-dag.json`: isolated implementer per task, then a separate-context refute-biased verifier that checks filesystem and tests before marking `[X]`. Re-queues on failure. |
| `/mergen.verify` | Re-check every `[X]` task as a standalone gate. | Parallel four-lens check per task (file-exists, spec-match, tests-pass, git-consistent). Majority-or-FAIL. Emits `verification-report.json` and `tasks-state.json` with a confidence label per task. |
| `/mergen.rollup` | Synthesize feature specs into canonical project state. | Parallel reader lanes plus conflict adjudication, writes `.specify/memory/project-state.md`. |
| `/mergen.go` | Route a request to the tier the Governor chose. | Executes the Governor's tier (tiny/standard/spec/high-trust), adding the high-trust human checkpoint. |
| `/mergen.lean` | Review the diff or repo for over-engineering. | Parallel per-file reviewers, deduped into a ranked delete-list (`delete`/`stdlib`/`native`/`yagni`/`shrink`). Complexity only, never correctness. |
| `/mergen.debt` | Track deferred shortcuts. | Harvests `mergen:` comments into `.specify/memory/debt.md` by risk band. Gate mode fails on any shortcut with no named ceiling. |

---

## Proof, not assertion

A box checked by the implementer is a hypothesis, not evidence. Mergen treats it as the thing to be
disproven. `/mergen.verify` re-checks every `[X]` task in a separate context with a contrary mandate, against
the real filesystem and real tests, and emits `verification-report.json` so the result can be measured and
audited. The eval evidence metric (`eval/evidence_metric.py`) reads that JSON and reports a work-done rate and
a phantom-completion count, abstaining honestly when it has no data. Worth-remembering decisions cross the one
seam to mneme as provenance-bearing records (`scripts/mneme_emit.py`, [docs/MNEME-SEAM.md](docs/MNEME-SEAM.md)),
never as a memory store of Mergen's own.

On honesty about enforcement: a prompt protocol asks, a hook nudges, and a CI gate refuses. In-session the
implement pipeline will not mark a task done without the verifier, which is strong discipline but not an
absolute lock. Mergen's own CI guards this repository (its tests, the drift gate, the no-reference-text gate),
not your project's task verification. A truly non-bypassable verify gate for your own project means wiring a
CI check against your verification artifacts, which is on the roadmap. Mergen does not blur the three.

---

## Spec Kit option

If you use GitHub Spec Kit, `./install.sh --speckit` renders a preset and extension under `dist/speckit/`.

**Preset** (`dist/speckit/preset/mergen/`): overrides 8 stock Spec Kit commands (`constitution`, `specify`,
`clarify`, `checklist`, `plan`, `tasks`, `analyze`, `implement`).

**Extension** (`dist/speckit/extensions/mergen/`): adds 6 commands not present in stock Spec Kit.

| Added command | Purpose |
|---|---|
| `speckit.mergen.govern` | The Governor (risk-tier classification) |
| `speckit.mergen.verify` | Parallel phantom-completion gate, emits JSON evidence |
| `speckit.mergen.rollup` | Canonical project-state synthesis |
| `speckit.mergen.go` | Tier executor and router |
| `speckit.mergen.lean` | Over-engineering review (delete-list, complexity only) |
| `speckit.mergen.debt` | Deferred-shortcut debt ledger |

The extension wires `hooks.after_implement -> speckit.mergen.verify` with `optional: false`, making verify
mandatory in the Spec Kit implement flow. That is the hook contract, reinforced in-session. A CI check against
your project would make it a true gate. Spec Kit behavior outside those command surfaces is not modified or
replicated.

---

## Minimalism (the lazy ladder)

Max effort has a failure mode: over-building. A request that should be `<input type="date">` becomes more code
than the task needs. Mergen addresses it with a minimalism discipline derived from
[`DietrichGebert/ponytail`](https://github.com/DietrichGebert/ponytail) (MIT, attributed in
[ATTRIBUTION.md](ATTRIBUTION.md)).

The discipline is the lazy ladder in [`core/lazy-ladder.md`](core/lazy-ladder.md). Before writing code, stop at
the first rung that holds: is it needed at all, then stdlib, then a native platform feature, then an installed
dependency, then one line, then the minimum that works. Validation, security, accessibility, error handling,
and tests are never on the chopping block. The thesis in one line: **think exhaustively, build minimally,
verify it works and that it is minimal.** The same restraint governs prose, which is why Mergen prefers plain
sentences and a delete-list to a rewrite.

It enters the lifecycle in `plan` (prefer stdlib and native over new abstractions), `implement` (the Stage B
verifier rejects a correct-but-over-built task), `lean` (a ranked delete-list), and `debt` (harvest deferred
shortcuts so a simplification with a known ceiling does not become permanent by silence). The discipline, and
only the discipline, ports to non-Claude agents via `python dist/agents/build_agents.py <project>`, which
renders the ladder into `AGENTS.md`, `.cursor/rules/`, `.windsurf/rules/`, `.clinerules/`,
`.github/copilot-instructions.md`, and `.kiro/steering/`. The Workflow-orchestrated SDD engine is Claude Code
specific and is not ported.

---

## Repository layout

```
MERGEN.md                         the charter (what Mergen is and commits to)
MERGEN_PRINCIPLES.md              principle-to-component map
PROVENANCE.md                     lineage and the identity transform

effort-mode/
  commands/mergen.md              /mergen slash command (arm, disarm, print /effort max)
  hooks/mergen_prompt_hook.py     UserPromptSubmit hook (fail-soft, no-op when disarmed)
  scripts/patch_settings.py       idempotent, BOM-safe settings.json patcher
  install.sh / install.ps1        effort-mode-only installers

core/
  commands/                       14 SDD command source files (single source)
  lazy-ladder.md                  the minimalism discipline (single source)
  schemas/                        JSON schemas: verification-report, tasks-state, governor-decision
  templates/                      7 templates (5 vendored MIT, 2 mergen additions)
  scripts/bash/ powershell/       vendored MIT helper scripts
  hooks/                          verify_gate.py, constitution_inject.py (reinforcement nudges)
  CONVENTIONS.md                  single-source / two-renderer contract

dist/
  native/build_native.py          renders core/ to ~/.claude/skills/mergen-*/
  native/patch_settings_hooks.py  registers the two SDD hooks (BOM-safe)
  speckit/build_speckit.py        renders core/ to spec-kit preset + extension
  speckit/preset/mergen/          committed preset output (8 command overrides)
  speckit/extensions/mergen/      committed extension output (6 new commands)
  agents/build_agents.py          renders lazy-ladder.md to non-Claude passive rule files

scripts/
  check_sync.py                   drift gate: committed dist/ matches a fresh render of core/
  check_no_reference_text.py      fails the build if reference-prompt fingerprints appear
  mneme_emit.py                   the mneme seam (verification report -> decision record)

eval/evidence_metric.py           minimal honest metric (work-done rate, phantom count) from verify JSON
install.sh / install.ps1          root installers (all three steps)
docs/                             HOW-IT-WORKS, SDD-SUPERSET, ROADMAP, MNEME-SEAM
LICENSE / NOTICE / ATTRIBUTION.md Apache-2.0 and third-party attribution
```

---

## Status

v1.0.0, experimental.

- Native shell: 14 `/mergen.*` commands installed as Claude Code skills, plus the effort-mode hook and command.
- Spec Kit shell: a preset overriding 8 commands plus an extension adding 6 (`verify`, `rollup`, `go`, `lean`,
  `debt`, `govern`).
- The Governor sets risk-calibrated ceremony with a deterministic high-trust floor.
- Machine-readable verify (`verification-report.json`, `tasks-state.json`) and a minimal eval evidence metric.
- The mneme seam ships as a documented, network-free stub. The full writeback adapter is on the roadmap.
- No benchmark numbers are claimed. The methodology and a reproduction procedure are in `eval/`.
- `/effort max` requires one manual paste per session. The binary does not expose that control to hooks.
- Hooks are reinforcement nudges. Enforcement is the implement pipeline's adversarial verify stage, made a
  true gate by CI.

Further reading: [MERGEN.md](MERGEN.md), [docs/HOW-IT-WORKS.md](docs/HOW-IT-WORKS.md),
[docs/SDD-SUPERSET.md](docs/SDD-SUPERSET.md), [docs/ROADMAP.md](docs/ROADMAP.md),
[docs/MNEME-SEAM.md](docs/MNEME-SEAM.md).

---

## Not affiliated with Anthropic or GitHub

This is an independent tool. It is not affiliated with, endorsed by, or sponsored by Anthropic or GitHub, Inc.
"Claude" and "Claude Code" are trademarks of Anthropic. "Spec Kit" is a project of GitHub, Inc. The behavior
described here was observed in a specific Claude Code build and may change.

## License

Apache License 2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE).
