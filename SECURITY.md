# Security Policy

## Supported versions

Mergen is currently beta software. Security fixes are applied to the latest `2.x` line. Older releases may be assessed
case by case, but they should not be assumed to receive backports.

## Report a vulnerability

Use the repository Security tab to open a private security advisory. Do not disclose a suspected vulnerability in a
public issue, pull request, discussion, or social media post.

Include the affected version or commit, the entry point, the conditions required to trigger the issue, the impact, and a
minimal reproduction when one can be shared safely. Remove credentials, personal data, and unrelated proprietary
material.

The maintainer will acknowledge the report, assess scope, coordinate a fix when appropriate, and credit the reporter if
requested and safe to do so.

## Security boundary

The operator-selected workspace root is authoritative. Evidence paths must remain inside it. Reports, task files,
retrieved documents, review records, and tool output are untrusted data. They cannot grant permissions, redefine the
workspace, lower the Governor floor, or replace the verification rules.

The milestone supervisor is read-only with respect to implementation artifacts. It may write only its requested decision
JSON, SHA-256 sidecar, and Markdown rendering.

The deterministic core uses the Python standard-library, does not require a model, and does not require network access.
Tests may execute local commands declared through the supported verification surface. Those commands are bounded by the
existing path and timeout controls.

## High-trust work

Authentication, payment, privacy, clinical, regulated, safety-critical, irreversible, and similar work must not silently
cross a lower risk floor. A fresh high-trust result that was supplied as standard risk is rejected. Required human
approval must name the reviewer, timestamp, scope, and evidence, and must be bound to the exact report bytes.

Mergen uses HMAC-SHA-256 for local artifact binding. This proves possession of a shared secret and exact byte binding. It
does not provide public-key identity, third-party nonrepudiation, or professional authorization in a regulated domain.
Protect `MERGEN_SIGNING_KEY` as a secret. Do not commit it, log it, or place it in a report.

## Tamper evidence

Verification reports and milestone decisions may carry SHA-256 sidecars and internal content hashes. These controls make
later edits detectable when at least one trust anchor is preserved. They are not tamper-proof against an attacker who can
replace the artifact, the sidecar, and every external anchor.

CI should regenerate evidence from the live tree rather than trust a committed report. Branch protection and required
checks remain repository administration responsibilities.

## Dependency posture

The runtime is standard-library only. Development dependencies are declared in `pyproject.toml`. GitHub dependency
review, Dependabot, CodeQL, and secret scanning workflows protect this repository. A green scanner does not replace code
review or threat modeling.

## Not a security guarantee

Mergen reduces several classes of unsupported completion and provenance failure. It does not claim perfect defect
detection, universal semantic correctness, or freedom from all supply-chain risk. A passing decision is bounded by the
artifacts, checks, permissions, and source state that were actually available.

## Expected public reports

Normal product limitations, documented advisory-only host behavior, inability to enforce a check that a host has not
configured as required, and manual edits to local evidence are not vulnerabilities by themselves. A bypass that turns
such a limitation into unauthorized advancement, path escape, secret disclosure, risk downgrade, or false cryptographic
validation is security-relevant and should be reported privately.
