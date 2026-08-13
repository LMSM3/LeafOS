#!/usr/bin/env pwsh
<#
LeafOS download doctor: hash and inventory already-downloaded model artifacts.

Public command:
  .\leaf.ps1 download doctor

This command never downloads files. It checks local artifacts only.
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$Installer = Join-Path $Root 'ProjectLeaf\leaf_model_installer'
$RawArgs = @($args)

function Resolve-LeafPython {
    $pythonCandidates = @(
        (Join-Path $Installer '.venv\Scripts\python.exe'),
        (Join-Path $Installer '.venv\bin\python.exe'),
        (Join-Path $Installer '.venv\bin\python3.exe')
    )
    $python = @($pythonCandidates | Where-Object { Test-Path $_ -PathType Leaf } | Select-Object -First 1)[0]
    if (-not $python) {
        $pythonCommand = Get-Command python -ErrorAction SilentlyContinue | Select-Object -First 1
        $python = if ($pythonCommand) { $pythonCommand.Source } else { $null }
    }
    if (-not $python) {
        $pythonCommand = Get-Command python3 -ErrorAction SilentlyContinue | Select-Object -First 1
        $python = if ($pythonCommand) { $pythonCommand.Source } else { $null }
    }
    if (-not $python) { throw 'Python not found; download doctor requires Python.' }
    return $python
}

function Convert-ToWslPathSoft {
    param([string]$Path)
    if (-not $Path) { return $Path }
    try {
        $wslFriendlyPath = $Path -replace '\\', '/'
        $converted = (& wsl.exe wslpath -a $wslFriendlyPath 2>$null).Trim()
        if ($LASTEXITCODE -eq 0 -and $converted) { return $converted }
    }
    catch {
        return $Path
    }
    return $Path
}

function Convert-DoctorArgsForWsl {
    param([string[]]$Values)
    $converted = @()
    $pathFlags = @('--dest', '--model-dir', '--report')
    for ($i = 0; $i -lt $Values.Count; $i++) {
        $arg = [string]$Values[$i]
        if ($arg -in @('--no-wsl', '-nowsl', '-no-wsl')) {
            continue
        }
        if ($arg -match '^(--dest|--model-dir|--report)=(.+)$') {
            $converted += "$($Matches[1])=$(Convert-ToWslPathSoft -Path $Matches[2])"
            continue
        }
        $converted += $arg
        if ($pathFlags -contains $arg -and ($i + 1) -lt $Values.Count) {
            $i++
            $converted += (Convert-ToWslPathSoft -Path ([string]$Values[$i]))
        }
    }
    return $converted
}

$NoWsl = [bool](@($RawArgs | Where-Object { $_ -in @('--no-wsl', '-nowsl', '-no-wsl') } | Select-Object -First 1))

if (-not $NoWsl) {
    $wsl = Get-Command wsl.exe -ErrorAction SilentlyContinue | Select-Object -First 1
    $bashScript = Join-Path $Root 'Bash-Version\download-doctor.sh'
    if ($wsl -and (Test-Path $bashScript -PathType Leaf)) {
        try {
            $wslFriendlyRoot = $Root -replace '\\', '/'
            $wslRoot = (& wsl.exe wslpath -a $wslFriendlyRoot).Trim()
            if ($LASTEXITCODE -eq 0 -and $wslRoot) {
                $wslScript = "$wslRoot/Bash-Version/download-doctor.sh"
                $wslArgs = @(Convert-DoctorArgsForWsl -Values $RawArgs)
                & wsl.exe --cd $wslRoot --exec /bin/bash --noprofile --norc $wslScript @wslArgs
                exit $LASTEXITCODE
            }
        }
        catch {
            Write-Warning "WSL download doctor was unavailable: $($_.Exception.Message). Trying PowerShell fallback."
        }
    }
}

$python = Resolve-LeafPython
$nativeArgs = @($RawArgs | Where-Object { $_ -notin @('--no-wsl', '-nowsl', '-no-wsl') })
$old = $env:PYTHONPATH
try {
    $env:PYTHONPATH = if ($old) { "$Installer;$old" } else { "$Installer" }
    & $python -B -m leaf_models.install_cli download-doctor @nativeArgs
    exit $LASTEXITCODE
}
finally {
    $env:PYTHONPATH = $old
}
