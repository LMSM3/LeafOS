param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$MonitorArgs
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$VenvPython = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
    $VenvPython = Join-Path $Root ".venv/bin/python"
}

if (-not (Test-Path $VenvPython)) {
    & (Join-Path $Root "install.ps1") -NoSmoke
}

& $VenvPython -m floweros_hwmon @MonitorArgs
exit $LASTEXITCODE
