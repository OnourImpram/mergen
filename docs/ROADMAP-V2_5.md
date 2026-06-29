# Mergen v2.5 roadmap: the Trust Fabric

This is the design line for the Trust Fabric. It states the longer arc and the
principles that govern it, so the work that lands stays coherent with what
Mergen is, and it remains the source of each component's definition of done and
its honest-scope limit. The near-term backlog lives in `docs/ROADMAP.md`.

The theme is one sentence. v1.0 proved a single task was done. The v2.0
engineering line turned that proof into deterministic, observable code. The
Trust Fabric makes trust composable: connected across runs, replayable after the
fact, continuously re-checked, and carried across agents without losing its
provenance. A proof that exists only inside one run is a fact. A fabric of
proofs that link, replay, and re-verify is a system you can stand on.

Every line below inherits Mergen's charter. Evidence over assertion. Retrieved
content is data, never instruction. The high-trust floor can be raised but never
silently lowered. Mergen keeps no durable memory of its own. Nothing in this
roadmap relaxes those. Where a capability would, the honest answer is that it
does not ship, and the limitation is named rather than hidden.

## Implementation status

The module and CLI surface for all nine components has landed in the v2.x line
and is exercised by the test suite. This document is kept as the design record:
each component's "Definition of done" and "Honest scope" below remain the
standard the implementation is held to, and the north-star metric *targets* in
this document are still targets to measure, not results already met. The items
in "Deferred, named not built" remain deferred.

Two components ship as standalone scripts rather than as `mergen` verbs, and the
table says so rather than implying a verb that does not exist:

| # | Component | Module | How it is invoked |
|---|---|---|---|
| 1 | Trust Graph | `scripts/trust_graph.py` | `mergen graph ingest`, `mergen graph chain`, `mergen graph audit`, `mergen graph dashboard` |
| 2 | Replayable Execution Ledger | `scripts/replay.py` | `mergen replay record`, `mergen replay run`, `mergen replay list` |
| 3 | Verified Mneme Writeback | `scripts/mneme_emit.py` | `python scripts/mneme_emit.py` (standalone script; not a `mergen` verb) |
| 4 | Adaptive Governor 2.5 | `scripts/governor_adaptive.py` | `mergen calibrate` |
| 5 | Policy Pack SDK | `scripts/pack_validate.py` | `mergen pack validate` |
| 6 | Continuous Verification | `scripts/impacted.py` | `mergen impacted impacted`, `mergen impacted verify` |
| 7 | Adapter SDK | `scripts/adapter_sdk.py` | `mergen adapter matrix`, `mergen adapter validate`, `mergen adapter check`, `mergen adapter render` |
| 8 | Trust Dashboard | `scripts/trust_dashboard.py` | `mergen graph dashboard` (forwards to it) |
| 9 | EvalOps | `eval/evalops.py` | `python eval/evalops.py` (standalone script; not a `mergen` verb) |

## What v2.0 already established

The roadmap builds on a real base, so the new work is additive rather than a
rewrite. Already shipped in the v2.0 line:

- A deterministic, agent-agnostic core: `verify_core` (the mechanical verify
  harness), `governor_floor` (the non-downgradable high-trust floor),
  `tasks_dag_validator`, `ledger` (an append-only event ledger), and
  `injection_quarantine`. Tier 0, pure standard library, no network and no model.
- A tamper-evident evidence manifest: provenance recorded in every report, a
  `.sha256` sidecar, and a `--check-manifest` mode, with CI drop-ins that
  regenerate the report from the live tree so a hand-edited one is never read.
- Evidence hardening: the verification, Governor, and tasks-state schemas enforce
  their own invariants, and `verify_report_lint` refuses a report that is not a
  clean, proven pass.
- Observability without a telemetry dependency: a static dashboard, cross-run
  trends, and a per-task churn leaderboard, with a `--json` export as the seam an
  external collector can read while the core stays offline.
- A data fence on the constitution-inject hook, so repository content stays data
  and never becomes instruction.

