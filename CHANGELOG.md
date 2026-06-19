# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/), and the project aims to follow
[Semantic Versioning](https://semver.org/).

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
    `~/.claude/skills/mergen-<name>/SKILL.md`, invoked as `/mergen.<name>`. `init` bootstraps a project's
    `.specify/` directory.
  - spec-kit renderer `dist/speckit/build_speckit.py` emits a preset `mergen` that overrides 8 stock Spec Kit
    commands, and an extension `mergen` that adds 6 commands (`verify`, `rollup`, `go`, `lean`, `debt`,
    `govern`) plus an `after_implement` verify gate.
- The Governor (`/mergen.govern`), Mergen's wisdom organ. It classifies a task into tiny, standard, spec, or
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
  MIT). `/mergen.lean` returns a tagged delete-list, `/mergen.debt` harvests `mergen:` deferred-shortcut
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

See `docs/ROADMAP.md`: a GitHub Action and PR comment bot, clinical and security domain packs, a dashboard,
churn analytics, the full benchmark suite, and a full mneme writeback adapter.
