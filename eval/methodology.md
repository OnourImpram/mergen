# Evaluation Methodology

**Status: the live head-to-head in this document is not yet measured.**
A separate deterministic benchmark (`eval/benchmark.py`, described in the README) now reports real,
reproducible numbers for metric 1 (phantom-completion) and a deterministic slice of metric 3
(adversarial catch) without a live model. This document is the LIVE spec-kit-vs-mergen comparison,
which additionally covers metric 2 (parallel speedup) and metric 4 (over-build) and has not been
run. Every SYNTHETIC or ILLUSTRATIVE figure in the tables below is a placeholder showing the shape
of the result table only. It is not a measured value. Replace every SYNTHETIC cell with real values
from the reproduction run before making any public claim.

---

## Background

spec-kit structures a development workflow around specification documents and a set of named
slash commands. Its own reported failure modes include:

- Phantom completions: tasks are marked `[X]` by a single-context agent that has not verified
  file existence or test passage.
- No task parallelism: tasks execute serially inside one context window.
- No verification gate: there is no mechanism that reverts a falsely completed task.
- Context decay: long runs of many tasks drift from the original spec because the specification
  is not re-injected into context during execution.

mergen addresses each of these through two layers.

**Effort-mode layer** (`effort-mode/`): the `UserPromptSubmit` hook
`effort-mode/hooks/mergen_prompt_hook.py` injects a standing Workflow orchestration directive
on every turn so that multi-agent coordination is always active. The hook is fail-soft and exits
0 when not applicable. Activating max reasoning effort (`/effort max`) requires one manual paste
by the user. The hook cannot flip that live value automatically because the control channel that
applies effort is not exposed to hooks and `max` cannot be persisted in `settings.json`. This
single manual step is the honest cost of reaching the max tier. The `/mergen` command prints
the `/effort max` line for the user to paste once.

**SDD layer** (`core/`): fourteen commands implement the full SDD lifecycle. The implement command
(`core/commands/implement.md`) runs a wave-parallel pipeline where each task is handled by an
isolated max-effort implementer followed by a separate-context, refute-biased verifier that
checks filesystem presence and test passage before writing `[X]`. On `pass: false` the task is
re-queued with the verifier's failure list appended. Tasks are never marked complete without
verifier-confirmed evidence. The verify command (`core/commands/verify.md`) runs a second full
pass with parallel multi-lens checkers (file-exists, spec-match, tests-pass, git-consistent) and
reverts any unverified `[X]` to `[ ]`, writing a full report to
`FEATURE_DIR/verification-report.md`.

The two hooks in `core/hooks/` (`verify_gate.py` and `constitution_inject.py`) are reinforcement
nudges: they inject reminders into model context via `additionalContext`. They are not enforcement
mechanisms and they do not block, prevent, or enforce any action. The real enforcement is the
implement pipeline's adversarial verify stage.

The spec-kit renderer (`dist/speckit/build_speckit.py`) produces a preset that overrides eight
stock spec-kit commands and an extension that adds verify, rollup, go, lean, debt, govern, and
agent as `speckit.mergen.*` commands wired via `after_implement` (optional: false). The native
renderer (`dist/native/build_native.py`) provides the complete 15-command suite. The eval below uses
the native renderer.

---

## Metric 1: Phantom-completion rate

### Definition

Given a completed run with a `tasks.md` file, the phantom-completion rate is:

```
phantom_rate = (count of [X] tasks with no backing artifact) / (total [X] tasks)
```

A task has no backing artifact when both of the following are true:

- The file path named in the task body does not exist in the working tree.
- No test function whose name matches the task identifier passes when the test suite is run
  with a filter targeting that identifier.

### Why it matters

A phantom-completion rate above 0 means the development record is false. Downstream tasks that
depend on a phantom-completed task inherit a broken foundation silently.

### mergen target

0. The implement pipeline marks `[X]` only after the separate-context verifier returns
`pass: true` with concrete command output confirming filesystem presence and test passage. The
verify command performs a second pass and reverts any `[X]` that fails the majority verdict of
its four parallel lenses.

### How to measure

