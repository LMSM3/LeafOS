#!/usr/bin/env pwsh
# bin/install_demo.ps1 -- Windows / WSL PowerShell installer for LeafOS
# Usage: pwsh -File bin/install_demo.ps1 [-Prefix <path>]
param(
    [string]$Prefix = (Join-Path $env:LOCALAPPDATA 'leafos')
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$ScriptDir = Split-Path $MyInvocation.MyCommand.Path
$RootDir   = Split-Path $ScriptDir
$ShareDir  = Join-Path $Prefix 'share' 'leafos'
$BinDir    = Join-Path $Prefix 'bin'

$IsWSLEnv = $false
if (Test-Path '/proc/version' -ErrorAction SilentlyContinue) {
    $pv = Get-Content '/proc/version' -ErrorAction SilentlyContinue
    $IsWSLEnv = $pv -match 'microsoft|wsl'
}
$EnvName = if ($IsWSLEnv) { 'WSL' } elseif ($IsWindows) { 'Windows' } else { 'Other' }

Write-Host "Installing LeafOS on $EnvName ..."
Write-Host "  prefix : $Prefix"
Write-Host "  share  : $ShareDir"
Write-Host "  bin    : $BinDir"

New-Item -ItemType Directory -Force -Path $ShareDir, $BinDir | Out-Null

Get-ChildItem $RootDir -Recurse | Where-Object {
    $_.FullName -notmatch '[/\\](\.git|build|\.vs)[/\\]'
} | ForEach-Object {
    $rel  = $_.FullName.Substring($RootDir.Length).TrimStart('\','/')
    $dest = Join-Path $ShareDir $rel
    if ($_.PSIsContainer) {
        New-Item -ItemType Directory -Force -Path $dest | Out-Null
    } else {
        Copy-Item $_.FullName -Destination $dest -Force
    }
}

$ModSrc  = Join-Path $ShareDir 'core' 'powershell' 'LeafOS.psm1'
if (Test-Path $ModSrc) {
    $ModDest = Join-Path (Split-Path $PROFILE) 'Modules' 'LeafOS' 'LeafOS.psm1'
    New-Item -ItemType Directory -Force -Path (Split-Path $ModDest) | Out-Null
    Copy-Item $ModSrc $ModDest -Force
    Write-Host "  installed module: $ModDest"
}

if ($IsWindows -and -not $IsWSLEnv) {
    $curPath = [System.Environment]::GetEnvironmentVariable('PATH', 'User')
    if ($curPath -notlike "*$BinDir*") {
        [System.Environment]::SetEnvironmentVariable('PATH', "$BinDir;$curPath", 'User')
        Write-Host "  added to user PATH: $BinDir  (restart shell)"
    }
}

Write-Host "Install complete."
Write-Host "Run: pwsh -File `"$ShareDir\bin\leafctl.ps1`" doctor"
