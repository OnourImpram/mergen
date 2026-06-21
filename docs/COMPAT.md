# Compatibility matrix

Which parts of Mergen need which runtime. The short version: the deterministic
core that proves work was done needs nothing but Python. The prompt and
orchestration layer needs a host that runs slash commands, and the full
multi-agent behavior needs Claude Code. This page states exactly where each line
falls, so a reader knows what they get on their own stack without guessing.

The split matters because it is the honest form of the project's claim. The
guarantee that a tool proves the work lives in the agent-agnostic core. The
prompts ask and the hooks nudge, and those need their host. Naming a host-only
feature as portable would be the kind of over-claim the charter forbids.

## Tier 0. Agent agnostic, pure Python

Standard library only. No network, no model, no Claude Code. Runs anywhere
Python 3.9 or newer runs. This is the layer that makes Mergen's verification and
governance real regardless of which agent, if any, sits above it.

| Component | What it does | Entry point |
|---|---|---|
| `scripts/verify_core.py` | Mechanical verify harness (file-exists, tests-pass, git-consistent), emits `verification-report.json` | `python scripts/verify_core.py` or `mergen verify` |
| `scripts/governor_floor.py` | Deterministic high-trust floor and the `policy_results` audit trail | `python scripts/governor_floor.py` |
| `scripts/tasks_dag_validator.py` | Validates a `tasks-dag.json` (unique ids, resolvable refs, no cycles, earlier-wave deps) | `python scripts/tasks_dag_validator.py --gate` |
| `scripts/project_config.py` | Reads `.specify/mergen.toml`, applies the floor-raising overlay | imported by `governor_floor --config` |
| `scripts/injection_quarantine.py` | Scans, fences, and classifies untrusted text | `python scripts/injection_quarantine.py` |
| `scripts/ledger.py` | Append-only event ledger | `python scripts/ledger.py` |
| `scripts/mneme_emit.py` | Emits, reads, and writes decision records across the mneme seam (`--write DIR`, redaction preflight). Each record is a verified writeback: it carries the trust-graph node id of the report that earns it, so a remembered decision walks back to its proof (`--read --proof-graph`). Dedup keys on the source commit, so the same feature at a new commit is a new decision, not a duplicate | `python scripts/mneme_emit.py` |
| `scripts/dashboard.py` | Static, offline HTML dashboard over a directory of verification reports (verdicts, phantom counts, provenance) | `python scripts/dashboard.py <dir>` or `mergen dashboard <dir>` |
| `scripts/tasks_status.py` | Summarizes a `tasks-state.json` (done versus pending, per task). The Spec Kit analog is `specify status` | `python scripts/tasks_status.py <file>` or `mergen status <file>` |
| `scripts/tasks_to_issues.py` | Renders GitHub issue stubs from a `tasks.md` (it renders, it does not create). The Spec Kit analog is taskstoissues | `python scripts/tasks_to_issues.py <file>` or `mergen issues <file>` |
| `scripts/trends.py` | Cross-run verification trends and per-task churn over a directory of reports, with a per-feature spec churn rollup and a side-by-side comparison when several directories are passed (self-contained HTML, or a `--json` metrics export). The snapshot dashboard's time dimension | `python scripts/trends.py <dir> [<dir>...]` or `mergen trends <dir>` |
| `scripts/verify_report_lint.py` | Refuses a verification report that is not a clean, proven pass (proofless pass, ambiguous pass, summary fail, conditional, unsigned high-trust). Stdlib enforcement of the report schema | `python scripts/verify_report_lint.py <file-or-dir>` or `mergen verify-lint` |
| `scripts/pr_guardian.py` | Summarizes and gates a verification report for a pull request (verdict, claimed versus verified, phantom count, sign-off, findings), failing on a phantom or an unsigned high-trust report. Reuses `verify_report_lint`. The drop-in CI Action is `eval/ci/pr-guardian.yml` | `python scripts/pr_guardian.py <report> --out comment.md` |
| `scripts/trust_graph.py` | Typed, append-only provenance graph over the ledger: ingest a verification report into typed nodes and edges, walk the proof chain that justifies an artifact, audit broken lineage and unsigned high-trust nodes. The rebuildable edge index keeps the JSONL the single source of truth. It proves lineage, not semantic correctness | `python scripts/trust_graph.py ingest --graph <jsonl> <report>` or `mergen graph ...` |
| `scripts/trust_dashboard.py` | One self-contained offline HTML page over a trust graph: the connected provenance (which report proved which state at which commit), broken lineage, and unsigned high-trust nodes. No network, no JavaScript, every value escaped. It mirrors lineage, it does not judge correctness | `python scripts/trust_dashboard.py <graph>` or `mergen graph dashboard --graph <graph>` |
| `scripts/replay.py` | Records a verification run (the tasks-state it verified, the source commit, the per-task verdicts) and replays it against the current tree by re-running verify_core, reporting match or divergence. The recorded input is the tasks-state, the variable is the tree. Only the deterministic surface replays, the LLM stages are not reproduced | `python scripts/replay.py record --report <r> --tasks-state <s> --runs <jsonl>` or `mergen replay ...` |
| `scripts/impacted.py` | Continuous verification: from a set of changed paths and the tasks DAG, computes the impacted task slice (directly changed plus transitive dependents) and re-verifies only that slice, flagging any task that flips from pass to fail against a prior report. Deterministic, offline, runs in a pre-commit hook or CI step | `python scripts/impacted.py verify --tasks-state <s> --dag <d> --changed <p> --against <r>` or `mergen impacted ...` |
| `scripts/pack_validate.py` | The Policy Pack SDK conformance check: validates a domain policy pack against `core/schemas/policy-pack.schema.json` and the invariants a schema cannot express (name matches the directory, only the raise-only fields appear, the path list is a single-line array the 3.9 and 3.10 fallback reader recovers). A pack can only raise the floor, never lower it | `python scripts/pack_validate.py validate domains/<name>` or `mergen pack validate ...` |
| `scripts/governor_adaptive.py` | The Adaptive Governor: a deterministic review-scope tier (by change size) that raises but never lowers the content floor, plus calibration that tunes the scope thresholds from the recorded governor history. The floor data is imported read-only, so adaptation can never weaken the floor. Every threshold that calibrate emits is clamped to `[minimum, shipped default]`, so a calibrated governor is never more permissive than the audited default. Raw thresholds passed straight to govern bypass that clamp and are the caller's responsibility, but even so they can only move the scope lower bound, never the floor | `python scripts/governor_adaptive.py calibrate --ledger <jsonl>` or `mergen calibrate ...` |
| `eval/benchmark.py` | Deterministic phantom-detection benchmark, no LLM | `python eval/benchmark.py --gate` |
| `eval/evidence_metric.py` | Evidence metric and CI gate over a committed report (`--strict` also lints each report for integrity) | `python eval/evidence_metric.py --gate` |

