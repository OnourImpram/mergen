# Mergen host capability matrix

Generated from `core/adapters/*.json` by `scripts/adapter_sdk.py`. Do not edit by hand.
Run `mergen adapter render --write` to regenerate it after a manifest changes.

| Capability | Claude Code (native skills) | GitHub Spec Kit (preset plus extension) | Generic agents (AGENTS.md, Cursor, Windsurf, Cline, Copilot, Kiro) |
| --- | --- | --- | --- |
| `slash_commands` | yes | yes | no |
| `command_suite` | yes | yes | no |
| `lifecycle_hooks` | yes | no | no |
| `settings_registration` | yes | no | no |
| `project_bootstrap` | yes | no | no |
| `workflow_orchestration` | yes | no | no |
| `verify_gate` | yes | yes | no |
| `passive_rules` | no | no | yes |

## Honest scope per host

- **native**: The full engine. The mergen command suite as /mergen-* skills, lifecycle hooks, and the Workflow-orchestrated SDD pipeline, the one host where the orchestration runs.
- **speckit**: A preset that overrides Spec Kit's own commands plus a mergen extension. The command suite is present and the verify gate runs as an after_implement hook. It does not run Claude Code lifecycle hooks or the Workflow orchestration, and it does not bootstrap a mergen scaffold of its own. Spec Kit's own specify init creates the .specify directory.
- **agents**: Ports the lazy-ladder minimalism discipline only, as a passive rule file. It does not port, and does not claim to port, the command suite, the verify gate, or the Workflow orchestration.
