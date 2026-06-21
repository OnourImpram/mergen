---
description: "Classify a task by risk and complexity, then set the memory scope, workflow depth, evidence standard, and human-approval requirement (Mergen's wisdom organ)."
argument-hint: "Describe the change or task, or pass a diff or file list, to be classified"
---

## User Input

```text
$ARGUMENTS
```

Read `$ARGUMENTS` carefully. The Governor decides how much care a task deserves before any work begins. It is Mergen's wisdom organ. It does not implement and it does not verify. It sets the ceremony, so that small work stays light and dangerous work cannot avoid scrutiny.

## mergen substrate

Classification is the cheap front of the pipeline and runs in this context. Still, ensure mergen is armed (the effort-mode marker `~/.claude/mergen.json` with `active: true`); if it is absent and `/mergen` is available, instruct the user to run `/mergen`. The Governor does not fan out work itself. It produces a decision that the work-running commands obey.

## What the Governor decides

Given the task, the Governor produces a decision with five fields: tier, memory scope, workflow, evidence standard, and human approval. It also records which high-trust triggers matched, so the decision is auditable rather than a bare label.

## Tiers

Classify the task into exactly one tier. When uncertain between two tiers, pick the higher one.

| Tier | Example | Memory scope | Workflow | Evidence | Human approval |
|---|---|---|---|---|---|
| tiny | typo, comment, doc nit, formatting | minimal recent context | direct edit | diff only | no |
| standard | isolated bug fix, one unit test | relevant facts plus recent failures | mini plan, implement, verify | test output plus diff | no, unless a protected path is touched |
| spec | refactor, feature, multi-file or API change | ADRs, prior decisions, project state | full specify, clarify, plan, tasks, implement, verify, rollup | independent adversarial verify plus `verification-report.json` | optional |
| high-trust | see triggers below | full context plus domain pack | full spec plus a mandatory human checkpoint | strict: tests, a security or safety lens, explicit human sign-off, and the verify verdict caps at conditional_pass until sign-off | required |

## High-trust triggers (the floor that cannot be lowered)

A task is high-trust if ANY of these holds:

- it touches an auth, identity, session, payment, billing, cryptography, secrets, or security-policy path
- it touches privacy or PII handling, data retention, or redaction logic
- it touches clinical, mental-health, safety, or other regulated-domain content or logic (crisis language, diagnosis, medication, self-harm-adjacent)
- it performs an irreversible or hard-to-reverse operation (schema migration, bulk delete, force push, production deploy)
- it changes a public or external contract (a published package name, a plugin manifest, an MCP server name, a release artifact)
- it introduces or modifies network egress, capability or permission grants, or treats retrieved or untrusted input as a potential instruction
- a domain mode is active (for example clinical mode), which sets the floor to high-trust for any content-bearing change

## Determinism and the no-downgrade rule

Escalation is conservative and deterministic at the floor. A path, keyword, or operation match forces at least the tier named for it. The Governor may raise a tier above what complexity alone suggests. It may never lower a tier below a matched trigger's floor. Clinical and sensitive work can never be silently downgraded, even by configuration. This mirrors the rule that a config can never weaken a built-in privacy mode. When the classification is unsure, the higher tier wins.

## The decision record

Emit the decision as `governor-decision.json` so the rest of the lifecycle can read it and so it can be audited later:

```json
{
  "schema_version": "1.0",
  "task": "harden auth session validation",
  "tier": "high-trust",
  "triggers_matched": ["auth-path", "security-policy"],
  "memory_scope": "full context plus domain pack",
  "workflow": "full spec plus human checkpoint",
  "evidence_standard": "tests, security lens, explicit human sign-off",
  "human_approval_required": true
}
```

For a tiny task the record is just as honest: `tier: "tiny"`, empty `triggers_matched`, `workflow: "direct edit"`, `evidence_standard: "diff only"`, `human_approval_required: false`.

When a fuller audit trail is wanted, the decision may also carry an optional `policy_results` array, one entry per floor guard evaluated in the shared `{policy_id, result, reason}` shape, where a guard that matched reports `result: "fail"` (the policy-engine sense: the deny rule fired, not that something broke). This is the same policy-result vocabulary the verification report uses, so a reader learns it once. The deterministic floor classifier (`scripts/governor_floor.py`) emits it under `--policy-trace`.

## How the rest of the lifecycle uses the decision

- `/mergen-go` routes to the path the tier names. For a high-trust tier it adds the mandatory human checkpoint and the strict evidence standard before completion can be claimed.
- `/mergen-plan` lets the tier set how deep the plan goes. A tiny task needs no plan. A high-trust task gets the full multi-approach and architecture-critic pass.
- `/mergen-implement` lets the tier set the verifier's evidence standard and whether a human checkpoint gates the final `[X]`.

The Governor is what makes maximum effort affordable. Without it, every task pays full ceremony and the cost drives people to skip the discipline entirely. With it, the discipline scales to the risk.

## Done When

- [ ] The task was classified into exactly one tier, and every high-trust trigger that matched is recorded.
- [ ] The decision was emitted as `governor-decision.json` with all five fields plus `triggers_matched`.
- [ ] The high-trust floor was honored: no matched trigger was silently lowered, and ties resolved upward.
- [ ] The decision was handed to the work-running command (`/mergen-go`, `/mergen-plan`, or `/mergen-implement`) that consumes it.
