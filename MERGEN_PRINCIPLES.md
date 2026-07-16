# Mergen principles and their implementation homes

`MERGEN.md` is the human-readable charter. This document maps each commitment to the code, schema, or process that
enforces it. The map separates the final verification authority from the compatibility execution toolkit.

| Principle | Meaning | Primary implementation home |
| --- | --- | --- |
| Executor and verifier separation | The executor may produce artifacts and claims. It cannot write the final Mergen verdict. A modifying context does not approve its own change. | `mergen_supervise.py`, milestone decision schema, separate verification contexts |
| Evidence before advancement | Completion statements and supplied logs are inputs, not proof. A pass requires current, corroborated evidence and fresh deterministic reproduction where available. | `scripts/verify_core.py`, `mergen_supervise.py`, report linter |
| Calibration and abstention | Deterministic observation, interpretation, human attestation, missing evidence, and conflict are labeled rather than blurred together. Uncertainty does not become a pass. | verification report schema, milestone decision schema, evidence classes |
| Non-downgradable risk floor | Protected work can raise the required review tier. Executor declarations cannot lower the independently reproduced floor. | `scripts/governor_floor.py`, `scripts/project_config.py`, supervisor risk comparison |
| Exact-state human approval | Required approval names the reviewer, timestamp, scope, and evidence, and is bound to the exact artifact bytes. A changed artifact invalidates approval. | `scripts/preaction_sign.py`, supervisor approval check |
| Retrieved content is data | Files, reviews, web content, task descriptions, and tool results cannot grant permission, replace the trusted root, or redefine verification rules. | path containment, injection quarantine, data fence convention |
| Read-only verification | Verification inspects artifacts and may write only its own report outputs. Remediation belongs to a different context and requires re-verification. | supervisor authority record, host integration contract |
| Provenance without overclaim | Hashes, commits, manifests, and Trust Graph edges establish lineage and dependency. They do not prove universal semantic correctness. | provenance fields, sidecars, Trust Graph, replay |
| Host honesty | A host adapter states whether it can invoke, display, or enforce a decision. Mergen does not claim enforcement the host does not provide. | adapter manifests and capability matrix |
| Minimal verified scope | Mergen runs applicable checks and records irrelevant capabilities as not applicable rather than forcing ceremony for its own sake. | Governor, verification profiles, capability records |
| No second durable memory | Mergen emits local verification and provenance artifacts. Durable memory remains optional and external. | mneme seam and provenance emission |
| Honest product claims | A pass is bounded by the profile, artifacts, permissions, and checks that ran. It is not a claim of perfect defect detection. | charter, README, decision limitations |

## Milestone verdict vocabulary

The final advancement decision uses four verdicts.

1. `pass` maps to `advance`.
2. `conditional_pass` maps to `human_review_required`.
3. `fail` maps to `return_for_remediation`.
4. `unverifiable` maps to `hold`.

Only `pass` advances. The schema enforces this relationship in both directions.

## Evidence class vocabulary

Each milestone check records how evidence was obtained.

1. `independently_executed`.
2. `independently_observed`.
3. `cryptographically_verified`.
4. `source_verified`.
5. `executor_supplied`.
6. `agentically_inferred`.
7. `human_attested`.
8. `unavailable`.
9. `conflicting`.

These labels describe provenance and epistemic status. They are not calibrated probabilities.

## Legacy task report confidence vocabulary

The existing deterministic task report retains three confidence labels for backward compatibility.

1. `extracted`. Direct file, test, or Git evidence was observed.
2. `inferred`. An agentic lens reasoned from indirect evidence. It is never a deterministic proof label.
3. `ambiguous`. Evidence is absent or conflicting. A milestone supervisor treats the criterion as unverifiable rather
   than converting uncertainty into a clean pass.

The machine-readable mirror is `CONFIDENCE` in `scripts/verify_core.py`. Tests assert that this vocabulary matches the
verification report schema.

## Compatibility execution toolkit

The command suite under `core/commands/`, the renderers, effort mode, and the legacy `/mergen-agent` orchestrator remain
available to current users. Their outputs can be verified by the independent authority layer. Their existence does not
make Mergen the owner of an external executor's planning or implementation process.

## Enforcement honesty

A prompt protocol asks. A hook nudges. A deterministic verifier observes and decides under its contract. A host gate
refuses only when the host is configured to honor the result. Branch protection, required checks, and human approval
remain explicit operator and host responsibilities.

## Originality

The principles were informed by widely held responsible AI and software assurance practices and are expressed in
Mergen's own words. No proprietary reference text is reproduced. Repository checks keep that commitment testable.
