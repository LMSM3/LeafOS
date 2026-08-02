#!/usr/bin/env pwsh
<#
LeafOS real installation automation.

Safe preview:
  .\install-real.ps1

Actual model installation:
  .\install-real.ps1 -Yes

The -Yes switch is the download boundary. It resolves exact repository files,
downloads/resumes the selected profile, verifies local artifacts, and writes a
run manifest.
#>

[CmdletBinding()]
param(
    [string]$Profile = 'runtime-default',
    [switch]$Yes,
    [switch]$NoAnimation,
    [switch]$SkipReadiness,
    [switch]$AllowFallback,
    [int]$MaxWorkers = 8,
    [switch]$ContinueOnError,
    [switch]$IncludeExperimental,
    [string]$ConfirmHeavy = '',
    [switch]$HashVerify,
    [switch]$SkipPackIdentity,
    [string]$ModelDir = '',
    [string]$ReportDir = ''
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$Root = Resolve-Path (Join-Path $PSScriptRoot '..')
$Leaf = Join-Path $PSScriptRoot 'leaf.ps1'
$RealModels = Join-Path $PSScriptRoot 'real-models.ps1'
$RuntimeConfigPath = Join-Path $Root 'ProjectLeaf\leafos_taskpack\config\runtime.json'

if (-not $ReportDir) {
    $ReportDir = Join-Path $PSScriptRoot ('reports\install-real-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
}

$null = New-Item -ItemType Directory -Force -Path $ReportDir
$LogPath = Join-Path $ReportDir 'install-real.log'
$ManifestPath = Join-Path $ReportDir 'install-real-manifest.json'
$ModelReportDir = Join-Path $ReportDir 'models'
$RuntimeRoleReportPath = Join-Path $ReportDir 'runtime-role-policy.json'

function Write-InstallLog {
    param([string]$Message)
    Add-Content -LiteralPath $LogPath -Value ("[{0}] {1}" -f (Get-Date -Format o), $Message) -Encoding UTF8
}

function Write-Banner {
    Write-Host ''
    Write-Host '╔══════════════════════════════════════════════════════════════════════╗' -ForegroundColor Cyan
    Write-Host '║                  LeafOS Real Installation                          ║' -ForegroundColor Green
    Write-Host '║        resolve • download/resume • verify • report                  ║' -ForegroundColor DarkCyan
    Write-Host '╚══════════════════════════════════════════════════════════════════════╝' -ForegroundColor Cyan
    Write-Host ''
}

function Invoke-Animation {
    param([string]$Label)
    if ($NoAnimation) {
        Write-Host "  -> $Label"
        return
    }
    $frames = @('🌱', '🌿', 'GGUF', '⬇', '✓')
    for ($i = 0; $i -lt 10; $i++) {
        Write-Host "`r  $($frames[$i % $frames.Count]) $Label   " -NoNewline -ForegroundColor Cyan
        Start-Sleep -Milliseconds 70
    }
    Write-Host "`r  ✓ $Label   " -ForegroundColor Green
}

function Invoke-Step {
    param(
        [string]$Name,
        [scriptblock]$Action,
        [switch]$Optional
    )

    Write-Host ''
    Write-Host "==> $Name" -ForegroundColor Cyan
    Write-InstallLog "START $Name"
    Invoke-Animation $Name

    $global:LASTEXITCODE = 0
    try {
        & $Action 2>&1 | Tee-Object -FilePath $LogPath -Append | ForEach-Object {
            Write-Host $_
        }
        if ($LASTEXITCODE -ne 0) {
            throw "$Name exited with code $LASTEXITCODE"
        }
        Write-Host "OK: $Name" -ForegroundColor Green
        Write-InstallLog "OK $Name"
        return $true
    }
    catch {
        Write-Host "FAILED: $Name" -ForegroundColor Red
        Write-Host $_.Exception.Message -ForegroundColor Red
        Write-InstallLog "FAILED $Name :: $($_.Exception.Message)"
        if (-not $Optional) { throw }
        return $false
    }
}

function Get-LeafRuntimeRolePolicyReport {
    if (-not (Test-Path $RuntimeConfigPath -PathType Leaf)) {
        throw "Runtime config not found: $RuntimeConfigPath"
    }
    $cfg = Get-Content -Raw -LiteralPath $RuntimeConfigPath | ConvertFrom-Json
    $rt = $cfg.leafos_runtime
    $codingModelKey = [string]$rt.role_policy.coding_model_key
    if (-not $codingModelKey) { $codingModelKey = 'gemma4-coder' }

    $coderKeys = @($rt.coder_models | ForEach-Object { $_.key })
    $mainKeys = @($rt.main_models | ForEach-Object { $_.key })
    $schedulerDefault = [string]$rt.defaults.scheduler_model

    if ($coderKeys.Count -ne 1 -or $coderKeys[0] -ne $codingModelKey) {
        throw "Runtime role policy violation: coder model must be exactly $codingModelKey"
    }
    if ($mainKeys -contains $codingModelKey) {
        throw "Runtime role policy violation: $codingModelKey cannot be in main_models"
    }
    if ($coderKeys -contains $schedulerDefault) {
        throw "Runtime role policy violation: scheduler model cannot be a coder model"
    }
    if (-not ($mainKeys -contains $schedulerDefault)) {
        throw "Runtime role policy violation: scheduler default must be in main_models"
    }

    [pscustomobject]@{
        generated_at = Get-Date -Format o
        runtime_config = $RuntimeConfigPath
        complete = $true
        coding_model = $codingModelKey
        coding_scope = [string]$rt.role_policy.coding_scope
        scheduler_model = $schedulerDefault
        main_model = [string]$rt.defaults.main_model
        main_and_scheduler_pool = $mainKeys
        coder_pool = $coderKeys
        rule = 'Fable/Gemma4-Coder is coding-only; Opus or another main model owns main and scheduler duties.'
    }
}

Write-Banner
Write-Host "root:       $Root"
Write-Host "profile:    $Profile"
Write-Host "reports:    $ReportDir"
Write-Host "max workers: $MaxWorkers"
Write-Host ''

if (-not $Yes) {
    Write-Host 'Preview mode: no network resolve and no download will be performed.' -ForegroundColor Yellow
    Write-Host 'To run the real installation, re-run with -Yes.' -ForegroundColor Yellow
}
else {
    Write-Host 'REAL INSTALL ENABLED: this run may download large model weights.' -ForegroundColor Yellow
}

$manifest = [ordered]@{
    schema_version = 1
    started_at = (Get-Date -Format o)
    root = [string]$Root
    surface = 'PowerShell-Version'
    profile = $Profile
    report_dir = [string](Resolve-Path $ReportDir)
    real_install_enabled = [bool]$Yes
    max_workers = $MaxWorkers
    runtime_role_policy_report = $RuntimeRoleReportPath
    steps = [ordered]@{}
}

$script:rolePolicyReport = $null
$manifest.steps.role_policy = Invoke-Step 'Runtime role policy' {
    $script:rolePolicyReport = Get-LeafRuntimeRolePolicyReport
    $script:rolePolicyReport | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $RuntimeRoleReportPath -Encoding UTF8
    "coding model    : $($script:rolePolicyReport.coding_model)"
    "main model      : $($script:rolePolicyReport.main_model)"
    "scheduler model : $($script:rolePolicyReport.scheduler_model)"
    "policy report   : $RuntimeRoleReportPath"
}

if (-not $SkipReadiness) {
    $manifest.steps.doctor = Invoke-Step 'LeafOS doctor' {
        & $Leaf doctor
    }

    $manifest.steps.runtime = Invoke-Step 'Runtime validation and selection' {
        & $Leaf runtime validate
        & $Leaf runtime select
    }
}
else {
    $manifest.steps.doctor = 'skipped'
    $manifest.steps.runtime = 'skipped'
}

$realArgs = @{
    Profile = $Profile
    OutDir = $ModelReportDir
    NoAnimation = [bool]$NoAnimation
    AllowFallback = [bool]$AllowFallback
    MaxWorkers = $MaxWorkers
    ContinueOnError = [bool]$ContinueOnError
    IncludeExperimental = [bool]$IncludeExperimental
    HashVerify = [bool]$HashVerify
}
if ($ModelDir) { $realArgs.ModelDir = $ModelDir }
if ($ConfirmHeavy) { $realArgs.ConfirmHeavy = $ConfirmHeavy }
if ($Yes) {
    $realArgs.Resolve = $true
    $realArgs.Apply = $true
    $realArgs.Yes = $true
}

$manifest.steps.models = Invoke-Step 'Real model automation' {
    & $RealModels @realArgs
}

if (-not $SkipPackIdentity) {
    $TaskPack = Join-Path $Root 'ProjectLeaf\leafos_taskpack'
    $manifest.steps.pack_identity = Invoke-Step 'Apply deterministic pack identity' {
        & $Leaf pack-identity apply --all-packs --only-if-missing
        & $Leaf pack-identity apply --registry (Join-Path $TaskPack 'config\pack-registry.json') --all-entries --only-if-missing
    } -Optional
}
else {
    $manifest.steps.pack_identity = 'skipped'
}

$manifest.finished_at = (Get-Date -Format o)
$manifest.model_report_dir = [string](Resolve-Path $ModelReportDir)
$manifest.runtime_role_policy = $script:rolePolicyReport
$manifest.next_real_install_command = ".\install-real.ps1 -Profile $Profile -Yes"
$manifest | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $ManifestPath -Encoding UTF8

Write-Host ''
if ($Yes) {
    Write-Host 'LeafOS real installation automation finished.' -ForegroundColor Green
}
else {
    Write-Host 'LeafOS real installation preview finished.' -ForegroundColor Green
    Write-Host 'Run this when ready to download/resume:' -ForegroundColor Cyan
    Write-Host "  .\install-real.ps1 -Profile $Profile -Yes"
}
Write-Host "manifest: $ManifestPath"
Write-Host "log:      $LogPath"
