# Mergen for Hermes

Verify a completion claim before treating it as evidence. This native Hermes plugin exposes [Mergen Verdict](https://github.com/OnourImpram/mergen)'s file, Git and test checks through two typed tools.

The adapter is version 0.1.0. It does not replace Hermes planning or implementation, and does not automatically block the agent's next action.

## Requirements

- Hermes 0.22.7 or newer.
- A POSIX terminal environment, including Linux, macOS, WSL, or a configured POSIX container/SSH backend.
- Git and `mergen-verdict==2.1.3` on that terminal's PATH.
- pytest in the same Python environment as Mergen when tasks declare test files.

The adapter itself has no Python dependencies. It intentionally does not install the CLI into a private plugin environment: that environment may not be visible to a Docker or SSH terminal. Have the operator approve installation in the selected terminal, for example in an existing project virtual environment:

```sh
python -m pip install 'mergen-verdict==2.1.3' pytest
mergen --help
mergen-supervise --help
```

Activate that environment for the Hermes terminal. Do not install the unrelated PyPI package named `mergen`.

## Install the plugin

From a checkout of this repository:

```sh
hermes plugins validate ./integrations/hermes --install-deps
hermes plugins doctor ./integrations/hermes --ci
```

Copy the `integrations/hermes` directory to `plugins/mergen` inside your active Hermes profile directory, then run `hermes plugins enable mergen`. Do not pass a local directory to `plugins install`: Hermes 0.22.7 interprets that command as a Git source.

Once a reviewed catalog entry is available, installation will use `hermes plugins install mergen`. A prepared catalog entry or open PR does not mean it is already listed.

## Use

Ask Hermes: "Use Mergen to verify the completion claims in tasks-state.json under /workspace/my-project. Show the failed evidence and any checks you could not run."

`mergen_verify` accepts:

```json
{
  "root": "/workspace/my-project",
  "tasks_state": "tasks-state.json",
  "test_timeout": 120,
  "timeout": 180
}
```

It runs the fixed command `mergen verify` with strict mode and JSON output. It does not write a report file. The two deadlines mean different things: `test_timeout` bounds each declared pytest task; `timeout` is Hermes terminal's wait budget. The terminal may return a tracked background process when its foreground window is exceeded. That is an unfinished operation, not a pass. Observe that process before starting another run.

When the operator already has a real Mergen report and its `.sha256` sidecar, `mergen_supervise` accepts:

```json
{
  "root": "/workspace/my-project",
  "tasks_state": "tasks-state.json",
  "report": "verification-report.json"
}
```

It rechecks report integrity, task-state binding, Git provenance, fresh reproduction, risk and required human review. It returns a decision on stdout. The adapter has no `--no-reproduce`, output-path, signing, or approval-token option. Supervision explicitly removes `MERGEN_SIGNING_KEY` and `MERGEN_ACK_TOKEN` from the child command environment, so an ambient key or token cannot satisfy human approval. Use the separately approved Mergen CLI workflow for signed approval.

For a persisted report, run the normal CLI through Hermes terminal after approving the output path:

```sh
mergen verify --root /workspace/my-project --tasks-state /workspace/my-project/tasks-state.json --out /workspace/my-project/verification-report.json --strict
```

Read the bundled `mergen:verify-completion` skill for the full workflow. Report `conditional_pass`, `fail`, and `unverifiable` honestly. A check that never ran is not evidence of success. A clean mechanical result with no test declaration does not prove a test suite passed. An empty task set is not evidence of completed work.

## Security and disclosures

- **Execution:** The plugin calls only the public `ctx.register_tool`, `ctx.register_skill`, and `ctx.dispatch_tool` APIs. It delegates execution to Hermes terminal, whose normal terminal approval checks remain active. It never calls a subprocess directly, retries a pending run, changes approval settings, or falls back after denial.
- **Nested dispatch limitation:** A nested terminal dispatch does not necessarily replay every outer tool middleware hook. Workflows requiring an outer terminal hook should use the documented CLI in a normal terminal tool call instead. No broader enforcement guarantee is claimed.
- **Repository reads:** Mergen reads the selected repository, tasks, report and Git state, outside the plugin's own data. Argument checks are lexical POSIX checks, not a sandbox. Use a trusted operator-selected root and inspect symlinks. Hermes may refuse work directories containing shell metacharacters even though the adapter safely quotes them. This refusal is returned unchanged. The supervisor also checks that evidence resolves inside its trusted root.
- **Project code:** Test-backed verification runs pytest. Tests, pytest plugins and configuration can read/write files, spawn programs or access the network with the terminal environment's permissions. The verifier does not sandbox this code. Review and approve it as you would any test run.
- **Writes:** These tools request stdout only. Git read commands and pytest may still create locks, caches or test artifacts. The implementation artifact is not repaired by the verifier. Explicit report-file creation belongs to a separate CLI action.
- **Credentials and network:** The adapter reads no credential store, requests no secrets, makes no network calls and stores no credentials. It has no telemetry, self-updater, daemon, or background scheduler. The invoked project tests can have their own behavior, as disclosed above.
- **Honest results:** Host denial, pending, timeout and unavailable responses are returned unchanged. A dispatch exception has an uncertain execution outcome. Inspect Hermes before retrying.
- **Human authority:** No verdict authorizes publication, deployment, payment, or other consequential actions. This plugin does not sign approvals or claim universal semantic correctness.

## Development

From the repository root:

```sh
python -m pytest tests/test_hermes_plugin.py -v
python -m pytest tests/ -v
ruff check .
mypy
hermes plugins doctor ./integrations/hermes --ci
hermes plugins validate ./integrations/hermes --install-deps
```

See [the demo guide](../../docs/HERMES-DEMO.md). The plugin and its documentation are Apache-2.0 licensed, as is Mergen.
