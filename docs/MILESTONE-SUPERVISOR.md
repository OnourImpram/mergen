# Milestone Supervisor

The Mergen milestone supervisor is an independent, deterministic authority process. It sits outside the implementation
path. An executor may claim that work is complete. It cannot write its own final Mergen decision or authorize its own
advancement.

The bundled supervisor currently verifies Mergen software task reports. The protocol is host neutral. Other artifact
profiles can be added without changing the executor and verifier separation.

## Inputs

The supervisor reads evidence produced by an external workflow.

1. `verification-report.json`.
2. `verification-report.json.sha256`.
3. The exact `tasks-state.json` named by report provenance.
4. The current Git source state.
5. Policy results and Governor risk information.
6. An optional external review record.
7. An optional exact state human approval token.

Every executor supplied field remains untrusted until it is reproduced or corroborated.

## Outputs

The supervisor emits machine-readable JSON, a SHA-256 sidecar, and human-readable Markdown.

| Verdict | Advancement action | Compatibility decision | Meaning |
| --- | --- | --- | --- |
| `pass` | `advance` | `advance` | Required evidence is current, consistent, independently reproduced, and passing. |
| `conditional_pass` | `human_review_required` | `block` | Deterministic criteria pass, but required exact state human approval is absent. |
| `fail` | `return_for_remediation` | `block` | Evidence demonstrates failed, incomplete, contradicted, rejected, or tampered work. |
| `unverifiable` | `hold` | `block` | Evidence is missing, stale, malformed, ambiguous, or unavailable. |

There is no guessed pass. Only `pass` authorizes advancement. The compatibility field `decision` exists for integrations
that understand only `advance` and `block`. New integrations should use `advancement_action`.

## Trust boundary

`--root` is selected by the operator who starts the supervisor. Evidence paths must resolve inside that root. Neither a
report nor an external review record can replace the root or direct the verifier to an arbitrary workspace. Path
traversal and symlink escapes are refused.

The supervisor does not edit source files, route implementation work, mark tasks complete, or call a model. Its only
writes are the requested decision artifact, its sidecar, and its Markdown rendering.

## Independent reproduction

A clean pass requires a fresh invocation of the deterministic verifier against the current repository. The executor
report remains an input claim until Mergen reproduces the applicable checks.

`--no-reproduce` exists for diagnostics. It always prevents a clean pass.

The supervisor compares the fresh risk level with the supplied report. A freshly detected high-trust surface that was
reported as a lower risk is a failure. This prevents an executor from silently lowering the Governor floor. When both
risk levels are valid, the higher tier is preserved. A recorded Governor trigger also requires the high-trust tier.

## Evidence classes

Each check records how its evidence was obtained.

| Class | Meaning |
| --- | --- |
| `independently_executed` | Mergen ran the deterministic check. |
| `independently_observed` | Mergen inspected current local state. |
| `cryptographically_verified` | Exact bytes matched a digest or approval token. |
| `source_verified` | A structured source was checked for consistency. |
| `executor_supplied` | The executor supplied the assertion. |
| `agentically_inferred` | An interpretive conclusion, not deterministic proof. |
| `human_attested` | A human decision was recorded. |
| `unavailable` | Required evidence could not be obtained. |
| `conflicting` | Evidence sources contradicted each other. |

A positive external review claim is recorded but is not used as proof of reviewer independence. Fields such as
`independent: true`, `workspace_root`, and reviewer names remain untrusted content.

```json
{
  "claimed_independent": true,
  "independence_verified": false,
  "used_as_positive_proof": false
}
```

A negative review can block. An unresolved review produces `unverifiable`.

## Human approval binding

When the effective risk level requires human review, a populated `human_review` record is necessary but not sufficient.
The approval must also carry a valid Mergen HMAC token for the exact report bytes. This prevents an approval copied from
one artifact state from authorizing another.

Create a local signing key and token.

```bash
export MERGEN_SIGNING_KEY="$(python -c 'import secrets; print(secrets.token_hex(32))')"
mergen sign sign --artifact verification-report.json > approval.txt
```

Place only the hexadecimal value after `mergen-ack-token:` in a file inside the trusted root. The secret remains in
`MERGEN_SIGNING_KEY`.

The HMAC proves that a holder of the shared secret authorized these exact bytes. It is not public-key identity or
third-party nonrepudiation.

## Run the supervisor

After installing the repository in editable mode:

```bash
mergen-supervise \
  --root . \
  --report verification-report.json \
  --tasks-state tasks-state.json \
  --out milestone-decision.json
```

For high-trust work:

```bash
mergen-supervise \
  --root . \
  --report verification-report.json \
  --tasks-state tasks-state.json \
  --approval-token-file approval-token.txt \
  --out milestone-decision.json
```

To observe a separate review record:

```bash
mergen-supervise \
  --root . \
  --report verification-report.json \
  --tasks-state tasks-state.json \
  --review-record external-review.json \
  --out milestone-decision.json
```

The output set is:

```text
milestone-decision.json
milestone-decision.json.sha256
milestone-decision.md
```

Exit codes are stable.

| Exit | Meaning |
| --- | --- |
| `0` | `pass`, `advance` |
| `1` | `fail`, `return_for_remediation` |
| `2` | `conditional_pass` or `unverifiable` |

## Required checks

A milestone can advance only when all applicable checks pass.

1. Evidence paths remain inside the trusted root.
2. The report and tasks state are readable JSON objects.
3. The report bytes match the sidecar digest.
4. The report source commit matches current `HEAD`.
5. The verifier recorded a clean starting tree.
6. The current worktree differs only by named evidence artifacts.
7. Tasks state bytes match report provenance.
8. Milestone identifiers and task sets match exactly.
9. Every task is complete and has a non-ambiguous, evidenced pass.
10. Summary counts agree with task-level evidence.
11. Policy results are complete and passing.
12. Deterministic evidence is freshly reproduced.
13. The supplied risk level does not downgrade the fresh Governor result.
14. Required human approval is complete and bound to exact report bytes.
15. Optional review records contain no unresolved or negative finding.

## Decision integrity

The decision includes a `source_state_hash` derived from report bytes, tasks state bytes, source commit, and the effective
Governor result. It also includes a `decision_hash` over the complete decision object except the hash field itself. The
serialized JSON receives a separate SHA-256 sidecar.

These controls make later edits detectable when at least one trust anchor is preserved. They are tamper-evident, not
tamper-proof against an attacker who can replace every artifact and every anchor.

## Schema

The output validates against `core/schemas/milestone-decision.schema.json`, schema version `1.1`. The schema enforces the
relationship between verdict and advancement action. `pass` must map to `advance`. Every other verdict must block.

## Honest limitations

The bundled profile understands the Mergen software task report contract. It does not yet provide complete academic,
design, game, data science, or generic artifact profiles. Provenance establishes lineage. It does not prove universal
semantic correctness. A passing decision means that the checks which applied were supported by the evidence available
at the verified source state.