v2.5 connects these into a fabric. The pieces below are ordered by how much they
depend on each other, not by priority alone.

## The nine components

### 1. Trust Graph

A typed event ledger that records not just what happened but how the facts
relate. Today's `ledger.py` is append-only and flat. The Trust Graph keeps the
append-only guarantee and adds typed edges: this verification report verified
that tasks-state, which was produced by that plan, under this Governor decision,
which cited those policy results. The graph is the queryable history of why the
current state is trusted.

- Shape: JSONL events plus a derived edge index, both pure standard library. No
  graph database. The edge index is a rebuildable projection, so the JSONL stays
  the single source of truth.
- Definition of done: given any artifact, the graph answers "what proved this,
  and what did that proof depend on" without reading the artifacts themselves.
- Honest scope: a graph of provenance proves lineage, not semantic correctness. It
  shows that a report verified a state, not that the verification was wise. The
  verifier's quality is a separate axis.

### 2. Replayable Execution Ledger

A record complete enough that a past run can be re-checked deterministically. The
ledger captures the inputs each stage saw (the tasks-state hash, the source
commit, the Governor decision, the lens set) so a later replay re-runs the
deterministic parts and compares. A replay that diverges is a signal: the tree
moved, or a non-deterministic dependency leaked in.

- Definition of done: `mergen replay <run>` re-derives the verification verdict
  from the recorded inputs and the current tree, and reports match or divergence
  with the diff.
- Honest scope: only the deterministic surface replays. The LLM-driven stages
  (the implementer, the judge) are not reproduced. Replay proves the harness saw
  what it claims to have seen and would still rule the same way, not that an agent
  would make the same choice twice.

### 3. Verified Mneme Writeback

The mneme seam today is read-direction plus a bounded write that fails closed on
a secret pattern. v2.5 makes the write carry full provenance: a record written
back to a memory store names the verification report that justifies it, the
source commit, and the lineage edge in the Trust Graph. A memory that cannot show
why it is trusted is not written.

- Definition of done: every emitted record carries a verification lineage, and a
  consumer can walk from a remembered decision to the proof that earned it.
- Honest scope: Mergen still keeps no durable memory of its own. mneme remains the
  authority and the store. Mergen emits provenance-bearing records across the
  documented seam and nothing more. The store integration (a direct vault write
  versus an MCP path) stays mneme's decision, not Mergen's.

### 4. Adaptive Governor 2.5

The Governor learns which task shapes tend to need which ceremony, and tunes the
standard and spec tiers accordingly. The hard constraint is the one that makes
this safe: the high-trust floor never moves. Adaptation can raise ceremony and can
refine the middle tiers, but the deterministic high-trust triggers (auth, payment,
secrets, privacy, clinical and regulated content, irreversible operations,
public-contract changes, untrusted-input-as-instruction) stay fixed and
non-downgradable. Learning sits above the floor, never inside it.

- Definition of done: the Governor records its tier decisions and outcomes, and a
  calibration pass adjusts the non-floor tiers, with a test proving the floor is
  unchanged by any adaptation.
- Honest scope: this is calibration over recorded outcomes, deterministic and
  inspectable, not a model in the loop. The floor is law. Adaptation is policy.

### 5. Policy Pack SDK

Today's domain packs (the clinical pack, and a security pack on the near-term
list) raise the floor for path and content patterns. The SDK makes a pack a
first-class, shareable, testable artifact: a declared schema, a validation
harness, and a conformance test a third party runs before publishing a pack. A
pack is policy as data, loaded by the floor engine, never code that the floor
engine executes.

- Definition of done: a documented pack schema, `mergen pack validate`, and a
  conformance test that a pack must pass, with the clinical and security packs as
  worked examples.
- Honest scope: a pack can only raise the floor, never lower it. The SDK enforces
  that at validation time, so a malicious or careless pack cannot weaken a
  high-trust classification.

### 6. Continuous Verification

