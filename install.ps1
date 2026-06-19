<#
.SYNOPSIS
  mergen root installer for Windows PowerShell.

.DESCRIPTION
  Default / --Native : install the full native experience (effort-mode + SDD layer).
  --Speckit          : (re)generate dist/speckit and print spec-kit install commands.
  --Init [<dir>]     : bootstrap .specify/ in <dir> (default: current directory).
  --Help             : show this message.

  Native install performs three steps in order:
    1. effort-mode\install.ps1         /mergen command + UserPromptSubmit effort hook
    2. build_native.py build           renders 14 /mergen.* skills to ~/.claude/skills/
    3. patch_settings_hooks.py         registers verify_gate + constitution_inject hooks

  After install: restart Claude Code (or run /hooks) so all new hooks load.
  To bootstrap SDD in a project: .\install.ps1 -Init C:\path\to\project

  Note: /effort max requires one manual paste after running /mergen in a session.
        The hooks are reinforcement nudges. Enforcement is the implement pipeline's
        adversarial verify stage (a separate-context verifier checks filesystem + tests).

  License: Apache-2.0 (see LICENSE and NOTICE)
  Not affiliated with GitHub or Anthropic.
  "Spec Kit" is a GitHub, Inc. project (MIT). See ATTRIBUTION.md.

.EXAMPLE
  .\install.ps1
.EXAMPLE
  .\install.ps1 -Native
.EXAMPLE
  .\install.ps1 -Speckit
.EXAMPLE
  .\install.ps1 -Init C:\path\to\project
.EXAMPLE
  .\install.ps1 -Help
#>
param(
  [switch]$Native,
  [switch]$Speckit,
  [string]$Init,
  [switch]$InitCurrent,
  [switch]$Help
)
$ErrorActionPreference = "Stop"

$Here = Split-Path -Parent $MyInvocation.MyCommand.Path

# --------------------------------------------------------------------------- #
# Python detection
# --------------------------------------------------------------------------- #
$Py = (Get-Command python3 -ErrorAction SilentlyContinue).Source
if (-not $Py) { $Py = (Get-Command python -ErrorAction SilentlyContinue).Source }
if (-not $Py) {
  Write-Host "ERROR: python3 (or python) was not found on PATH. Install Python 3.8+ and retry." -ForegroundColor Red
  exit 1
}

# --------------------------------------------------------------------------- #
# Help
# --------------------------------------------------------------------------- #
if ($Help) {
  Write-Host @"
mergen installer

Usage:
  .\install.ps1                  install the full native experience
  .\install.ps1 -Native          same as default
  .\install.ps1 -Speckit         regenerate dist/speckit and print spec-kit install commands
  .\install.ps1 -Init [<dir>]    bootstrap .specify/ in <dir> (default: current directory)
  .\install.ps1 -Help            show this message

Native install steps (in order):
  1. effort-mode\install.ps1         /mergen command + UserPromptSubmit effort hook
  2. build_native.py build           renders 14 /mergen.* skills to ~/.claude/skills/
  3. patch_settings_hooks.py         registers verify_gate + constitution_inject hooks

Note: /effort max requires one manual paste after running /mergen in a session.
      The hooks are reinforcement nudges. Enforcement is the implement pipeline's
      adversarial verify stage (a separate-context verifier checks filesystem + tests).

Not affiliated with GitHub or Anthropic.
"@
  exit 0
}

# --------------------------------------------------------------------------- #
# --Speckit
# --------------------------------------------------------------------------- #
if ($Speckit) {
  Write-Host "==> (Re)generating dist/speckit ..."
  $BuildSpeckit = Join-Path $Here "dist\speckit\build_speckit.py"
  if (-not (Test-Path $BuildSpeckit)) {
    Write-Host "ERROR: expected file not found: $BuildSpeckit" -ForegroundColor Red
    exit 1
  }
  & $Py "$BuildSpeckit"
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

  $AbsPreset = Join-Path $Here "dist\speckit\preset\mergen"
  $AbsExt    = Join-Path $Here "dist\speckit\extensions\mergen"

  Write-Host @"

dist/speckit generated.

To install mergen into a spec-kit project that already has "specify init":

  specify preset add --dev "$AbsPreset"
  specify extension add --dev "$AbsExt"

The preset overrides 8 Spec Kit core commands (constitution, specify, clarify,
checklist, plan, tasks, analyze, implement) with mergen-powered versions.

The extension adds six commands Spec Kit does not have (verify, rollup, go, lean, debt, govern)
as speckit.mergen.<cmd> and wires the verify gate as an after_implement hook.

"Spec Kit" is a GitHub, Inc. project (MIT). See ATTRIBUTION.md for attribution.
"@
  exit 0
}

# --------------------------------------------------------------------------- #
# --Init [<dir>]
# --------------------------------------------------------------------------- #
if ($PSBoundParameters.ContainsKey('Init') -or $InitCurrent) {
  if ($Init) {
    $InitDir = $Init
  } else {
    $InitDir = (Get-Location).Path
  }
  Write-Host "==> Bootstrapping .specify/ in: $InitDir"
  $BuildNative = Join-Path $Here "dist\native\build_native.py"
  if (-not (Test-Path $BuildNative)) {
    Write-Host "ERROR: expected file not found: $BuildNative" -ForegroundColor Red
    exit 1
  }
  & $Py "$BuildNative" init "$InitDir"
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
  Write-Host ""
  Write-Host "Project initialized. Open a Claude Code session in $InitDir and run /mergen.specify to start."
  exit 0
}

# --------------------------------------------------------------------------- #
# Native install (default or -Native) - three sequential steps
# --------------------------------------------------------------------------- #

Write-Host "==> Step 1/3: Installing effort-mode (/mergen command + effort hook) ..."
$EffortInstaller = Join-Path $Here "effort-mode\install.ps1"
if (-not (Test-Path $EffortInstaller)) {
  Write-Host "ERROR: expected file not found: $EffortInstaller" -ForegroundColor Red
  exit 1
}
& powershell.exe -ExecutionPolicy Bypass -File "$EffortInstaller"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host ""
Write-Host "==> Step 2/3: Building native SDD skills (14 /mergen.* commands) ..."
$BuildNative = Join-Path $Here "dist\native\build_native.py"
if (-not (Test-Path $BuildNative)) {
  Write-Host "ERROR: expected file not found: $BuildNative" -ForegroundColor Red
  exit 1
}
& $Py "$BuildNative" build
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host ""
Write-Host "==> Step 3/3: Registering SDD hooks (verify_gate + constitution_inject) ..."
$PatchHooks = Join-Path $Here "dist\native\patch_settings_hooks.py"
if (-not (Test-Path $PatchHooks)) {
  Write-Host "ERROR: expected file not found: $PatchHooks" -ForegroundColor Red
  exit 1
}
& $Py "$PatchHooks" --python "$Py"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host @"

mergen installed.

Next steps:
  1. Restart Claude Code (or run /hooks) so all new hooks load.
  2. To arm max-effort mode in a session, run: /mergen
     Then paste the line it prints:  /effort max
     (One manual paste is required -- a hook cannot flip the live effort value.)
  3. Use the SDD commands anywhere: /mergen.specify, /mergen.plan, etc.
  4. To bootstrap SDD in a project, run from this repo:
       .\install.ps1 -Init C:\path\to\your\project

Disarm effort mode any time with:  /mergen off
Reinstall SDD hooks or skills:     .\install.ps1  (idempotent)
"@
