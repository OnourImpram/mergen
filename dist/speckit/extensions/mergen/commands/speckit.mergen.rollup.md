---
description: "Reconcile all feature specs into a single canonical project-state.md."
argument-hint: "Optional path filter or notes about which specs to include"
---

## User Input

```text
$ARGUMENTS
```

Consider the user input before proceeding. It may narrow which feature specs to include or add notes the synthesis should respect.

## mergen substrate (do this first)

This command runs under the mergen substrate: maximum reasoning effort plus Workflow orchestration. Before executing:

1. Ensure mergen is armed (the effort-mode marker `~/.claude/mergen.json` with `active: true`). If a `/mergen` command is available and the marker is absent, instruct the user to run `/mergen`.
2. Remind the user once, verbatim: "For genuine max effort, paste this into Claude Code now: `/effort max`". Do not block on it, but state that synthesis quality scales with it.
3. You MUST use the Workflow tool to orchestrate the synthesis lanes described below. Do not read all specs and write the output in this single context. Single-context monologue is exactly the failure mode this command exists to prevent.

## Discovery

Before launching the Workflow, collect the full input set in this context:

1. Enumerate all feature spec directories: look for `specs/*/spec.md` and `specs/*/plan.md` under the repository root. Also check `.specify/memory/` for any previously written `project-state.md`.
2. List the files found and, for each spec directory, note whether `plan.md`, `data-model.md`, `contracts/`, `research.md`, and `tasks.md` exist. This inventory is passed to every Workflow lane.
3. Load `.specify/memory/constitution.md` if it exists. Its governance constraints take precedence over any spec claim.

## Synthesis via the Workflow tool

Use the Workflow tool to run the following lanes. Lanes A through C run in parallel. Lane D is a barrier: it starts only after all three parallel lanes return.

### Lane A: Requirements reader

A subagent receives the full file inventory and reads every `spec.md` found. Its output is a flat, deduplicated list of functional requirements, user stories, and acceptance criteria drawn verbatim or closely paraphrased from the sources, each tagged with its origin file (e.g., `[specs/001-auth/spec.md:FR-003]`). It flags any requirement that appears in more than one spec with a `[CONFLICT]` or `[DUPLICATE]` marker so the synthesizer can adjudicate.

### Lane B: Plan and data-model reader

A subagent receives the full file inventory and reads every `plan.md` and `data-model.md` found. Its output is:
- A merged, deduplicated list of key entities and their attributes, noting conflicts.
- The agreed technical context (language, dependencies, storage, testing, target platform) derived from the union of all plans, with `[CONFLICT]` where plans disagree.
- A list of superseded requirements: requirements mentioned in earlier specs that a later spec explicitly overrides or removes.

### Lane C: Tasks and contracts reader

A subagent receives the full file inventory and reads every `tasks.md` and every file under `contracts/`. Its output is:
- The current completion status of every task across all features (`[X]` done, `[ ]` open, missing).
- Any API or data contracts that are still active (not superseded).
- A list of open tasks that belong to features already retired or superseded, which the synthesizer should mark as moot.

### Lane D: Synthesis and adversarial verification

After lanes A, B, and C return, a single synthesis subagent receives:
- The outputs of lanes A, B, and C.
- The constitution (if present).
- The user input from `$ARGUMENTS`.

It does the following in order.

**Step 1: Adjudicate conflicts.** For each `[CONFLICT]` or `[DUPLICATE]` flagged by lanes A or B, apply the rule: the most recent spec wins unless the constitution forbids it. Record each adjudication decision inline.

**Step 2: Drop superseded material.** Remove requirements, entities, contracts, and tasks that lane B or C identified as superseded or moot. Do not carry historical diffs forward. The output must describe what the system CURRENTLY does, not a change log.

**Step 3: Write `.specify/memory/project-state.md`.** The file structure must follow `.specify/templates/project-state-template.md` (the template is created in step 5 if it does not yet exist). Populate every section with the reconciled, current-state content. Do not leave placeholder text; if a section has no content, write "None identified."

**Step 4: Adversarial self-check (refute-biased).** Before returning, the synthesis subagent re-reads the file it just wrote and checks:
- Every functional requirement from lane A that was not dropped appears in the output.
- Every active contract from lane C appears or is explicitly noted as superseded.
- No section contains contradictory claims.
- No section carries historical change-log language ("previously", "was changed to", "in v2").
- The file follows the template structure without missing sections.

If the self-check finds any failure, the synthesis subagent corrects `.specify/memory/project-state.md` before returning. It returns `{ "pass": bool, "evidence": [...], "failures_corrected": [...] }`.

**Step 5: Create or update `.specify/templates/project-state-template.md`.** If the template does not yet exist, write it now with the canonical section headings used in the output above. The template uses placeholder text (`[FILL IN]`) for all values. This ensures future `/rollup` runs and `/specify` runs share the same structure.

## Inject note

State explicitly in the written `.specify/memory/project-state.md` under a `## Note` heading at the top: "This file is the canonical, current-state project description. It is injected into `/specify` runs to ensure new feature specs are consistent with the existing system."

## Done When

- [ ] All `specs/*/spec.md`, `specs/*/plan.md`, `specs/*/data-model.md`, `specs/*/contracts/`, and `specs/*/tasks.md` files were read across parallel Workflow lanes.
- [ ] Every conflict and duplicate was adjudicated, with the winning source recorded.
- [ ] All superseded requirements, entities, contracts, and tasks were dropped from the output.
- [ ] `.specify/memory/project-state.md` exists, follows the template structure, and contains no placeholder text or historical change-log language.
- [ ] The inject note is present at the top of `.specify/memory/project-state.md`.
- [ ] The adversarial self-check returned `pass: true` or all failures it found were corrected before completion.
- [ ] `.specify/templates/project-state-template.md` exists with canonical section headings and placeholder values.
