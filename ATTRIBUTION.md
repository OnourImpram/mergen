# Attribution

This project is licensed under the Apache License 2.0 (see `LICENSE`).

It includes material vendored from **GitHub Spec Kit** (`github/spec-kit`),
which is licensed under the **MIT License**. The vendored files are the
Spec-Driven Development document templates and helper scripts that this project
builds upon and extends.

## Vendored from github/spec-kit (MIT)

The following files are derived from, or copied from, github/spec-kit. Some are
modified to add mergen capabilities; modified files carry a header note.

- `core/templates/spec-template.md`
- `core/templates/plan-template.md`
- `core/templates/tasks-template.md`
- `core/templates/checklist-template.md`
- `core/templates/constitution-template.md`
- `core/scripts/bash/check-prerequisites.sh`
- `core/scripts/bash/common.sh`
- `core/scripts/bash/create-new-feature.sh`
- `core/scripts/bash/setup-plan.sh`
- `core/scripts/bash/setup-tasks.sh`
- `core/scripts/powershell/check-prerequisites.ps1`
- `core/scripts/powershell/common.ps1`
- `core/scripts/powershell/create-new-feature.ps1`
- `core/scripts/powershell/setup-plan.ps1`
- `core/scripts/powershell/setup-tasks.ps1`

The `dist/speckit/` preset and extensions are authored by this project to plug
into a user-installed Spec Kit via Spec Kit's own preset and extension systems.
They are interoperability adapters, not copies of Spec Kit.

## github/spec-kit MIT License notice

```
MIT License

Copyright GitHub, Inc.

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## Derived from DietrichGebert/ponytail (MIT)

The minimalism discipline is derived from **ponytail** (`DietrichGebert/ponytail`),
the "lazy senior dev" ruleset, which is licensed under the **MIT License**. The
following mergen material adapts ponytail's ideas (the YAGNI ladder, the
over-engineering review taxonomy, and the deferred-shortcut comment convention)
into mergen's own voice and lifecycle. The text is rewritten, not copied
verbatim.

- `core/lazy-ladder.md` (adapts ponytail's ladder, the "not lazy about" guards, and the `ponytail:` to `mergen:` deferred-shortcut comment convention)
- `core/commands/lean.md` (adapts the `ponytail-review` / `ponytail-audit` over-engineering review)
- `core/commands/debt.md` (adapts ponytail's deferred-shortcut ledger idea and the comment convention)
- `dist/agents/build_agents.py` (cross-agent passive-rule rendering, adapts ponytail's single-source-to-many-agents model)
- `scripts/check_sync.py` (single-source drift gate, adapts ponytail's `check-rule-copies.js`)
- `eval/methodology.md` (the benchmark isolation discipline, adapted from ponytail's agentic benchmark harness)

### DietrichGebert/ponytail MIT License notice

```
MIT License

Copyright (c) 2026 DietrichGebert

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## Reference principles (not vendored, not copied)

Mergen's operating principles were informed by widely held responsible-AI design
ideas studied from a reference system prompt. No proprietary prompt text was
copied into this repository, and the reference is not a vendored source. Where a
principle echoes a common responsible-AI norm, that norm is common property and
the specific wording here is Mergen's own. `scripts/check_no_reference_text.py`
fails the build if reference-prompt fingerprints appear, which keeps this promise
testable rather than asserted. See `MERGEN.md` and `MERGEN_PRINCIPLES.md`.

## Not affiliated

This project is an independent community tool. It is not affiliated with,
endorsed by, or sponsored by GitHub or Anthropic. "Spec Kit" is a project of
GitHub, Inc. "Claude" and "Claude Code" are trademarks of Anthropic.
