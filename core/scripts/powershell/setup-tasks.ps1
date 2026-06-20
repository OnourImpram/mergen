#!/usr/bin/env pwsh
# Thin shim: delegates all logic to feature_ops.py.
# Accepted flags (unchanged): -Json, -Help
[CmdletBinding(PositionalBinding=$false)]
param(
    [switch]$Json,
    [switch]$Help
)
$ErrorActionPreference = 'Stop'
$pyArgs = @()
if ($Json) { $pyArgs += '--json' }
if ($Help) { $pyArgs += '--help' }
$featureOps = Join-Path $PSScriptRoot '../feature_ops.py'
$pyCmd = if (Get-Command python3 -ErrorAction SilentlyContinue) { 'python3' } else { 'python' }
& $pyCmd $featureOps setup-tasks @pyArgs
exit $LASTEXITCODE
