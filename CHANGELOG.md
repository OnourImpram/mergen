# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/), and the project aims to follow
[Semantic Versioning](https://semver.org/).

## [Unreleased]

## [2.0.0] - 2026-06-28

Engineering line that turns the guarantees the v1.0.0 prompts describe into
deterministic code. The theme is a tool proves over a prompt promises. This is the
first public release: the v2.0.0 tag closes the engineering line below.

### Added

- Evidence calibration on every verified task, a non-verdict-changing observability
  signal that ranks how strongly the passing lenses ground a pass. The deterministic
  harness records `evidence_tier` (executed when a test ran and passed, corroborated
  when only a static lens passed, none when no lens passed) and `evidence_strength`
  (the share of total lens weight that passed, in 0 to 1), with the summary counting
  `untested_passes`. The per-lens weights encode a strict ordering (tests over git
  over file presence), not a calibrated probability, and nothing here changes a
  verdict: a failed hard gate still fails the task, and the Governor floor and
  human_review_required are untouched, so a soft signal can never weaken a hard gate.
  The report stays on schema_version 1.0 because the fields are additive and optional.
- Evidence hardening, so a verdict without proof cannot pass as one. The three
  JSON schemas now enforce their own invariants declaratively. A verification
  report whose task is verified `pass` must carry concrete evidence (a file, a
  test, or recorded output) and cannot be labelled `ambiguous`, and a high-trust
  report must flag that human review is required. A Governor decision with a
  matched high-trust trigger must sit at the high-trust tier and must require
  human approval. The tasks-state status set gains `blocked` and `conditional`.
  The runtime counterpart is `scripts/verify_report_lint.py` (`mergen verify-lint`),
  a pure-stdlib linter that refuses a report that is not a clean, proven pass
  (proofless pass, ambiguous pass, summary fail, conditional, unsigned high-trust),
  enforcing the same required surface and pass rules the schema declares with no
  schema-validation dependency. `eval/evidence_metric.py --strict` runs the gate
  and this lint together. The `summary` block records a machine-readable
  `human_review` sign-off state, so an unsigned high-trust report fails the lint
  by default.
- A PR Guardian (`scripts/pr_guardian.py`) and its drop-in CI Action
  (`eval/ci/pr-guardian.yml`). The script reads one verification report and emits
  a compact markdown summary a CI step posts as a pull-request comment (verdict,
  risk level, tasks claimed versus verified, phantom count, human sign-off state,
  and any integrity finding), gating the same way `verify-lint` does and failing
  additionally on any phantom completion. The gate decision reuses
  `verify_report_lint` rather than re-deriving the rules, so the two cannot drift.
  The Action regenerates the report from the live tree, comments with the gh CLI
  (no third-party action beyond the SHA-pinned setup steps), and the exit code is
  the gate. Tier 0, pure standard library, no network in the script itself.
- A deterministic, agent-agnostic core, pure standard library, no network and no
  model. `scripts/verify_core.py` (the mechanical verify harness that emits
  `verification-report.json`), `scripts/governor_floor.py` (the non-downgradable
  high-trust floor and a `policy_results` audit trail), `scripts/tasks_dag_validator.py`
  (unique ids, resolvable refs, no cycles, earlier-wave deps), `scripts/ledger.py`
  (an append-only event ledger), `scripts/injection_quarantine.py` (scan, fence,
  classify untrusted text), and `scripts/project_config.py` (a floor-raising
  project overlay). A real, no-LLM phantom-detection benchmark in `eval/benchmark.py`.
- `mergen_cli.py`, one cross-platform CLI with `install`, `doctor`, `uninstall`,
  `upgrade`, and an agent-agnostic `verify` verb that forwards to the harness.
- The mneme seam read direction (`scripts/mneme_emit.py` parses Mergen's own
  emitted record shape) and shareable domain packs (`domains/clinical`).
- A bounded mneme write-to-vault direction (`scripts/mneme_emit.py --write DIR`):
  persists a decision record into a directory you name, with a producer-side
  redaction preflight that fails closed on a secret pattern and duplicate
  detection that skips a substantively-equal record. The store integration
  (direct vault write versus MCP) stays open. Each emitted record now carries a
  record type (decision, trajectory, failure, or policy), an automatic sha256 of
  the exact report file it came from, and the verification lineage (the source
  commit, tasks-state hash, and verifier version) read from the report's own
  provenance, so a remembered decision can be walked back to the proof that earned
  it without shelling git. Substantive duplicate detection still ignores the
  metadata, so a re-verify is not double-recorded.
- A static, offline verification dashboard (`scripts/dashboard.py`, `mergen
  dashboard <dir>`): one self-contained HTML page over a directory of reports,
  showing each verdict, phantom-completion count, and provenance, with every
  report value HTML-escaped. No network, no JavaScript, pure standard library.
- The cross-run dimension over that same corpus (`scripts/trends.py`, `mergen
  trends <dir>`). Where the dashboard is a snapshot, this is the time view:
  phantom-completion and work-done-rate history across runs with an inline SVG
  sparkline, and a per-task churn leaderboard ranking the tasks that most often
  flip verdict or return as phantoms, the spec patterns that reliably fight the
  verifier. Metrics are computed from each report's schema-required `tasks`
  array, so they hold for any conforming report. A `--json` flag emits the same
  metrics as a machine-readable export, the honest observability seam: an
  external collector can ingest it while mergen core keeps no telemetry
  dependency and makes no network call. Self-contained HTML, no JavaScript.
- Spec-pattern clustering and cross-corpus aggregation in `mergen trends`. The
  same churn now rolls up per feature (a spec churn leaderboard), so a whole spec
  that keeps fighting the verifier surfaces above its individual tasks. Because a
  feature is the natural namespace for a task, the rollup never pools a task id
  across two features. Passing more than one reports directory compares corpora
  side by side, each read independently so a task id is never pooled across two
  unrelated projects. The `--json` export carries the per-feature rollup and, in
  multi-corpus mode, a corpus comparison alongside each corpus in full (schema
  `mergen-trends/1.1`).
- Spec Kit diagnostic parity in the agent-agnostic CLI. `mergen status`
  (`scripts/tasks_status.py`) summarizes a `tasks-state.json` (done versus
  pending, per task), the `specify status` analog. `mergen issues`
  (`scripts/tasks_to_issues.py`) renders GitHub issue stubs from a `tasks.md`,
  the taskstoissues analog, and renders rather than creates because creating an
  issue is a side effect that needs your GitHub auth. `mergen doctor` now also
  self-checks the shipped JSON schemas are well-formed.
- A worked end-to-end example (`examples/verify-demo/`) and a compatibility
  matrix (`docs/COMPAT.md`) mapping which features need which runtime.
- A tamper-evident evidence manifest. `verify_core.py` records provenance
  (verifier version, source commit, working-tree-clean, and a sha256 of the exact
  tasks-state it verified) in every report, writes a `<report>.sha256` sidecar on
  `--out`, and a `--check-manifest` mode recomputes the hash to catch an edited
  report (and with `--require-fresh`, a report whose source commit no longer
  matches HEAD). Tamper-evident, not tamper-proof: meaningful when CI recomputes
  the sidecar from the live tree rather than trusting it.
- Two stronger CI drop-ins that close the committed-report gap. `eval/ci/verify-gate-live.yml`
  regenerates the verification report in CI from the live tree (running `verify_core`
  against the real files and tests) and gates on that fresh report, so a hand-edited
  committed report is never read. `eval/ci/verify-attest.yml` adds an OIDC-bound
  Sigstore attestation over the fresh report via `actions/attest-build-provenance`,
  so `gh attestation verify` fails on any later edit. Enforcing them (branch
  protection, required check) stays a repository-admin setting. Mergen's own CI
  dogfoods the live pattern against `examples/verify-demo/`.

### Changed

- A data fence on the constitution-inject hook, so repository content stays data
  and never becomes instruction. The hook re-surfaces a project constitution's
  section headings each turn. It now frames them as policy data to weigh, not
  commands, and states they do not override system, developer, user, safety,
  privacy, or tool-permission boundaries. Each heading is sanitized (control and
  format characters stripped, fullwidth and combining-mark obfuscation folded,
  length capped) and screened for override or exfiltration phrasing, with a
  matching heading flagged as untrusted rather than relayed. The flag is a
  best-effort tripwire, not a guarantee. A heading worded as a plain operational
  step with no trigger vocabulary can still pass the screen, and there the framing
  is the defense, not the flag.
- One confidence vocabulary, defined once in `MERGEN_PRINCIPLES.md` and mirrored
  by `verify_core.CONFIDENCE`, with a test asserting the code and the schema enum
  cannot drift. One `policy_results` shape shared between the Governor decision
  and the verification report, with a test asserting the two schemas stay identical.
- `verify.md` makes tests-pass a hard gate alongside file-exists, aligned with the
  harness's any-applicable-lens-fails rule.
- A mypy --strict CI gate over the Python surface. The bash and PowerShell command
  logic collapsed into one Python layer. The test suite inverted into focused
  per-module files.
- CI hardened with a Windows test job (the platform that produces the BOM the
  readers now tolerate) and a coverage job with a fail-under floor in
  `[tool.coverage.report]`, measuring statement coverage over the full Python
  source surface. The floor starts below the measured value and is meant to
  ratchet upward.

### Fixed

- Removed a stale confidence vocabulary from the docs. `tasks-state.json` never
  carried a confidence label. The label lives on the verification report.
- Honest scoping of the `PROVENANCE.md` no-seed-tokens claim, effort-patcher
  parity with the native patcher, and installer Python-version strings.

## [1.0.0] - 2026-06-19

Initial release of Mergen, the execution backbone for AI coding agents. Mergen is the execution half of the
Agent Continuity Stack. mneme is the memory half. mneme remembers why. Mergen judges what a task needs and
proves it was done.

Mergen's engine was seeded from the operator's own prior project (`claude-code-hypercode`). The lineage and
the identity transform are recorded in `PROVENANCE.md`. This is a fresh repository with its own identity, not
a renamed one, so its history begins here rather than carrying the seed project's version log.

### Added

- The spec-driven development command suite, authored once in `core/commands/` (14 commands): `constitution`,
  `specify`, `clarify`, `checklist`, `plan`, `tasks`, `analyze`, `implement`, `verify`, `rollup`, `go`,
  `lean`, `debt`, and `govern`. Each command is a named Workflow pattern (judge panel, multi-approach plus
  architecture critic, loop-until-dry plus dependency DAG, wave-parallel verified pipeline, multi-lens
  verification), not a single-context monologue.
- Single source, two renderers (`core/CONVENTIONS.md`):
  - Native renderer `dist/native/build_native.py` renders each command into
    `~/.claude/skills/mergen-<name>/SKILL.md`, invoked as `/mergen-<name>`. `init` bootstraps a project's
    `.specify/` directory.
  - spec-kit renderer `dist/speckit/build_speckit.py` emits a preset `mergen` that overrides 8 stock Spec Kit
    commands, and an extension `mergen` that adds 6 commands (`verify`, `rollup`, `go`, `lean`, `debt`,
    `govern`) plus an `after_implement` verify gate.
- The Governor (`/mergen-govern`), Mergen's wisdom organ. It classifies a task into tiny, standard, spec, or
  high-trust, and sets the memory scope, workflow depth, evidence standard, and human-approval requirement.
  High-trust triggers (auth, payment, secrets, privacy, clinical and regulated content, irreversible
  operations, public-contract changes, untrusted-input-as-instruction) force a deterministic floor that can
  be raised but never silently lowered. It emits `governor-decision.json`. The `go` router executes the
  chosen tier and adds the high-trust human checkpoint.
- Machine-readable verification. `verify` emits `verification-report.json` and `tasks-state.json` beside the
  markdown, conforming to the schemas in `core/schemas/`, each task carrying a confidence label.
- The operating-principles layer. `MERGEN.md` (the charter) and `MERGEN_PRINCIPLES.md` (the principle to
  component map) state Mergen's commitments in its own voice: evidence honesty, calibration and abstention,
  retrieved content as data and never instruction, minimal communication, honest pushback, surfacing
  conflicts, restraint in reproduction, and care in sensitive domains. The principles were informed by
  responsible-AI design ideas and reproduce no proprietary text. A repository check enforces that.
- The minimalism discipline (the lazy ladder, `core/lazy-ladder.md`, derived from `DietrichGebert/ponytail`,
  MIT). `/mergen-lean` returns a tagged delete-list, `/mergen-debt` harvests `mergen:` deferred-shortcut
  comments into a ledger, and `implement` builds to the ladder while its verifier checks the result is
  minimal as well as correct.
- The cross-agent renderer `dist/agents/build_agents.py` ports the minimalism discipline only into passive
  rule files for non-Claude agents.
- The mneme seam (`docs/MNEME-SEAM.md`, `scripts/mneme_emit.py`). Mergen stores no memory of its own. It
  emits provenance-bearing decision records that mneme ingests through its public interface, with no network
  or LLM on the path.
- The eval evidence metric (`eval/evidence_metric.py`). A minimal honest measure derived from the verify
  JSON: a work-done rate and a phantom-completion count. It abstains on minimal-change without lean data.
- Reinforcement hooks (`core/hooks/`): `verify_gate.py` and `constitution_inject.py`, both fail-soft. They
  reinforce the discipline. The enforcement is the implement pipeline's adversarial verify stage and CI.
- Gates and CI. `scripts/check_sync.py` is the single-source drift gate. `scripts/check_no_reference_text.py`
  fails the build if reference-prompt fingerprints appear. Both run in CI alongside the test suite.
- Vendored Spec Kit templates and scripts (MIT), attributed in `ATTRIBUTION.md`.

### Honesty notes

- "Non-bypassable" describes the spec-kit `after_implement` hook contract and the implement pipeline's own
  gate. In-session these are strong reinforcement. The gate that genuinely cannot be talked around is CI.
- No benchmark numbers are claimed. The eval methodology is described and the full benchmark is on the
  roadmap.

### Deferred to a later release

See `docs/ROADMAP.md`: a GitHub Action and PR comment bot, clinical and security domain packs, the full
benchmark suite, and a full mneme writeback adapter. The dashboard, cross-run trends, and churn analytics
listed here originally have since shipped in the Unreleased line above.
