# Live-chain eval

This is the specification for the measurements that a live tool chain alone can make, and the
honest boundary around them. The deterministic benchmark and EvalOps measure the verify harness
with no model in the loop. Two of the four north-star metrics are not measurable that way, and
this document says exactly how they would be measured and why the numbers are not produced here.

## Why these two are different

- Metric 2, parallel speedup, is a property of the wave-parallel implement pipeline running a real
  task graph against a real model. There is no model-free proxy for it.
- Metric 4, over-build, is a property of what an agent actually writes when given a spec. It needs
  an agent, a model, and a labelled spec whose required surface is known.

Both need a real Claude Code binary, a live model, and the network. None of that runs in CI here,
and none of it is simulated. A simulated number would be a fabricated one.

## The protocol

`eval/live_chain_eval.py protocol` prints the protocol as structured data. In short:

- A scenario carries an id, the spec or task graph the agent is given, the required surface the
  spec genuinely demands (the over-build baseline), and the arms to run: `parallel`, `serial`, and
  `baseline-no-discipline`.
- Parallel speedup is the wall-clock of the parallel arm divided by the serial arm on the same
  graph, with both raw times reported so the ratio is auditable.
- Over-build is the surplus of files and lines the agent produced beyond the required surface,
  normalized by the required size, compared against a baseline agent run without the lazy-ladder
  restraint discipline.

## The runner contract

The operator supplies a runner: a callable `runner(scenario, arm)` that executes one arm against
the live tool chain and returns its measured outcome (`wall_clock_s`, `files_written`,
`lines_written`, `passed`). This repository provides no runner, on purpose. With no runner,
`eval/live_chain_eval.py run` refuses and exits non-zero rather than returning a result, so an
automated caller can never mistake silence for a passing measurement.

## The honest boundary

The protocol is settled and committed. The numbers are the operator's live-environment job, run
with a real account, a real model, and a real tool chain. They are named here as external and are
never fabricated, in CI or anywhere else. When a live run produces them, they belong in a results
artifact alongside the raw times and surfaces that make each number auditable, not as a bare
headline figure.
