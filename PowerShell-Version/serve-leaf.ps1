#!/usr/bin/env pwsh
<#
Start the minimal LeafOS browser/API surface.

Examples:
  .\serve-leaf.ps1
  .\serve-leaf.ps1 --host 0.0.0.0 --port 8765
#>

[CmdletBinding()]
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$ServeArgs = @()
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$Server = Join-Path $Root 'ProjectLeaf\leafos_taskpack\system\serve_leaf.py'

if (-not (Test-Path $Server -PathType Leaf)) {
    Write-Error "serve_leaf.py not found: $Server"
    exit 1
}

$python = $null
foreach ($candidate in @('py', 'python', 'python3')) {
    try {
        if ($candidate -eq 'py') {
            & $candidate -3 -c "import sys; raise SystemExit(0)" 2>$null
        }
        else {
            & $candidate -c "import sys; raise SystemExit(0)" 2>$null
        }
        if ($LASTEXITCODE -eq 0) {
            $python = $candidate
            break
        }
    }
    catch {
    }
}

if (-not $python) {
    Write-Error 'Python 3 was not found.'
    exit 1
}

if ($python -eq 'py') {
    & $python -3 $Server @ServeArgs
}
else {
    & $python $Server @ServeArgs
}
exit $LASTEXITCODE
