# Contributing to mergen

Thank you for your interest. This is a small, focused tool, contributions that stay within that scope are most welcome.

## Development setup

```bash
git clone https://github.com/TheGoatPsy/mergen.git
cd mergen
pip install pytest
python -m pytest tests/ -v
```

No other dependencies are required. The project uses only the Python standard library.

## Running tests

```bash
python -m pytest tests/ -v
```

Tests use `tmp_path` fixtures and monkeypatch `Path.home()` so they never touch your real `~/.claude` directory. All 16 tests should pass on Python 3.9, 3.11, and 3.12.

## CI

[![CI](https://github.com/TheGoatPsy/mergen/actions/workflows/ci.yml/badge.svg)](https://github.com/TheGoatPsy/mergen/actions/workflows/ci.yml)

CI runs the test suite on every push and pull request to `main`, across Python 3.9, 3.11, and 3.12.

## Pull request requirements

- Any change to `hooks/mergen_prompt_hook.py` or `scripts/patch_settings.py` must include or update corresponding tests.
- The test suite must pass (`python -m pytest tests/ -v`) before requesting review.
- Keep the scope tight. This tool does one thing: reconstruct `max effort + standing orchestration` from two halves. Extensions that add unrelated features belong in separate projects.

## Reporting issues

Open a GitHub issue. Include your Claude Code version, OS, and Python version.
