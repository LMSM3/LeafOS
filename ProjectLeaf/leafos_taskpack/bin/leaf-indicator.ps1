#!/usr/bin/env pwsh
# Parse literal CLI tokens so GNU-style flags survive PowerShell's parameter
# binder in the same way they do through the root leafos.ps1 launcher.
$Action = 'status'
$Pack = ''
$Json = $false
$Root = ''
$positionals = [Collections.Generic.List[string]]::new()
for ($index = 0; $index -lt $args.Count; $index++) {
    $token = "$($args[$index])"
    switch ($token.ToLowerInvariant()) {
        '--json' { $Json = $true; continue }
        '-json' { $Json = $true; continue }
        '--root' {
            if ($index + 1 -ge $args.Count) { throw '--root requires a path' }
            $index++
            $Root = "$($args[$index])"
            continue
        }
        '-root' {
            if ($index + 1 -ge $args.Count) { throw '-Root requires a path' }
            $index++
            $Root = "$($args[$index])"
            continue
        }
        default {
            if ($token.StartsWith('-')) { throw "unknown indicator option: $token" }
            $positionals.Add($token)
        }
    }
}
if ($positionals.Count -gt 0) { $Action = $positionals[0].ToLowerInvariant() }
if ($positionals.Count -gt 1) { $Pack = $positionals[1] }
if ($positionals.Count -gt 2) { throw 'too many indicator arguments' }
if ($Action -notin @('status', 'set', 'clear', 'preview', 'doctor', 'help')) {
    throw "unknown indicator action: $Action"
}

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# Direct Bash/MSYS/WSL dispatch bypasses the root leaf.ps1 encoding setup.
# Initialize UTF-8 here so the pack glyph survives Windows process interop.
try {
    [Console]::OutputEncoding = [Text.Encoding]::UTF8
    [Console]::InputEncoding = [Text.Encoding]::UTF8
    $OutputEncoding = [Text.Encoding]::UTF8
} catch { }

$TaskpackRoot = if ($Root) {
    [IO.Path]::GetFullPath($Root)
} else {
    [IO.Path]::GetFullPath((Split-Path $PSScriptRoot))
}
$Module = Join-Path $TaskpackRoot 'core\powershell\LeafOS.psm1'

function Get-IndicatorHostReport {
    $checks = New-Object System.Collections.Generic.List[object]
    $edition = if ($PSVersionTable.ContainsKey('PSEdition')) { "$($PSVersionTable.PSEdition)" } else { 'Desktop' }
    $versionOk = $PSVersionTable.PSVersion.Major -ge 5
    $checks.Add([pscustomobject][ordered]@{
        id = 'host.powershell'; ok = $versionOk
        detail = "PowerShell $($PSVersionTable.PSVersion) ($edition)"
        repair = if ($versionOk) { $null } else { 'install Windows PowerShell 5.1 or PowerShell 7+' }
    })
    $scriptOk = Test-Path -LiteralPath $PSCommandPath -PathType Leaf
    $checks.Add([pscustomobject][ordered]@{
        id = 'install.indicator_script'; ok = $scriptOk; detail = $PSCommandPath
        repair = if ($scriptOk) { $null } else { 'reinstall LeafOS or invoke the indicator from its installed root' }
    })
    $moduleOk = Test-Path -LiteralPath $Module -PathType Leaf
    $moduleDetail = if ($moduleOk) { $Module } else { "missing: $Module" }
    if ($moduleOk) {
        try {
            $tokens = $null; $parseErrors = $null
            $null = [Management.Automation.Language.Parser]::ParseFile($Module, [ref]$tokens, [ref]$parseErrors)
            if (@($parseErrors).Count -gt 0) {
                $moduleOk = $false
                $moduleDetail = "module parse failed: $($parseErrors[0].Message)"
            }
        } catch {
            $moduleOk = $false
            $moduleDetail = "module probe failed: $($_.Exception.Message)"
        }
    }
    $checks.Add([pscustomobject][ordered]@{
        id = 'install.indicator_module'; ok = $moduleOk; detail = $moduleDetail
        repair = if ($moduleOk) { $null } else { 'from the LeafOS root run: .\PowerShell-Version\install-leafos.ps1 -Action verify; reinstall if the file is missing or its hash differs' }
    })
    $packRoot = Join-Path $TaskpackRoot 'config\packs'
    $packsOk = Test-Path -LiteralPath $packRoot -PathType Container
    $checks.Add([pscustomobject][ordered]@{
        id = 'install.pack_registry'; ok = $packsOk; detail = if ($packsOk) { $packRoot } else { "missing: $packRoot" }
        repair = if ($packsOk) { $null } else { 'repair the LeafOS installation; the pack registry directory is missing' }
    })
    $executionPolicies = @()
    try {
        $executionPolicies = @(Get-ExecutionPolicy -List | ForEach-Object {
            [pscustomobject]@{ scope = $_.Scope.ToString(); policy = $_.ExecutionPolicy.ToString() }
        })
    } catch { }
    $failed = @($checks | Where-Object { -not $_.ok })
    $isWindowsHost = [Environment]::OSVersion.Platform -eq [PlatformID]::Win32NT
    $procVersion = if (Test-Path -LiteralPath '/proc/version') { Get-Content -LiteralPath '/proc/version' -Raw -ErrorAction SilentlyContinue } else { '' }
    $osRoute = if ($isWindowsHost) { 'windows' } elseif ($procVersion -match 'microsoft|wsl') { 'wsl' } else { 'unix' }
    $shellRoute = if ($env:LEAF_SHELL_ROUTE) { "$($env:LEAF_SHELL_ROUTE)" } else { "$osRoute-native" }
    $hostProcess = try { [Diagnostics.Process]::GetCurrentProcess().MainModule.FileName } catch { '' }
    $checkArray = @($checks | ForEach-Object { $_ })
    $repairs = @($failed | ForEach-Object { [pscustomobject]@{ check = $_.id; action = $_.repair } })
    [pscustomobject][ordered]@{
        leafos_object = 'leafos.indicator_host_report'
        version = 1
        status = if ($failed.Count -eq 0) { 'ready' } else { 'not_ready' }
        ready = ($failed.Count -eq 0)
        host = [pscustomobject][ordered]@{
            powershell = $PSVersionTable.PSVersion.ToString()
            edition = $edition
            os = $osRoute
            route = $shellRoute
            process = $hostProcess
        }
        taskpack_root = $TaskpackRoot
        execution_policy = $executionPolicies
        checks = $checkArray
        repairs = $repairs
    }
}