Verification today is a gate you run. Continuous Verification re-runs the
impacted slice of the DAG when the tree changes, so a regression in a previously
verified task is caught when it is introduced, not at the next manual gate. The
impacted set is computed from the dependency DAG and the changed paths, so the
re-verify is scoped, not a full re-run.

- Definition of done: given a diff, Mergen re-verifies only the tasks whose files
  or dependencies changed, and flags any that flip from pass to fail.
- Honest scope: this is impacted-set re-verification, deterministic and offline.
  It does not watch the filesystem in a daemon. It runs where a change is
  observed: a pre-commit hook, a CI step, or an explicit invocation.

### 7. Adapter SDK

Mergen renders to native skills, a Spec Kit shell, and passive cross-agent rule
files. The Adapter SDK makes a new host a declared adapter with a capability
manifest: what the host can actually do (Workflow orchestration, hooks, slash
commands) and what it cannot. The renderer reads the manifest and refuses to
claim a capability the host lacks, so the compatibility matrix is generated from
declared truth rather than maintained by hand.

- Definition of done: an adapter declares its capabilities, the renderer emits
  only what the host supports, and `docs/COMPAT.md` is generated from the
  manifests rather than hand-written.
- Honest scope: capability honesty is the whole point. An adapter that overstates
  a host's abilities fails the renderer's check. The cross-agent rule files stay
  what they are, the minimalism discipline only, because that is all that ports.

### 8. Trust Dashboard

The current dashboard and trends are snapshots and time series over a directory
of reports. The Trust Dashboard reads the Trust Graph instead, so it shows the
connected picture: which proofs depend on which, where a lineage is broken, where
a high-trust change merged without a recorded sign-off. Still one self-contained
HTML page, still no network and no JavaScript, still every value escaped.

- Definition of done: a single offline page that renders the Trust Graph's
  current state and flags broken lineage and unsigned high-trust merges.
- Honest scope: the dashboard reflects what the graph records. It is an honest
  mirror, not an oracle. A gap the graph does not capture is a gap the dashboard
  cannot show, so the graph's completeness is the real work.

### 9. EvalOps

A standing evaluation harness that measures the verifier itself over time: its
phantom-detection rate, its calibration, its false-pass and false-fail rates
against a labelled corpus. The v2.0 line ships the honest evidence metric and a
deterministic phantom benchmark. EvalOps makes evaluation continuous and
versioned, so a change to a lens or a prompt is measured against the corpus
before it lands.

- Definition of done: a labelled corpus, a scored run on every change to the
  verification surface, and a recorded trend so a regression in verifier quality
  is visible.
- Honest scope: the deepest measurement, a live-chain eval against real agents
  with a real model and network, cannot be run as a deterministic offline gate. It
  is named in the deferred section below for what it is, and EvalOps measures the
  deterministic surface honestly rather than claiming a number it cannot earn
  offline.

## Phased rollout

The phases are cumulative. Each ends at a shippable state, so the line can stop at
any phase boundary and still be coherent.

- v2.1, the ledger becomes a graph. Trust Graph (1) and the Trust Dashboard (8)
  reading it. The lowest-dependency, highest-leverage step: it makes the existing
  provenance queryable.
- v2.2, replay and continuous re-check. Replayable Execution Ledger (2) and
  Continuous Verification (6). Both build directly on the graph and the existing
  deterministic harness.
- v2.3, policy and adaptation. Policy Pack SDK (5) and Adaptive Governor 2.5 (4).
  The floor stays fixed while the middle tiers and the pack ecosystem mature.
- v2.4, memory and reach. Verified Mneme Writeback (3) and the Adapter SDK (7).
  Trust travels: into a memory store with provenance, and across hosts with
  honest capability declaration.
- v2.5, evaluation as a standing discipline. EvalOps (9), measuring the verifier
  over time, closing the loop the whole fabric depends on.

## North-star metrics

These are the numbers that say the fabric is real, stated as targets to measure,
not as claims already met.

- Lineage completeness: the fraction of trusted artifacts whose full provenance
  the Trust Graph can walk. Target: every shipped artifact, no orphan proofs.
