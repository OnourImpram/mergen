# Packaging and distribution

This is the packaging-prep note for mergen. It states honestly what ships today, what is ready to
be packaged for a marketplace, and what the actual publication needs that this repository cannot
supply on its own. It does not claim a distribution path that is not yet live.

## What ships and works today

Two install paths are real, tested, and documented in the README.

- Native install. `./install.sh` (or `.\install.ps1`) renders the command suite into Claude Code
  skills under `~/.claude/skills/`, installs the lifecycle hooks, and registers them. The same
  steps run idempotently through the Python CLI: `pipx install -e .` then `mergen install`, with
  `mergen uninstall` removing every artifact it created.
- Spec Kit install. `./install.sh --speckit` renders the committed preset and extension under
  `dist/speckit/`, which a Spec Kit user adds with `specify preset add` and `specify extension add`.

Both are single-source renders from `core/`, guarded against drift by `scripts/check_sync.py`.

## What is ready for marketplace packaging

The Adapter SDK already declares, as data, exactly what each host can and cannot do
(`core/adapters/*.json`, surfaced in `docs/CAPABILITIES.md`). A marketplace listing is a faithful
restatement of that declared truth, so the honest scope per host is settled and machine readable
before any listing exists. The renderers produce the host-specific artifacts a package would
bundle, and the Policy Pack SDK gives a domain a shareable, validated form. These are the pieces a
package would assemble.

## What the actual publication needs (external)

Publishing to a marketplace is not a step this repository can take by itself, and it is named here
rather than faked.

- A Claude Code plugin marketplace listing needs a real `marketplace.json` plus a plugin manifest
  that point at a published, versioned artifact, and it needs the operator's marketplace account
  and a deliberate decision to publish. Until that artifact is published, this repository does not
  ship a `marketplace.json`, because a listing that advertises an install command that does not yet
  resolve would be exactly the kind of page-as-honest-as-the-product failure mergen is built to
  prevent.
- A PyPI distribution (so `pipx install mergen` resolves without `-e .`) needs a built wheel that
  bundles `core/` as package data and a release uploaded under the operator's account. The wheel
  layout is on the roadmap; the editable install is the supported path until then.

## The honest line

The packaging is prepared in the sense that the declared capabilities, the renderers, and the
shareable pack form are all in place. The publication is a deliberate operator action, with a real
account and a real published artifact, and it is named as external rather than claimed as done.
