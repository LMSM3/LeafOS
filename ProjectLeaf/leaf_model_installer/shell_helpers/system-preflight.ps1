# Compatibility wrapper for the canonical local-only doctor and plan commands.
param(
    [ValidateRange(1, 5)][int]$Slot = 1,
    [string]$Quant = "",
    [string]$Dest = (Join-Path $HOME ".leaf\models"),
    [string]$Plan = (Join-Path $PSScriptRoot "..\leaf-model-plan.json")
)

$ErrorActionPreference = "Stop"
$Py = Join-Path $PSScriptRoot "..\.venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $Py)) {
    throw "Installer environment missing. Run install.ps1 first."
}
& $Py -m leaf_models.install_cli doctor
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$Args = @("-m", "leaf_models.install_cli", "plan", "--slot", "$Slot", "--dest", $Dest, "--out", $Plan)
if ($Quant) { $Args += @("--quant", "$Slot=$Quant") }
& $Py @Args
exit $LASTEXITCODE

<#
Legacy hardware-report implementation retained temporarily for migration history.

# Leaf Model Puller Version 3 system preflight for Windows PowerShell.
# Reads system/GPU/RAM info, shows a visible loading animation, writes an explicit target-location report,
# and optionally flushes DNS cache. No exit-event tricks. No fake success.