if ($Action -eq 'doctor') {
    $hostReport = Get-IndicatorHostReport
    if ($Json) {
        $hostReport | ConvertTo-Json -Depth 8 -Compress
    } else {
        Write-Host "LeafOS indicator host: $($hostReport.status)"
        Write-Host "  PowerShell : $($hostReport.host.powershell) ($($hostReport.host.edition))"
        Write-Host "  OS route   : $($hostReport.host.os)"
        Write-Host "  shell route: $($hostReport.host.route)"
        Write-Host "  executable : $($hostReport.host.process)"
        foreach ($check in $hostReport.checks) {
            Write-Host "  $(if ($check.ok) { '[ok]' } else { '[fail]' }) $($check.id): $($check.detail)"
            if (-not $check.ok) { Write-Host "         repair: $($check.repair)" }
        }
    }
    if (-not $hostReport.ready) { exit 1 }
    exit 0
}

Import-Module $Module -Force

function Write-IndicatorResult {
    param([object]$Result)
    if ($Json) {
        $Result | ConvertTo-Json -Depth 8 -Compress
        return
    }
    $mark = Format-LeafPackIndicator -Indicator $Result -RequireActive
    $heading = if ($mark) { "$mark LeafOS PowerShell indicator" } else { 'LeafOS PowerShell indicator' }
    Write-Host $heading
    Write-Host "  state      : $(if ($Result.active) { 'ACTIVE' } else { 'inactive' })"
    Write-Host "  pack       : $(if ($Result.pack_id) { $Result.pack_id } else { '(none)' })"
    Write-Host "  glyph      : $($Result.glyph)"
    Write-Host "  source     : $($Result.source)"
    Write-Host "  customized : $($Result.customized)"
    Write-Host "  subsystem  : $(if ($Result.evidence.subsystem) { $Result.evidence.subsystem } else { '(none)' })"
    Write-Host "  evidence   : $($Result.evidence.evidence_grade) via $($Result.evidence.source)"
    Write-Host "  claims     : $(if ($Result.evidence.claims.Count) { $Result.evidence.claims -join ', ' } else { '(none)' })"
    Write-Host "  reason     : $($Result.reason)"
}

switch ($Action) {
    'set' {
        if (-not $Pack) { throw 'indicator set requires a pack id or manifest path' }
        Write-IndicatorResult (Set-LeafActivePack -Pack $Pack -Root $TaskpackRoot -Persist)
    }
    'clear' {
        Write-IndicatorResult (Clear-LeafActivePack -Root $TaskpackRoot -Persist)
    }
    'preview' {
        if (-not $Pack) { throw 'indicator preview requires a pack id or manifest path' }
        Write-IndicatorResult (Get-LeafPackIndicator -Pack $Pack -Root $TaskpackRoot -Refresh)
    }
    'help' {
        Write-Host 'LeafOS PowerShell pack indicator'
        Write-Host ''
        Write-Host '  leafos indicator status [--json]'
        Write-Host '  leafos indicator preview PACK [--json]'
        Write-Host '  leafos indicator set PACK [--json]'
        Write-Host '  leafos indicator clear [--json]'
        Write-Host '  leafos indicator doctor [--json]'
        Write-Host ''
        Write-Host 'Enable it in the current PowerShell session:'
        Write-Host "  Import-Module '$Module'"
        Write-Host '  Enable-LeafPackIndicator'
    }
    default {
        Write-IndicatorResult (Get-LeafPackIndicator -Root $TaskpackRoot -Refresh)
    }
}
