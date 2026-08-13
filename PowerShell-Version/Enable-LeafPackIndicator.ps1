# Dot-source this file to install the LeafOS pack glyph in the current prompt.
# The prompt path supports Windows PowerShell 5/5.1 and PowerShell 7+. It must
# stay in the caller's process; launching another host cannot alter this prompt.
[CmdletBinding()]
param(
    [string]$Pack = '',
    # Windows PowerShell 5.1 can expose an empty PSScriptRoot while evaluating
    # a dot-sourced script's parameter defaults. Resolve it in the body instead.
    [string]$Root = '',
    [switch]$PassThru
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

if ($PSVersionTable.PSVersion.Major -lt 5) {
    throw "The LeafOS indicator requires PowerShell 5 or newer; found $($PSVersionTable.PSVersion)."
}
if (-not $Root) {
    $Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
}

$TaskpackRoot = Join-Path $Root 'ProjectLeaf\leafos_taskpack'
$Module = Join-Path $TaskpackRoot 'core\powershell\LeafOS.psm1'
if (-not (Test-Path -LiteralPath $Module -PathType Leaf)) {
    throw "LeafOS indicator module is missing at '$Module'. From the LeafOS root, run: .\leafos.ps1 indicator doctor"
}
Import-Module $Module -Force -Global
$indicator = Enable-LeafPackIndicator -Pack $Pack -Root $TaskpackRoot
if ($PassThru) { $indicator }
