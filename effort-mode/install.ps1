<#
.SYNOPSIS
  Install, check, or uninstall the mergen mode for Claude Code on Windows.
.EXAMPLE
  ./install.ps1
.EXAMPLE
  ./install.ps1 -Check
.EXAMPLE
  ./install.ps1 -Uninstall
#>
param(
  [switch]$Uninstall,
  [switch]$Check
)
$ErrorActionPreference = "Stop"

$Here = Split-Path -Parent $MyInvocation.MyCommand.Path
$ClaudeDir = Join-Path $HOME ".claude"

$Py = (Get-Command python3 -ErrorAction SilentlyContinue).Source
if (-not $Py) { $Py = (Get-Command python -ErrorAction SilentlyContinue).Source }
if (-not $Py) { Write-Host "ERROR: python3 (or python) was not found on PATH. Install Python 3 and retry." -ForegroundColor Red; exit 1 }

$Patch = Join-Path $Here "scripts/patch_settings.py"

if ($Uninstall) {
  & $Py "$Patch" --remove
  Remove-Item -Force -ErrorAction SilentlyContinue -LiteralPath `
    (Join-Path $ClaudeDir "commands/mergen.md"), `
    (Join-Path $ClaudeDir "hooks/mergen_prompt_hook.py"), `
    (Join-Path $ClaudeDir "mergen.json")
  Write-Host "mergen uninstalled. Restart Claude Code (or run /hooks) so the hook is dropped."
  exit 0
}

if ($Check) {
  $fail = $false

  $cmd = Join-Path $ClaudeDir "commands/mergen.md"
  if (Test-Path $cmd) {
    Write-Host "  [OK] $cmd"
  } else {
    Write-Host "  [MISSING] $cmd" -ForegroundColor Red
    $fail = $true
  }

  $hk = Join-Path $ClaudeDir "hooks/mergen_prompt_hook.py"
  if (Test-Path $hk) {
    Write-Host "  [OK] $hk"
  } else {
    Write-Host "  [MISSING] $hk" -ForegroundColor Red
    $fail = $true
  }

  $null = & $Py "$Patch" --status 2>&1
  if ($LASTEXITCODE -eq 0) {
    Write-Host "  [OK] settings.json hook entry"
  } else {
    Write-Host "  [MISSING] settings.json hook entry" -ForegroundColor Red
    $fail = $true
  }

  if ($fail) {
    Write-Host "mergen check FAILED. Re-run ./install.ps1 to fix." -ForegroundColor Red
    exit 1
  } else {
    Write-Host "mergen check passed."
    exit 0
  }
}

New-Item -ItemType Directory -Force -Path (Join-Path $ClaudeDir "commands"), (Join-Path $ClaudeDir "hooks") | Out-Null
Copy-Item -Force (Join-Path $Here "commands/mergen.md") (Join-Path $ClaudeDir "commands/mergen.md")
Copy-Item -Force (Join-Path $Here "hooks/mergen_prompt_hook.py") (Join-Path $ClaudeDir "hooks/mergen_prompt_hook.py")
& $Py "$Patch" --python "$Py"

Write-Host @"

mergen installed.

Next steps:
  1. Restart Claude Code (or run /hooks) so the new UserPromptSubmit hook loads.
  2. In a session, run:  /mergen
  3. Paste the line it prints:  /effort max

Disarm any time with:  /mergen off
Check install with:    ./install.ps1 -Check
Uninstall with:        ./install.ps1 -Uninstall
"@
