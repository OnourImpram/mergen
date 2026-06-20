---
name: mergen
description: Arm mergen mode (max reasoning effort + standing dynamic-workflow orchestration), one tier above native ultracode. Activation is explicit (only this command) and session-scoped (the current session only). Writes a marker and emits the /effort max line to paste. Run "/mergen off" to disarm. Run "/mergen status" to check.
argument-hint: "[off|status]"
tags: [effort, orchestration, mergen]
---

# /mergen

`mergen` is the top of the effort ladder, `max` reasoning, combined with standing dynamic-workflow orchestration on every substantive task. It is one tier above native `ultracode` (`xhigh + dynamic workflow orchestration`).

Claude Code couples the native `ultracode` flag to `xhigh` in the compiled binary (`effortValue: ultracode ? "xhigh" : ...`), so `max + orchestration` is not reachable through any single native command. The two halves are reconstructed separately. The orchestration half comes from this command's standing directive (a slash command instructing Workflow use is a documented Workflow opt-in). The max half comes from the interactive `/effort max` command, which only the user can type.

## What to do

Look at `$ARGUMENTS`. If it is `off`, DISARM. If it is `status`, CHECK. Otherwise, ARM.

### ARM (no argument)

1. Write the marker (use a real ISO timestamp):

```bash
mkdir -p ~/.claude && printf '{"active": true, "mode": "mergen", "started_at": "%s", "note": "max reasoning + standing workflow orchestration"}\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > ~/.claude/mergen.json && echo "mergen armed"
```

2. Show the user this exact block (the genuine native `max` tier only opens through the interactive command, so this one paste is the single manual step):

> Mergen armed. To open the genuine max effort tier, paste this line into Claude Code once:
>
>     /effort max

3. For the rest of this session, the UserPromptSubmit hook (`mergen_prompt_hook.py`) injects the mergen standing directive each turn: max reasoning posture, default Workflow orchestration, adversarial verification. A new session starts clean until you run /mergen again. Acknowledge briefly, do not repeat it.

**Custom directive (optional):** The marker file accepts an optional `directive` field. If present, the hook uses that string instead of the built-in directive. This lets you customise without editing hook code (which the installer overwrites on upgrade). Example one-liner to set it:

```bash
python3 -c "
import json, pathlib
p = pathlib.Path.home() / '.claude' / 'mergen.json'
d = json.loads(p.read_text())
d['directive'] = 'My custom directive.'
p.write_text(json.dumps(d, indent=2))
"
```

To revert to the default, remove the `directive` key from the marker JSON.

### DISARM (`$ARGUMENTS` is `off`)

1. Remove the marker:

```bash
rm -f ~/.claude/mergen.json && echo "mergen off"
```

2. Tell the user mergen is off and the standing directive will no longer inject. Effort does not drop on its own. To lower it, paste `/effort high` (or another level).

### CHECK (`$ARGUMENTS` is `status`)

1. Read the marker:

```bash
if [ -f ~/.claude/mergen.json ]; then
  cat ~/.claude/mergen.json
else
  echo "mergen: DISARMED (marker absent)"
fi
```

2. Report the result clearly:
   - If the file exists and `active` is `true`: print `mergen: ARMED since <started_at>` plus the note field.
   - If the file exists and `active` is `false`: print `mergen: DISARMED (active: false)`.
   - If the file does not exist: print `mergen: DISARMED (marker absent)`.
   - If a custom `directive` key is present, also note: `Custom directive: active`.

## Notes

- The marker snippets above are POSIX shell. On Windows they run under Claude Code's Bash tool (Git Bash), so no change is needed there. In a native PowerShell session, create or remove the same `~/.claude/mergen.json` marker with PowerShell idioms (`New-Item`, `Set-Content`, `Remove-Item`). The marker contract is the file and its JSON, not the shell that writes it.
- Activation is explicit. Only this command activates mergen. Mentioning the word `mergen` in a prompt does not turn it on.
- Activation is session-scoped. The marker at `~/.claude/mergen.json` binds to the session where you ran /mergen on its first prompt, and the directive injects only in that session. A new session starts clean (the marker, still bound to the old session, is inert) until you run /mergen again. Use `/mergen off` to disarm explicitly.

## Related

- ultracode (native): `xhigh + dynamic workflow orchestration`
- Hook: `~/.claude/hooks/mergen_prompt_hook.py`
- Design and binary evidence: `docs/HOW-IT-WORKS.md`