A worked end-to-end run of this tier is in [`examples/verify-demo/`](../examples/verify-demo/README.md).

To use the verify harness outside this repository you do not need to install
anything. `scripts/verify_core.py` is a single self-contained standard-library
file. Copy it, or install the repo and call `mergen verify`, which forwards to
it verbatim.

## Tier 1. Needs a renderer install, then runs in that host

The 14 SDD commands are authored once in `core/commands/` and rendered into one
of two shells. The rendered command is a prompt, so it needs a host that runs
slash commands. The single-source contract is in `core/CONVENTIONS.md`.

| Component | Needs | Notes |
|---|---|---|
| `/mergen-*` native skills | Claude Code | `dist/native/build_native.py` renders to `~/.claude/skills/mergen-<name>/SKILL.md` |
| `speckit.*` and `speckit.mergen.*` | Spec Kit | `dist/speckit/build_speckit.py` renders a preset (8 overrides) and an extension (6 additions) |
| `verify_gate.py`, `constitution_inject.py` | Claude Code hooks | Reinforcement nudges via `settings.json`. No-ops where the hook system is absent |

## Tier 2. Needs Claude Code specifically

| Component | Why |
|---|---|
| Workflow orchestration in every command | The multi-agent fan-out (judge panel, refute-biased verifier, wave-parallel pipeline) is Claude Code's Workflow tool. Another host that runs the prompt gets the single-context reading of it, not the fan-out |
| `/effort max` | Claude Code's effort ladder. A hook cannot set the live effort value, so one manual paste is irreducible |
| Effort-mode standing directive | `effort-mode/hooks/mergen_prompt_hook.py` is a Claude Code `UserPromptSubmit` hook |

## Tier 3. Optional integrations

| Component | Behavior when absent |
|---|---|
| mneme memory seam | `scripts/mneme_emit.py` round-trips Mergen's own emitted record shape and, with `--write DIR`, persists records into a directory you name. With no mneme vault present it returns an empty result. mneme is optional and consumed only across the documented seam |
| Non-Claude agent rule files | `dist/agents/build_agents.py` ports only the lazy-ladder minimalism discipline to Cursor, Windsurf, Cline, Copilot, and Kiro as passive rule files. The SDD engine and the Workflow orchestration do not port, and the renderer does not claim they do |

## One-line summary

If all you want is the proof that work was done and was minimal, Tier 0 is the
whole answer and it runs on plain Python. Everything above Tier 0 is about how
the work gets produced, and that is where the host starts to matter.
