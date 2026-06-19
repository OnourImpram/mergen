---
description: "Generate a dependency-ordered tasks.md plus a parallel-wave DAG."
argument-hint: "Optional guidance, scope filter, or additional constraints for task generation"
scripts:
  sh: scripts/bash/setup-tasks.sh --json
  ps: scripts/powershell/setup-tasks.ps1 -Json
---

## User Input

```text
$ARGUMENTS
```

Consider the user input before proceeding. If it names a scope filter (for example, "US1 only" or "skip polish phase"), apply it during generation. If it is empty, generate the full task list.

## mergen substrate (do this first)

This command runs under the mergen substrate: maximum reasoning effort plus Workflow orchestration. Before executing:

1. Ensure mergen is armed (the effort-mode marker `~/.claude/mergen.json` with `active: true`). If a `/mergen` command is available and the marker is absent, instruct the user to run `/mergen`.
2. Remind the user once, verbatim: "For genuine max effort, paste this into Claude Code now: `/effort max`". Do not block on it, but note that task completeness and DAG correctness scale with it.
3. You MUST use the Workflow tool to run the completeness-critic loop and the DAG emission as described below. Generating the full task list in this single context and calling it done is exactly the failure mode this command exists to prevent.

## Pre-generation setup

1. Run the setup-tasks script from repo root and parse `FEATURE_DIR`, `AVAILABLE_DOCS`, and `TASKS_TEMPLATE` (absolute paths).
2. Load context. Required: `plan.md`, `spec.md`. If present, also load: `data-model.md`, `contracts/`, `research.md`, `quickstart.md`, and `.specify/memory/constitution.md`. Record which are absent. Missing optional files do not abort the run but narrow the task surface.
3. Identify every user story, acceptance criterion, and non-functional requirement stated in `spec.md`. Build a checklist of spec scenarios before writing a single task. This checklist drives the completeness loop below.

## Task generation (initial pass)

4. Using the `tasks-template.md` as your structural guide, draft the full `FEATURE_DIR/tasks.md`. Follow the template's section and phase conventions exactly:

   - **Phase 1: Setup**, project initialization and shared infrastructure.
   - **Phase 2: Foundational**, blocking prerequisites that all user stories depend on.
   - **Phase 3+: One phase per user story**, ordered by priority (P1 first). Each phase includes an optional test sub-section (write-and-fail-before-implement) and an implementation sub-section.
   - **Final phase: Polish and cross-cutting concerns**.

   For every task:
   - Assign a sequential ID (T001, T002, ...).
   - Mark parallelizable tasks `[P]` when they touch disjoint files and share no runtime dependency.
   - Attach a user story label `[US1]`, `[US2]`, etc., for every task that belongs to a story.
   - Include the exact file path the task will create or modify.
   - Write acceptance criteria inline as a brief note so the verifier in `/implement` has a target.

   Do not fabricate tasks for functionality not present in the spec or plan. Do not leave vague task descriptions.

## LOOP-UNTIL-DRY completeness critic (Workflow tool, cap 3 iterations)

This loop is the core mergen advantage for tasks generation. Run it via the Workflow tool, not in this context.

5. After the initial draft exists, use the Workflow tool to spawn a completeness-critic lane. The critic receives the spec-scenario checklist from step 3 and the current draft of `tasks.md`. Its sole mandate is adversarial: find spec scenarios that have no covering task.

   The critic checks:
   - Every functional requirement in `spec.md` has at least one task that implements it.
   - Every acceptance criterion in `spec.md` has at least one test task or verification note.
   - Every non-functional requirement (performance, security, accessibility, i18n) has at least one task addressing it.
   - Every entity in `data-model.md` (if present) has at least one task that creates or migrates it.
   - Every endpoint or contract in `contracts/` (if present) has at least one task that implements it.

   The critic returns: `{ "gaps": [ { "scenario": "...", "spec_location": "...", "gap_description": "..." } ] }`. If `gaps` is empty, the loop exits immediately. Do not continue iterating when there are no gaps.

6. For each gap the critic returns, add the missing tasks to `tasks.md`, assign IDs, and update the dependencies section. Then re-run the critic (step 5) with the updated draft. Cap at three iterations total. If gaps remain after three iterations, record them as known gaps in a `## Known Gaps` section at the bottom of `tasks.md` and proceed.

