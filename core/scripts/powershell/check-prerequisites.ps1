#!/usr/bin/env pwsh
# Thin shim: delegates all logic to feature_ops.py.
# Accepted flags (unchanged): -Json, -RequireTasks, -RequireSpec,
#   -IncludeTasks, -PathsOnly, -Help
[CmdletBinding(PositionalBinding=$false)]
param(
    [switch]$Json,
    [switch]$RequireTasks,
    [switch]$RequireSpec,
    [switch]$IncludeTasks,
    [switch]$PathsOnly,
    [switch]$Help
)
$ErrorActionPreference = 'Stop'
$pyArgs = @()
if ($Json)         { $pyArgs += '--json' }
if ($RequireTasks) { $pyArgs += '--require-tasks' }
if ($RequireSpec)  { $pyArgs += '--require-spec' }
if ($IncludeTasks) { $pyArgs += '--include-tasks' }
if ($PathsOnly)    { $pyArgs += '--paths-only' }
if ($Help)         { $pyArgs += '--help' }
$featureOps = Join-Path $PSScriptRoot '../feature_ops.py'
$pyCmd = if (Get-Command python3 -ErrorAction SilentlyContinue) { 'python3' } else { 'python' }
& $pyCmd $featureOps check-prerequisites @pyArgs
exit $LASTEXITCODE
