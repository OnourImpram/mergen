#!/usr/bin/env pwsh
# Thin shim: delegates all logic to feature_ops.py.
# Accepted flags (unchanged): -Json, -DryRun, -AllowExistingBranch,
#   -ShortName <name>, -Number N, -Timestamp, -Help
[CmdletBinding(PositionalBinding=$false)]
param(
    [switch]$Json,
    [switch]$AllowExistingBranch,
    [switch]$DryRun,
    [string]$ShortName,
    [long]$Number = 0,
    [switch]$Timestamp,
    [switch]$Help,
    [Parameter(Position = 0, ValueFromRemainingArguments = $true)]
    [string[]]$FeatureDescription
)
$ErrorActionPreference = 'Stop'
$pyArgs = @()
if ($Json)                { $pyArgs += '--json' }
if ($DryRun)              { $pyArgs += '--dry-run' }
if ($AllowExistingBranch) { $pyArgs += '--allow-existing-branch' }
if ($ShortName)           { $pyArgs += '--short-name'; $pyArgs += $ShortName }
if ($Number -ne 0)        { $pyArgs += '--number'; $pyArgs += "$Number" }
if ($Timestamp)           { $pyArgs += '--timestamp' }
if ($Help)                { $pyArgs += '--help' }
if ($FeatureDescription)  { $pyArgs += $FeatureDescription }
$featureOps = Join-Path $PSScriptRoot '../feature_ops.py'
$pyCmd = if (Get-Command python3 -ErrorAction SilentlyContinue) { 'python3' } else { 'python' }
& $pyCmd $featureOps create-new-feature @pyArgs
exit $LASTEXITCODE
