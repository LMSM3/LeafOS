#!/usr/bin/env pwsh
$ScriptDir = Split-Path $MyInvocation.MyCommand.Path
& (Join-Path $ScriptDir 'leafctl.ps1') tui --native @args
exit $LASTEXITCODE
