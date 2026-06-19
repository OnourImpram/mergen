#!/usr/bin/env bash
# Install, check, or uninstall the mergen mode for Claude Code.
# Usage:
#   ./install.sh             install
#   ./install.sh --check     verify installed artefacts (read-only)
#   ./install.sh --uninstall remove
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLAUDE_DIR="${HOME}/.claude"

PY="$(command -v python3 || command -v python || true)"
if [ -z "${PY}" ]; then
  echo "ERROR: python3 (or python) was not found on PATH. Install Python 3 and retry." >&2
  exit 1
fi

if [ "${1:-}" = "--uninstall" ]; then
  "${PY}" "${HERE}/scripts/patch_settings.py" --remove
  rm -f "${CLAUDE_DIR}/commands/mergen.md" \
        "${CLAUDE_DIR}/hooks/mergen_prompt_hook.py" \
        "${CLAUDE_DIR}/mergen.json"
  echo "mergen uninstalled. Restart Claude Code (or run /hooks) so the hook is dropped."
  exit 0
fi

if [ "${1:-}" = "--check" ]; then
  FAIL=0

  if [ -f "${CLAUDE_DIR}/commands/mergen.md" ]; then
    echo "  [OK] ${CLAUDE_DIR}/commands/mergen.md"
  else
    echo "  [MISSING] ${CLAUDE_DIR}/commands/mergen.md"
    FAIL=1
  fi

  if [ -f "${CLAUDE_DIR}/hooks/mergen_prompt_hook.py" ]; then
    echo "  [OK] ${CLAUDE_DIR}/hooks/mergen_prompt_hook.py"
  else
    echo "  [MISSING] ${CLAUDE_DIR}/hooks/mergen_prompt_hook.py"
    FAIL=1
  fi

  if "${PY}" "${HERE}/scripts/patch_settings.py" --status > /dev/null 2>&1; then
    echo "  [OK] settings.json hook entry"
  else
    echo "  [MISSING] settings.json hook entry"
    FAIL=1
  fi

  if [ "${FAIL}" -eq 0 ]; then
    echo "mergen check passed."
  else
    echo "mergen check FAILED. Re-run ./install.sh to fix." >&2
    exit 1
  fi
  exit 0
fi

mkdir -p "${CLAUDE_DIR}/commands" "${CLAUDE_DIR}/hooks"
cp "${HERE}/commands/mergen.md" "${CLAUDE_DIR}/commands/mergen.md"
cp "${HERE}/hooks/mergen_prompt_hook.py" "${CLAUDE_DIR}/hooks/mergen_prompt_hook.py"
"${PY}" "${HERE}/scripts/patch_settings.py" --python "${PY}"

cat <<'EOF'

mergen installed.

Next steps:
  1. Restart Claude Code (or run /hooks) so the new UserPromptSubmit hook loads.
  2. In a session, run:  /mergen
  3. Paste the line it prints:  /effort max

Disarm any time with:  /mergen off
Check install with:    ./install.sh --check
Uninstall with:        ./install.sh --uninstall
EOF
