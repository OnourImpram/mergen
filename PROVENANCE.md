# Provenance and lineage

Mergen is a new repository. It was not renamed from another project in place. It was seeded from the
operator's own prior repository and then transformed into its own identity. This file records exactly what
was inherited and what changed, so the lineage stays visible and honest.

## Seed

Mergen's execution engine was seeded from `TheGoatPsy/claude-code-hypercode` (v1.1.0), the operator's own
private spec-driven-development and effort-mode toolkit. That repository is the operator's own work, so the
seed carries no third-party obligation. The seed brought across the single-source command suite
(`core/commands/`), the two renderers (`dist/native`, `dist/speckit`), the cross-agent renderer
(`dist/agents`), the effort-mode hook, the minimalism discipline (`core/lazy-ladder.md`), the drift gate
(`scripts/check_sync.py`), the eval methodology, the templates, the tests, the installers, and the docs.

## Identity transform

Every occurrence of the prior internal names was transformed into Mergen, preserving casing.

- hypercode, Hypercode, HYPERCODE became mergen, Mergen, MERGEN
- hyperspec, Hyperspec, HYPERSPEC became mergen, Mergen, MERGEN
- the repository slug `claude-code-hypercode` became `mergen`

Command surface. `/hypercode` became `/mergen`. The `/hyperspec.<cmd>` family became `/mergen.<cmd>`. The
native skill prefix `hyperspec-<name>` became `mergen-<name>`. The spec-kit preset and extension became
`mergen` with `speckit.mergen.<cmd>` ids. The deferred-shortcut comment convention `hyperspec:` became
`mergen:`. The state marker `~/.omc/state/hypercode.json` became `~/.claude/mergen.json`.

Files renamed. `effort-mode/commands/hypercode.md` to `mergen.md`, and
`effort-mode/hooks/hypercode_prompt_hook.py` to `mergen_prompt_hook.py`. The generated spec-kit output was
deleted and regenerated from the transformed source, so `dist/speckit/preset/mergen` and
`dist/speckit/extensions/mergen` are fresh renders, not edited copies.

Verified after transform. All `hyper*` tokens were removed from the operational source and the rendered
tree. The only surviving mentions are in this file and `CHANGELOG.md`, which record the rename lineage on
purpose. `check_sync` reports the committed output in sync with `core/`. The native renderer plans 14
skills. The test suite passes.

## Naming

The GitHub repository is `TheGoatPsy/mergen`. The bare `mergen` name on npm is taken by an unrelated
package, so the npm publishing identity, if and when Mergen publishes, is the scoped name
`@thegoatpsy/mergen`.

## Relationship to mneme

Mergen is the execution layer. mneme (`TheGoatPsy/mneme`, published and MIT) is the memory layer and remains
untouched. No mneme package name (`mneme-core`, `mneme-mcp-server`, `mneme-cc-plugin`, the `mneme-mcp`
command) was renamed, forked, or vendored. Mergen consumes mneme only across the documented seam, through
mneme's public interface.

## Reference principles

Mergen's operating principles were informed by responsible-AI design principles studied from a reference
system prompt. No proprietary prompt text was copied into this repository. The principles are re-expressed
in Mergen's own voice in `MERGEN.md` and mapped to components in `MERGEN_PRINCIPLES.md`. A repository check
fails the build if verbatim reference text appears.
