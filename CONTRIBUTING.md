# Contributing to Mergen

Mergen is original work with a strict single-source contract and an honest
posture about what it can and cannot enforce. A few rules keep both intact.
This is a small, focused tool. Contributions that stay within that scope are
most welcome.

## Development setup

```bash
git clone https://github.com/TheGoatPsy/mergen.git
cd mergen
pip install pytest ruff mypy
python -m pytest tests/ -v
```

The library itself uses only the Python standard library; `ruff` and `mypy` are
development-only tools that the CI gates run. Their exact pinned versions live in
the `[dependency-groups]` dev group in `pyproject.toml`, which `pip install pytest
ruff mypy` matches closely enough for local work. Tests use `tmp_path` fixtures and
monkeypatch `Path.home()`, so they never touch your real `~/.claude` directory.

## The single-source contract

`core/` is the source of truth. The files under `dist/` are rendered output, and
they are committed so the install path needs no build step. Never hand-edit a file
under `dist/`. Edit the matching source in `core/`, then re-render and prove the
tree is in sync:

```bash
python dist/native/build_native.py build --dry-run
python dist/speckit/build_speckit.py --dry-run
python scripts/check_sync.py
```

`check_sync.py` is the drift gate. It re-renders from `core/` and fails if the
committed `dist/` is stale. A pull request with stale output will not pass.

## Gates that must stay green

```bash
python -m pytest tests/ -v
python scripts/check_sync.py
python scripts/check_no_reference_text.py
ruff check .
mypy
```

`check_no_reference_text.py` fails the build if any structural fingerprint of a
proprietary reference prompt appears in the repository. Mergen reproduces no
proprietary text. Keep it that way.

## Style

Authored prose uses periods and commas only. No em dash, no en dash, no semicolon,
no emoji. This is the same minimal-output discipline Mergen applies to its own
work. Code is exempt from the punctuation rule, since a semicolon in Python or
YAML is syntax, not prose.

## The lazy ladder

Before adding code, stop at the first rung that holds: is it needed at all, then
the standard library, then a native platform feature, then an installed
dependency, then one line, then the minimum that works. Validation, security,
accessibility, error handling, and tests are never on the chopping block. The
discipline lives in `core/lazy-ladder.md`.

## Review is a separate lane

Authoring and review run in separate passes. A change is complete when an
independent check confirms it against the real filesystem and real tests, not when
the author asserts it. New behavior needs a test. A claim without evidence is a
hypothesis, not a result.

## Commit messages

Conventional Commits. Keep the subject in the imperative and under about seventy
characters. Explain the why in the body when the change is not obvious.

## Reporting issues

Open a GitHub issue. Include your Claude Code version, OS, and Python version. For
a security issue, follow `SECURITY.md` instead and report it privately.
