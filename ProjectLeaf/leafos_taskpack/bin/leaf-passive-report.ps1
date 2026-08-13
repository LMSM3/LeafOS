#!/usr/bin/env pwsh
<##
.SYNOPSIS
    Connect a LeafOS run to the existing model-free HTML reporting surface.

.DESCRIPTION
    This is an orchestration wrapper, not a second runner. It can discover the
    active run or start one through leafctl.ps1, then delegates HTML generation
    to core/python/leaf_live_report.py. Optional watch mode delegates to the
    existing leaf-sandbox.ps1 reporting supervisor.
#>
[CmdletBinding()]
param(
    [string]$RunRoot = '',
    [string]$Project = '',
    [ValidateSet('off', 'auto', 'required')]
    [string]$Provider = 'off',
    [ValidateSet('auto', 'generic')]
    [string]$Template = 'auto',
    [int]$BudgetMinutes = 64,
    [int]$ReportIntervalMinutes = 30,
    [string]$Objective = '',
    [switch]$StartProject,
    [switch]$NewProject,
    [switch]$Approve,
    [switch]$Watch,
    [switch]$Open,
    [switch]$SkipHealthCheck,
    [switch]$Json,
    [Alias('h')]
    [switch]$Help
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$LeafRoot = Split-Path -Parent $ScriptDir
$LeafCtl = Join-Path $ScriptDir 'leafctl.ps1'
$ReportTool = Join-Path $LeafRoot 'core' 'python' 'leaf_live_report.py'
$SandboxTool = Join-Path $ScriptDir 'leaf-sandbox.ps1'

function Show-Usage {
    @'
Usage:
  leafctl passive-report [-RunRoot RUN] [-Open] [-Json]
  leafctl passive-report -StartProject -Project DIR [-BudgetMinutes N] [-Provider off|auto|required]
  leafctl passive-report -RunRoot RUN -Watch [-ReportIntervalMinutes N] [-Open]

The wrapper discovers or starts a run through leafctl, renders LIVE_REPORT.html
through leaf_live_report.py, and optionally delegates watch mode to the existing
model-free sandbox reporter.
'@ | Write-Host
}

function Require-File([string]$PathValue, [string]$Label) {
    if (-not (Test-Path -LiteralPath $PathValue -PathType Leaf)) {
        throw "$Label not found: $PathValue"
    }
}

function Require-Directory([string]$PathValue, [string]$Label) {
    if (-not (Test-Path -LiteralPath $PathValue -PathType Container)) {
        throw "$Label not found: $PathValue"
    }
}

function Invoke-LeafCtl([string[]]$Arguments) {
    # Capture information output (including Write-Host) so -Json remains a
    # single machine-readable document for callers composing this command.
    $output = @(& $LeafCtl @Arguments 6>&1)
    $succeeded = $?
    if (-not $succeeded) {
        $details = ($output -join [Environment]::NewLine).Trim()
        if (-not $details) { $details = 'command failed' }
        throw "leafctl failed: $details"
    }
    return ($output -join [Environment]::NewLine)
}

function Invoke-LeafJson([string[]]$Arguments) {
    $text = Invoke-LeafCtl $Arguments
    try {
        return ($text | ConvertFrom-Json)
    } catch {
        throw "leafctl did not return JSON: $text"
    }
}

if ($Help) {
    Show-Usage
    exit 0
}
if ($BudgetMinutes -lt 1) { throw 'BudgetMinutes must be at least 1.' }
if ($ReportIntervalMinutes -lt 1) { throw 'ReportIntervalMinutes must be at least 1.' }
if ($StartProject -and [string]::IsNullOrWhiteSpace($Project)) {
    throw '-Project is required with -StartProject.'
}
if ($NewProject -and -not $StartProject) {
    throw '-NewProject requires -StartProject.'
}

Require-File $LeafCtl 'LeafOS PowerShell entrypoint'
Require-File $ReportTool 'LeafOS HTML report tool'
if ($Watch) { Require-File $SandboxTool 'LeafOS sandbox reporting tool' }
$PythonCommand = Get-Command python -ErrorAction SilentlyContinue
if (-not $PythonCommand) { throw 'Python 3 is required for passive HTML reporting.' }
$Python = $PythonCommand.Source

if (-not $SkipHealthCheck) {
    [void](Invoke-LeafCtl @('runtime', 'validate'))
    [void](Invoke-LeafJson @('model-profile', 'validate', '--json'))
    if ($Provider -ne 'off') {
        [void](Invoke-LeafJson @('provider-stack', 'check', '--json'))
    }
}

if ($StartProject) {
    $liveArgs = @('live', $Project, '--provider', $Provider, '--mode', 'quiet', '--budget', [string]$BudgetMinutes, '--no-tui', '--json')
    if ($NewProject) { $liveArgs += @('--new', '--template', $Template) }
    if ($Approve) { $liveArgs += '--yes' }
    if ($Objective) { $liveArgs += @('--objective', $Objective) }
    $live = Invoke-LeafJson $liveArgs
    $RunRoot = [string]$live.run_dir
}

if ([string]::IsNullOrWhiteSpace($RunRoot)) {
    $active = Invoke-LeafJson @('loop', 'status', 'active', '--json')
    $RunRoot = [string]$active.run_dir
}

if ([string]::IsNullOrWhiteSpace($RunRoot)) { throw 'No run directory was selected.' }
$RunRoot = (Resolve-Path -LiteralPath $RunRoot -ErrorAction Stop).Path
Require-Directory $RunRoot 'Run directory'
Require-File (Join-Path $RunRoot 'run.json') 'Run manifest'

$Html = Join-Path $RunRoot 'LIVE_REPORT.html'
$reportOutput = @(& $Python $ReportTool $RunRoot '--output' $Html)
$reportSucceeded = $?
if (-not $reportSucceeded -or -not (Test-Path -LiteralPath $Html -PathType Leaf)) {
    $details = ($reportOutput -join [Environment]::NewLine).Trim()
    if ($details) { throw "HTML report generation failed: $details" }
    throw "HTML report generation failed: $Html"
}

$opened = $false
if ($Open) {
    Start-Process -FilePath $Html
    $opened = $true
}

$result = [ordered]@{
    leafos_object = 'leafos.passive_report_launch'
    version = 1
    run_root = $RunRoot
    html = $Html
    started_project = [bool]$StartProject
    provider = $Provider
    budget_minutes = $BudgetMinutes
    report_interval_minutes = $ReportIntervalMinutes
    watch = [bool]$Watch
    opened = $opened
    source_policy = 'read-only journal.lje, telemetry.jsonl, and actions.jsonl projection'
}

if ($Watch) {
    $watchOutput = @(& $SandboxTool '--sandbox' $RunRoot 'report' '--watch' '--interval-minutes' $ReportIntervalMinutes '--no-open')
    $watchSucceeded = $?
    if (-not $watchSucceeded) {
        $details = ($watchOutput -join [Environment]::NewLine).Trim()
        if ($details) { throw "passive report watch failed: $details" }
        exit 1
    }
}

if ($Json) {
    $result | ConvertTo-Json -Depth 8
} else {
    Write-Host "run_root : $RunRoot"
    Write-Host "html     : $Html"
    Write-Host "watch    : $Watch"
    Write-Host "provider : $Provider"
}
exit 0
