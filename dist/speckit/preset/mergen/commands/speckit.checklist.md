---
description: "Generate a requirements-quality checklist (unit tests for requirements)."
argument-hint: "Spec file path or feature name, plus optional focus area (e.g. 'auth spec, focus: edge cases')"
---

## User Input

```text
$ARGUMENTS
```

Consider the user input before proceeding. It specifies the spec, feature, or focus area to derive checklist items from. If empty, scan the current feature directory for `spec.md` and infer the scope.

## mergen substrate (do this first)

This command runs under the mergen substrate: maximum reasoning effort plus Workflow orchestration. Before executing:

1. Ensure mergen is armed (the effort-mode marker `~/.claude/mergen.json` with `active: true`). If the marker is absent and `/mergen` is available, instruct the user to run `/mergen` first.
2. Remind the user once, verbatim: "For genuine max effort, paste this into Claude Code now: `/effort max`". Do not block on it, but note that checklist depth and adversarial coverage scale with reasoning effort.
3. You MUST use the Workflow tool to orchestrate the checklist generation as described below. Do not generate the checklist in this single context. Running a single-context monologue is exactly the failure mode this command exists to prevent.

## Pre-execution

1. Locate the feature directory. If a spec file path is given in `$ARGUMENTS`, resolve it. Otherwise look for `spec.md` under the nearest feature directory relative to the working directory.
2. Load context: REQUIRED `spec.md`. IF EXISTS `plan.md`, `tasks.md`, `data-model.md`, `contracts/`, and `.specify/memory/constitution.md`. These documents are the only ground truth for generating checklist items. Do not invent requirements that are not traceable to one of these documents.
3. Identify the focus area from `$ARGUMENTS` (e.g., "edge cases", "security", "data integrity", "API contract", "error handling"). If no focus is given, derive categories from the spec's own section headings.
4. Confirm the output path: `FEATURE_DIR/checklists/<focus-area-slug>.md`. If `checklists/` does not exist, create it.

## Workflow: parallel derivation lanes

5. Use the Workflow tool to fan out the following lanes in parallel. Each lane runs in an isolated context and receives only the documents listed for it, not the full session state.

   **Lane 1, Requirements analyst.**
   Receives: `spec.md`, focus area from `$ARGUMENTS`.
   Task: Extract every stated requirement, constraint, and acceptance criterion from the spec that falls within the focus area. For each one, draft a checklist item in imperative form: "Verify that X is true when Y." Assign sequential IDs starting at CHK001. Return a flat list of `{ id, category, text, source_line }` objects. Do not evaluate whether the requirements are good; only extract and restate them faithfully.

   **Lane 2, Gap analyst.**
   Receives: `spec.md`, `plan.md` (if available), focus area.
   Task: Identify requirements that are implied but not stated, boundary conditions not covered, and error paths not specified. For each gap, draft a checklist item of the form "Verify that [implied behavior] is defined and handled." Return a flat list with ids continuing from where Lane 1 ended (coordinate via a shared counter by agreeing that Lane 2 starts at CHK100 to avoid collisions; the synthesizer will re-sequence). Mark each with `type: gap`.

   **Lane 3, Contract and interface checker.**
   Receives: `spec.md`, `contracts/` directory (if available), `data-model.md` (if available).
   Task: For every API endpoint, event, data schema, or inter-module contract mentioned in the spec or contracts, draft checklist items that verify the contract is complete: input types are defined, output types are defined, error responses are specified, and invariants are stated. Return a flat list marked `type: contract`.

6. After all three lanes complete, run a single Workflow synthesis task:

   **Synthesis task.**
   Receives: the three flat lists from lanes 1, 2, and 3; the focus area; the full `checklist-template.md` template structure.
   Task: Merge all items, deduplicate overlaps (keep the more specific item), group by category derived from the spec's section headings, and re-sequence IDs as CHK001, CHK002, and so on. Map the result onto the `checklist-template.md` format: fill in the `[CHECKLIST TYPE]` header with the focus area, `[FEATURE NAME]` with the feature name, the `**Purpose**` line with a one-sentence description, and the `**Feature**` line with a relative path to `spec.md`. Replace every sample item in the template with the actual derived items. Emit the completed checklist as a Markdown string.

## Adversarial verification (mandatory attempt, warns on unresolved failures)

7. Before writing the file, use the Workflow tool to run an adversarial verify task in a separate isolated context.

   **Adversarial verifier.**
   Receives: the synthesized checklist Markdown, `spec.md`, and the focus area. It does NOT receive the reasoning from steps 5 or 6.
   Mandate: disprove completeness. Specifically check:
   a. Every section heading in `spec.md` that falls within the focus area maps to at least one checklist item.
   b. No checklist item is untraceable to a statement or implication in the provided documents.
   c. No checklist item is a duplicate of another with only surface wording differences.
   d. The template structure is followed: header fields are filled, no sample placeholder text remains, all items are in imperative "Verify that..." form, all IDs are unique and sequential.
   Return `{ "pass": bool, "failures": [ { "item_or_section": "...", "reason": "..." } ] }`. Default to `pass: false` when uncertain.

8. If the verifier returns `pass: false`, revise the checklist to address every listed failure, then re-run the adversarial verifier. Cap at two revision cycles. If the checklist still does not pass after two cycles, write it anyway, but prepend a `> WARNING:` blockquote at the top listing the unresolved failures so the user can address them manually.

## Output

9. Write the verified checklist to `FEATURE_DIR/checklists/<focus-area-slug>.md` using the resolved content from step 7 or 8.
10. Report: the output file path, the number of items generated per lane (requirements, gaps, contracts), the total item count after deduplication, and whether the adversarial verifier returned a clean pass.

## Done When

- [ ] The checklist file exists at `FEATURE_DIR/checklists/<focus-area-slug>.md`.
- [ ] Every item is traceable to a statement or implication in the spec or contract documents (no fabricated requirements).
- [ ] The file follows `checklist-template.md` exactly: header fields filled, no sample placeholder text, items in imperative form, IDs unique and sequential.
- [ ] The adversarial verifier returned `pass: true`, or unresolved failures are surfaced in a `> WARNING:` blockquote.
- [ ] The Workflow tool was used for parallel lane execution and adversarial verification (single-context generation is not acceptable).
- [ ] Completion reported with item count, lane breakdown, and verifier result.
