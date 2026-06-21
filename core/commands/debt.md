---
description: "Harvest mergen: deferred-shortcut comments into a debt ledger so simplifications stay visible across the lifecycle."
argument-hint: "Empty to harvest into the ledger, 'check' to fail on any shortcut with no named ceiling, or a path to narrow the scan"
---

## User Input

```text
$ARGUMENTS
```

If `$ARGUMENTS` contains `check`, run in gate mode (see Gate mode below). If it names a path, scan only that subtree. Otherwise harvest the whole repository into the ledger. Default is harvest mode over the repository.

## mergen substrate (do this first)

This command runs under the mergen substrate: maximum reasoning effort plus Workflow orchestration. It is the bookkeeping counterpart to the lazy ladder (`core/lazy-ladder.md`). `/mergen-lean` finds over-engineering that should be cut now. This command tracks the simplifications already taken, so a deferred shortcut does not become permanent by silence.

The harvest itself is a deterministic scan, not a reasoning task. Do not inflate it. The substrate earns its place in two narrow steps: classifying each shortcut by risk, and enforcing that every shortcut named a ceiling and an upgrade path. For a small surface, do both in this context. For a large repository, use the Workflow tool to fan out one classifier per top-level source directory, then merge.

## The convention being harvested

A `mergen:` comment marks an intentional simplification. When the shortcut has a known ceiling, the comment names the ceiling and the upgrade path so "later" does not become "never":

```
# mergen: global lock. switch to per-account locks if throughput matters.
```

The form is `mergen: <what was simplified>. <ceiling and the upgrade trigger>.` The convention is defined in `core/lazy-ladder.md`.

## Harvest

1. Collect every `mergen:` comment in the scan scope. Skip `node_modules`, `.git`, build output, and vendored or generated directories. A portable scan:

   ```bash
   git grep -n 'mergen:' -- . ':!*.lock' ':!dist/*'
   ```

   Fall back to a recursive `grep -rn 'mergen:'` when the tree is not a git repository.

2. Parse each hit into a record: `file:line`, the text after `mergen:` split at the first sentence boundary into `simplified` (what was made simpler) and `ceiling` (the named limit plus the upgrade trigger, or empty when absent).

3. Reconcile with the existing ledger at `.specify/memory/debt.md` if it is present. For a shortcut already recorded at the same `file:line` and text, increment its `survived` count (the number of harvests it has outlived without being upgraded). A rising `survived` count is the signal that a "later" is turning into a "never". A shortcut whose comment is gone since the last harvest is moved to a `## Resolved` section with the harvest date supplied in `$ARGUMENTS` or omitted when not supplied.

## Classify (Workflow when the surface is large)

For each shortcut, assign a risk band:

- `high`: the ceiling is named and names a correctness, security, or data-loss boundary (a global lock, an unbounded buffer, a naive auth check). These are deferred risks, not cosmetic ones.
- `medium`: the ceiling is named and names a performance or scale limit (an O(n squared) scan, a synchronous call that should batch).
- `low`: a cosmetic or local simplification with a named ceiling.
- `unnamed`: the comment has no ceiling or upgrade path. This violates the convention. It is a defect regardless of the underlying risk, because nobody can decide when to upgrade a shortcut whose limit was never written down.

## Write the ledger

Write or update `.specify/memory/debt.md`. Group by risk band, highest first. Each row is one line:

`<file>:<line> | <simplified> | <ceiling or UNNAMED> | survived: <n>`

End with the only counts that matter:

`total: <N> shortcuts. unnamed: <U>. high-risk: <H>.`

If there are no `mergen:` comments in scope, write `No deferred shortcuts recorded.` and stop.

## Gate mode (`$ARGUMENTS` contains `check`)

Do not write the ledger. Instead report every `unnamed` shortcut as a defect in the form `<file>:<line>: mergen comment has no named ceiling or upgrade path`. State `PASS` only when every `mergen:` comment in scope names a ceiling and an upgrade trigger. State `FAIL` with the defect list otherwise. This mode is for CI and pre-commit use. It makes the convention enforceable instead of advisory.

## Done When

- [ ] Every `mergen:` comment in scope was collected, with `file:line`.
- [ ] Each shortcut was classified, and any comment lacking a ceiling and upgrade path was marked `unnamed`.
- [ ] Harvest mode wrote `.specify/memory/debt.md` grouped by risk with the summary counts, or recorded that none exist.
- [ ] Gate mode returned `PASS` only when no `unnamed` shortcut remained, otherwise `FAIL` with the defect list.
- [ ] The command did not edit any source comment. It only reads and records.