7. Once the loop exits dry (or the cap is reached), the `tasks.md` file is considered structurally complete. Write it to `FEATURE_DIR/tasks.md`.

## DAG emission (Workflow tool, parallel to final critic pass)

8. Use the Workflow tool to spawn a DAG-builder lane concurrent with the final critic pass. The DAG builder receives the finalized task list and produces `FEATURE_DIR/tasks-dag.json`.

   The JSON structure is an array of waves. Each wave is an array of task objects:

   ```json
   [
     [
       {
         "id": "T001",
         "files": ["src/models/entity.py"],
         "parallel": true,
         "depends_on": [],
         "test_task": "T010"
       }
     ],
     [
       {
         "id": "T002",
         "files": ["src/services/service.py"],
         "parallel": false,
         "depends_on": ["T001"],
         "test_task": "T011"
       },
       {
         "id": "T003",
         "files": ["src/models/other.py"],
         "parallel": true,
         "depends_on": [],
         "test_task": "T012"
       }
     ]
   ]
   ```

   Rules for wave assignment:
   - Tasks with no dependencies form wave 1 (or join the earliest wave where all their dependencies are satisfied).
   - Tasks whose `[P]` flag is set and whose file sets are disjoint are placed in the same wave.
   - Tasks that share a file with another task in the same wave must be serialized into separate waves.
   - A task's `test_task` is the ID of the test sub-task that must exist (and fail) before this task enters Stage A of `/implement`. Set to `null` if no test task exists for this task.
   - TDD ordering is enforced: every test task must appear in an earlier wave than its implementation task (or in the same wave if the test task has no other dependencies that delay it, as long as the test is written before the implementation within that task's pipeline).

   The DAG builder returns the JSON and writes it to `FEATURE_DIR/tasks-dag.json`. This file is the primary input `/implement` uses for wave-parallel execution. Its correctness directly determines parallelism quality.

## Adversarial verification before writing

9. Before writing the final files, spawn an adversarial verifier lane via the Workflow tool. The verifier receives `tasks.md` and `tasks-dag.json` and checks:
   - No task ID is duplicated.
   - Every `depends_on` reference points to a real task ID.
   - No cycle exists in the dependency graph (any task that transitively depends on itself is a critical error).
   - Every `test_task` reference points to a real task ID or is `null`.
   - Wave ordering is consistent: no wave contains a task whose dependency appears in a later wave.

   The verifier returns `{ "pass": bool, "errors": [...] }`. If `pass` is false, fix the reported errors before writing. Do not write a DAG known to be inconsistent.

## Write outputs

10. Write `FEATURE_DIR/tasks.md` using the verified, loop-dried draft.
11. Write `FEATURE_DIR/tasks-dag.json` using the verified DAG structure.
12. If a `## Known Gaps` section exists in `tasks.md`, surface it explicitly in the completion report so the user can decide whether to address the gaps before running `/implement`.

## Done When

- [ ] The setup-tasks script ran successfully and `FEATURE_DIR`, `TASKS_TEMPLATE` were resolved.
- [ ] The spec-scenario checklist was built from `spec.md` before any task was drafted.
- [ ] The Workflow tool was used to run the LOOP-UNTIL-DRY completeness critic. Single-context task drafting without a critic pass is not acceptable.
- [ ] The completeness-critic loop ran to dry (zero gaps) or exhausted three iterations with remaining gaps recorded in `## Known Gaps`.
- [ ] The Workflow tool was used to spawn the DAG-builder lane.
- [ ] `FEATURE_DIR/tasks-dag.json` was written with correct wave arrays, `id`, `files`, `parallel`, `depends_on`, and `test_task` fields for every task.
- [ ] The adversarial DAG verifier confirmed no duplicate IDs, no broken references, no cycles, and consistent wave ordering before the files were written.
- [ ] `FEATURE_DIR/tasks.md` follows the tasks-template structure: Setup, Foundational, per-story phases with `[P]` and `[USn]` labels, exact file paths, and a Dependencies section.
- [ ] Any known gaps are surfaced explicitly in the completion report.
