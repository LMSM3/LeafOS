$ErrorActionPreference = 'Stop'
$env:PYTHONDONTWRITEBYTECODE = '1'
$root = Split-Path -Parent $PSScriptRoot
$python = Get-Command python3 -ErrorAction SilentlyContinue
if (-not $python) { $python = Get-Command python -ErrorAction SilentlyContinue }
if (-not $python) { throw 'leafctl requires Python 3.' }
& $python.Source (Join-Path $root 'core\cli.py') @args
exit $LASTEXITCODE