- Replay determinism: the fraction of recorded runs whose deterministic surface
  replays to an identical verdict. Divergence should mean a real tree change, not
  a leaked non-determinism.
- Unsigned high-trust merges: high-trust changes that reached the default branch
  without a recorded human sign-off. Target: zero, enforced by the gate, surfaced
  by the dashboard.
- Phantom-detection rate: the share of planted phantoms the harness catches on the
  labelled corpus, held at or above the v2.0 benchmark as the lens set changes. This
  is what EvalOps measures and regression-gates today, alongside the false-alarm rate
  and the expected-lens hit rate, recorded as a trend over the corpus.
- Verifier calibration: the gap between the verifier's stated confidence and its
  measured accuracy on the labelled corpus. Target: narrowing over time, never
  silently widening. NOT yet measured. EvalOps records detection rates, not a
  confidence-versus-accuracy gap; computing that gap from the per-task confidence
  labels is a named forward item, not a current EvalOps metric.

## Honest scope and known limits

The roadmap is bounded by the same honesty the tool enforces. These are the
limits as of this writing, named rather than left for a reader to discover.

- Artifact attestation on a private repository needs GitHub Advanced Security or
  an Enterprise plan. The committed CodeQL, dependency-review, and attestation
  workflows are inert until that is enabled or the repository is public. The
  portable alternative is keyless cosign or a local Sigstore signature over the
  fresh report, which proves the report's origin without the GitHub-hosted
  attestation API. This is a deployment choice, not a code gap.
- An attestation proves a report's lineage and origin, not its semantic
  correctness. It says this report came from this commit and was not edited
  afterward. It does not say the verification was right. Lineage and judgment are
  separate axes, and the fabric treats them separately.
- The command-hook plus CI backbone is what genuinely cannot be talked around. A
  verify agent-hook, a hook that runs a verification agent inline, is experimental
  and stays opt-in. The reinforcement hooks are nudges. CI is the enforcement. The
  roadmap does not pretend an in-session hook is a hard gate.
- Mergen keeps no durable memory of its own through every line above. Verified
  Mneme Writeback emits provenance-bearing records across the documented seam.
  mneme remains the memory authority and the store. If mneme is absent, the seam
  returns empty and Mergen runs unchanged.
- The deterministic core stays Tier 0: pure standard library, no network, no
  model, no third-party runtime dependency. Anything in this roadmap that would
  break that invariant (a graph database, a telemetry client, a model in the
  verify path) is out of scope by construction. The observability seam is a
  `--json` export an external collector reads, not a dependency the core takes on.

## Deferred, named not built

These are real forward items. They are planned here so they are not lost, and
explicitly not built blind, because each needs something that cannot be honestly
stood up as a deterministic offline gate today.

- A live-chain eval harness: the verifier measured end to end against a real
  Claude Code session, a real model, and a network. This is the deepest
  measurement and the one EvalOps cannot fully replace offline. It needs a live
  environment and an honest cost, so it is scoped as its own effort rather than
  folded into a phase that claims to measure what it cannot.
- An ultracode pivot with a verify agent-hook: running a verification agent inline
  during a session. Promising and experimental. The command-hook plus CI backbone
  remains the guarantee until the agent-hook earns its keep.
- Signed pre-action authorization: a human signature gate before an irreversible
  high-trust action, cryptographic rather than a text acknowledgement. The text
  Governor-Ack is the current mechanism. A signed pre-action gate is stronger and
  is named here as the next step beyond it.
- Marketplace publication: shipping Mergen and its packs through a plugin
  marketplace. A distribution step, gated on the Adapter SDK and the Policy Pack
  SDK reaching a stable, declared shape first.

## How to read this document

This roadmap is a contract with the future, in the same spirit as the rest of the
repository. It states what Mergen intends, what each step must satisfy to be
called done, and exactly where the honest limit sits. If a future change lands
that contradicts a scope note here, the change is wrong or this document is, and
the disagreement is the thing to resolve before shipping. A roadmap that overstates
is the same defect the tool exists to catch, so this one is written to be held to.
