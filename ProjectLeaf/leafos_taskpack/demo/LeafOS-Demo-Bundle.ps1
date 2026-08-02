#!/usr/bin/env pwsh
<#
LeafOS-Demo-Bundle.ps1

Automated PowerShell demo for LeafOS runtime + installer planning.

Default behavior is safe:
- validates local layout;
- shows runtime/persona selection;
- demonstrates worker escalation;
- emits a runtime event envelope;
- creates an offline runtime model plan when the installer source is present;
- never resolves remote metadata;
- never downloads model weights;
- never applies an install plan.

Run from anywhere:

  pwsh -File .\demo\LeafOS-Demo-Bundle.ps1

Useful options:

  -SkipModelPlan      Do not create the offline model plan.
  -OutputDir PATH     Write transcript and demo files to PATH.
  -OpenFolder         Open the output folder at the end.
#>

[CmdletBinding()]
param(
    [string]$OutputDir = '',
    [switch]$SkipModelPlan,
    [switch]$OpenFolder
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RootDir = Resolve-Path (Join-Path $ScriptDir '..')
$LeafCtl = Join-Path $RootDir 'bin\leafctl.ps1'
$InstallerRoot = Join-Path (Split-Path $RootDir) 'leaf_model_installer'

if (-not $OutputDir) {
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $OutputDir = Join-Path $RootDir "reports\demo-powershell-$stamp"
}

$null = New-Item -ItemType Directory -Force -Path $OutputDir
$TranscriptPath = Join-Path $OutputDir 'transcript.txt'
$SummaryPath = Join-Path $OutputDir 'summary.txt'
$RuntimeJsonPath = Join-Path $OutputDir 'runtime-selection.json'
$FridayJsonPath = Join-Path $OutputDir 'runtime-friday.json'
$PlanPath = Join-Path $OutputDir 'leaf-runtime-plan.json'

function Write-DemoLine {
    param([string]$Message = '')
    Write-Host $Message
    Add-Content -LiteralPath $SummaryPath -Value $Message -Encoding UTF8
}

function Write-DemoHeader {
    param([string]$Title)
    Write-DemoLine ''
    Write-DemoLine ('=' * 72)
    Write-DemoLine $Title
    Write-DemoLine ('=' * 72)
}

function Invoke-DemoCommand {
    param(
        [Parameter(Mandatory)][string]$Label,
        [Parameter(Mandatory)][scriptblock]$Command,
        [switch]$AllowFailure
    )

    Write-DemoHeader $Label
    try {
        & $Command
        Write-DemoLine ''
        Write-DemoLine "OK: $Label"
    }
    catch {
        Write-DemoLine ''
        Write-DemoLine "FAILED: $Label"
        Write-DemoLine $_.Exception.Message
        if (-not $AllowFailure) { throw }
    }
}

function Get-DemoPython {
    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python) { return $python.Source }

    $python3 = Get-Command python3 -ErrorAction SilentlyContinue
    if ($python3) { return $python3.Source }

    return ''
}

function Invoke-LeafModelsSource {
    param([Parameter(ValueFromRemainingArguments)][string[]]$Args)

    if (-not (Test-Path $InstallerRoot -PathType Container)) {
        throw "leaf_model_installer folder not found: $InstallerRoot"
    }

    $cmd = Join-Path $InstallerRoot 'leaf-models.cmd'
    if (Test-Path $cmd -PathType Leaf) {
        & $cmd @Args
        return
    }

    $python = Get-DemoPython
    if (-not $python) {
        throw 'python was not found on PATH, and leaf-models.cmd is not present.'
    }

    $oldPythonPath = $env:PYTHONPATH
    try {
        if ($oldPythonPath) {
            $env:PYTHONPATH = "$InstallerRoot;$oldPythonPath"
        }
        else {
            $env:PYTHONPATH = "$InstallerRoot"
        }
        & $python -B -m leaf_models.install_cli @Args
    }
    finally {
        $env:PYTHONPATH = $oldPythonPath
    }
}

function Save-JsonCommand {
    param(
        [Parameter(Mandatory)][string]$Path,
        [Parameter(Mandatory)][scriptblock]$Command
    )
    $json = & $Command
    $json | Set-Content -LiteralPath $Path -Encoding UTF8
    $json
}

