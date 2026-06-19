---
description: "Non-destructive cross-artifact consistency and quality analysis."
argument-hint: "Optional focus area, artifact subset, or specific consistency check to prioritize"
---

## User Input

```text
$ARGUMENTS
```

Consider the user input before proceeding. If it names a specific focus area (for example, "spec vs plan only" or "constitution compliance"), narrow the checker lanes accordingly. If it is empty, run all lanes.

## mergen substrate (do this first)

This command runs under the mergen substrate: maximum reasoning effort plus Workflow orchestration. Before executing:

1. Ensure mergen is armed (the effort-mode marker `~/.claude/mergen.json` with `active: true`). If a `/mergen` command is available and the marker is absent, instruct the user to run `/mergen`.
2. Remind the user once, verbatim: "For genuine max effort, paste this into Claude Code now: `/effort max`". Do not block on it, but note that analysis depth scales with it.
3. You MUST use the Workflow tool to fan out checker lanes as described below. Do not perform all checks in this single context. Single-context serial checking is exactly the failure mode this command exists to prevent. Fan out first, then synthesize.

## Pre-analysis setup

1. Run the prerequisite script from repo root and parse `FEATURE_DIR` and `AVAILABLE_DOCS` (absolute paths).
2. Determine which artifacts are present. Load every artifact that exists: `spec.md`, `plan.md`, `tasks.md`, `data-model.md`, `contracts/`, `research.md`, and `.specify/memory/constitution.md`. Record which are absent; absent artifacts are flagged in the report but do not abort the run.
3. If `tasks-dag.json` exists, include it as a fourth source of ground truth alongside spec, plan, and tasks.

## Parallel checker lanes (Workflow tool, run all lanes concurrently)

Use the Workflow tool to spawn the following lanes in parallel. Each lane receives only the artifacts it needs, not the full context. Each lane is adversarially biased: its mandate is to find inconsistencies and defects, not to confirm that everything is fine.

### Lane 1: spec vs. plan consistency

Receives: `spec.md`, `plan.md`.

Checks:
- Every requirement in spec has a corresponding section or decision in plan. Flag requirements that plan ignores.
- Every architectural decision in plan is traceable to a requirement or constraint in spec. Flag plan decisions with no spec grounding.
- Terminology is consistent across both documents. Flag synonyms or conflicting definitions.
- Scope boundaries are aligned. Flag features mentioned in one document but absent in the other.

Returns a structured list: `{ "finding": "...", "severity": "critical|major|minor", "location": "spec L42 / plan L17" }`.

### Lane 2: plan vs. tasks consistency

Receives: `plan.md`, `tasks.md` (and `tasks-dag.json` if present).

Checks:
- Every phase or component in plan has at least one concrete task in tasks. Flag plan sections with zero task coverage.
- Every task in tasks maps to a plan component or decision. Flag orphan tasks with no plan ancestry.
- Task dependencies in tasks are internally consistent (no cycles, no missing prerequisites). Cross-check against `tasks-dag.json` if present.
- Effort and sequencing in tasks match the ordering implied by plan. Flag sequencing mismatches.

Returns the same structured finding list.

### Lane 3: tasks vs. spec consistency (requirements coverage)

Receives: `spec.md`, `tasks.md`.

Checks:
- Every functional requirement in spec is covered by at least one task. Flag uncovered requirements.
- Every acceptance criterion in spec has a corresponding verification task or test task. Flag criteria with no verification coverage.
- Tasks do not implement behavior that contradicts a spec constraint or out-of-scope boundary. Flag overreach.
- Non-functional requirements (performance, security, accessibility) have at least one task addressing each. Flag silent gaps.

Returns the same structured finding list.

### Lane 4: constitution and governance compliance

Receives: `.specify/memory/constitution.md` (if present), `spec.md`, `plan.md`, `tasks.md`.

Checks:
- All artifacts respect the naming conventions, prohibited patterns, and architectural constraints stated in the constitution.
- No artifact introduces a dependency, pattern, or approach the constitution forbids.
- If the constitution specifies mandatory sections (for example, a security review section or a data-model section), verify those sections exist in the relevant artifact.
- Flag any clause the constitution declares mandatory that is absent or contradicted in any artifact.

If `.specify/memory/constitution.md` is absent, this lane emits a single advisory: "No constitution found; governance compliance could not be checked."

Returns the same structured finding list.

## Adversarial verification before synthesis

After all lanes complete, each lane's findings are treated as claims, not conclusions. Before proceeding to synthesis:

- Verify that every finding cites a specific location (file, line range, or section heading). Discard any finding that cannot be located in the artifacts.
- For each "critical" finding, re-examine the source artifacts to confirm the inconsistency is real and not an artifact of ambiguous wording. Downgrade or remove false positives.
- This adversarial verification step is non-negotiable. Do not skip it to save time.

## Deduplication and severity ranking

Merge findings from all four lanes:

1. Deduplicate: if two lanes flag the same inconsistency (for example, a missing requirement flagged by both Lane 1 and Lane 3), merge into a single finding and note which lanes confirmed it.
2. Sort by severity: critical (blocks implementation or verification), major (likely to cause rework), minor (style, terminology, or low-risk gaps).
3. Group by artifact pair: spec-plan, plan-tasks, spec-tasks, constitution.

## Report (non-destructive output only)

Emit a structured analysis report. This command DOES NOT edit any artifact. It reports only.

The report contains:

- **Summary table**: one row per finding, with columns for severity, artifact pair, location, and brief description.
- **Detailed findings**: for each finding, the exact quoted text from each artifact that creates the inconsistency, the specific gap or conflict, and a recommended resolution (as a suggestion only, not an edit).
- **Coverage matrix**: a table showing which spec requirements have plan coverage, task coverage, and verification coverage. Mark each cell as COVERED, PARTIAL, or MISSING.
- **Constitution compliance status**: PASS, ADVISORY (constitution absent), or FAIL with specific clause references.
- **Artifacts analyzed**: list each artifact that was loaded and each that was absent.
- **Lane confidence**: for each lane, note whether it had all required inputs or was degraded by absent artifacts.

## Done When

- [ ] The Workflow tool was used to fan out all four checker lanes concurrently. Single-context serial checking is not acceptable.
- [ ] Adversarial verification was applied to all findings before synthesis. No finding is reported without a confirmed artifact location.
- [ ] Findings from all lanes are deduplicated and sorted by severity.
- [ ] The report includes the summary table, detailed findings, coverage matrix, and constitution compliance status.
- [ ] No artifact was modified. This command is strictly non-destructive.
- [ ] Absent artifacts are listed in the report; their absence does not suppress findings from the lanes that could still run.
