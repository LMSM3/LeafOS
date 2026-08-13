#!/usr/bin/env pwsh
[CmdletBinding()]
param([Parameter(ValueFromRemainingArguments = $true)][string[]]$RawArgs = @())

$ErrorActionPreference = 'Stop'
$RootDir = Resolve-Path (Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) '..')
$Program = Join-Path $RootDir 'core\python\leaf_web_model_pipe.py'
$Python = Get-Command python -ErrorAction SilentlyContinue
if (-not $Python) { $Python = Get-Command py -ErrorAction SilentlyContinue }
if (-not $Python) { throw 'leaf-web-model: Python 3 is required' }

if ($Python.Name -eq 'py.exe' -or $Python.Name -eq 'py') {
    & $Python.Source -3 $Program @RawArgs
}
else {
    & $Python.Source $Program @RawArgs
}
exit $LASTEXITCODE
