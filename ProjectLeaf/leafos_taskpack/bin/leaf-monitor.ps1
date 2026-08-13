#!/usr/bin/env pwsh
# bin/leaf-monitor.ps1 -- Lightweight live process monitor for LeafOS.
# This is a secondary action: not part of LeafOS itself, but useful for
# watching long-running downloads, chat servers, or agent loops.
param(
	[Parameter()][int]$DurationSeconds = 0,
	[Parameter()][string]$Query = "leaf|python|pwsh|node"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Show-ProcessTable {
	Clear-Host
	$procs = Get-Process | Where-Object {
		$_ -and ($_.ProcessName -match $Query -or ($_.Path -match $Query))
	} | Sort-Object CPU -Descending | Select-Object -First 20 |
		Select-Object Id,
			@{N='Name'; E={$_.ProcessName}},
			@{N='CPU(s)'; E={[math]::Round($_.CPU, 1)}},
			@{N='WorkingSetMB'; E={[math]::Round($_.WorkingSet64 / 1MB, 1)}},
			@{N='Path'; E={
				try { if ($_.Path) { $_.Path } else { '-' } } catch { '-' }
			}}
	Write-Host "LeafOS live monitor  (filter: $Query)  $(Get-Date -Format 'T')" -ForegroundColor Green
	$procs | Format-Table -AutoSize
}

$end = if ($DurationSeconds -gt 0) { (Get-Date).AddSeconds($DurationSeconds) } else { $null }
Show-ProcessTable
if ($end) {
	while ((Get-Date) -lt $end) {
		Start-Sleep -Seconds 1
		Show-ProcessTable
	}
} else {
	Write-Host 'Press Ctrl+C to stop.' -ForegroundColor Yellow
	while ($true) {
		Start-Sleep -Seconds 1
		Show-ProcessTable
	}
}
