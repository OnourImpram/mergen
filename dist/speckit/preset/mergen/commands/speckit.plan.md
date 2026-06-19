---
description: "Produce the implementation plan and design artifacts."
argument-hint: "Optional design constraints, preferred approach, or focus areas"
scripts:
  sh: scripts/bash/setup-plan.sh --json
  ps: scripts/powershell/setup-plan.ps1 -Json
---

## User Input

```text
$ARGUMENTS
```

Consider the user input before proceeding (if not empty); it may express design constraints, a preferred approach, or areas the architecture-critic should pay extra attention to.

## mergen substrate (do this first)

This command runs under the mergen substrate: maximum reasoning effort plus Workflow orchestration. Before executing:

1. Ensure mergen is armed (the effort-mode marker `~/.claude/mergen.json` with `active: true`). If a `/mergen` command is available and the marker is absent, instruct the user to run `/mergen`.
2. Remind the user once, verbatim: "For genuine max effort, paste this into Claude Code now: `/effort max`". Do not block on it, but state that plan quality scales with it.
3. You MUST use the Workflow tool to orchestrate the multi-approach generation and architecture-critic lanes described below. Do not produce a plan in this single context. Single-context plan generation is exactly the shallow, first-draft failure mode this command exists to prevent.

## Pre-planning

1. Run the setup-plan script from repo root and parse `FEATURE_SPEC`, `IMPL_PLAN`, and `SPECS_DIR` (absolute paths). The script copies the plan template if `plan.md` does not yet exist and returns the feature directory.
2. Load context: REQUIRED `spec.md`; IF EXISTS `research.md`, `quickstart.md`, and `.specify/memory/constitution.md` (governance constraints). If `spec.md` is absent, stop and tell the user to run `/mergen.specify` first.
3. Constitution check: scan the loaded constitution for architectural constraints (forbidden patterns, required patterns, complexity limits). Record violations that must be justified in the plan's Complexity Tracking table.

## Workflow execution (MULTI-APPROACH + ARCHITECTURE-CRITIC)

You MUST use the Workflow tool to run the following lanes. Do not collapse this into a monologue in the current context.

### Lane 1, Multi-approach generation (run in parallel)

Spawn two or three candidate-design agents in parallel. Each agent receives the full `spec.md`, any `research.md`, and the constitution, but not the other agents' outputs. Each agent produces one complete candidate covering:

- Chosen architecture pattern and rationale.
- Concrete project structure (real directory tree, not placeholder options).
- Data model sketch (entities, relationships, key fields).
- Module contracts (public interfaces, API surface, event boundaries).
- How it satisfies every requirement in the spec.
- Estimated complexity and known risks.

Suggested design lenses (assign one per agent):

- **Lean**: smallest implementation that satisfies the spec, deferring everything not required now. Apply the lazy ladder (stdlib, native platform feature, installed dependency, one line) before introducing any new abstraction or dependency.
- **Conventional**: standard layered or domain-driven design matching the detected stack.
- **Scalable**: design that handles the spec's scale and performance goals with headroom, accepting higher initial complexity.

If `$ARGUMENTS` names a specific approach, use it as one of the lenses rather than replacing all three.

### Lane 2, Architecture-critic (refute-biased, separate context)

After all candidate agents return, spawn a single architecture-critic agent in a separate Workflow context. Its mandate is adversarial: find reasons each candidate should be rejected. The critic receives all candidate outputs and the constitution. It must report, for each candidate:

- Over-engineering violations (complexity added beyond what the spec requires).
- Missed requirements (spec items not addressed by the design).
- Constitution violations (patterns forbidden or required but absent).
- Simpler alternative: could a stripped-down variant satisfy the spec equally well?
- The critic's ranked verdict: which candidate to adopt, with required modifications.

The critic defaults to skepticism. It may recommend a hybrid. It may reject all three and describe what a fourth design should look like.

### Lane 3, Synthesis (this context, after Lanes 1 and 2 complete)

After both lanes return, you (in this context) synthesize the final plan:

1. Select the candidate (or hybrid) the critic recommends, incorporating any required modifications.
2. Fill in `plan.md` (the file the setup-plan script created) using the plan-template structure: Summary, Technical Context, Constitution Check, Project Structure, Complexity Tracking.
3. Produce `research.md` if it does not already exist: summarize prior art, library choices, and any open questions the spec leaves unresolved.
4. Produce `data-model.md` if the design involves persistent or structured data: entities, relationships, field types, and key constraints.
5. Produce `contracts/` entries (one file per module boundary or API surface) if the design has non-trivial interfaces.
6. Record every constitution violation that the chosen design retains (because they are necessary) in the Complexity Tracking table with justification.

Do NOT produce tasks.md. That is the responsibility of `/mergen.tasks`.

## Adversarial verify before claiming done

After synthesis, use the Workflow tool to spawn a verifier agent in a separate context. Its mandate is to disprove completeness. The verifier receives only the produced `plan.md` (and companion artifacts) and the original `spec.md`. It checks:

1. Every requirement in `spec.md` is addressed in `plan.md` (no silent gaps).
2. The project structure is concrete: no placeholder option labels remain, all real paths are filled in.
3. Technical Context fields are resolved: no field says `NEEDS CLARIFICATION` unless the spec genuinely does not provide the information.
4. Constitution check section reflects the loaded constitution, not a generic placeholder.
5. Companion artifacts (`data-model.md`, `contracts/`) exist whenever the design requires them.

The verifier returns `{ "pass": bool, "gaps": [...] }`. If `pass` is false, return to Lane 3 synthesis, address each gap, and re-run the verifier. Do not report the plan as done until the verifier returns `pass: true` with evidence.

## Done When

- [ ] setup-plan script ran cleanly and `FEATURE_SPEC`, `IMPL_PLAN`, `SPECS_DIR` are resolved.
- [ ] All candidate-design agents completed (Lane 1) and architecture-critic returned a ranked verdict (Lane 2). Both ran in separate Workflow contexts, not in this context.
- [ ] `plan.md` is filled in from the chosen design: no placeholder option labels, no unresolved `NEEDS CLARIFICATION` fields where the spec provides the information, Complexity Tracking populated for any constitution violations.
- [ ] `research.md`, `data-model.md`, and `contracts/` exist whenever the design requires them.
- [ ] Adversarial verifier returned `pass: true` with evidence that all spec requirements are addressed.
- [ ] `tasks.md` is NOT created (that is the job of `/mergen.tasks`).
