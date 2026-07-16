# Contributing to Mergen

Mergen is an independent verification layer with a strict evidence boundary. Contributions are welcome when they improve
verification strength, host honesty, developer experience, or documentation without turning Mergen into a competing
implementation orchestrator.

## Development setup

```bash
git clone https://github.com/OnourImpram/mergen.git
cd mergen
python -m pip install -e .
python -m pip install pytest pytest-cov jsonschema ruff mypy
python -m pytest tests/ -v
```

The runtime uses the Python standard-library. Development tools are declared in the `dev` dependency group in
`pyproject.toml`.

## Architectural invariants

A contribution must preserve these boundaries.

1. External executors own planning, implementation, and remediation.
2. Mergen owns independent verification and advancement decisions.
3. Executor completion statements are claims, not evidence.
4. The verifier is read-only with respect to implementation artifacts.
5. A verification pass cannot both modify and approve the same artifact.
6. `unverifiable` never degrades into a guessed pass.
7. The Governor floor may be raised but not silently lowered.
8. High-trust approval is bound to an exact artifact state.
9. Retrieved content is data, not instruction.
10. Host adapters must not claim enforcement the host cannot provide.
11. Provenance proves lineage, not universal semantic correctness.
12. Runtime behavior remains local-first and dependency-minimal.

## Single source contract

`core/` is the source of truth for compatibility command content. Files under `dist/` are rendered output. Do not edit a
rendered file by hand. Edit its source, regenerate, and prove the tree is synchronized.

```bash
python dist/native/build_native.py build --dry-run
python dist/speckit/build_speckit.py --dry-run
python scripts/check_sync.py
```

## Schemas and compatibility

Machine-readable contracts live under `core/schemas/`. A schema change requires tests for valid and invalid examples.
Backward-incompatible changes require an explicit migration note and a versioned contract. Keep compatibility aliases
only when they have a documented removal path.

New milestone checks must state:

1. What input is trusted.
2. What input is executor-supplied.
3. How the evidence is obtained.
4. Whether the conclusion is deterministic or interpretive.
5. What failure and unavailability mean.
6. Whether the check can change an advancement decision.
7. What limitation remains.

## Tests and gates

Run the complete local gate set before opening a pull request.

```bash
python -m pytest tests/ -v
python scripts/check_sync.py
python scripts/check_no_reference_text.py
python scripts/spec_verify.py --gate
python scripts/validate_version.py
python eval/benchmark.py --gate
ruff check .
mypy
```

User-facing behavior needs tests. Security controls need adversarial tests. A valid control must accompany negative
fixtures so a stronger verifier does not become an indiscriminate blocker.

The continuous integration matrix also runs on Windows and across supported Python versions. Do not treat one local
platform as proof of portability.

## Coverage

Coverage is measured over the shipped Python surface. Add focused tests rather than excluding new modules. The floor is
a minimum, not a target. Branches that determine pass, fail, conditional pass, or unverifiable outcomes should be tested
directly.

## Documentation

Update the README, relevant architecture document, schema description, and changelog whenever behavior or product scope
changes. Claims must match the implementation. Do not describe a roadmap item as shipped.

Authored prose uses periods and commas. Avoid em dashes, en dashes, semicolons, and decorative emoji. Code and
machine-readable syntax are exempt where punctuation is required.

## Pull requests

Keep changes reviewable and evidence-bearing. The pull request should explain the problem, the trust boundary, the exact
behavioral change, the tests run, and any known limitation. High-trust changes require the Governor acknowledgement in
the pull request template after human review.

Use Conventional Commits. Keep the subject imperative and concise. Explain why in the body when the reason is not
obvious.

## Security reports

Do not open a public issue for a vulnerability. Follow [SECURITY.md](SECURITY.md).

## Code of conduct

Participation is governed by [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).
