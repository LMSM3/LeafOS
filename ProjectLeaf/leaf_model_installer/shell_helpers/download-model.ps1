# Compatibility wrapper for the canonical plan-first installer.
param(
    [ValidateRange(1, 5)][int]$Slot = 1,
    [string]$Quant = "",
    [string]$Dest = (Join-Path $HOME ".leaf\models"),
    [string]$Plan = (Join-Path $PSScriptRoot "..\leaf-model-plan.json"),
    [switch]$AllowFallback,
    [switch]$Resolve,
    [switch]$Apply,
    [switch]$Yes
)

$ErrorActionPreference = "Stop"
$Py = Join-Path $PSScriptRoot "..\.venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $Py)) {
    throw "Installer environment missing. Run install.ps1 first."
}

$Args = @("-m", "leaf_models.install_cli", "plan", "--slot", "$Slot", "--dest", $Dest, "--out", $Plan)
if ($Quant) { $Args += @("--quant", "$Slot=$Quant") }
if ($AllowFallback) { $Args += "--allow-fallback" }
& $Py @Args
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$ResolvedPlan = [IO.Path]::Combine(
    [IO.Path]::GetDirectoryName((Resolve-Path -LiteralPath $Plan).Path),
    "$([IO.Path]::GetFileNameWithoutExtension($Plan)).resolved.json"
)
if ($Resolve -or $Apply) {
    & $Py -m leaf_models.install_cli resolve $Plan --out $ResolvedPlan
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
if ($Apply) {
    if (-not $Yes) { throw "-Apply requires -Yes." }
    & $Py -m leaf_models.install_cli apply $ResolvedPlan --yes
    exit $LASTEXITCODE
}

Write-Host "Plan prepared. No model download was started." -ForegroundColor Green
exit 0

<#
Legacy direct-downloader implementation retained temporarily for migration history.

param(
    [ValidateSet("gemma4-coder", "qwen-opus-reasoning")]
    [string]$Model = "gemma4-coder",

    [ValidateSet("Q2_K", "Q3_K_M", "Q4_K_M", "Q6_K", "Q8_0")]
    [string]$Quant = "Q4_K_M",

    [string]$Dest = ".\models",
    [switch]$VerifyOnly,
    [int64]$MinBytes = 1048576
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Fail([string]$Message) {
    Write-Host "FAILED: $Message" -ForegroundColor Red
    exit 1
}

function Run-Native([string]$File, [string[]]$Arguments) {
    & $File @Arguments
    if ($LASTEXITCODE -ne 0) {
        Fail "Command failed with exit code $LASTEXITCODE: $File $($Arguments -join ' ')"
    }
}

switch ($Model) {
    "gemma4-coder" {
        $Repo = "yuxinlu1/gemma-4-12B-coder-fable5-composer2.5-v1-GGUF"
        $LocalDir = "Gemma4-Coder"
        switch ($Quant) {
            "Q2_K"   { $Pattern = "*Q2_K*.gguf" }
            "Q3_K_M" { $Pattern = "*Q3_K_M*.gguf" }
            "Q4_K_M" { $Pattern = "*Q4_K_M*.gguf" }
            "Q6_K"   { $Pattern = "*Q6_K*.gguf" }
            "Q8_0"   { $Pattern = "*Q8_0*.gguf" }
            default { Fail "Unknown quant: $Quant" }
        }
    }
    "qwen-opus-reasoning" {
        $Repo = "tvall43/Qwen3.5-14B-A3B-Claude-4.6-Opus-Reasoning-Distilled-reap-gguf"
        $LocalDir = "Qwen3.5-Claude-Reasoning"
        $Pattern = "*.gguf"
    }
    default { Fail "Unknown model: $Model" }
}

if (-not (Test-Path -LiteralPath $Dest)) {
    New-Item -ItemType Directory -Force -Path $Dest | Out-Null
}
$DestResolved = (Resolve-Path -LiteralPath $Dest).Path
$Target = Join-Path $DestResolved $LocalDir
New-Item -ItemType Directory -Force -Path $Target | Out-Null

Write-Host "Model:   $Model"
Write-Host "Repo:    $Repo"
Write-Host "Pattern: $Pattern"
Write-Host "Target:  $Target"

if (-not $VerifyOnly) {
    $Cli = Get-Command huggingface-cli -ErrorAction SilentlyContinue
    if (-not $Cli) {
        Fail "huggingface-cli not found. Run the main installer first or install huggingface_hub. Machines remain annoyingly literal."
    }
    Run-Native "huggingface-cli" @("download", $Repo, "--include", $Pattern, "--local-dir", $Target)
}

$Files = Get-ChildItem -LiteralPath $Target -Recurse -File -ErrorAction SilentlyContinue | Where-Object { $_.Name -like $Pattern }
if (-not $Files -or $Files.Count -eq 0) {
    Fail "No files matching $Pattern found under $Target"
}

$Bad = @()
foreach ($File in $Files) {
    if ($File.Length -lt $MinBytes) {
        $Bad += $File.FullName
    }
}
if ($Bad.Count -gt 0) {
    Write-Host "Suspiciously tiny files:" -ForegroundColor Red
    $Bad | ForEach-Object { Write-Host "  $_" }
    Fail "Verification failed"
}

$Manifest = Join-Path $Target "leaf_shell_manifest.txt"
@(
    "created_at=$(Get-Date -Format o)",
    "repo=$Repo",
    "pattern=$Pattern",
    "target=$Target",
    "files=$($Files.Count)"
) | Set-Content -Encoding UTF8 $Manifest

foreach ($File in $Files) {
    Write-Host ("OK  {0,10:N2} GB  {1}" -f ($File.Length / 1GB), $File.FullName)
}
Write-Host "VERIFIED: files exist at $Target" -ForegroundColor Green
Write-Host "Manifest: $Manifest"
exit 0
#>
