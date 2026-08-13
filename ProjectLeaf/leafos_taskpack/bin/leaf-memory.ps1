param([Parameter(ValueFromRemainingArguments)] [string[]]$Rest = @())
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot
$advanced = $Rest.Count -gt 0 -and (
    $Rest[0] -in @('index', 'query', 'pack', 'stats', 'archive', 'checkpoint') -or
    ($Rest[0] -eq 'append' -and $Rest -contains '--kind')
)
if ($advanced) {
    & python (Join-Path $root 'core\memory\memory_cli.py') @Rest
    exit $LASTEXITCODE
}
$candidates = @()
if ($env:LEAF_MEMORY_BIN) { $candidates += $env:LEAF_MEMORY_BIN }
$candidates += (Join-Path $root 'build\leaf-memory.exe')
$candidates += (Join-Path $root 'build\leaf-memory')
$binary = $candidates | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1
if (-not $binary) { throw 'leaf-memory: native executable not found; build the taskpack first or set LEAF_MEMORY_BIN.' }
& $binary @Rest
exit $LASTEXITCODE
