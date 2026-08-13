# LeafOS README and release steward. Run without arguments for the menu.
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

try {
    [Console]::OutputEncoding = [Text.Encoding]::UTF8
    [Console]::InputEncoding = [Text.Encoding]::UTF8
    $OutputEncoding = [Text.Encoding]::UTF8
} catch {}

$program = Join-Path $PSScriptRoot 'ProjectLeaf\leafos_taskpack\core\python\leaf_program.py'
$python = Get-Command python3 -ErrorAction SilentlyContinue
if (-not $python) { $python = Get-Command python -ErrorAction SilentlyContinue }
if ($python) {
    & $python.Source $program @args
    exit $LASTEXITCODE
}

$py = Get-Command py -ErrorAction SilentlyContinue
if ($py) {
    & $py.Source -3 $program @args
    exit $LASTEXITCODE
}

Write-Error 'LeafOS program needs Python 3 on PATH.'
exit 127