param(
    [ValidateSet("gemma4-coder", "qwen-opus-reasoning")]
    [string]$Model = "gemma4-coder",

    [ValidateSet("Q2_K", "Q3_K_M", "Q4_K_M", "Q6_K", "Q8_0")]
    [string]$Quant = "Q4_K_M",

    [string]$Dest = ".\models",
    [int]$WaitSeconds = 12,
    [switch]$FlushDns,
    [switch]$FullComputerInfo
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Fail([string]$Message) {
    Write-Host "FAILED: $Message" -ForegroundColor Red
    exit 1
}
#>

function Get-ModelLocalDir([string]$ModelName) {
    switch ($ModelName) {
        "gemma4-coder" { return "Gemma4-Coder" }
        "qwen-opus-reasoning" { return "Qwen3.5-Claude-Reasoning" }
        default { Fail "Unknown model: $ModelName" }
    }
}

function Get-QuantRecommendation([double]$RamGb, [double]$MaxVramGb) {
    if ($Model -eq "qwen-opus-reasoning") {
        return [pscustomobject]@{
            recommended_quant = $null
            reason = "This model entry pulls all matching GGUF files; no quant selector is used."
            memory_basis = "catalog has no quant options"
        }
    }
    if (($MaxVramGb -ge 15) -or ($RamGb -ge 48)) {
        return [pscustomobject]@{ recommended_quant = "Q8_0"; reason = "Enough detected memory for the largest listed file with headroom."; memory_basis = "high VRAM/RAM" }
    }
    if (($MaxVramGb -ge 11.5) -or ($RamGb -ge 32)) {
        return [pscustomobject]@{ recommended_quant = "Q6_K"; reason = "Enough detected memory for a higher-quality quant with some margin."; memory_basis = "moderate-high VRAM/RAM" }
    }
    if (($MaxVramGb -ge 8) -or ($RamGb -ge 16)) {
        return [pscustomobject]@{ recommended_quant = "Q4_K_M"; reason = "Recommended baseline for sane local use."; memory_basis = "baseline VRAM/RAM" }
    }
    if (($MaxVramGb -ge 6.5) -or ($RamGb -ge 12)) {
        return [pscustomobject]@{ recommended_quant = "Q3_K_M"; reason = "Memory looks tight for the baseline; cautious fallback."; memory_basis = "limited VRAM/RAM" }
    }
    return [pscustomobject]@{ recommended_quant = "Q2_K"; reason = "Very limited detected memory; smallest option."; memory_basis = "low VRAM/RAM" }
}

try {
    Write-Host "☠ Leaf Model Puller v0.3.0 preflight" -ForegroundColor Cyan

    if ($FullComputerInfo) {
        Get-ComputerInfo
    } else {
        Get-ComputerInfo | Select-Object CsName, OsName, OsVersion, WindowsVersion, OsArchitecture, CsProcessors, CsTotalPhysicalMemory, BiosVersion | Format-List
    }

    Write-Host "NVIDIA SMI:" -ForegroundColor Cyan
    $GpuRows = @()
    $NvidiaSmi = Get-Command nvidia-smi -ErrorAction SilentlyContinue
    if ($NvidiaSmi) {
        $RawGpu = nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader,nounits
        foreach ($Line in $RawGpu) {
            Write-Host "$Line MB"
            $Parts = $Line -split ","
            if ($Parts.Count -ge 3) {
                $GpuRows += [pscustomobject]@{
                    name = $Parts[0].Trim()
                    driver_version = $Parts[1].Trim()
                    memory_total_mb = [int]([double]$Parts[2].Trim())
                }
            }
        }
    } else {
        Write-Host "NVIDIA SMI not found."
    }

    Write-Host "RAM:" -ForegroundColor Cyan
    $RamModules = Get-CimInstance Win32_PhysicalMemory | Group-Object Capacity | ForEach-Object {
        [pscustomobject]@{ capacity_gb = [math]::Round(([double]$_.Name / 1GB), 2); count = $_.Count }
    }
    $RamLine = $RamModules | ForEach-Object { "{0}GB x {1}" -f $_.capacity_gb, $_.count }
    Write-Host ($RamLine -join ", ")
    $RamTotalGb = [math]::Round(((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory / 1GB), 2)
    Write-Host "Total RAM: $RamTotalGb GB"
    Write-Host ""

    if ($WaitSeconds -gt 0) {
        $frames = @('𒅒', '𒈔', '𒅒', '𒇫', '𒄆')
        $stopwatch = [System.Diagnostics.Stopwatch]::StartNew()
        $i = 0
        while ($stopwatch.Elapsed.TotalSeconds -lt $WaitSeconds) {
            $frame = $frames[$i % $frames.Count]
            Write-Progress -Activity "Loading..." -Status "$frame  $([math]::Round($stopwatch.Elapsed.TotalSeconds, 1))s"
            Start-Sleep -Milliseconds 200
            $i++
        }
        Write-Progress -Activity "Loading..." -Completed
        Write-Host "Loading complete. No success implied."
    }

    $DnsReport = [pscustomobject]@{ requested = [bool]$FlushDns; success = $true; attempted = @(); messages = @() }
    if ($FlushDns) {
        try {
            $DnsReport.attempted += "Clear-DnsClientCache"
            Clear-DnsClientCache
            $DnsReport.attempted += "ipconfig /flushdns"
            $FlushOut = ipconfig /flushdns
            $DnsReport.messages += $FlushOut
            Write-Host "DNS cache flushed explicitly." -ForegroundColor Green
        } catch {
            $DnsReport.success = $false
            $DnsReport.messages += $_.Exception.Message
            Fail "DNS flush was requested and failed: $($_.Exception.Message)"
        }
    }

    if (-not (Test-Path -LiteralPath $Dest)) {
        New-Item -ItemType Directory -Force -Path $Dest | Out-Null
    }
    $DestResolved = (Resolve-Path -LiteralPath $Dest).Path
    $LocalDir = Get-ModelLocalDir $Model
    $Target = Join-Path $DestResolved $LocalDir
    New-Item -ItemType Directory -Force -Path $Target | Out-Null

    $MaxVramGb = 0
    if ($GpuRows.Count -gt 0) {
        $MaxVramGb = [math]::Round((($GpuRows | Measure-Object -Property memory_total_mb -Maximum).Maximum / 1024), 2)
    }
    $Recommendation = Get-QuantRecommendation -RamGb $RamTotalGb -MaxVramGb $MaxVramGb

    $Report = [pscustomobject]@{
        created_at = (Get-Date -Format o)
        model = $Model
        requested_quant = $Quant
        destination_root = $DestResolved
        target_dir = $Target
        nvidia_smi = if ($NvidiaSmi) { $NvidiaSmi.Source } else { $null }
        gpus = @($GpuRows)
        ram_total_gb = $RamTotalGb
        ram_modules = @($RamModules)
        dns_flush = $DnsReport
        recommendation = $Recommendation
    }
    $ReportPath = Join-Path $Target "leaf_preflight_report.json"
    $Report | ConvertTo-Json -Depth 6 | Set-Content -Encoding UTF8 $ReportPath

    Write-Host "Target download directory:" -ForegroundColor Cyan
    Write-Host "  $Target"
    Write-Host "Recommended quant: $($Recommendation.recommended_quant)"
    Write-Host "Reason: $($Recommendation.reason)"
    Write-Host "Preflight report: $ReportPath"
    Write-Host "PREFLIGHT COMPLETE. No model download has been claimed." -ForegroundColor Green
    exit 0
} catch {
    Write-Host "PREFLIGHT FAILED: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
