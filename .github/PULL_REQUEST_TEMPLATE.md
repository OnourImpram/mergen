<!-- Mergen pull request. Keep the description honest and evidence-bearing, the
     same standard the tool enforces. Delete sections that do not apply. -->

## What and why

<!-- One paragraph. What changes, and what problem it solves. -->

## Evidence

<!-- How you know it works. The verification report, the tests you ran, the
     output you checked. A claim without evidence is a claim, not a result. -->

- [ ] Tests pass on 3.9 and 3.11 (`python -m pytest tests/ -q`)
- [ ] `ruff check .`, `mypy`, `python scripts/check_sync.py`, and `python scripts/check_no_reference_text.py` are green
- [ ] Docs and CHANGELOG updated where user-facing behavior changed

## Governor acknowledgement

<!-- The govern-diff CI gate classifies the real diff against the deterministic
     high-trust floor (auth, payment, secrets, privacy, clinical, irreversible
     operations, public-contract changes, untrusted-input-as-instruction). A
     high-trust change fails the build unless this line is present in the PR body,
     exactly as written, on its own line. The floor is non-downgradable: it can be
     raised but never silently lowered. Add the line only after a human has
     reviewed the high-trust change. -->

<!-- Uncomment the next line if the diff is high-trust: -->
<!-- Governor-Ack: high-trust -->

## Scope honesty

<!-- Anything deferred, any caveat, any place the change is narrower than it
     might appear. Name it here rather than letting a reader infer more. -->
