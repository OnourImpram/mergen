# The lazy ladder (minimalism discipline)

mergen reasons exhaustively and then builds the minimum that works. Maximum
effort is spent on thinking, not on producing code. The best code is the code
never written. This discipline is derived from the "lazy senior dev" ruleset of
`ponytail` (MIT, see `ATTRIBUTION.md`) and is the operational form of the
operator's standing rules (Simplicity First, Demand Elegance, smallest correct
change).

## The ladder

Before writing any code, stop at the first rung that holds:

1. Does this need to be built at all? If no, skip it (YAGNI).
2. Does the standard library already do this? Use it.
3. Does a native platform feature cover it? Use it.
4. Does an already-installed dependency solve it? Use it.
5. Can this be one line? Make it one line.
6. Only then write the minimum code that works.

## Rules

- No abstractions that were not explicitly requested.
- No new dependency if it can be avoided.
- No boilerplate nobody asked for.
- Deletion over addition. Boring over clever. Fewest files possible.
- Question complex requests. Ask whether the requester needs X, or whether Y already covers it.
- When two standard-library approaches are the same size, pick the edge-case-correct one. Lazy means less code, not the flimsier algorithm.

## Never lazy about

Input validation at trust boundaries, error handling that prevents data loss,
security, accessibility, calibration that real hardware needs, and anything
explicitly requested are never on the chopping block. Lazy code without its
check is unfinished. Non-trivial logic leaves one runnable check behind, the
smallest thing that fails if the logic breaks. Trivial one-liners need no test.

## The `mergen:` deferred-shortcut convention

Mark every intentional simplification with a `mergen:` comment. When the
shortcut has a known ceiling (a global lock, an O(n squared) scan, a naive
heuristic), the comment names the ceiling and the upgrade path so "later" does
not become "never":

```
# mergen: global lock. switch to per-account locks if throughput matters.
```

`/mergen-debt` harvests these comments into a ledger so deferred work stays
visible across the spec-driven lifecycle.

## How the lifecycle uses the ladder

- `/mergen-plan` prefers stdlib, native, and installed dependencies over new
  abstractions, and its architecture-critic rejects complexity the spec does not require.
- `/mergen-implement` builds each task to the ladder, and its adversarial
  verifier checks that the result is minimal as well as correct.
- `/mergen-lean` reviews a diff or the repo for over-engineering and returns
  a delete-list. It judges complexity only, never correctness.
