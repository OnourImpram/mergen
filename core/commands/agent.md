---
description: "The Mergen Agent: arm, govern, and route a task through the full SDD lifecycle in one command. The single entry point that orchestrates the 14 /mergen-* skills without replacing them."
argument-hint: "Describe the change, feature, or task in plain language"
---

## User Input

```text
$ARGUMENTS
```

Read `$ARGUMENTS` carefully. This is the Mergen Agent, the single entry point that turns a plain-language task description into a fully governed, verified execution. It does not replace the 14 `/mergen-*` skills; it orchestrates them. A user who wants granular control can still call any `/mergen-*` skill directly. The Agent is for when you want the whole lifecycle in one command.

## What the Agent does

The Agent runs four phases in order. Each phase delegates to an existing Mergen skill or mechanism. The Agent itself does not implement, verify, or classify; it sequences the skills that do.

1. **Arm** ensure the mergen substrate is active (max reasoning effort plus standing Workflow orchestration).
2. **Govern** classify the task by risk and complexity, producing `governor-decision.json`.
3. **Route and execute** run the Governor's chosen tier (tinySpec, standard, mergen, or high-trust) by delegating to `/mergen-go`.
4. **Report** surface a one-screen summary of what ran, what passed, and what remains.

## Phase 1: Arm

Before any classification or execution, ensure the mergen substrate is active. The effort marker has one owner, the `/mergen` command; this Agent checks it, it does not write it.

1. Check whether the effort-mode marker exists at `~/.claude/mergen.json` with `active: true`.
2. If the marker is absent and `/mergen` is available, instruct the user to run `/mergen` once to arm the mode. Do not write the marker yourself; the effort-mode command is its single owner, and duplicating that write here would split the marker contract across two places.
3. Remind the user once, verbatim (the genuine native `max` tier only opens through the interactive command, so this one paste is the single manual step):

> For genuine max effort, paste this into Claude Code now: `/effort max`

Do not block on the paste. Do not repeat the reminder. Proceed to Phase 2.

## Phase 2: Govern

Run the Governor. The Agent does not classify the task itself; the Governor is the single classifier, and the Agent respects its decision.

1. Call `/mergen-govern $ARGUMENTS` and read the resulting `governor-decision.json`.
2. Extract the `tier` field (`tiny`, `standard`, `spec`, or `high-trust`).
3. Extract the `human_review_required` field and the `triggers_matched` list.
4. If the Governor output is missing or genuinely ambiguous between two tiers, take the higher one. This is the no-downgrade rule: when unsure, the tier goes up, never down.
5. State the classification to the user in one line:

> Governor tier: **{tier}**. Triggers matched: {triggers_matched or "none"}. Human review required: {yes/no}.

Proceed to Phase 3.

## Phase 3: Route and execute

Delegate to `/mergen-go`. The Agent does not re-derive the routing; `/mergen-go` reads the Governor's tier and runs the matching execution path.

1. Call `/mergen-go $ARGUMENTS`.
2. `/mergen-go` will:
   - Read the Governor's tier from `governor-decision.json`.
   - Run the matching path:
     - `tiny` runs the tinySpec path (direct edit, minimal verification).
     - `standard` runs the standard path (specify, plan, tasks, implement, verify).
     - `spec` runs the mergen path (full SDD lifecycle with Workflow fan-out).
     - `high-trust` runs the mergen path plus a mandatory human checkpoint.
   - Use the Workflow tool to fan out implementation and verification lanes for the standard and spec tiers. Do not collapse into this context.
   - Run `/mergen-verify` as the required final gate.
   - For high-trust: present the diff, the verifier evidence, and the matched triggers to the operator and wait for explicit sign-off before finalizing.

3. Do not interfere with `/mergen-go`'s execution. The Agent's job is to sequence, not to second-guess the router. If `/mergen-go` reports a failure, surface it in Phase 4; do not retry or route around it here.

## Phase 4: Report

After `/mergen-go` completes, produce a one-screen summary. The summary is honest: it reports what passed, what failed, and what the user should do next.

