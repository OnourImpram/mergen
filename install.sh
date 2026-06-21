#!/usr/bin/env sh
# mergen root installer - macOS / Linux / Git Bash
#
# Usage:
#   ./install.sh                  install the full native experience (effort-mode + SDD layer)
#   ./install.sh --native         same as default
#   ./install.sh --speckit        (re)generate dist/speckit and print spec-kit install commands
#   ./install.sh --init [<dir>]   bootstrap .specify/ in <dir> (defaults to current directory)
#   ./install.sh --help           show this message
#
# The native install performs three steps in order:
#   1. Run effort-mode/install.sh  - installs /mergen command + UserPromptSubmit effort hook
#   2. python dist/native/build_native.py build  - renders the 14 /mergen-* skills
#   3. python dist/native/patch_settings_hooks.py --python <python>  - registers SDD hooks
#
# After install: restart Claude Code (or run /hooks) so all new hooks load.
# To bootstrap SDD in a project: ./install.sh --init <project-dir>
#
# License: Apache-2.0  (see LICENSE and NOTICE)
# Not affiliated with GitHub or Anthropic.
# "Spec Kit" is a GitHub, Inc. project (MIT). See ATTRIBUTION.md.
set -e

HERE="$(cd "$(dirname "$0")" && pwd)"

# --------------------------------------------------------------------------- #
# Python detection
# --------------------------------------------------------------------------- #
PY="$(command -v python3 2>/dev/null || command -v python 2>/dev/null || true)"
if [ -z "${PY}" ]; then
  echo "ERROR: python3 (or python) was not found on PATH. Install Python 3.9+ and retry." >&2
  exit 1
fi

# --------------------------------------------------------------------------- #
# Help
# --------------------------------------------------------------------------- #
print_help() {
  cat <<'HELP'
mergen installer

Usage:
  ./install.sh                  install the full native experience
  ./install.sh --native         same as default
  ./install.sh --speckit        regenerate dist/speckit and print spec-kit install commands
  ./install.sh --init [<dir>]   bootstrap .specify/ in <dir> (default: current directory)
  ./install.sh --help           show this message

Native install steps (in order):
  1. effort-mode/install.sh          /mergen command + UserPromptSubmit effort hook
  2. build_native.py build           renders 14 /mergen-* skills to ~/.claude/skills/
  3. patch_settings_hooks.py         registers verify_gate + constitution_inject hooks

Note: /effort max requires one manual paste after running /mergen in a session.
      The hooks are reinforcement nudges. Enforcement is the implement pipeline's
      adversarial verify stage (a separate-context verifier checks filesystem + tests).

Not affiliated with GitHub or Anthropic.
HELP
}

# --------------------------------------------------------------------------- #
# Mode dispatch
# --------------------------------------------------------------------------- #
MODE="${1:-}"

case "${MODE}" in

  --help|-h)
    print_help
    exit 0
    ;;

  --speckit)
    echo "==> (Re)generating dist/speckit ..."
    "${PY}" "${HERE}/dist/speckit/build_speckit.py"
    ABS_PRESET="${HERE}/dist/speckit/preset/mergen"
    ABS_EXT="${HERE}/dist/speckit/extensions/mergen"
    cat <<EOF

dist/speckit generated.

To install mergen into a spec-kit project that already has "specify init":

  specify preset add --dev "${ABS_PRESET}"
  specify extension add --dev "${ABS_EXT}"

The preset overrides 8 Spec Kit core commands (constitution, specify, clarify,
checklist, plan, tasks, analyze, implement) with mergen-powered versions.

The extension adds six commands Spec Kit does not have (verify, rollup, go, lean, debt, govern)
as speckit.mergen.<cmd> and wires the verify gate as an after_implement hook.

"Spec Kit" is a GitHub, Inc. project (MIT). See ATTRIBUTION.md for attribution.
EOF
    exit 0
    ;;

  --init)
    INIT_DIR="${2:-$(pwd)}"
    echo "==> Bootstrapping .specify/ in: ${INIT_DIR}"
    "${PY}" "${HERE}/dist/native/build_native.py" init "${INIT_DIR}"
    echo ""
    echo "Project initialized. Open a Claude Code session in ${INIT_DIR} and run /mergen-specify to start."
    exit 0
    ;;

  --native|"")
    # Full native install - fall through to the block below.
    ;;

  *)
    echo "ERROR: Unknown option '${MODE}'. Run ./install.sh --help for usage." >&2
    exit 1
    ;;

esac

# --------------------------------------------------------------------------- #
# Native install - three sequential steps
# --------------------------------------------------------------------------- #

echo "==> Step 1/3: Installing effort-mode (/mergen command + effort hook) ..."
EFFORT_INSTALLER="${HERE}/effort-mode/install.sh"
if [ ! -f "${EFFORT_INSTALLER}" ]; then
  echo "ERROR: expected file not found: ${EFFORT_INSTALLER}" >&2
  exit 1
fi
bash "${EFFORT_INSTALLER}"

echo ""
echo "==> Step 2/3: Building native SDD skills (14 /mergen-* commands) ..."
BUILD_SCRIPT="${HERE}/dist/native/build_native.py"
if [ ! -f "${BUILD_SCRIPT}" ]; then
  echo "ERROR: expected file not found: ${BUILD_SCRIPT}" >&2
  exit 1
fi
"${PY}" "${BUILD_SCRIPT}" build

echo ""
echo "==> Step 3/3: Registering SDD hooks (verify_gate + constitution_inject) ..."
PATCH_SCRIPT="${HERE}/dist/native/patch_settings_hooks.py"
if [ ! -f "${PATCH_SCRIPT}" ]; then
  echo "ERROR: expected file not found: ${PATCH_SCRIPT}" >&2
  exit 1
fi
"${PY}" "${PATCH_SCRIPT}" --python "${PY}"

cat <<'NEXT'

mergen installed.

Next steps:
  1. Restart Claude Code (or run /hooks) so all new hooks load.
  2. To arm max-effort mode in a session, run: /mergen
     Then paste the line it prints:  /effort max
     (One manual paste is required, a hook cannot flip the live effort value.)
  3. Use the SDD commands anywhere: /mergen-specify, /mergen-plan, etc.
  4. To bootstrap SDD in a project, run from this repo:
       ./install.sh --init /path/to/your/project

Disarm effort mode any time with:  /mergen off
Reinstall SDD hooks or skills:     ./install.sh  (idempotent)
NEXT
