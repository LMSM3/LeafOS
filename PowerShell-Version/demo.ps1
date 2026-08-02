#!/usr/bin/env pwsh
<#
Run the PowerShell LeafOS demo bundle from the friendly root surface.
#>

[CmdletBinding()]
param(
    [switch]$SkipModelPlan
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$Root = Resolve-Path (Join-Path $PSScriptRoot '..')
$Demo = Join-Path $Root 'ProjectLeaf\leafos_taskpack\demo\LeafOS-Demo-Bundle.ps1'
$Out = Join-Path $PSScriptRoot ('reports\demo-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))

if (-not (Test-Path $Demo -PathType Leaf)) {
    throw "Demo bundle not found: $Demo"
}

if ($SkipModelPlan) {
    & $Demo -SkipModelPlan -OutputDir $Out
}
else {
    & $Demo -OutputDir $Out
}
