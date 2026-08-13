#!/usr/bin/env pwsh
# FlowerOS operator entrypoint; LeafOS remains the execution engine.
$ErrorActionPreference = 'Stop'
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$leafctl = Join-Path $scriptDir 'leafctl.ps1'
if (-not (Test-Path -LiteralPath $leafctl -PathType Leaf)) {
    Write-Error "LeafOS engine entrypoint not found: $leafctl"
    exit 1
}
$env:LEAF_UI_SURFACE = 'FlowerOS'
& $leafctl @args
exit $LASTEXITCODE
