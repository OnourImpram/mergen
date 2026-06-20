# Evaluation Harness

This directory contains the evaluation methodology and reproduction procedure for comparing
mergen against vanilla spec-kit on four concrete metrics.

**Status: the deterministic harness-detection benchmark reports real numbers; the live
head-to-head is still methodology only.**
`benchmark.py` (below) measures metric 1 (phantom-completion) and a deterministic slice of
metric 3 (adversarial catch) with real, reproducible numbers and no LLM. The live spec-kit
head-to-head for metric 2 (parallel speedup) and metric 4 (over-build) is still unmeasured: the
figures for those in the methodology document remain explicitly labeled SYNTHETIC or ILLUSTRATIVE
and must be replaced by real measurements before any public claim is made.

## What is being evaluated

mergen is a spec-driven-development (SDD) harness that runs the same lifecycle as spec-kit
but under two additional mechanisms:

1. Max reasoning effort plus standing Workflow orchestration (the effort-mode layer).
   The `effort-mode/hooks/mergen_prompt_hook.py` hook injects a standing directive on every
   turn. Activating genuine `max` effort requires one manual paste of `/effort max` by the user.
   The hook cannot set the live effort value automatically. This is a known, honest constraint.

2. An adversarial verify pipeline inside `core/commands/implement.md` that runs a
   separate-context, refute-biased verifier and confirms filesystem presence plus passing tests
   before any task is marked `[X]`. The `core/commands/verify.md` command provides a second full
   pass over the entire task list with parallel multi-lens checkers (file-exists, spec-match,
   tests-pass, git-consistent) and reverts any unverified `[X]` to `[ ]`.

The two hooks in `core/hooks/` (`verify_gate.py` and `constitution_inject.py`) are reinforcement
nudges injected into context. They are not enforcement mechanisms and they do not block any action.
Real enforcement comes from the implement pipeline's adversarial verify stage.

spec-kit's own documentation reports three recurring failure modes: phantom completions (tasks
marked done with no backing file or test), no task parallelism, and no verification gate. The
four metrics below target those failure modes directly.

## Evidence metric

`evidence_metric.py` in this directory is a minimal honest metric derived from the machine-readable verify output. It reports two values: work-done rate (fraction of tasks with verifier-confirmed evidence) and phantom-completion count (tasks marked `[X]` with no backing artifact). The metric abstains on minimal-change runs that lack lean data rather than reporting a misleading zero. It reads `verification-report.json` and `tasks-state.json` emitted by `/mergen.verify` (schemas in `core/schemas/`). It reads BOM-prefixed JSON (the form Windows PowerShell writes) without choking. The full benchmark suite is on the roadmap.

Gate use, honest defaults. `python eval/evidence_metric.py <report> --gate` fails the build when a claimed-done task is not verifier-confirmed. With nothing claimed done it abstains and passes, because a gate cannot enforce work that was never claimed. That abstention also means an empty report would pass, so a CI step meant to prove work was done should require at least one claimed task. The recommended CI invocation is:

```
python eval/evidence_metric.py path/to/verification-report.json --gate --min-claimed 1
```

With `--min-claimed 1` an empty or under-claiming report fails instead of passing silently. The deeper guarantee still rests on the verifier that produced the report, not on this metric: the gate acts on a committed artifact, so a hand-edited report can pass. What it buys is that phantom, unverified, or empty work fails the build by default.

## Deterministic phantom-detection benchmark

`benchmark.py` is a runnable, reproducible benchmark that needs no LLM, no network, and no live
spec-kit. It builds a corpus of task-completion scenarios with known ground truth inside throwaway
git repos, runs the real shipped harness (`scripts/verify_core.py`) over each, and measures how
many planted phantom completions the harness catches against how many genuine completions it
wrongly fails.

```
$ python eval/benchmark.py
  phantom catch rate (treatment): 1.00  (5/5 caught)
  phantom catch rate (baseline):  0.00  (trust the [X] checkbox, re-checks nothing)
  false-alarm rate (treatment):   0.00  (0/3 genuine wrongly failed)
  caught by the expected lens:    1.00
```

