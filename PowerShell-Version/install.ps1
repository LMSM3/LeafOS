#requires -Version 5.1
<#
.SYNOPSIS
    LeafOS installation forwarding entry point.

.DESCRIPTION
    This script exists only as a cosmetic convenience. It immediately forwards
    to the authoritative safe installation surface, real-models.ps1.

    Do not add installation logic here. The real work is performed by
    install_cli.py and orchestrator.py; real-models.ps1 is the guided front end.
#>
$ErrorActionPreference = 'Stop'
$realModels = Join-Path $PSScriptRoot 'real-models.ps1'
if (-not (Test-Path $realModels)) {
    throw "Cannot find installer surface: $realModels"
}

& $realModels @args
