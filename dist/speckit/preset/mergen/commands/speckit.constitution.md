---
description: "Create or update the project constitution; keep dependent templates in sync."
argument-hint: "Optional: path to existing constitution, amendment description, or key principles to encode"
scripts:
  sh: scripts/bash/check-prerequisites.sh --json
  ps: scripts/powershell/check-prerequisites.ps1 -Json
---

## User Input

```text
$ARGUMENTS
```

Read the user input before proceeding. It may supply an amendment description, a list of principles to encode, a path to an existing constitution file, or guidance on scope. If it is empty, infer scope from the project context.

## mergen substrate (do this first)

This command runs under the mergen substrate: maximum reasoning effort plus Workflow orchestration. Before proceeding:

1. Ensure mergen is armed (the effort-mode marker `~/.claude/mergen.json` with `active: true`). If a `/mergen` command is available and the marker is absent, instruct the user to run `/mergen`.
2. Remind the user once, verbatim: "For genuine max effort, paste this into Claude Code now: `/effort max`". Do not block on it, but note that constitution quality scales with reasoning depth.
3. This command runs as a **single agent at max effort**. There is no fan-out. The Workflow tool is used only for the adversarial verify pass at the end, not for parallelizing authorship.

## Pre-authorship setup

1. Run the prerequisite script from repo root and parse `FEATURE_DIR` and `AVAILABLE_DOCS`.
2. Locate the constitution target. Check in order:
   - The path supplied in `$ARGUMENTS`, if any.
   - `.specify/memory/constitution.md` (the canonical location used by `implement.md` and other commands).
   - `.specify/memory/constitution.md` relative to repo root.
   - If none exists, you will create it at `.specify/memory/constitution.md`.
3. Load related context: IF EXISTS `plan.md`, `spec.md`, `tasks.md`, `data-model.md`, and any files under `contracts/`. These will be cross-checked after the constitution is written to identify sync requirements.
4. Load the constitution template structure from `.specify/templates/constitution-template.md` (sections: Core Principles, additional constraint sections, Governance, version metadata). The authored file must follow this template's section names and version footer.

## Interactive or argument-driven authoring

Proceed as follows depending on the user input.

**If $ARGUMENTS supplies an amendment description or principles:**
Work from that input directly. Do not ask clarifying questions unless a required section cannot be inferred (for example, no project name can be determined). If you must ask, ask at most two focused questions in a single message before proceeding.

**If $ARGUMENTS is empty:**
Conduct a brief interactive elicitation. Ask the user for the following in one message:
- Project name and one-sentence purpose.
- The two or three non-negotiable engineering or process constraints (examples: TDD mandatory, library-first architecture, no framework magic).
- Any governance rule about amendment process or authority.

Do not ask more than three questions. Use project context (plan.md, spec.md) to fill gaps silently.

## Constitution authoring

Write or update the constitution file using the template structure:

1. **Header**: `# [PROJECT_NAME] Constitution` with a one-line subtitle.
2. **Core Principles**: one named section per principle, each with a concise rule statement and the concrete implications. Mark any principle as `(NON-NEGOTIABLE)` where it must never be relaxed. Use roman numerals if there are four or more principles.
3. **Additional constraint sections** (as needed): for example, Security Requirements, Performance Standards, or Technology Stack. Include only sections that have real content for this project.
4. **Development Workflow** (if not already covered by a principle): describe the mandatory gates, review steps, or TDD cycle that all contributors must follow.
5. **Governance**: state that the constitution supersedes all other practices, how amendments are proposed and ratified, and what file to consult for runtime development guidance.
6. **Version footer**: `**Version**: [version] | **Ratified**: [date] | **Last Amended**: [date]`

If updating an existing constitution, preserve all existing ratified principles unless the user explicitly requests removal. Clearly mark new or amended sections with an inline comment `<!-- amended [date] -->`.

## Sync scan (post-authoring, mandatory)

After writing the constitution, scan each dependent artifact for references that must stay in sync:

- `plan.md`: check that architecture decisions referenced in the constitution are consistent with the plan's approach.
- `spec.md`: check that quality gates or interface contracts in the spec do not contradict any constitution principle.
- `tasks.md`: check that no task is framed in a way that would require violating a constitution rule.
- `data-model.md` and `contracts/`: check that data shapes and API contracts respect any constitution constraints on schema or versioning.

For each artifact that exists, produce a short sync-note: either "consistent" or a specific discrepancy with the line reference. List all sync-notes in a "Sync status" section in your response. Do not silently skip artifacts.

## Adversarial verify pass

Use the Workflow tool to run one adversarial verify lane in a separate context. That lane receives ONLY the written constitution file and the sync-notes, not your authoring reasoning. Its mandate is to disprove completeness. It must check:

1. Every section named in `constitution-template.md` is either present or explicitly justified as not applicable.
2. No principle is stated so vaguely that it cannot be tested against a concrete task or PR.
3. The version footer is present and well-formed.
4. Sync-notes are accurate: re-examine each flagged discrepancy and confirm the artifact reference is real.
5. The file is saved at the expected path.

The verifier returns `{ "pass": bool, "evidence": [...], "issues": [...] }`. Default to `pass: false` when uncertain.

If `pass: false`, address every issue the verifier raised, then re-run the verify lane once more. If it fails a second time, report the unresolved issues explicitly and do not claim the command is done.

## Done When

- [ ] The constitution file exists at the resolved path and follows the `constitution-template.md` structure.
- [ ] Every Core Principle section has a concrete, testable rule statement (not placeholder text).
- [ ] The Governance section states the amendment process and the supersession rule.
- [ ] The version footer is present with a valid date.
- [ ] All dependent artifacts (plan.md, spec.md, tasks.md, data-model.md, contracts/) have been scanned and sync-notes are reported.
- [ ] The adversarial verify lane returned `pass: true` with evidence, or all issues it raised are explicitly addressed and reported.
