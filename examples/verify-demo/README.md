# Worked example: the verify harness on a committed tree

This is a tiny end-to-end run of Mergen's deterministic verify harness
(`scripts/verify_core.py`) over a committed project. It shows the harness
confirming a task that was genuinely done and catching a task that was marked
done but has no backing file. The point of the name Mergen is precision about
what was actually hit, and this is that property in the smallest honest form.

The harness is agent agnostic. It is pure Python standard library, needs no
network, no model, and no Claude Code. It runs anywhere Python 3.9 or newer runs.

## What is in here

```
verify-demo/
  src/greeter.py            a real file, the artifact for task T001
  tests/test_greeter.py     a passing test, the evidence for task T001
  tasks-state.json          two tasks, both claimed done
```

`tasks-state.json` claims two tasks are done. T001 names `src/greeter.py` and a
test that covers it. T002 names `src/teardown.py`, a file that does not exist. The
`done` mark is the claim. The harness is what challenges it.

## Run it

From the repository root, either invoke the harness directly:

```
python scripts/verify_core.py --tasks-state examples/verify-demo/tasks-state.json --root examples/verify-demo
```

or through the packaged CLI, which forwards to the same harness:

```
mergen verify --tasks-state examples/verify-demo/tasks-state.json --root examples/verify-demo
```

## What you get

The harness runs three mechanical lenses per task (file exists, tests pass, git
consistent) and emits a JSON report to stdout. It exits non-zero because one
claimed-done task did not hold up. Trimmed to the fields that matter, the real
output is:

```json
{
  "summary": {
    "verdict": "fail",
    "mechanically_passed": 1,
    "mechanically_failed": 1
  },
  "tasks": [
    {
      "task_id": "T001",
      "verified_status": "pass",
      "lens_file_exists": "pass",
      "lens_tests_pass": "pass",
      "lens_git_consistent": "pass",
      "evidence": [
        "exists: src/greeter.py",
        "pytest exit 0 for tests/test_greeter.py",
        "git-tracked: src/greeter.py"
      ]
    },
    {
      "task_id": "T002",
      "verified_status": "fail",
      "lens_file_exists": "fail",
      "failures": [
        "missing: src/teardown.py",
        "git-unknown: src/teardown.py"
      ]
    }
  ]
}
```

T001 is confirmed by real evidence: the file is on disk, its test exits zero,
and git tracks it. T002 is the phantom. The bare `[X]` checkbox would have
accepted it. The harness refuses it, names the missing file, and fails the run.
The process exit code is `1`, so a CI step that runs this blocks the merge.

## Why it cannot rot

`tests/test_examples.py` in the repository runs this exact example through
`verify_core.build_report` and asserts the phantom is caught and the genuine
task is confirmed. If a future change broke the harness or the example, that test
would fail. The example is proof that runs, not a screenshot that ages.
