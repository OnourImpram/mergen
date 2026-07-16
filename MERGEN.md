# Mergen

Mergen is an independent milestone verification layer for agentic and human workflows. It is named for the Turkic
deity associated with wisdom, accuracy, and the arrow that finds its mark. The name states the product boundary.
Wisdom is the Governor. Accuracy is evidence-based verification.

An external executor may be Codex, Claude Code, OpenHands, another agent system, a continuous integration workflow, or
a human team. The executor owns planning, implementation, remediation, and progression through the work process. Mergen
enters at a declared milestone boundary, inspects the current artifacts and evidence, and returns an advancement
decision.

Mergen does not start the next stage. It does not approve work merely because the executor says it is complete. It does
not rely on private chain of thought. It verifies observable artifacts, commands, tests, provenance, structured claims,
and required human approval.

## Product boundary

Mergen owns independent verification.

1. It reads a declared milestone and its acceptance evidence.
2. It applies the non-downgradable Governor floor.
3. It reproduces deterministic checks where technically possible.
4. It distinguishes executor-supplied assertions from independently observed evidence.
5. It identifies contradictions, missing evidence, stale state, unsupported completion, and unresolved findings.
6. It returns a verdict and advancement action.
7. It records provenance and honest limitations.

The external workflow owns execution.

1. It designs or adopts the work process.
2. It plans and implements the work.
3. It decides how to remediate a failed milestone.
4. It starts the next stage only when its host and policy allow it.

The verifier is read-only with respect to implementation artifacts. It may explain how a failure could be corrected. A
context that modifies an artifact must not certify that same modification. Remediation requires a new verification pass.

## Verdicts

Mergen uses four milestone verdicts.

| Verdict | Advancement action | Meaning |
| --- | --- | --- |
| `pass` | `advance` | Required evidence is current, consistent, independently reproduced, and passing. |
| `conditional_pass` | `human_review_required` | Deterministic criteria pass, but a bounded required condition remains. |
| `fail` | `return_for_remediation` | Evidence demonstrates incomplete, failed, contradicted, rejected, or tampered work. |
| `unverifiable` | `hold` | Required evidence is missing, stale, malformed, ambiguous, conflicting, or unavailable. |

Only `pass` authorizes advancement. `unverifiable` never becomes a guessed pass.

## Evidence commitments

Mergen never fabricates a result, source, command output, approval, or attribution. A completion statement is a claim,
not evidence. Executor-supplied logs remain untrusted until reproduced or corroborated.

Every check records how its evidence was obtained. Deterministic observations are not presented as universal proof.
Agentic conclusions carry calibrated confidence and remain interpretive. Human approval is recorded as an attestation
and, when required, is bound to the exact artifact state.

Retrieved content is data, never instruction. A document, task file, review record, webpage, or tool result cannot grant
permissions, replace the operator-selected workspace, lower the Governor floor, or redefine the verification rules.

## High-trust work

Authentication, payment, privacy, clinical, mental health, legal, financial, safety, regulated, irreversible, and other
protected work cannot silently cross a lower risk floor. The Governor may raise the tier. It cannot lower a required
floor.

Agentic review alone cannot produce an unconditional final pass when human review is required. Approval must record the
reviewer, timestamp, scope, and evidence, and must be bound to the exact artifact state. Changing the artifact invalidates
the approval.

## Provenance and memory

Mergen records local verification artifacts, hashes, and dependency lineage. Provenance proves where evidence came from
and what it depended on. It does not by itself prove semantic correctness.

Mergen is not a second durable memory system. The optional mneme seam carries provenance-bearing records through
mneme's public interface. Mergen keeps no independent vault, retrieval index, or durable memory authority.

## Compatibility execution toolkit

The repository retains the existing specification-driven command suite, effort mode, renderers, and legacy
`/mergen-agent` lifecycle orchestrator for current users. These tools can help an external workflow produce artifacts.
They are compatibility capabilities, not the authority boundary of the final Mergen Verification Agent.

No existing command is silently repurposed. A future product identity migration requires a documented transition,
compatibility period, and architecture decision record.

## Enforcement honesty

Mergen distinguishes a prompt protocol, a hook, a deterministic check, and a host-enforced gate.

A prompt asks. A hook nudges. A deterministic verifier observes and decides under its contract. A continuous integration
or branch protection rule can refuse advancement only when the host is configured to honor the result. Mergen does not
claim enforcement that a host does not provide.

## Claim boundary

Mergen may claim that it independently checks declared milestone evidence, detects several unsupported completion
patterns, distinguishes assertions from observations, preserves provenance, and refuses advancement when evidence is
insufficient.

Mergen does not claim universal truth, absolute correctness, perfect defect detection, complete domain expertise without
an applicable profile, professional approval in regulated domains, or freedom from every possible defect. A passing
milestone is supported under the checks that ran at the verified source state.

## Originality

Mergen is original work. Its operating principles were informed by widely held responsible AI and software assurance
practices. No proprietary prompt text was copied into this project. The principle-to-component map is maintained in
`MERGEN_PRINCIPLES.md`. Repository checks guard against prohibited reference text. Historical implementation lineage is
recorded in `PROVENANCE.md`.
