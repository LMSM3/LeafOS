#!/usr/bin/env pwsh
# PowerShell bridge for the Linux/WSL FlowerOS high-frequency monitor.
[CmdletBinding()]
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$MonitorArgs = @()
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RootDir = Split-Path -Parent $ScriptDir
$Launcher = Join-Path $ScriptDir 'flower-monitor'
$Source = Join-Path $RootDir 'core\monitor\flower.c'

if ($MonitorArgs.Count -gt 0 -and $MonitorArgs[0] -eq '--source') {
    Write-Output $Source
    exit 0
}

if ($IsLinux) {
    & bash $Launcher @MonitorArgs
    exit $LASTEXITCODE
}

if (-not $IsWindows) {
    Write-Error 'flower-monitor requires Linux or WSL (/proc, termios, and ioctl are used)'
    exit 1
}

$Wsl = Get-Command wsl.exe -ErrorAction SilentlyContinue
if (-not $Wsl) {
    Write-Error 'flower-monitor requires WSL on Windows'
    exit 1
}

$LinuxLauncher = (& $Wsl.Source --exec wslpath -a -u $Launcher | Select-Object -First 1).Trim()
if (-not $LinuxLauncher) {
    Write-Error "Could not translate Flower monitor path for WSL: $Launcher"
    exit 1
}

[string[]]$WslArgs = @($MonitorArgs)
for ($Index = 0; $Index -lt $WslArgs.Count; $Index++) {
    if ($WslArgs[$Index] -eq '--root') {
        if (($Index + 1) -ge $WslArgs.Count) {
            Write-Error 'flower-monitor: --root requires PATH'
            exit 2
        }
        if ($WslArgs[$Index + 1] -match '^[A-Za-z]:[\\/]') {
            $TranslatedRoot = (& $Wsl.Source --exec wslpath -a -u $WslArgs[$Index + 1] |
                Select-Object -First 1).Trim()
            if (-not $TranslatedRoot) {
                Write-Error "Could not translate Flower monitor root for WSL: $($WslArgs[$Index + 1])"
                exit 1
            }
            $WslArgs[$Index + 1] = $TranslatedRoot
        }
        $Index++
    }
}

& $Wsl.Source --exec bash $LinuxLauncher @WslArgs
exit $LASTEXITCODE
