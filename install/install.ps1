[CmdletBinding()]
param([string]$Target = (Join-Path $env:LOCALAPPDATA 'LeafOS'), [switch]$AddToPath)
$ErrorActionPreference = 'Stop'
$source = Split-Path -Parent $PSScriptRoot
New-Item -ItemType Directory -Force -Path $Target | Out-Null
foreach ($name in 'bin','core','config','packs','VERSION') {
    Copy-Item -LiteralPath (Join-Path $source $name) -Destination $Target -Recurse -Force
}
$bin = Join-Path $Target 'bin'
if ($AddToPath) {
    $current = [Environment]::GetEnvironmentVariable('Path', 'User')
    $parts = @($current -split ';' | Where-Object { $_ })
    if ($bin -notin $parts) { [Environment]::SetEnvironmentVariable('Path', (($parts + $bin) -join ';'), 'User') }
}
& (Join-Path $bin 'leafctl.ps1') doctor
exit $LASTEXITCODE
