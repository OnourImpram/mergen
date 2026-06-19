---
description: "Ask up to 5 targeted clarification questions and encode the answers into the spec."
argument-hint: "Optional: path to spec.md, or leave blank to auto-detect from FEATURE_DIR"
scripts:
  sh: scripts/bash/check-prerequisites.sh --json --require-spec
  ps: scripts/powershell/check-prerequisites.ps1 -Json -RequireSpec
---

## User Input

```text
$ARGUMENTS
```

If the user provided a path or constraint above, prefer it when locating `spec.md`. Otherwise auto-detect from `FEATURE_DIR`.

## mergen substrate (do this first)

This command runs under the mergen substrate: maximum reasoning effort plus Workflow orchestration. Before executing:

1. Ensure mergen is armed (the effort-mode marker `~/.claude/mergen.json` with `active: true`). If a `/mergen` command is available and the marker is absent, instruct the user to run `/mergen`.
2. Remind the user once, verbatim: "For genuine max effort, paste this into Claude Code now: `/effort max`". Do not block on it, but the quality of ambiguity detection scales with it.
3. You MUST use the Workflow tool to run the analysis and encode lanes as described below. Do not execute all of this in a single context. The whole point of using the Workflow tool here is that a fresh, isolated context cannot rationalize away gaps the way the originating context tends to.

## Load context

1. Run the prerequisite script from repo root and parse `FEATURE_DIR` and `AVAILABLE_DOCS`.
2. Load `FEATURE_DIR/spec.md` (required). Also load if present: `plan.md`, `data-model.md`, `contracts/`, `research.md`, `.specify/memory/constitution.md`. These extend the surface to scan for underspecification.
3. Identify the template this spec was authored against. The canonical template is `.specify/templates/spec-template.md`. Its key sections are: User Scenarios and Testing, Requirements, Success Criteria, and Assumptions.

## Ambiguity scan (via the Workflow tool)

4. Use the Workflow tool to launch an **exhaustive ambiguity scan** in an isolated context. That context receives only the loaded spec and template, with no prior reasoning from this session. Its mandate is to find every underspecified area. Specifically it must check:

   - **User Scenarios and Testing**: missing priority levels, acceptance scenarios that are not independently testable, vague "Given/When/Then" steps, missing edge cases for boundary conditions and error paths.
   - **Requirements**: functional requirements that contain `[NEEDS CLARIFICATION]` markers, requirements using vague quantifiers (e.g. "fast", "large", "many") without measurable bounds, missing data retention or security requirements implied by the domain, and implicit behavioral assumptions encoded nowhere.
   - **Key Entities**: relationships described in prose only, cardinality not stated, attributes mentioned in scenarios but absent from the entity list.
   - **Success Criteria**: criteria that are not measurable as written, criteria that have no corresponding test strategy, missing performance or reliability targets if the feature is infrastructure-adjacent.
   - **Assumptions**: assumptions that are load-bearing for implementation (e.g. auth system reuse, storage medium, scale target) but stated so briefly that a planner would have to guess details, and silent assumptions present in the scenarios but absent from the Assumptions section.
   - **Cross-section consistency**: a user scenario names a behavior that no requirement covers, or a success criterion references an entity not defined anywhere.

   The scan context returns a ranked list of gaps. Each entry has: section, gap description, why it matters for correct implementation, and estimated blast radius if left unresolved.

## Question selection (via the Workflow tool)

5. Use the Workflow tool to launch a **question-selection** context. That context receives the ranked gap list from step 4. Its mandate is to select at most 5 questions, applying these rules:

   - Prefer gaps whose resolution changes architecture, data model, or acceptance criteria. Cosmetic gaps are skipped.
   - Merge gaps that share a root cause into one question (e.g. two missing cardinality gaps become "What is the expected relationship between X and Y?").
   - Each question must be self-contained: answerable without follow-up, and with a clear effect on a specific spec section.
   - Questions are ordered by blast radius descending: the gap that would most damage a planner if left unanswered comes first.
   - The output is a numbered list of at most 5 questions, each with: the question text, the section it targets, and the spec field or sentence to update once answered.

## Ask the user

6. Present all selected questions in a single batch. Do not ask them one at a time. Format:

   > **Clarification needed before planning can proceed.**
   >
   > **Q1 (targets: Requirements > FR-00X):** [question text]
   >
   > **Q2 (targets: User Scenarios > Story N):** [question text]
   >
   > ...

   Then wait. Do not proceed to step 7 until the user provides answers.

## Encode answers (via the Workflow tool)

7. Once the user answers, use the Workflow tool to launch an **encoding** context. That context receives: the current `spec.md` content, the question list from step 5, and the user's answers verbatim. Its mandate is to edit `spec.md` in-place, following these rules:

   - Apply each answer to the section and field identified in step 5.
   - Replace any `[NEEDS CLARIFICATION: ...]` markers that the answer resolves.
   - If the answer reveals a new entity or relationship, add it to Key Entities.
   - If the answer changes or tightens a success criterion, edit the criterion and make it measurable.
   - If the answer introduces a new explicit assumption, append it to Assumptions.
   - Do not delete content; only clarify, extend, or tighten it.
   - Do not invent information the user did not provide. If the user's answer is partial, encode what was given and leave the remainder explicitly marked `[STILL NEEDS CLARIFICATION: ...]`.

   The encoding context writes the updated `spec.md` to disk and returns a summary of every change it made, keyed by question number.

## Adversarial verify (via the Workflow tool)

8. Use the Workflow tool to launch a **verify** context. That context receives: the original `spec.md` content (before edits), the change summary from step 7, and the updated `spec.md` on disk. Its mandate is to confirm:

   - Every question that was answered has a corresponding edit in the file; no answer was silently dropped.
   - No pre-existing content was removed or overwritten with a weaker statement.
   - Remaining `[NEEDS CLARIFICATION]` and `[STILL NEEDS CLARIFICATION]` markers are listed explicitly (they are not a failure; omitting them from the report is).
   - The spec still validates against the template structure (all mandatory sections present).

   The verify context returns `{ "pass": bool, "changes_confirmed": [...], "remaining_gaps": [...], "failures": [...] }`. Default to `pass: false` when uncertain.

9. If verify returns `pass: false`, surface the failures and re-run step 7 with the failures appended as guidance. Do not mark the command complete until verify returns `pass: true`.

## Done When

- [ ] `spec.md` has been read and all four mandatory sections (User Scenarios and Testing, Requirements, Success Criteria, Assumptions) have been scanned for ambiguity via the Workflow tool in an isolated context.
- [ ] At most 5 targeted questions were identified and batched into a single prompt to the user.
- [ ] The user's answers have been encoded into `spec.md` in-place via the Workflow tool, with every answered gap updated and no pre-existing content removed.
- [ ] The adversarial verify context confirmed all changes are present in the file and returned `pass: true`.
- [ ] Any gaps the user did not answer are explicitly marked `[STILL NEEDS CLARIFICATION: ...]` in the file and listed in the final report.
- [ ] A summary of all changes made to `spec.md` has been reported, keyed by question number.
