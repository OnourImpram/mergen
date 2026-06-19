---
description: "Route a request to the right SDD tier by complexity."
argument-hint: "Describe your change, feature, or task in plain language"
---

## User Input

```text
$ARGUMENTS
```

Read `$ARGUMENTS` carefully before proceeding. The entire routing decision depends on the nature of the request.

## mergen substrate

This command runs under the mergen substrate: maximum reasoning effort plus Workflow orchestration. Before classifying and routing:

1. Ensure mergen is armed (the effort-mode marker `~/.claude/mergen.json` with `active: true`). If the marker is absent and `/mergen` is available, instruct the user to run `/mergen`.
2. Remind the user once, verbatim: "For genuine max effort, paste this into Claude Code now: `/effort max`". Do not block on this, but note that routing quality and downstream execution both scale with it.
3. For any tier that fans out work (standard and mergen), you MUST use the Workflow tool. Do not execute multi-task plans in this single context. That single-context collapse is the exact failure mode mergen exists to prevent.

## Governor classification (policy source)

Classification follows the Governor. Run `/mergen.govern $ARGUMENTS` first and read its `governor-decision.json`. The paths below are the execution side of the Governor's tiers: tiny maps to the tinySpec path, standard to the standard path, and spec to the mergen path. A fourth tier, high-trust, runs the mergen path and adds the high-trust path's human checkpoint and strict evidence standard. A high-trust task can never be routed below that floor, even when its complexity alone looks moderate. The tiers and the high-trust triggers are defined in `/mergen.govern`.

## Complexity classification

Classify `$ARGUMENTS` into exactly one of the three tiers below. Apply the rule strictly. When uncertain between two tiers, pick the higher one.

### Tier A: tinySpec (trivial)

Criteria: the change touches a single file, adds or fixes one small thing (a constant, a typo, a one-line guard, a config value, a single failing test), requires no design, no new contracts, and no cross-file coordination. The full implementation fits in one isolated context without losing anything.

If the request meets all criteria, go to the **tinySpec path** below.

### Tier B: standard (medium feature)

Criteria: the change spans two to five files, or touches a clear module boundary, or requires a short design thought, or adds a user-visible capability. The normal SDD chain (specify, plan, tasks, implement, verify) is appropriate. Parallelism is useful but not critical.

If the request meets these criteria, go to the **standard path** below.

### Tier C: mergen (complex)

Criteria: any of the following apply: multiple subsystems or packages are involved, a new public contract or data model is introduced, the change is safety-critical or security-relevant, the request is ambiguous enough that a judge panel is needed to resolve it, or the expected task list is ten or more tasks. Full parallel orchestration, adversarial verification, and a dedicated constitution review are warranted.

If the request meets any one of these criteria, go to the **mergen path** below.

## tinySpec path

Do not spin up a Workflow for a one-button change. Excessive ceremony is its own failure mode.

1. State the tier classification and the single file you will touch.
2. Implement the change directly in this context using the Edit or Write tool.
3. Run the minimal verification: confirm the file exists with the expected content, run the targeted test if one exists, and report the result.
4. Mark done. No spec file, no tasks.md, no DAG needed.

Stop here. Do not proceed to the standard or mergen paths.

## standard path

1. State the tier classification and the files you expect to touch.
2. If `$ARGUMENTS` is underspecified, run `/mergen.clarify $ARGUMENTS` first (at most five questions, encode answers back before continuing).
3. Run `/mergen.specify $ARGUMENTS` to produce the spec. This command uses a judge-panel Workflow internally; you do not need to orchestrate it yourself.
4. Run `/mergen.plan` to produce `plan.md` with a short multi-approach generation and architecture-critic pass.
5. Run `/mergen.tasks` to produce `tasks.md` and `tasks-dag.json`.
6. Use the Workflow tool to run `/mergen.implement` over the task waves as described in the implement command. Each task goes through an isolated implementer lane and an adversarial verifier lane before it can be marked `[X]`. Do not collapse the waves into this context.
7. Run `/mergen.verify` as the required final gate. The pipeline will not advance without it.
8. Proceed to the Done When checklist below.

