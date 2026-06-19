---
description: "Create the feature specification from a natural-language description."
argument-hint: "Natural-language description of the feature to specify"
scripts:
  sh: scripts/bash/create-new-feature.sh
  ps: scripts/powershell/create-new-feature.ps1
---

## User Input

```text
$ARGUMENTS
```

Read the user input carefully before proceeding. It is the raw feature description that drives every lane below.

## mergen substrate (do this first)

This command runs under the mergen substrate: maximum reasoning effort plus Workflow orchestration.

1. Ensure mergen is armed (the effort-mode marker `~/.claude/mergen.json` with `active: true`). If a `/mergen` command is available and the marker is absent, instruct the user to run `/mergen` first.
2. Remind the user once, verbatim: "For genuine max effort, paste this into Claude Code now: `/effort max`". Do not block on it, but state that specification quality scales with it.
3. You MUST use the Workflow tool to orchestrate execution as described below. Do not draft the spec in this single context. Single-context drafting is exactly the failure mode this command exists to prevent: one perspective, one blind spot, unchallenged acceptance criteria.

## Pre-flight

Run the `create-new-feature` script (the `scripts:` entry above) from repo root. Parse its output to obtain:

- `FEATURE_DIR`, the absolute path to the newly created feature directory (e.g. `features/###-feature-name/`).
- `FEATURE_BRANCH`, the git branch name created for this feature.

If the script reports an error, stop and surface the message to the user before proceeding.

## Judge-panel specification (Workflow)

Use the Workflow tool to fan out the following lanes. All three drafting lanes run in parallel; the adversarial review lane runs only after all three draft lanes have returned.

### Lane 1, End-user lens

Mandate: author a complete draft `spec.md` from the perspective of the end user. Focus on user journeys, priority ordering (P1 before P2 before P3), and the independent testability of each story. Each acceptance scenario must be written as a concrete Given/When/Then triple that a human tester could execute without reading the source code. Do not speculate about implementation. Fill every section of the spec template: User Scenarios and Testing, Requirements, Success Criteria, Assumptions.

Input to this lane: the user input from `$ARGUMENTS` and the spec template structure (section names: User Scenarios and Testing, Requirements, Functional Requirements, Key Entities, Success Criteria, Assumptions).

Output: a fully populated draft spec document, clearly labeled "Draft A, End-user lens".

### Lane 2, Senior architect lens

Mandate: author a complete draft `spec.md` from the perspective of a senior architect who has seen this class of system fail in production. Identify the highest-risk integration points, data-consistency hazards, and scalability boundaries implied by the feature description. For each risk, write a functional requirement or acceptance scenario that would catch the failure before it ships. Do not invent features the user did not ask for, but do surface every assumption the user made implicitly. Fill every section of the spec template.

Input to this lane: the user input from `$ARGUMENTS` and the spec template structure.

Output: a fully populated draft spec document, labeled "Draft B, Senior architect lens".

### Lane 3, Customer-rejection lens

Mandate: author a complete draft `spec.md` as if you are a demanding customer who rejects vague acceptance criteria. Every acceptance scenario must be precise enough to be automated. Every functional requirement must be falsifiable. Replace any placeholder language ("System MUST handle errors gracefully") with a concrete, measurable statement. Fill every section of the spec template.

Input to this lane: the user input from `$ARGUMENTS` and the spec template structure.

Output: a fully populated draft spec document, labeled "Draft C, Customer-rejection lens".

### Lane 4, Adversarial reviewer (runs after lanes 1-3 complete)

Mandate: your job is to disprove that any of the three drafts is ready to ship. Receive Drafts A, B, and C. For each draft, score every acceptance scenario on three axes:

1. Missing, is there a scenario the feature obviously requires that no draft covers?
2. Contradictory, does any scenario conflict with another scenario in the same draft or across drafts?
3. Untestable, is any scenario too vague to automate or to verify by hand?

Return a structured findings report: for each finding, cite the draft letter, the section, the scenario or requirement identifier, the defect type (Missing, Contradictory, Untestable), and a one-sentence fix. Default to reporting a defect when uncertain. Do not soften findings.

Output: the adversarial findings report, labeled "Adversarial Review".

## Synthesis

After the Workflow returns all four lane outputs, synthesize a single canonical `spec.md` in this context:

1. Start from the draft that had the fewest adversarial findings.
2. Merge the strongest acceptance scenarios from the other two drafts, resolving any contradictions in favor of the more concrete and testable formulation.
3. Apply every fix the adversarial reviewer identified as mandatory (Missing or Contradictory defects). For Untestable defects, either sharpen the scenario or flag it with `[NEEDS CLARIFICATION: ...]`.
4. Populate the Feature Branch and Created fields at the top of the spec from the `create-new-feature` script output.
5. Ensure the final spec uses exactly the section names from the spec template: User Scenarios and Testing, Requirements (Functional Requirements, Key Entities), Success Criteria, Assumptions.

Write the finished spec to `FEATURE_DIR/spec.md`.

## Adversarial self-check before claiming done

Before marking this command complete, re-read the written `spec.md` and answer all three questions:

- Does every acceptance scenario have a concrete Given/When/Then triple?
- Is every functional requirement falsifiable without reading the implementation?
- Does at least one acceptance scenario cover each risk the architect lens identified?

If any answer is no, revise the relevant section and re-check. Only claim done when all three are yes.

## Done When

- [ ] The `create-new-feature` script ran without error and `FEATURE_DIR` and `FEATURE_BRANCH` are known.
- [ ] The Workflow tool was used to run lanes 1, 2, and 3 in parallel and lane 4 after they returned.
- [ ] The adversarial reviewer scored all three drafts and the findings report was produced.
- [ ] A single canonical `spec.md` was synthesized, incorporating mandatory adversarial fixes.
- [ ] `FEATURE_DIR/spec.md` exists on disk with all spec template sections populated (no unfilled placeholders except explicit `[NEEDS CLARIFICATION: ...]` markers).
- [ ] The adversarial self-check passed (concrete Given/When/Then, falsifiable requirements, architect risks covered).
