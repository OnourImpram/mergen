# The verify-gate, a CI check for your own project

Mergen's in-session pipeline asks and nudges, and its own continuous integration
guards this repository. Neither runs the verify command against your project. The
verify-gate closes that distance. It is the layer that refuses, the only one that
can block a merge in your repository.

## What it is

`verify-gate.yml` is a drop-in GitHub Actions workflow. It runs the `--gate` mode
of `eval/evidence_metric.py` against a committed `verification-report.json` and
fails the build when the report shows phantom or unverified work.

A phantom is a task claimed done that the verifier did not confirm pass. By
default the gate tolerates none. It also requires a work-done rate of 1.0, so
every claimed-done task must carry concrete evidence. Relax either bound with
`--max-phantoms` or `--min-work-done`.

## Setup

1. Vendor the metric into your repository, for example at `tools/evidence_metric.py`.
   It is Python standard library only, so there is nothing to install.
2. Run `/mergen.verify` in your project and commit the `verification-report.json`
   it emits.
3. Copy `verify-gate.yml` into your project's `.github/workflows/` directory and
   point the run step at your committed report.

## Running it locally

```bash
python eval/evidence_metric.py path/to/verification-report.json \
  --gate --max-phantoms 0 --min-work-done 1.0
```

Exit code `0` means the report passed the gate. Exit code `1` means it showed
phantom or unverified work. With no tasks claimed done, the gate has nothing to
enforce and passes.

## What it does and does not prove

The gate reads the committed report. It catches an agent that honestly recorded
phantom completions, and it forces the report to exist and to be green before a
merge. It does not read your filesystem or re-run your tests, and a hand-edited
report can still pass. The deepest guarantee rests on the separate-context
verifier that produced the report, not on this check. Mergen names each layer for
exactly what it does. A prompt protocol asks, a hook nudges, this gate refuses,
and even this gate reads the committed report rather than your live tree.