## mergen path

1. State the tier classification and the reasons it qualified as mergen.
2. Run `/mergen.clarify $ARGUMENTS` to resolve ambiguity before any spec work (at most five questions).
3. Run `/mergen.specify $ARGUMENTS`. The judge panel spawns three spec drafts (user lens, architect lens, prod-failure skeptic) and an adversarial reviewer in separate Workflow lanes, then synthesizes. Ensure the Workflow tool is used for this fan-out; do not collapse into one context.
4. Run `/mergen.constitution` if no constitution exists yet or if the spec introduces new governance constraints. Keep templates in sync.
5. Run `/mergen.checklist` to apply the requirements-quality checklist before any implementation begins.
6. Run `/mergen.plan`. A multi-approach generation lane and an architecture-critic lane run in parallel via the Workflow tool; the critic's mandate is to refute the leading approach, not to endorse it.
7. Run `/mergen.tasks`. The completeness-critic loop runs until no new tasks emerge, then emits `tasks-dag.json` with the full dependency DAG.
8. Run `/mergen.analyze` to surface cross-artifact inconsistencies (spec vs. plan vs. tasks vs. contracts) before a single line of code is written. Fix any flagged inconsistencies.
9. Use the Workflow tool to run `/mergen.implement` at maximum parallelism. Every task wave fans out via the Workflow tool into isolated implementer contexts and separate adversarial verifier contexts. The verifier's mandate is to disprove completion. A task is marked `[X]` only on a verifier-signed `pass: true` with filesystem and test evidence. Failed tasks are re-queued with the verifier's failure list; retries are capped at two. After the cap the task is left `[ ]` and surfaced in the report.
10. Run `/mergen.verify` as the required final gate: independent multi-lens verifiers (file-exists, spec-match, tests-pass, git-consistent) re-check every `[X]` task. Majority-or-FAIL. Any `[X]` that fails reverts to `[ ]` and is re-queued. The pipeline does not advance without it. A CI gate for your own project ships as `eval/ci/verify-gate.yml`. It fails the build when the committed verification report shows phantom or unverified work, and because it reads the committed artifact, the deepest guarantee rests on the verifier that produced it.
11. Run `/mergen.rollup` to reconcile all specs into `project-state.md`.
12. Proceed to the Done When checklist below.

## high-trust path

A high-trust task (per the Governor) runs the full mergen path above and then gates completion on a human checkpoint. Before reporting done, present the diff, the verifier evidence, and the matched high-trust triggers to the operator and wait for explicit sign-off. The verify verdict stays at conditional_pass until the operator approves. Do not auto-complete a high-trust task. This is the floor the Governor sets, and `go` must not lower it.

## Adversarial verification requirement

For both standard and mergen paths, adversarial verification is not optional and cannot be skipped. The verifier in each task pipeline receives only the task spec and the resulting diff, never the implementer's reasoning. Its explicit mandate is to find reasons the task is not complete. This separation of context is what makes mergen more reliable than single-context execution. If the Workflow tool is unavailable, state that clearly and do not proceed with a simulated single-context verification; escalate to the user instead.

## Done When

- [ ] Tier was classified (tinySpec, standard, or mergen) and the classification was stated with reasoning.
- [ ] For tinySpec: the change was made directly, the file was confirmed, and no unnecessary ceremony was added.
- [ ] For standard and mergen: every SDD step was routed to its named command, not collapsed into this context.
- [ ] For standard and mergen: the Workflow tool was used to fan out implementation and verification lanes; single-context execution did not occur.
- [ ] Every task is either verifier-confirmed `[X]` with filesystem and test evidence, or explicitly reported as failing with the verifier's failure list (no silent or assertion-only completions).
- [ ] The required verify gate passed for all `[X]` tasks.
- [ ] For high-trust: the operator signed off before any `[X]` was finalized, and the matched triggers were shown.
- [ ] For mergen: `project-state.md` was updated by `/mergen.rollup`.
- [ ] The user received a summary of tier, commands executed, verification results, and any remaining failures.
