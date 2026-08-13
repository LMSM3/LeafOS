#!/usr/bin/env pwsh
param(
	[Parameter(ValueFromRemainingArguments)]
	[string[]]$Arguments
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$RootDir = Split-Path $PSScriptRoot
$Script = Join-Path $RootDir 'core\python\leaf_overnight.py'

if (-not (Test-Path $Script -PathType Leaf)) {
	throw "LeafOS overnight CLI not found: $Script"
}

$Python = Get-Command python -ErrorAction SilentlyContinue
if (-not $Python) {
	$Python = Get-Command py -ErrorAction SilentlyContinue
}
if (-not $Python) {
	throw 'Python 3 is required to run LeafOS overnight inference tooling.'
}

if ($Python.Name -eq 'py.exe' -or $Python.Name -eq 'py') {
	& $Python.Source -3 $Script @Arguments
} else {
	& $Python.Source $Script @Arguments
}
exit $LASTEXITCODE
