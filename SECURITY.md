# Security

## Reporting

If you find a security issue, please report it privately. Open a private security
advisory on this repository through the Security tab, or contact the maintainer
through the GitHub profile at https://github.com/OnourImpram. Please do not open a
public issue for a vulnerability.

Include the affected file or command, the conditions that trigger the issue, and
the impact you observed. A minimal reproduction helps. You can expect an
acknowledgement and a path forward.

## Scope and posture

Mergen is built entirely from public Claude Code extension points (slash commands,
hooks, and `settings.json`). It does not patch or modify the Claude Code binary.
The core loop runs on the Python standard library, requires no network, and runs
no model on its critical path.

The settings patchers are corruption-safe and idempotent. They strip a UTF-8 BOM
before parsing, preserve all unrelated settings, and never write secrets. Mergen
does not store, log, or transmit credentials. The hooks are fail-soft. They exit
zero and no-op when their inputs are absent or unreadable, so a malformed state
file cannot block a session.

Retrieved content is treated as data, never as instruction. A task file, a spec,
or an external page is material to reason about. None of it is a command to obey
or a grant of new capability. This boundary is a security property, not only a
correctness one.

## What is not a vulnerability

The in-session pipeline asks and nudges. A person can edit a task file by hand.
That is documented honestly in `MERGEN.md` and is not a defect. The layer that
refuses is the CI gate (`eval/ci/verify-gate.yml`), which a project adds to its
own continuous integration.