$transcriptStarted = $false
try {
    Start-Transcript -Path $TranscriptPath -Force | Out-Null
    $transcriptStarted = $true
}
catch {
    Write-Warning "Could not start transcript: $($_.Exception.Message)"
}

try {
    Set-Content -LiteralPath $SummaryPath -Value @(
        'LeafOS PowerShell Demo Bundle'
        "Started: $(Get-Date -Format o)"
        "Root: $RootDir"
        "Output: $OutputDir"
        ''
        'This demo does not resolve, apply, or download model weights.'
    ) -Encoding UTF8

    Write-DemoHeader 'LeafOS PowerShell Demo Bundle'
    Write-DemoLine "Root:   $RootDir"
    Write-DemoLine "Output: $OutputDir"
    Write-DemoLine 'Safety: no resolve, no apply, no downloads.'

    if (-not (Test-Path $LeafCtl -PathType Leaf)) {
        throw "leafctl.ps1 not found: $LeafCtl"
    }

    Invoke-DemoCommand 'A1. Check LeafOS layout' {
        & $LeafCtl doctor
    }

    Invoke-DemoCommand 'A2. Show system status' {
        & $LeafCtl status
    }

    Invoke-DemoCommand 'B1. Validate runtime config' {
        & $LeafCtl runtime validate
    }

    Invoke-DemoCommand 'B2. Show default runtime selection' {
        & $LeafCtl runtime select
    }

    Invoke-DemoCommand 'B3. Save default runtime selection JSON' {
        Save-JsonCommand -Path $RuntimeJsonPath -Command {
            & $LeafCtl runtime select --json
        }
        Write-DemoLine "Saved: $RuntimeJsonPath"
    }

    Invoke-DemoCommand 'B4. Persona tour: Monday, Wednesday, Friday' {
        & $LeafCtl runtime select --persona monday
        & $LeafCtl runtime select --persona wednesday
        Save-JsonCommand -Path $FridayJsonPath -Command {
            & $LeafCtl runtime select --persona friday --json
        }
        Write-DemoLine "Saved Friday JSON: $FridayJsonPath"
        Write-DemoLine 'Friday suppresses coder workers until the user is explicitly stuck.'
    }

    Invoke-DemoCommand 'B5. Worker escalation by confidence score' {
        & $LeafCtl runtime workers 0.86
        & $LeafCtl runtime workers 0.62
        & $LeafCtl runtime workers 0.42 tests_failed
    }

    Invoke-DemoCommand 'B6. Runtime event envelope' {
        & $LeafCtl runtime event plan 0.86 'Demo plan: inspect, plan, verify, checkpoint.'
    }

    if ($SkipModelPlan) {
        Write-DemoHeader 'C1. Offline runtime model plan'
        Write-DemoLine 'Skipped because -SkipModelPlan was provided.'
    }
    else {
        Invoke-DemoCommand 'C1. Show canonical model catalog' {
            Invoke-LeafModelsSource catalog
        } -AllowFailure

        Invoke-DemoCommand 'C2. Create offline runtime model plan' {
            Invoke-LeafModelsSource plan --profile runtime-default --out $PlanPath
            Write-DemoLine "Saved: $PlanPath"
            Write-DemoLine 'This is only a plan. It did not resolve metadata or download weights.'
        } -AllowFailure
    }

    Write-DemoHeader 'Demo complete'
    Write-DemoLine "Transcript: $TranscriptPath"
    Write-DemoLine "Summary:    $SummaryPath"
    Write-DemoLine "Runtime:    $RuntimeJsonPath"
    if (Test-Path $PlanPath -PathType Leaf) {
        Write-DemoLine "Plan:       $PlanPath"
    }
    Write-DemoLine ''
    Write-DemoLine 'Next manual step, only when ready:'
    Write-DemoLine '  resolve the plan, review it, then apply with --yes if you want downloads.'
}
finally {
    if ($transcriptStarted) {
        try { Stop-Transcript | Out-Null } catch {}
    }
}

if ($OpenFolder) {
    Invoke-Item -LiteralPath $OutputDir
}
