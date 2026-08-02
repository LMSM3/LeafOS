#!/usr/bin/env pwsh
# Compatibility helper. Plan-only by default; downloads require -Resolve -Apply -Yes.
param(
    [ValidateSet("runtime-default", "default", "extended", "experimental")]
    [string]$Profile = "runtime-default",
    [string]$Dest = (Join-Path $HOME ".leaf\models"),
    [string]$Plan = (Join-Path $PSScriptRoot "..\leaf-model-plan.json"),
    [int]$Workers = 8,
    [switch]$AllowFallback,
    [switch]$Resolve,
    [switch]$Apply,
    [switch]$Yes,
    [switch]$IncludeExperimental,
    [string]$ConfirmHeavy = ""
)

$ErrorActionPreference = "Stop"
$Py = Join-Path $PSScriptRoot "..\.venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $Py)) {
    throw "Installer environment missing. Run install.ps1 first."
}

$PlanArgs = @("-m", "leaf_models.install_cli", "plan", "--profile", $Profile, "--dest", $Dest, "--out", $Plan)
if ($AllowFallback) { $PlanArgs += "--allow-fallback" }
& $Py @PlanArgs
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$ResolvedPlan = [IO.Path]::Combine(
    [IO.Path]::GetDirectoryName((Resolve-Path -LiteralPath $Plan).Path),
    "$([IO.Path]::GetFileNameWithoutExtension($Plan)).resolved.json"
)
if ($Resolve -or $Apply) {
    & $Py -m leaf_models.install_cli resolve $Plan --out $ResolvedPlan
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
if ($Apply) {
    if (-not $Yes) {
        throw "-Apply requires -Yes."
    }
    $ApplyArgs = @("-m", "leaf_models.install_cli", "apply", $ResolvedPlan, "--yes", "--max-workers", "$Workers")
    if ($IncludeExperimental) { $ApplyArgs += "--include-experimental" }
    if ($ConfirmHeavy) { $ApplyArgs += @("--confirm-heavy", $ConfirmHeavy) }
    & $Py @ApplyArgs
    exit $LASTEXITCODE
}

Write-Host "Plan prepared. No model download was started." -ForegroundColor Green
