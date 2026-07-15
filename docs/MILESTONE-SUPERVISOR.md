# Milestone Supervisor

Mergen's authority layer is an independent, deterministic milestone supervisor. It sits outside the implementation
path. An implementation agent can propose that work is complete, but it cannot authorize its own advancement.

The supervisor consumes a verification report, its SHA-256 sidecar, the exact tasks-state input, repository
provenance, policy results, and any required artifact-bound human approval. It emits one machine-readable decision:

| Verdict | Decision | Meaning |
|---|---|---|
| `pass` | `advance` | The required evidence is complete, current, internally consistent, and passing. |
| `fail` | `block` | The evidence positively demonstrates failed, incomplete, rejected, or tampered work. |
| `unverifiable` | `block` | Evidence is missing, stale, malformed, ambiguous, or cannot be authenticated. |

There is no fourth path. `unverifiable` never degrades into a guessed pass.

## Trust boundary

`--root` is selected by the operator who starts the supervisor. Evidence paths must resolve inside that root.
Neither a verification report nor an external review record can replace the root or direct the supervisor to an
arbitrary workspace.

The supervisor does not edit source files, route implementation work, mark tasks done, or call a model. Its only
write is the requested decision artifact and its SHA-256 sidecar.

## External review claims

An optional review record may be observed. A negative or unresolved review blocks. A positive review is recorded,
but it is not used as proof that the reviewer is independent. Fields such as `independent: true`, `workspace_root`,
or a reviewer name are claims from untrusted data. The decision artifact therefore records:

```json
{
  "claimed_independent": true,
  "independence_verified": false,
  "used_as_positive_proof": false
}
```

Independent supervision comes from the separate deterministic authority process and direct evidence checks, not
from a self-description inside the evidence.

## Human approval binding

When `verification-report.json` says human review is required, a populated `human_review` object is necessary but
not sufficient. The approval must also carry a valid Mergen HMAC token for the exact report bytes. This prevents an
approval copied from one report from authorizing another.

Mergen's existing signer creates the token:

```bash
export MERGEN_SIGNING_KEY="$(python -c 'import secrets; print(secrets.token_hex(32))')"
mergen sign sign --artifact verification-report.json > approval.txt
```

Place only the hexadecimal value after `mergen-ack-token:` in a file inside the trusted root, or expose it through
`MERGEN_ACK_TOKEN`. The shared secret remains in `MERGEN_SIGNING_KEY`.

The HMAC proves that a holder of the shared secret authorized these exact bytes. It is not public-key identity or
third-party non-repudiation. That limitation remains explicit.

## Run the supervisor

After installing the repository in editable mode:

```bash
mergen-supervise \
  --root . \
  --report verification-report.json \
  --tasks-state tasks-state.json \
  --out milestone-decision.json
```

For a high-trust report:

```bash
mergen-supervise \
  --root . \
  --report verification-report.json \
  --tasks-state tasks-state.json \
  --approval-token-file approval-token.txt \
  --out milestone-decision.json
```

An optional external review can be observed without treating it as proof:

```bash
mergen-supervise \
  --root . \
  --report verification-report.json \
  --tasks-state tasks-state.json \
  --review-record external-review.json \
  --out milestone-decision.json
```

The command exits `0` only for `pass` and `advance`. It exits `1` for `fail` and `block`, and `2` for
`unverifiable` and `block`.

## Required evidence

A milestone can advance only when all applicable checks pass.

1. The report and tasks state are readable JSON objects inside the trusted root.
2. The report bytes match `<report>.sha256`.
3. The report source commit matches the current repository `HEAD`.
4. The verifier recorded a clean tree, and no later workspace changes exist outside the named evidence artifacts.
5. The tasks-state bytes match the digest recorded in report provenance.
6. Feature identifiers and task sets match exactly.
7. Every task is complete and has a non-ambiguous, evidenced pass.
8. Summary counts agree with task-level evidence.
9. No policy result is failed or unresolved.
10. Any required human review is complete and bound to the exact report bytes.

The output validates against `core/schemas/milestone-decision.schema.json`. Its own `.sha256` sidecar makes later
edits detectable.
