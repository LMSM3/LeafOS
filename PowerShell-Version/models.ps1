#!/usr/bin/env pwsh
<# Compatibility wrapper for the real-model-first workflow. #>

[CmdletBinding()]
param(
    [string]$Profile = 'runtime-default',
    [switch]$Resolve,
    [switch]$Apply,
    [switch]$Yes,
    [switch]$StatusOnly,
    [switch]$NoAnimation,
    [switch]$AllowFallback,
    [int]$MaxWorkers = 8,
    [switch]$ContinueOnError,
    [switch]$IncludeExperimental,
    [string]$ConfirmHeavy = '',
    [switch]$HashVerify,
    [string]$ModelDir = '',
    [string]$OutDir = ''
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$RealModels = Join-Path $PSScriptRoot 'real-models.ps1'
$forward = @{
    Profile = $Profile
}
if ($Resolve) { $forward.Resolve = $true }
if ($Apply) { $forward.Apply = $true }
if ($Yes) { $forward.Yes = $true }
if ($StatusOnly) { $forward.StatusOnly = $true }
if ($NoAnimation) { $forward.NoAnimation = $true }
if ($AllowFallback) { $forward.AllowFallback = $true }
if ($MaxWorkers) { $forward.MaxWorkers = $MaxWorkers }
if ($ContinueOnError) { $forward.ContinueOnError = $true }
if ($IncludeExperimental) { $forward.IncludeExperimental = $true }
if ($ConfirmHeavy) { $forward.ConfirmHeavy = $ConfirmHeavy }
if ($HashVerify) { $forward.HashVerify = $true }
if ($ModelDir) { $forward.ModelDir = $ModelDir }
if ($OutDir) { $forward.OutDir = $OutDir }

& $RealModels @forward
