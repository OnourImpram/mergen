---
description: "Review the diff or repo for over-engineering and return a delete-list. Complexity only, never correctness."
argument-hint: "Empty for the current diff, 'audit' for the whole repo, or lite|full|ultra for intensity"
---

## User Input

```text
$ARGUMENTS
```

If `$ARGUMENTS` contains `audit`, scan the whole repository tree, not just the diff. Otherwise review the current uncommitted diff (`git diff` plus staged). If it names an intensity (`lite`, `full`, `ultra`), apply that intensity. Default scope is the diff, default intensity is `full`.

## mergen substrate (do this first)

This command runs under the mergen substrate: maximum reasoning effort plus Workflow orchestration. It is the minimalism counterpart to `/mergen.verify`. `/mergen.verify` proves the code is correct. This command proves the code is minimal. Use the Workflow tool to fan out the review. Reviewing a large diff or repo in this single context is the shallow failure mode this command exists to prevent.

## Scope (read before reviewing)

Over-engineering and complexity ONLY. Correctness bugs, security holes, and performance belong to `/mergen.verify` and a normal review pass. Do not flag them here. A single smoke test or assert-based self-check is the lazy-ladder minimum, not bloat. Never flag validation, security, accessibility, error handling, or tests for deletion. The discipline is `core/lazy-ladder.md`.

## Review (Workflow fan-out)

1. Collect the review surface. Diff mode: `git diff HEAD` and `git diff --staged`, grouped by file. Audit mode: the source tree, skipping `node_modules`, `.git`, build output, and vendored or generated directories.
2. Use the Workflow tool to spawn one reviewer per file or coherent area, in parallel, each blind to the others. Each reviewer hunts only for over-engineering against the lazy ladder: reinvented standard library, dependencies for what the platform already does, speculative abstractions, dead flexibility, config nobody sets, layers with one caller, manual code a one-liner replaces.
3. Each finding is one line:

   `L<line>: <tag> <what>. <replacement>.` or `<file>:L<line>: <tag> <what>. <replacement>.` for multiple files.

   Tags:
   - `delete`: dead code, unused flexibility, speculative feature. Replacement: nothing.
   - `stdlib`: a hand-rolled thing the standard library ships. Name the function.
   - `native`: a dependency or code doing what the platform already does. Name the feature.
   - `yagni`: an abstraction with one implementation, config nobody sets, a layer with one caller.
   - `shrink`: same logic, fewer lines. Show the shorter form.

4. A synthesis step (this context, after the lane returns) deduplicates findings across reviewers and ranks them biggest cut first.

## Intensity

- `lite`: name the lazier alternative for each finding. The user decides.
- `full`: the ladder enforced. List every cut. Default.
- `ultra`: deletion-first. Lead with what should not exist at all, then challenge the requirement that asked for it.

## Output

A ranked delete-list in the format above. End with the only metric that matters:

`net: -<N> lines possible` (audit mode also reports `-<N> dependencies removable`).

If there is nothing to cut, output `Lean already. Ship.` and stop. This command lists cuts. It does not apply them.

## Done When

- [ ] The Workflow tool fanned out the review. A single-context monologue review is not acceptable for a non-trivial surface.
- [ ] Every finding is one line with a tag and a concrete replacement.
- [ ] Correctness, security, and performance were left out of scope (routed to `/mergen.verify`).
- [ ] The output ends with `net: -<N> lines possible` or `Lean already. Ship.`
- [ ] No fix was applied. The command only lists.