```markdown
## Mergen Agent report

**Task:** {one-line summary of $ARGUMENTS}

**Governor tier:** {tier}
**Triggers matched:** {triggers_matched or "none"}
**Human review required:** {yes/no} ({if yes: "completed" or "PENDING"})

**Execution path:** {tinySpec / standard / mergen / mergen + high-trust checkpoint}

**Commands executed:**
- /mergen-govern (done)
- /mergen-go (done)
- {list each /mergen-* skill that /mergen-go called, in order, with pass or fail}

**Verification:**
- Verifier verdict: {pass / fail / conditional_pass}
- Tasks verified: {N}/{M}
- Phantom completions: {0 or count}
- Report artifact: {path to verification-report.json}

**Remaining:**
- {list any tasks that failed verification, with the verifier's failure reason}
- {if high-trust and sign-off is pending: "Human sign-off required before this task is finalized"}

**Next step:**
- {if all passed: "Task complete. The verification report is the proof."}
- {if failures: "Address the failures above, then re-run /mergen-agent on the remaining tasks."}
- {if high-trust pending: "Review the diff and sign off, or reject with a reason."}
```

## What the Agent does NOT do

- **Does not classify.** The Governor classifies. The Agent reads the Governor's decision.
- **Does not implement.** The `/mergen-implement` skill implements, in an isolated Workflow lane.
- **Does not verify.** The `/mergen-verify` skill verifies, in a separate context.
- **Does not re-route.** `/mergen-go` routes. The Agent delegates and reports.
- **Does not skip the verify gate.** Verification is the required final step for the standard and spec tiers. The Agent never reports done without it.
- **Does not auto-complete high-trust.** If the Governor set `human_review_required: true`, the Agent surfaces the checkpoint and waits. It does not finalize.

## Relationship to the existing skills

The 14 `/mergen-*` skills are unchanged. They remain available for granular, step-by-step use. The Agent is a fifteenth skill that calls them in the right order. A user who wants to run only `/mergen-specify` and then stop can still do so. The Agent is for when you want the whole lifecycle in one command.

| Existing skill | Role | Called by Agent? |
|---|---|---|
| `/mergen-govern` | Classify task | Yes (Phase 2) |
| `/mergen-go` | Route by tier | Yes (Phase 3) |
| `/mergen-specify` | Write spec | Indirectly (via /mergen-go) |
| `/mergen-clarify` | Ask questions | Indirectly (via /mergen-go) |
| `/mergen-checklist` | Requirements check | Indirectly (via /mergen-go) |
| `/mergen-plan` | Implementation plan | Indirectly (via /mergen-go) |
| `/mergen-tasks` | Task DAG | Indirectly (via /mergen-go) |
| `/mergen-analyze` | Cross-artifact check | Indirectly (via /mergen-go) |
| `/mergen-implement` | Execute tasks | Indirectly (via /mergen-go) |
| `/mergen-verify` | Verify gate | Indirectly (via /mergen-go) |
| `/mergen-rollup` | Synthesize state | Indirectly (via /mergen-go) |
| `/mergen-constitution` | Author constitution | Indirectly (via /mergen-go) |
| `/mergen-lean` | Over-build review | No (optional, user-invoked) |
| `/mergen-debt` | Debt ledger | No (optional, user-invoked) |
| `/mergen` (effort-mode) | Arm/disarm | Yes (Phase 1, the Agent instructs the user to run it) |

## Done When

- [ ] The mergen substrate was armed (marker present, or the user was instructed to run `/mergen`), and the `/effort max` reminder was shown once.
- [ ] The Governor's tier was read from `governor-decision.json` and stated to the user.
- [ ] `/mergen-go` was called and its execution path completed (tinySpec, standard, mergen, or high-trust).
- [ ] The verify gate ran for the standard and spec tiers (not skipped).
- [ ] For high-trust: the human checkpoint was surfaced and the operator's decision recorded.
- [ ] A one-screen report was produced with: tier, commands executed, verification verdict, remaining failures, and next step.
- [ ] The report is honest: phantom completions, failed tasks, and pending sign-offs are surfaced, not hidden.
