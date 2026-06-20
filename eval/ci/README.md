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

That last gap is what the two workflows below close.

## A stronger gate: re-verify the live tree (`verify-gate-live.yml`)

`verify-gate-live.yml` does not read a committed report at all. It regenerates
the report in CI by running `verify_core` against the files and tests actually
present at the merge commit, then gates on that fresh report. Editing a committed
`verification-report.json` by hand changes nothing, because CI never reads it. It
recomputes from the live tree.

The residual trust narrows accordingly. With `verify-gate.yml` you trust the
verifier that produced the committed report. With `verify-gate-live.yml` you trust
the `verify_core` lenses running in CI on the real tree, which is a smaller and
more honest claim. What it still does not do: prove which model, if any, wrote the
code, or catch a defect no mechanical lens checks for. The spec-match lens stays
deferred to a human or an LLM.

Setup vendors both stdlib-only scripts (`verify_core.py` and `evidence_metric.py`)
and points the regenerate step at your `tasks-state` JSON. See the comments in the
file.

## Forgery becomes detectable: attest the fresh report (`verify-attest.yml`)

`verify-attest.yml` extends the live gate with a signed provenance attestation.
After regenerating and gating, it attests the fresh report with GitHub's hosted
`actions/attest-build-provenance`, binding the report's SHA-256 to a SLSA
provenance predicate signed by a short-lived Sigstore certificate minted from the
run's OIDC token. `gh attestation verify <report> --repo <owner>/<repo>` then
re-derives the digest and fails on any edit.

The signing key is minted by GitHub for the run and is unreachable by the build
steps, so this is not the forgeable pattern where a build signs its own
provenance. Two things stay manual, because they are repository permissions a repo
admin sets once, not something a workflow file can grant itself: protecting the
default branch, and requiring the attestation verification as a status check
before merge. Authoring the workflow is automatic. Enforcing it is your call.

So the honesty ladder of gates reads, in full: a prompt protocol asks, a hook
nudges, `verify-gate.yml` refuses on a committed report, `verify-gate-live.yml`
refuses on a freshly recomputed report so a hand-edit cannot pass, and
`verify-attest.yml` makes any edit to that fresh report cryptographically
detectable.
