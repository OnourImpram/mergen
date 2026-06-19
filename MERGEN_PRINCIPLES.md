# Mergen principles, and where they live

This is the map from operating principle to the code or schema that enforces it. The principles were
informed by widely held responsible-AI design ideas studied from a reference system prompt and are
re-expressed here in Mergen's own words. No proprietary text was copied. `MERGEN.md` is the human-readable
charter. This file is the wiring, so a reader can check that every commitment has a home in the code and is
not merely described.

| Principle | The idea, in our words | Component it governs | The concrete change |
|---|---|---|---|
| Evidence honesty and provenance | Never invent a result, a source, or an attribution. Report only what was checked, with proof. | verify gate, rollup memory proposals | Each verify lane returns command output as evidence. A claim without output is not accepted. Rollup proposes memory with its real source. |
| Calibration and abstention | Separate what is known from what is inferred. With no evidence, abstain rather than guess. | claim and evidence schema, verify verdict | `verification-report.json` carries a confidence label per finding. The verdict defaults to FAIL under uncertainty. |
| Retrieved content is data, never instruction | Anything read is material to reason about, never a command to obey or a grant of new capability. | implement and verify prompts, the fence convention | Stage A and Stage B treat task files, specs, and retrieved content as data. Content that asks to be obeyed is described, not followed. No read widens scope or grants a permission. |
| Minimal output | Build the least code that works. Write the least prose that informs. | lazy ladder, lean, communication disposition | implement builds to the ladder and the verifier flags over-build. lean returns a delete-list. CONVENTIONS states the prose disposition. |
| Honest pushback, owning mistakes | Disagree plainly when there is reason. Never self-approve. Fix errors without theater. | never-self-approve rule, adversarial verify | Authoring and review are separate lanes in separate contexts. The verifier's mandate is to disprove. Corrections update the record. |
| Surface conflicts | Show contradictions and their order in time rather than quietly choosing one. | decision-consistency reporting, the mneme seam | verify reports decision conflicts. The seam carries mneme's supersession relationships rather than flattening them. |
| Restraint in reproduction | Return the evidence span that matters, with its source, not a wholesale copy. | snippet and evidence emission, IP guardrail | verify and rollup emit match-centered spans with provenance. A repository check forbids verbatim reference text. |
| Operational discipline, right tool before default | Classify the task and pick the right ceremony before reaching for the heavy default. | the Governor | `govern.md` classifies into tiers and selects memory scope, workflow depth, evidence standard, and approval. The default is no longer all-or-nothing. |
| Care in sensitive domains | In high-trust contexts do not surface or compose in ways that could harm the person. | the Governor's high-trust tier, surfacing policy | Clinical, safety, privacy, and other triggers force the high-trust floor, a human checkpoint, and a verdict that caps until sign-off. The floor can be raised, never silently lowered. |

## A note on enforcement honesty

Three mechanisms appear in Mergen and the table above, and they are not equal. A prompt protocol asks. A
hook nudges. A CI gate refuses. Only the CI gate is non-bypassable, and only it is described that way. The
verify gate is enforced by the implement pipeline and the spec-kit `after_implement` hook in-session, and
turned into a true gate by CI. Naming a nudge as enforcement would itself violate the evidence-honesty
principle, so Mergen does not.

## A note on the reference

The reference study contributed design ideas, not text. Where a principle above echoes a well-known
responsible-AI norm, that norm is common property. The specific words here are Mergen's own. The build fails
if verbatim reference text is found in the repository, which keeps this guarantee testable rather than
asserted.