The baseline arm is bare spec-kit behavior: trust the `[X]` checkbox, which re-checks nothing and
so catches zero phantoms by construction. The treatment arm is verify_core's three mechanical
lenses (file-exists, tests-pass, git-consistent). `python eval/benchmark.py --gate` exits non-zero
if the harness ever misses a planted phantom or false-alarms a genuine completion, so a regression
in verify_core fails the build.

Scope and honesty: this measures the harness's mechanical detection on planted fixtures with known
ground truth. It is not a code-quality comparison of two live toolchains, and it does not measure
parallel speedup or over-build, which need a live model (metrics 2 and 4 in methodology.md, still
on the roadmap). The benchmark's phantom set is a superset of methodology.md's strict definition
(declared file missing, or declared test failing); it adds two adjacent cases the harness also
refuses to confirm, a completion with no checkable evidence at all and a declared artifact the
repository does not track. All five are cases the bare checkbox accepts and the harness rejects.

## Four metrics

| # | Metric | Definition |
|---|--------|------------|
| 1 | Phantom-completion rate | Fraction of `[X]` tasks whose named file or test does not exist at measurement time |
| 2 | Parallel speedup | Ratio of serial wall-clock to wave-parallel wall-clock for independent task waves |
| 3 | Adversarial catch | Count of real defects (spec gaps, missing files, failing tests) surfaced by the verify lanes before the human accepts the run |
| 4 | Over-build rate | Fraction of added lines that `/mergen.lean` flags as removable (the minimalism layer, with correctness-critical lines never counted) |

## Measurement isolation

Both arms install global hooks and skills. A run that reads the other arm's global configuration is
contaminated. Run each arm headlessly with real `claude -p`, pass `--setting-sources project,local`,
give each arm its own `--plugin-dir`, use the same agent and model for both arms with the harness
disabled as the baseline, and take the median of at least four trials. This isolation discipline is
adapted from ponytail's agentic benchmark harness (MIT, attributed in [ATTRIBUTION.md](../ATTRIBUTION.md)).

## How to reproduce

Full procedure with rationale: [methodology.md](methodology.md)
Procedure script skeleton: [run_eval.sh](run_eval.sh)

## Tooling requirements

- `spec-kit` installed and available on PATH (see https://github.com/github/spec-kit)
- Claude Code CLI with mergen installed (see repo root [README.md](../README.md))
- A POSIX shell for `run_eval.sh` (bash 4+)
- Python 3.9+ (for `dist/native/build_native.py` and `dist/native/patch_settings_hooks.py`)
- `jq` 1.6+ (for parsing `tasks-dag.json` wave structure)
- `git` (for consistency checks in metric 3)

## Scope of comparison

The spec-kit renderer (`dist/speckit/build_speckit.py`) produces:

- A **preset** (`dist/speckit/preset/mergen/`) that overrides eight stock spec-kit commands
  (constitution, specify, clarify, checklist, plan, tasks, analyze, implement) via `preset.yml`.
- An **extension** (`dist/speckit/extensions/mergen/`) that adds six commands
  (`speckit.mergen.verify`, `speckit.mergen.rollup`, `speckit.mergen.go`,
  `speckit.mergen.lean`, `speckit.mergen.debt`, `speckit.mergen.govern`) via `extension.yml`, with
  `after_implement` wired to `speckit.mergen.verify` (optional: false).

The native renderer (`dist/native/build_native.py`) provides the full 14-command suite
under `~/.claude/skills/mergen-<name>/SKILL.md`. The eval uses the native renderer by
default and notes where spec-kit renderer behavior differs.

## Affiliation notice

This project is not affiliated with GitHub, Inc. or Anthropic, PBC.
Spec Kit is a GitHub, Inc. project distributed under the MIT License.
Claude and Claude Code are trademarks of Anthropic, PBC.
Vendored spec-kit material is MIT-attributed in [ATTRIBUTION.md](../ATTRIBUTION.md) and
[NOTICE](../NOTICE).
