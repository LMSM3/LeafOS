param(
    [switch]$NoSmoke
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

function Find-Python {
    $candidates = @(
        @{ Command = "py"; Args = @("-3") },
        @{ Command = "python"; Args = @() },
        @{ Command = "python3"; Args = @() }
    )
    foreach ($candidate in $candidates) {
        try {
            $output = & $candidate.Command @($candidate.Args) -c "import sys; print(sys.executable)" 2>$null
            if ($LASTEXITCODE -eq 0 -and $output) {
                return [pscustomobject]$candidate
            }
        } catch {
        }
    }
    throw "Python 3.9+ was not found. Install Python, then rerun install.ps1."
}

Write-Host "FlowerOS Hardware Monitor installer" -ForegroundColor Magenta
$Python = Find-Python
& $Python.Command @($Python.Args) -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 9) else 1)"
if ($LASTEXITCODE -ne 0) {
    throw "Python 3.9+ is required."
}

& $Python.Command @($Python.Args) -m venv .venv
$VenvPython = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
    $VenvPython = Join-Path $Root ".venv/bin/python"
}

& $VenvPython -m pip install --upgrade pip
& $VenvPython -m pip install -e .

if (-not $NoSmoke) {
    & $VenvPython -m unittest discover -s tests
    & $VenvPython -m floweros_hwmon --once --no-alt-screen
}

Write-Host ""
Write-Host "Installed. Run with:" -ForegroundColor Green
Write-Host "  .\run.ps1"
Write-Host "  .\.venv\Scripts\floweros-hwmon.exe"
