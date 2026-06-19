# How mergen works

## The native effort model

Claude Code's effort state, as observed in the compiled binary, is two independent fields:

- `effortValue`, one of `["low", "medium", "high", "xhigh", "max"]`
- `ultracode`, a boolean that turns on a standing "use the Workflow tool to orchestrate every substantive task" directive

The interactive `/effort` picker exposes six entries: the five effort levels plus `ultracode`, which is shown as `xhigh + dynamic workflow orchestration`.

## The coupling that makes `max + orchestration` unreachable

The two fields are not freely combinable. Three observed behaviors pin this down:

1. When `ultracode` is turned on, the effort value is forced to `xhigh`. The state reducer is, in effect, `{ ...state, ultracode: on, effortValue: on ? "xhigh" : state.effortValue }`, and the resolver returns `{ value: "xhigh" }` whenever the level is `ultracode`. Requests are sent with `effort: level === "ultracode" ? "xhigh" : level`.
2. Selecting any plain level, including `max`, sets `ultracode` to `false`.
3. The persisted settings schema for `effortLevel` only accepts `["low", "medium", "high", "xhigh"]`. Both `max` and `ultracode` are session-scoped and are not written to disk as a persisted effort level.

Together these mean there is no command and no `settings.json` value that yields `max` effort with the orchestration directive at the same time. They are mutually exclusive in the binary. Adding a new native `/effort` level is also not possible, because the ladder is compiled in.

## The two-halves reconstruction

`mergen` rebuilds the combination from two supported, independent mechanisms.

### Half 1: standing orchestration via a hook

A `UserPromptSubmit` hook runs on every turn. When the mode is armed it returns:

```json
{ "hookSpecificOutput": { "hookEventName": "UserPromptSubmit", "additionalContext": "Mergen is on: ..." } }
```

Claude Code injects the `additionalContext` field returned by a `UserPromptSubmit` hook into the model context for that turn. `additionalContext` is a documented hook output field (the same field name other hook events such as `SessionStart` also use), so this is a supported channel rather than a workaround. The injected text instructs the model to orchestrate with the Workflow tool by default and to adversarially verify before claiming completion. The Workflow tool explicitly accepts "a skill or slash command whose instructions tell you to call Workflow" as a valid opt-in, so this is a documented path rather than a workaround.

This faithfully reproduces native ultracode's per-turn standing reminder, but at the `max` tier instead of `xhigh`.

### Custom directive

By default the hook injects the built-in `DIRECTIVE` constant. If `~/.claude/mergen.json` contains a `"directive"` key, the hook uses that string instead. This allows customisation without editing the hook file itself, which the installer overwrites on upgrade. The built-in string remains the default when the key is absent or empty.

Example: add a project-specific instruction:

```bash
python3 -c "
import json, pathlib
p = pathlib.Path.home() / '.claude' / 'mergen.json'
d = json.loads(p.read_text())
d['directive'] = 'Mergen is on: max reasoning. Always write tests before implementation.'
p.write_text(json.dumps(d, indent=2))
"
```

To revert to the built-in directive, delete the `directive` key from the marker.

### Half 2: max effort via one paste

The genuine native `max` tier is only opened by the interactive `/effort max` command. A hook cannot flip the live effort value (the control channel that applies effort is not exposed to hooks), and `max` cannot be persisted in `settings.json`. So the `/mergen` command prints the `/effort max` line for you to paste once. This single manual step is irreducible. It is the honest cost of reaching a tier the binary does not let any extension set programmatically.

## Why a hook and not a "keep working" loop

Some Claude Code orchestration modes (for example persistence loops) use a `Stop` hook that blocks the session from ending to force continued work. `mergen` deliberately does **not** do that. It is a reasoning posture, not a never-stop loop. A `UserPromptSubmit` advisory injects guidance without preventing the session from stopping normally, which is the correct shape for "reason harder and orchestrate," and it keeps the tool from interfering with other modes.

## State and lifecycle

- Armed state is a single marker file at `~/.claude/mergen.json` with `{"active": true, ...}`.
- Activation is explicit. Only the `/mergen` command writes the marker. Mentioning the word `mergen` in a prompt does not activate the mode. There is no keyword auto-trigger.
- Activation is session-scoped. The first prompt seen after arming binds the marker to that session id (`{"active": true, "session_id": "..."}`), and the directive injects only for prompts in that session. A new session starts clean. The marker, still bound to the old session, is inert there until you run `/mergen` again, which rebinds it to the new session. Disarm any time with `/mergen off`.
- The optional `directive` field in the marker allows customising the injected text without forking the hook file.

## Caveats

- The exact binary internals above were observed in a specific Claude Code build. Anthropic may change the effort model in future versions. If the `UserPromptSubmit` `additionalContext` channel or the `/effort` command changes, this tool may need updating.
- `max` effort can use significantly more tokens and take longer. Disarm when you do not need it.
