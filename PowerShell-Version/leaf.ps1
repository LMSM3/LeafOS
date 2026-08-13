#!/usr/bin/env pwsh
<#
LeafOS PowerShell entrypoint.

This is the friendly PowerShell-facing command at the reformatted root.
It delegates into the preserved source tree:

  ProjectLeaf\leafos_taskpack\bin\leafctl.ps1

NOTE: This script intentionally does NOT use [CmdletBinding()] or an explicit
param block. Using them causes PowerShell to treat subcommand flags such as
--out, --error, and --warning as common parameters (-OutVariable, -ErrorVariable,
-WarningVariable). The automatic $args variable preserves every token exactly as
entered by the user.
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# Ensure UTF-8 console I/O so glyphs and non-ASCII status text render correctly
# on Windows hosts whose default code page differs from UTF-8.
try {
    [System.Console]::OutputEncoding = [System.Text.Encoding]::UTF8
    [System.Console]::InputEncoding  = [System.Text.Encoding]::UTF8
    $OutputEncoding                  = [System.Text.Encoding]::UTF8
} catch {
    # Encoding helpers may fail in constrained hosts; continue gracefully.
}

if ($PSVersionTable.PSVersion.Major -lt 7) {
    # The prompt indicator is deliberately supported in the current Windows
    # PowerShell 5/5.1 process; switching hosts would decorate the wrong prompt.
    if ($args.Count -gt 0 -and $args[0] -in @('indicator', 'pack-indicator')) {
        $legacyRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
        $indicatorScript = Join-Path $legacyRoot 'ProjectLeaf\leafos_taskpack\bin\leaf-indicator.ps1'
        if (-not (Test-Path -LiteralPath $indicatorScript -PathType Leaf)) {
            Write-Error "LeafOS indicator script is missing: $indicatorScript"
            exit 1
        }
        $indicatorArgs = @($args | Select-Object -Skip 1)
        & $indicatorScript @indicatorArgs
        if ($?) { exit 0 }
        exit 1
    }

    $resolver = Join-Path $PSScriptRoot 'Resolve-LeafPowerShellHost.ps1'
    if (-not (Test-Path -LiteralPath $resolver -PathType Leaf)) {
        Write-Error "LeafOS PowerShell resolver is missing: $resolver"
        exit 1
    }
    . $resolver
    $Pwsh = Resolve-LeafPowerShellHost -MinimumMajor 7
    if (-not $Pwsh.usable) {
        Write-Error 'This LeafOS command requires PowerShell 7+. The indicator still works here with: leafos indicator status. Install PowerShell 7 or repair PATH, then retry.'
        exit 1
    }

    & $Pwsh.command -NoProfile -File $PSCommandPath @args
    exit $LASTEXITCODE
}

$Root = Resolve-Path (Join-Path $PSScriptRoot '..')
$TaskPack = Join-Path $Root 'ProjectLeaf\leafos_taskpack'
$LeafCtl = Join-Path $TaskPack 'bin\leafctl.ps1'
$ChatLocal = Join-Path $PSScriptRoot 'chat-local.ps1'
$DownloadDoctor = Join-Path $PSScriptRoot 'download-doctor.ps1'

function Get-RemainingArgs {
    param([int]$Skip)
    $remaining = @()
    for ($i = $Skip; $i -lt $args.Count; $i++) {
        $remaining += $args[$i]
    }
    return $remaining
}

function Invoke-ScriptWithArgs {
    # Works around a PowerShell array-splat + typed-parameter binding regression
    # (confirmed via isolated repro against this host's pwsh build) where
    # '& $Script @argsArray' mis-binds '-Name' tokens into typed [int]/[switch]
    # parameters. Reconstructing and invoking the literal command line avoids
    # the splat path entirely and binds exactly as a direct call would.
    param([string]$ScriptPath, [string[]]$ScriptArgs)
    $quoted = $ScriptArgs | ForEach-Object {
        if ($_ -match '^-[A-Za-z][A-Za-z0-9]*$') { $_ } else { "'" + ($_ -replace "'", "''") + "'" }
    }
    $commandLine = "& '$ScriptPath'" + $(if ($quoted.Count -gt 0) { ' ' + ($quoted -join ' ') } else { '' })
    Invoke-Expression $commandLine
}

if ($args.Count -gt 0 -and $args[0] -in @('chat-local', 'local-chat', 'chat-real')) {
    $remaining = @(Get-RemainingArgs -Skip 1)
    Invoke-ScriptWithArgs -ScriptPath $ChatLocal -ScriptArgs $remaining
    if ($?) { exit 0 } else { exit 1 }
}

if ($args.Count -gt 1 -and $args[0] -eq 'train' -and $args[1] -eq 'continually') {
    $remaining = @(Get-RemainingArgs -Skip 2)
    $WorkspaceRoot = Resolve-Path (Join-Path $Root '..')
    $TrainContinually = Join-Path $WorkspaceRoot 'FF\LeafOS\leafos\kernel\Invoke-TrainContinually.ps1'
    if (-not (Test-Path $TrainContinually -PathType Leaf)) {
        Write-Error "Train-continually kernel not found: $TrainContinually"
        exit 1
    }
    Invoke-ScriptWithArgs -ScriptPath $TrainContinually -ScriptArgs $remaining
    if ($?) { exit 0 } else { exit 1 }
}

if ($args.Count -gt 1 -and $args[0] -eq 'download' -and $args[1] -eq 'doctor') {
    $remaining = @(Get-RemainingArgs -Skip 2)
    Invoke-ScriptWithArgs -ScriptPath $DownloadDoctor -ScriptArgs $remaining
    if ($?) { exit 0 } else { exit 1 }
}

if (-not (Test-Path $LeafCtl -PathType Leaf)) {
    Write-Error "LeafOS source command not found: $LeafCtl"
    exit 1
}

& $LeafCtl @args
if ($?) { exit 0 }
exit 1
