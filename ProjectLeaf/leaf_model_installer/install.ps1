# Bootstrap the LeafOS model installer. This installs tooling only; it never downloads models.
param([string]$PythonCommand = "")

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Invoke-Native {
    param(
        [Parameter(Mandatory = $true)][string]$File,
        [Parameter(Mandatory = $true)][string[]]$Arguments
    )
    & $File @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code ${LASTEXITCODE}: $File $($Arguments -join ' ')"
    }
}

Push-Location $PSScriptRoot
$Candidate = Join-Path $PSScriptRoot ".venv.next-$PID"
$Final = Join-Path $PSScriptRoot ".venv"
$BackupRoot = Join-Path $PSScriptRoot ".backups"

try {
    Write-Host "Installing LeafOS model planning tools" -ForegroundColor Cyan

    if ($PythonCommand) {
        $PyCmd = $PythonCommand
        $PyArgs = @()
    } elseif (Get-Command py -ErrorAction SilentlyContinue) {
        $PyCmd = "py"
        $PyArgs = @("-3")
    } elseif (Get-Command python -ErrorAction SilentlyContinue) {
        $PyCmd = "python"
        $PyArgs = @()
    } else {
        throw "Python 3.9+ was not found."
    }

    if (Test-Path -LiteralPath $Candidate) {
        Remove-Item -LiteralPath $Candidate -Recurse -Force
    }
    Invoke-Native $PyCmd ($PyArgs + @("-m", "venv", $Candidate))
    $CandidatePython = Join-Path $Candidate "Scripts\python.exe"
    Invoke-Native $CandidatePython @("-m", "pip", "install", "--upgrade", "pip")
    Invoke-Native $CandidatePython @("-m", "pip", "install", ".")
    Invoke-Native $CandidatePython @("-m", "leaf_models.install_cli", "doctor")

    New-Item -ItemType Directory -Force -Path $BackupRoot | Out-Null
    if (Test-Path -LiteralPath $Final) {
        $Stamp = Get-Date -Format "yyyyMMdd-HHmmss"
        Move-Item -LiteralPath $Final -Destination (Join-Path $BackupRoot ".venv.$Stamp")
    }
    Move-Item -LiteralPath $Candidate -Destination $Final

@"
@echo off
"%~dp0.venv\Scripts\python.exe" -m leaf_models.install_cli %*
exit /b %ERRORLEVEL%
"@ | Set-Content -Encoding ASCII (Join-Path $PSScriptRoot "leaf-models.cmd")

@"
`$ErrorActionPreference = "Stop"
& "`$PSScriptRoot\.venv\Scripts\python.exe" -m leaf_models.install_cli @args
exit `$LASTEXITCODE
"@ | Set-Content -Encoding UTF8 (Join-Path $PSScriptRoot "leaf-models.ps1")

    Write-Host ""
    Write-Host "Installer tooling is ready. No model download was started." -ForegroundColor Green
    Write-Host "Catalog: .\leaf-models.cmd catalog"
    Write-Host "Plan:    .\leaf-models.cmd plan --profile default"
    exit 0
}
catch {
    if (Test-Path -LiteralPath $Candidate) {
        Remove-Item -LiteralPath $Candidate -Recurse -Force -ErrorAction SilentlyContinue
    }
    Write-Host "INSTALL FAILED: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
finally {
    Pop-Location
}
