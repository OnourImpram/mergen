# Mergen milestone verification release

Date: 2026-07-16

Mergen is now published on the default branch as an independent, fail-closed milestone verification layer for externally managed engineering workflows.

## Product boundary

External executors such as Codex, Claude Code, OpenHands, continuous integration systems, and human teams retain ownership of planning, implementation, remediation, and workflow progression. Mergen independently inspects the milestone state, reproduces deterministic evidence where possible, applies the Governor risk floor, and returns an advancement decision.

Mergen does not start the next stage. It does not treat an executor completion statement as proof. It does not modify an implementation artifact and approve that same modification in one verification context.

## Shipped surface

- `mergen-supervise`, the standalone milestone supervisor.
- Milestone decision schema 1.1.
- `pass`, `conditional_pass`, `fail`, and `unverifiable` verdicts.
- `advance`, `human_review_required`, `return_for_remediation`, and `hold` actions.
- Fresh deterministic reproduction by default.
- Independent risk-floor reclassification and risk downgrade detection.
- Exact-report human approval binding through the existing offline HMAC signer.
- Evidence classes, source-state hashing, decision hashing, SHA-256 sidecars, and human-readable Markdown.
- Professional README, package metadata, security guidance, contribution guidance, support guidance, issue forms, and pull request intake.

## Compatibility

The package remains `mergen`. The Apache-2.0 license is unchanged. Existing CLI verbs remain available. The prior specification-driven command suite and `/mergen-agent` lifecycle orchestrator remain available as compatibility tooling.

## Verification evidence

The release change passed the complete GitHub Actions matrix across supported Python versions and Windows. Ruff, strict mypy, coverage, version consistency, schema validation, renderer synchronization, phantom-completion dogfood, CodeQL, dependency review, and gitleaks also passed.

## Honest limitations

The bundled supervisor profile currently verifies Mergen software task reports. Broader domain profiles remain explicit extension points. Provenance establishes lineage, not universal semantic correctness. A passing milestone is supported under the checks that ran and is not a guarantee that every possible defect is absent.
