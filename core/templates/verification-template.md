---
description: "Per-task acceptance criteria and machine-checkable verification commands for the verify command."
---

# Verification Report: [FEATURE NAME]

**Feature Branch**: `[###-feature-name]`

**Generated**: [DATE]

**Verified by**: `/mergen-verify` (or `/speckit.mergen.verify`)

**Source tasks.md**: `[PATH]/tasks.md`

---

## How to Read This Report

Each task entry below records the four verification lenses that were run in parallel via the Workflow tool. A task earns PASS only when a strict majority of lenses return PASS AND at least one piece of concrete filesystem or test evidence is supplied. A task earns FAIL if any critical lens fails or evidence is absent. The `[X]` mark in `tasks.md` is never accepted as evidence; only the commands below are.

---

## Task Verification Matrix

### T[ID] [Task Title]

**Status**: PASS / FAIL / PARTIAL

**Acceptance criteria (from tasks.md)**:

> [Copy the exact acceptance criteria text from the task spec here.]

#### Lens 1, file-exists

Command to run:

```bash
# Confirm every file the task names was created or modified.
ls -la [path/to/expected/file1]
ls -la [path/to/expected/file2]
git show --stat HEAD -- [path/to/expected/file1]
```

Result: PASS / FAIL

Evidence:

> [Paste actual command output or "MISSING, file not found".]

#### Lens 2, spec-match

Command to run:

```bash
# Confirm the implementation matches the acceptance criteria.
# Grep for key symbols, function signatures, or config values named in the spec.
grep -n "[expected_symbol_or_value]" [path/to/file]
```

Result: PASS / FAIL

Evidence:

> [Paste grep output or explain what was checked and what was found vs. expected.]

#### Lens 3, tests-pass

Command to run:

```bash
# Run the test(s) that directly cover this task.
# Replace with the actual test runner and filter for this project.
pytest [path/to/test_file.py] -v
# or: npm test -- --testPathPattern=[pattern]
# or: go test ./... -run [TestName]
```

Result: PASS / FAIL

Evidence:

> [Paste test runner output summary, e.g. "3 passed, 0 failed" or the failure trace.]

#### Lens 4, git-consistent

Command to run:

```bash
# Confirm git state is consistent with the claimed change.
git log --oneline -5
git diff HEAD~1 --name-only
git status --short
```

Result: PASS / FAIL

Evidence:

> [Paste output confirming the expected files appear in the diff, or describe the inconsistency.]

#### Majority verdict

Lenses passed: [0-4] / 4

Verdict: **PASS** (majority with evidence) / **FAIL** (minority or no evidence)

If FAIL, recommended action: revert task to `[ ]` in tasks.md and re-queue with the failures below as guidance.

Failures:

- [Describe each failure with the lens name, the command that was run, and the actual vs. expected output.]

---

[Repeat the block above for every task in tasks.md.]

---

## Summary Table

| Task ID | Title | file-exists | spec-match | tests-pass | git-consistent | Verdict |
|---------|-------|-------------|------------|------------|----------------|---------|
| T001    | ...   | PASS/FAIL   | PASS/FAIL  | PASS/FAIL  | PASS/FAIL      | PASS/FAIL |
| T002    | ...   | PASS/FAIL   | PASS/FAIL  | PASS/FAIL  | PASS/FAIL      | PASS/FAIL |

---

## Reverted Tasks (require re-implementation)

Tasks whose `[X]` mark was reverted to `[ ]` by this verification run:

- T[ID]: [reason, evidence reference]

---

## Verification Gate Result

All `[X]` tasks confirmed by independent evidence: YES / NO

If NO, this report must be re-run after re-implementation before completion is claimed.