1. Complete a run with both toolchains on the identical feature spec (see Reproduction Steps).
2. Parse `tasks.md` to collect all `[X]` entries and their named files or test identifiers.
   Example extraction using standard POSIX tools:
   ```bash
   grep -i '^\- \[x\]' tasks.md | sed 's/.*`\([^`]*\)`.*/\1/'
   ```
3. For each named file, check existence:
   ```bash
   test -f "$file" && echo "EXISTS" || echo "PHANTOM"
   ```
4. For each named test identifier, run the test suite with a filter and check the exit code:
   ```bash
   python -m pytest -k "$test_id" --tb=no -q
   echo "exit: $?"
   ```
5. Count all tasks where both checks indicate absence. Divide by total `[X]` count.

### Result table (ILLUSTRATIVE, not measured)

| Toolchain | [X] tasks | Phantom count | Phantom rate |
|-----------|-----------|---------------|--------------|
| spec-kit  | SYNTHETIC | SYNTHETIC     | SYNTHETIC    |
| mergen | SYNTHETIC | SYNTHETIC     | SYNTHETIC    |

Replace every SYNTHETIC cell with real values from the reproduction run.

---

## Metric 2: Parallel speedup

### Definition

Given a `tasks-dag.json` emitted by `/mergen-tasks` (see `core/commands/tasks.md`), the
tasks form waves: each wave contains tasks whose `depends_on` list is fully satisfied by prior
waves. Within a wave, tasks are independent and can run in parallel.

```
speedup = serial_wall_clock / wave_parallel_wall_clock
```

- `serial_wall_clock`: wall time when every task in every wave runs one at a time in order.
- `wave_parallel_wall_clock`: wall time when all tasks within a wave run concurrently and waves
  are sequenced by the `depends_on` relation.

### Why it matters

Single-context serial execution is the only mode available to vanilla spec-kit. mergen's
implement command dispatches each wave as a set of parallel Workflow tool invocations. On a spec
with W waves and an average of P independent tasks per wave, the theoretical minimum speedup is
P (assuming uniform task cost and zero dispatch overhead). Real speedup will be lower because
task durations vary and because API dispatch has latency.

### How to measure

1. After running `/mergen-tasks`, the file `FEATURE_DIR/tasks-dag.json` exists. Inspect the
   wave structure:
   ```bash
   jq 'length' FEATURE_DIR/tasks-dag.json          # number of waves
   jq '[.[] | length]' FEATURE_DIR/tasks-dag.json   # tasks per wave
   ```
2. During a live implement run, capture per-wave progress from the session output. The implement
   command reports which tasks passed, were re-queued, or failed after each wave. It does not write
   a timing log file itself, so capture timing externally by redirecting the session output to a file:
   ```bash
   # The implement command does not write a timing log. Redirect the Claude Code session
   # output to a file during the run, then read the per-wave progress lines from that
   # captured session output to derive per-task and per-wave durations.
   ```
3. Compute serial time as the sum of all individual task durations.
4. Reconstruct wave structure from `tasks-dag.json` and compute parallel time as the sum over
   waves of the maximum task duration within each wave:
   ```bash
   # Example jq pipeline to list wave composition (adjust field names to actual log format)
   jq '[.[] | {wave_tasks: [.[].id]}]' FEATURE_DIR/tasks-dag.json
   ```
5. Speedup = serial time / parallel time.

Run at least three trials and report the median to reduce API latency noise.

### Result table (ILLUSTRATIVE, not measured)

| Spec | Waves | Max tasks/wave | Serial (s) | Parallel (s) | Speedup |
|------|-------|----------------|------------|--------------|---------|
| SYNTHETIC example | SYNTHETIC | SYNTHETIC | SYNTHETIC | SYNTHETIC | SYNTHETIC |

Replace every SYNTHETIC cell with real values from the reproduction run.

---

## Metric 3: Adversarial catch

### Definition

The adversarial catch count is the number of distinct defects surfaced by mergen's verify
lanes before the human accepts the run. A defect is one of:

- A spec gap: a requirement stated in the spec has no corresponding task or implementation.
- A missing file: a file named in a task does not exist on the filesystem.
- A failing test: a test associated with a task exits non-zero when run.
- A git inconsistency: a file the task claims to have modified does not appear in
  `git diff --name-only` against the prior commit.

Defects are deduplicated by unique file path or requirement identifier, not by the number of
lenses that flag the same issue.

### Why it matters

Defects that are not caught by the toolchain reach the human review phase or production. An
adversarial catch count above 0 means the toolchain provided a safety net that vanilla spec-kit's
single-context execution does not offer. spec-kit has no equivalent verify lane, so its catch
count is structurally 0.

### How to measure

1. After the mergen implement run completes, invoke `/mergen-verify` (native) or
   `speckit.mergen.verify` (spec-kit renderer path).
2. The verify command writes its report to `FEATURE_DIR/verification-report.md`. Parse the
   report to count reverted tasks and flagged issues per lens:
   ```bash
   grep -c 'REVERTED'     FEATURE_DIR/verification-report.md
   grep -c 'MISSING FILE' FEATURE_DIR/verification-report.md
   grep -c 'TEST FAIL'    FEATURE_DIR/verification-report.md
   grep -c 'SPEC GAP'     FEATURE_DIR/verification-report.md
   ```
3. Deduplicate across lenses by file path or requirement ID. Record the deduplicated count as
   the adversarial catch for that run.
4. For spec-kit: record 0 because no equivalent verify pass exists. Confirm by manually checking
   all `[X]` tasks after the spec-kit run using the phantom-rate procedure (Metric 1 steps 2-5).

### Result table (ILLUSTRATIVE, not measured)

| Toolchain | Defects introduced (manual audit) | Defects caught by toolchain | Catch rate |
|-----------|-----------------------------------|-----------------------------|------------|
| spec-kit  | SYNTHETIC                         | STRUCTURAL-ZERO (no lane)   | STRUCTURAL-ZERO |
| mergen | SYNTHETIC                         | SYNTHETIC                   | SYNTHETIC  |

The spec-kit catch rate of 0% is structural, not a measured figure. It reflects the absence of
any verify mechanism in the vanilla toolchain, not an empirical observation. Replace the
SYNTHETIC cells with real values from the reproduction run.

---

## Metric 4: Over-build rate

### Definition

A max-effort agent with no minimalism gate over-builds: it writes abstractions, dependencies, and
boilerplate the task never required. This is the failure mode the lazy ladder (`core/lazy-ladder.md`)
and the `/mergen-lean` review target. The over-build rate is:

```
over_build_rate = (lines /mergen-lean flags as removable) / (total lines added in the diff)
```

A line is flagged when `/mergen-lean audit` tags it `delete`, `stdlib`, `native`, `yagni`, or
`shrink`. Lines tagged for validation, security, accessibility, error handling, or tests are never
counted, because the ladder never cuts those.

### Why it matters

This is the only metric that measures the minimalism layer. Phantom-completion and
adversarial-catch measure correctness. Over-build rate measures whether the verified output is also
minimal. A toolchain can score perfectly on the first three metrics and still ship twice the code a
task needs.

### mergen target

Lower than the baseline. The implement pipeline's Stage B verifier (`core/commands/implement.md`)
rejects a task that is correct but over-built, tagging the surplus with the same taxonomy, so
over-build is caught inside the pipeline rather than surfaced only by a later review. The exact
reduction is not claimed. It is measured.

### How to measure

1. Use the SAME agent and model for both arms. The baseline is that agent running the identical
   spec WITHOUT the lazy-ladder layer (plain spec-kit implement). The mergen arm is the same
   agent with the lazy-ladder injection and Stage B minimalism check active. This isolates the
   minimalism layer, not the model.
2. After each arm completes, capture the added lines with `git diff --numstat` against the
   pre-implementation commit.
3. Run `/mergen-lean audit` on each arm's diff and parse the tagged delete-list. Count flagged
   lines by tag, excluding any line whose tag would touch validation, security, accessibility, or
   tests (the review already excludes these by scope).
4. `over_build_rate = flagged_lines / added_lines` for each arm.

### Honest caveat

`/mergen-lean` is itself an LLM-judged review, so this metric measures the review's judgment of
surplus, not a ground-truth line count. Run the review with a fixed model and record it. Report the
two arms' rates side by side rather than as an absolute, since the judgment is the same instrument
applied to both.

### Result table (ILLUSTRATIVE, not measured)

| Toolchain | Added lines | Lean-flagged lines | Over-build rate |
|-----------|-------------|--------------------|-----------------|
| baseline (no ladder) | SYNTHETIC | SYNTHETIC | SYNTHETIC |
| mergen | SYNTHETIC | SYNTHETIC | SYNTHETIC |

Replace every SYNTHETIC cell with real values from the reproduction run.

---

## Measurement isolation (read before any run)

Both arms install global Claude Code extension points: `UserPromptSubmit` and `PostToolUse` hooks,
plus skills under `~/.claude/`. When two arms share one machine, a run of one arm can be contaminated
by the other arm's globally-registered hooks and skills, so the measured difference reflects leaked
configuration rather than the toolchain under test. This isolation discipline is adapted from
ponytail's agentic benchmark harness (MIT, attributed in `ATTRIBUTION.md`).

Run each arm in isolation:

- Drive the agent headlessly with real `claude -p`, not an interactive session, so each run is
  reproducible and scriptable.
- Pass `--setting-sources project,local` so the run reads only project and local settings, never the
  global `~/.claude/settings.json` that the other arm may have written.
- Give each arm its own `--plugin-dir` so each arm sees only its own commands and hooks.
- Use the same agent and model for both arms. A fair baseline is the same agent with the harness
  disabled, never a different or weaker tool. The comparison must isolate the harness, not the model.
- Run at least four trials per arm and report the median. A single trial is not representative under
  variable API latency.

---

## Reproduction Steps

These steps produce a controlled head-to-head comparison on an identical feature spec. Follow
them exactly to generate valid data for all four metrics.

### Prerequisites

- `spec-kit` installed and on PATH.
- mergen installed: run `effort-mode/install.sh` (Linux/macOS) or `effort-mode/install.ps1`
  (Windows PowerShell), then run:
  ```bash
  python dist/native/build_native.py build
  python dist/native/patch_settings_hooks.py
  ```
  The first command renders skills to `~/.claude/skills/mergen-*/SKILL.md`. The second
  registers `core/hooks/verify_gate.py` (PostToolUse, matcher `Write|Edit|MultiEdit`) and
  `core/hooks/constitution_inject.py` (UserPromptSubmit) in `settings.json` idempotently. Pass
  `--dry-run` to either script to preview without writing.
- Claude Code CLI authenticated and available on PATH.
- Python 3.9+, bash 4+, `jq` 1.6+, `git` available.
- A clean scratch repository with no uncommitted changes. Do not run the eval in the mergen
  repo itself to avoid contaminating results.
- Throughout these steps, FEATURE_DIR is the feature-specific directory created under `.specify/`
  by the specify step (for example `.specify/specs/<feature-name>/`). Substitute the actual path
  from your run wherever FEATURE_DIR appears.

### Step 1: Author the canonical feature spec

Write a single feature spec document using `core/templates/spec-template.md` as the base. The
spec must meet all of the following requirements to produce meaningful data across all three
metrics:

- Describe a feature with at least six implementation tasks.
- At least four of those tasks must be parallelizable (disjoint file sets, no shared runtime
  dependency) to produce a meaningful parallel speedup value.
- Require at least two distinct output files per task.
- Include at least one acceptance criterion per task that maps to a testable assertion.

Save it as `eval/fixtures/feature-spec.md` inside your scratch repo. Commit it:

```bash
git add eval/fixtures/feature-spec.md
git commit -m "eval: canonical feature spec"
```

Do not modify this file between the two toolchain runs. The spec is the controlled variable.

### Step 2: Run spec-kit (baseline)

```bash
git checkout -b eval-speckit

spec-kit init
spec-kit specify --spec eval/fixtures/feature-spec.md
spec-kit tasks

date +%s > eval/results/speckit-start.txt
spec-kit implement
date +%s > eval/results/speckit-end.txt
```

After the run completes:

```bash
cp FEATURE_DIR/tasks.md eval/results/speckit-tasks.md
```

Run the phantom-rate measurement (Metric 1 steps 2-5) and write results:

```bash
# Record counts manually after running the grep/test/pytest steps
echo "speckit_phantom_rate=MEASURED_VALUE" > eval/results/speckit-phantom.txt
```

Record adversarial catch as 0 (structural absence of verify lane):

```bash
echo "speckit_adversarial_catch=0" > eval/results/speckit-adversarial.txt
```

Commit the result files:

```bash
git add eval/results/
git commit -m "eval: spec-kit baseline run results"
```

### Step 3: Run mergen (native renderer)

```bash
git checkout main
git checkout -b eval-mergen

python dist/native/build_native.py init .
```

Open Claude Code in the scratch repo. Before invoking any mergen command, activate max effort:

```
Run /mergen in Claude Code. Copy the printed /effort max line and paste it into the
active Claude Code session. This one manual paste is required. The hook cannot set the
live effort value automatically.
```

Inside Claude Code, invoke the commands in order:

```
/mergen-specify   (pass eval/fixtures/feature-spec.md as the spec source)
/mergen-tasks     (emits FEATURE_DIR/tasks-dag.json)
```

Record the start timestamp:

```bash
date +%s > eval/results/mergen-start.txt
```

Inside Claude Code:

```
/mergen-implement
```

Record the end timestamp:

```bash
date +%s > eval/results/mergen-end.txt
```

Inside Claude Code:

```
/mergen-verify
```

After the run completes, collect artifacts:

```bash
cp FEATURE_DIR/tasks.md        eval/results/mergen-tasks.md
cp FEATURE_DIR/tasks-dag.json  eval/results/mergen-tasks-dag.json
cp FEATURE_DIR/verification-report.md eval/results/mergen-verify-report.md
```

Run the phantom-rate measurement and the adversarial-catch measurement, then record results:

```bash
echo "mergen_phantom_rate=MEASURED_VALUE"      > eval/results/mergen-phantom.txt
echo "mergen_adversarial_catch=MEASURED_VALUE" > eval/results/mergen-adversarial.txt
echo "mergen_speedup=MEASURED_VALUE"           > eval/results/mergen-speedup.txt
```

Commit result files:

```bash
git add eval/results/
git commit -m "eval: mergen run results"
```

### Step 4: Aggregate results

Run `eval/run_eval.sh` to read the result files and print a summary table. After the script
runs successfully, replace all SYNTHETIC placeholders in this document with the real values
and commit the updated methodology before publishing any claim.

---

## Honest limitations

- These metrics measure toolchain behavior on a single synthetic feature spec authored by the
  evaluator. They do not measure outcome quality (does the generated code work correctly in
  production), model reasoning quality, or long-term maintainability.
- Parallel speedup depends on model API latency, which varies by time of day and account tier.
  Run at least four trials and report the median. A single-trial speedup figure is not
  representative.
- Over-build rate (metric 4) is scored by `/mergen-lean`, which is an LLM-judged review, not a
  deterministic counter. It measures the review's judgment of surplus applied identically to both
  arms. Report the two arms side by side, not as an absolute, and record the model used for the
  review.
- Both arms must run in isolation (see "Measurement isolation"). A run that reads the other arm's
  global hooks or skills is contaminated and must be discarded.
- Adversarial catch depends on the complexity and ambiguity of the spec. A trivial spec with
  unambiguous tasks may produce zero defects on both toolchains, making metric 3 uninformative.
  Choose a spec with realistic ambiguity and at least one intentionally underspecified
  acceptance criterion.
- The effort-mode layer requires one manual paste step (`/effort max`) that is not automatable
  by any hook or script. Runs without that paste operate at the default effort level, not at
  `max`. Record whether the paste was performed for each run and note it in the results.
- The spec-kit comparison covers the preset (eight command overrides) and extension (six
  additional commands: verify, rollup, go, lean, debt, govern) produced by `dist/speckit/build_speckit.py`. It
  does not claim full spec-kit feature parity beyond that scope.
- Both toolchains invoke a live LLM. Results will vary across models, model versions, and API
  conditions. Record the Claude Code version and model identifier for each run.
