# Leaf Model Puller installer for Windows PowerShell.
# Creates a local venv, installs the package, writes launchers, and backs up old launchers before overwrite.

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

# Temporarily bypass script execution limits for the child actions in this session
Set-ExecutionPolicy -ExecutionPolicy Bypass -Scope Process -Force

function Run-Native {
    param(
        [Parameter(Mandatory=$true)][string]$File,
        [Parameter(Mandatory=$true)][string[]]$Arguments
    )
    & $File @Arguments
    if ($LASTEXITCODE -ne 0) {
        # FIXED: Wrapped LASTEXITCODE in curly braces to eliminate the parser syntax crash
        throw "Command failed with exit code ${LASTEXITCODE}: $File $($Arguments -join ' ')"
    }
}

function Backup-IfExists {
    param([Parameter(Mandatory=$true)][string]$Path)
    if (Test-Path -LiteralPath $Path) {
        $Stamp = Get-Date -Format "yyyyMMdd-HHmmss"
        $BackupDir = Join-Path (Get-Location) ".backups"
        New-Item -ItemType Directory -Force -Path $BackupDir | Out-Null
        $Name = Split-Path -Leaf $Path
        $Backup = Join-Path $BackupDir "$Name.$Stamp.bak"
        Copy-Item -LiteralPath $Path -Destination $Backup -Force
        Write-Host "Backed up $Path -> $Backup" -ForegroundColor DarkGray
    }
}

Push-Location (Split-Path -Parent $PSScriptRoot)
try {
    Write-Host "☠ Installing Leaf Model Puller" -ForegroundColor Cyan

    $Python = Get-Command py -ErrorAction SilentlyContinue
    if ($Python) {
        $PyCmd = "py"
        $PyArgs = @("-3")
    } else {
        $Python = Get-Command python -ErrorAction SilentlyContinue
        if (-not $Python) {
            throw "Python 3 was not found. Install Python 3.9+ and try again. Yes, the machine does need a language before it can run code."
        }
        $PyCmd = "python"
        $PyArgs = @()
    }

    # Execute system setup & local python environment generation
    Run-Native $PyCmd ($PyArgs + @("-m", "venv", ".venv"))
    Run-Native ".\.venv\Scripts\python.exe" @("-m", "pip", "install", "--upgrade", "pip")
    Run-Native ".\.venv\Scripts\python.exe" @("-m", "pip", "install", "-e", ".")
    Run-Native ".\.venv\Scripts\python.exe" @("-m", "leaf_models.cli", "doctor")

    # Safety archival steps
    Backup-IfExists ".\leaf-models.cmd"
    Backup-IfExists ".\leaf-models.ps1"

@"
@echo off
"%~dp0.venv\Scripts\python.exe" -m leaf_models.cli %*
exit /b %ERRORLEVEL%
"@ | Set-Content -Encoding ASCII .\leaf-models.cmd

@"
`$ErrorActionPreference = "Stop"
& "`$PSScriptRoot\.venv\Scripts\python.exe" -m leaf_models.cli @args
exit `$LASTEXITCODE
"@ | Set-Content -Encoding UTF8 .\leaf-models.ps1

    Write-Host ""
    Write-Host "Installed and verified." -ForegroundColor Green
    Write-Host "Run: .\leaf-models.cmd"
    Write-Host "Preflight first: .\leaf-models.cmd preflight --model gemma4-coder --dest .\models"
    Write-Host "Try: .\leaf-models.cmd download --model gemma4-coder --quant Q4_K_M --dest .\models"
    Write-Host "Verify later: .\leaf-models.cmd verify --model gemma4-coder --quant Q4_K_M --dest .\models"
    Write-Host "Shell preflight fallback: .\shell_helpers\system-preflight.ps1 -Model gemma4-coder -Quant Q4_K_M -Dest .\models"
    Write-Host "Shell download fallback: .\shell_helpers\download-model.ps1 -Model gemma4-coder -Quant Q4_K_M -Dest .\models"
    Write-Host "If Hugging Face wants authentication: .\.venv\Scripts\huggingface-cli.exe login"
    exit 0
}
catch {
    Write-Host ""
    Write-Host "INSTALL FAILED: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "No success message was printed because reality, for once, was consulted." -ForegroundColor Yellow
    exit 1
}
finally {
    Pop-Location
}
