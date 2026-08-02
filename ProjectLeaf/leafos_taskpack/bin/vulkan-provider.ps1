#!/usr/bin/env pwsh
[CmdletBinding()]
param(
	[ValidateSet('check', 'start', 'status', 'stop')]
	[string]$Action = 'check',
	[string]$Config = (Join-Path (Split-Path $PSScriptRoot) 'config\vulkan-provider-stack.json'),
	[switch]$Json
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Write-StackResult {
	param([hashtable]$Result, [int]$ExitCode = 0)
	if ($Json) {
		$Result | ConvertTo-Json -Depth 8 -Compress
	} else {
		Write-Host "Vulkan provider: $($Result.status)"
		Write-Host "  server: $($Result.server)"
		Write-Host "  endpoint: $($Result.endpoint)"
		Write-Host "  reason: $($Result.reason)"
	}
	exit $ExitCode
}

function Get-StackConfiguration {
	if (-not (Test-Path $Config -PathType Leaf)) {
		throw "Provider stack configuration not found: $Config"
	}
	$settings = Get-Content $Config -Raw | ConvertFrom-Json
	if ($settings.backend -ne 'vulkan' -or $settings.provider -ne 'llamacpp') {
		throw 'Provider stack configuration must select llamacpp with the vulkan backend.'
	}
	return $settings
}

function Get-StackPaths {
	param($Settings)
	$root = Split-Path $PSScriptRoot
	$runDir = Join-Path $root 'runs\vulkan-provider'
	New-Item -ItemType Directory -Path $runDir -Force | Out-Null
	return @{
		RunDir = $runDir
		Pid = Join-Path $runDir 'llama-server.pid'
		Out = Join-Path $runDir 'llama-server.out.log'
		Err = Join-Path $runDir 'llama-server.err.log'
	}
}

function Get-StackProcess {
	param([hashtable]$Paths)
	if (-not (Test-Path $Paths.Pid -PathType Leaf)) { return $null }
	try {
		$pidValue = [int](Get-Content $Paths.Pid -Raw)
		return Get-Process -Id $pidValue -ErrorAction SilentlyContinue
	} catch {
		return $null
	}
}

function Test-StackHealth {
	param([string]$Endpoint)
	try {
		$response = Invoke-WebRequest -Uri "$($Endpoint.TrimEnd('/'))/health" -TimeoutSec 2 -UseBasicParsing
		return $response.StatusCode -ge 200 -and $response.StatusCode -lt 300
	} catch {
		return $false
	}
}

function Get-StackErrorTail {
	param([hashtable]$Paths)
	if (-not (Test-Path $Paths.Err -PathType Leaf)) { return @() }
	return @(Get-Content $Paths.Err -Tail 12 -ErrorAction SilentlyContinue)
}

function Get-VulkanPreflight {
	param($Settings)
	$server = [string]$Settings.server.executable
	$model = [string]$Settings.server.model
	$endpoint = "http://$($Settings.server.host):$($Settings.server.port)"
	$result = @{ status = 'not_ready'; server = $server; model = $model; endpoint = $endpoint; reason = ''; devices = @() }
	if ([string]::IsNullOrWhiteSpace($server) -or -not (Test-Path $server -PathType Leaf)) {
		$result.reason = 'Configure server.executable with a local Vulkan-capable llama-server.exe path.'
		return $result
	}
	if ([string]::IsNullOrWhiteSpace($model) -or -not (Test-Path $model -PathType Leaf)) {
		$result.reason = 'Configure server.model with an existing local GGUF path.'
		return $result
	}
	try {
		$deviceText = (& $server --list-devices 2>&1 | Out-String)
	} catch {
		$result.reason = "llama-server device query failed: $($_.Exception.Message)"
		return $result
	}
	$result.devices = @($deviceText -split "`r?`n" | Where-Object { $_ -match 'Vulkan' } | ForEach-Object { $_.Trim() })
	if ($result.devices.Count -eq 0) {
		$result.reason = 'Configured llama-server does not expose a Vulkan device.'
		return $result
	}
	$result.status = 'ready'
	$result.reason = 'Local Vulkan llama.cpp server and configured model passed preflight.'
	return $result
}

$settings = Get-StackConfiguration
$paths = Get-StackPaths $settings
$preflight = Get-VulkanPreflight $settings

if ($Action -eq 'check') {
	Write-StackResult $preflight $(if ($preflight.status -eq 'ready') { 0 } else { 1 })
}

if ($Action -eq 'status') {
	$process = Get-StackProcess $paths
	$healthy = $null -ne $process -and (Test-StackHealth $preflight.endpoint)
	$preflight.process_id = if ($process) { $process.Id } else { $null }
	$preflight.health_ready = $healthy
	$preflight.stdout_log = $paths.Out
	$preflight.stderr_log = $paths.Err
	if ($healthy) {
		$preflight.status = 'running'
		$preflight.reason = 'Configured local Vulkan provider process is running and healthy.'
		Write-StackResult $preflight
	}
	if ($process) {
		$preflight.status = 'degraded'
		$preflight.reason = 'Provider process exists but the health endpoint is unavailable.'
		$preflight.error_tail = Get-StackErrorTail $paths
		Write-StackResult $preflight 1
	}
	if (Test-Path $paths.Pid) { Remove-Item $paths.Pid -Force }
	$preflight.status = if ($preflight.status -eq 'ready') { 'stopped' } else { $preflight.status }
	Write-StackResult $preflight 1
}

if ($Action -eq 'stop') {
	if (Test-Path $paths.Pid) {
		$pidValue = [int](Get-Content $paths.Pid -Raw)
		$process = Get-Process -Id $pidValue -ErrorAction SilentlyContinue
		if ($process) { Stop-Process -Id $pidValue -Force }
		Remove-Item $paths.Pid -Force
	}
	$preflight.status = 'stopped'
	$preflight.reason = 'Local provider process stopped; no model or configuration was removed.'
	Write-StackResult $preflight
}

if ($preflight.status -ne 'ready') {
	Write-StackResult $preflight 1
}
if (Test-Path $paths.Pid) {
	$existing = Get-StackProcess $paths
	if ($existing) {
		$healthy = Test-StackHealth $preflight.endpoint
		$preflight.status = if ($healthy) { 'running' } else { 'degraded' }
		$preflight.reason = if ($healthy) { 'Local Vulkan provider already running and healthy.' } else { 'Local Vulkan provider already exists but is not healthy.' }
		$preflight.process_id = $existing.Id
		$preflight.health_ready = $healthy
		Write-StackResult $preflight $(if ($healthy) { 0 } else { 1 })
	}
	Remove-Item $paths.Pid -Force
}

$arguments = @(
	'--model', [string]$settings.server.model,
	'--host', [string]$settings.server.host,
	'--port', [string]$settings.server.port,
	'--gpu-layers', [string]$settings.server.gpu_layers,
	'--ctx-size', [string]$settings.server.context_tokens,
	'--parallel', [string]$settings.server.parallel_slots
)
$startParams = @{
	FilePath = [string]$settings.server.executable
	ArgumentList = $arguments
	RedirectStandardOutput = $paths.Out
	RedirectStandardError = $paths.Err
	PassThru = $true
}
$isWindowsHost = ($env:OS -eq 'Windows_NT')
if (Get-Variable -Name IsWindows -ErrorAction SilentlyContinue) {
	$isWindowsHost = $IsWindows
}
if ($isWindowsHost) {
	$startParams.WindowStyle = 'Hidden'
}
$process = Start-Process @startParams
Set-Content -Path $paths.Pid -Value $process.Id -NoNewline
$preflight.process_id = $process.Id
$preflight.stdout_log = $paths.Out
$preflight.stderr_log = $paths.Err
$startupTimeout = if ($settings.lifecycle.startup_timeout_seconds) { [int]$settings.lifecycle.startup_timeout_seconds } else { 90 }
$pollMilliseconds = if ($settings.lifecycle.health_poll_milliseconds) { [int]$settings.lifecycle.health_poll_milliseconds } else { 500 }
$deadline = [DateTime]::UtcNow.AddSeconds($startupTimeout)
do {
	Start-Sleep -Milliseconds $pollMilliseconds
	$process.Refresh()
	if ($process.HasExited) {
		if (Test-Path $paths.Pid) { Remove-Item $paths.Pid -Force }
		$preflight.status = 'failed'
		$preflight.health_ready = $false
		$preflight.exit_code = $process.ExitCode
		$preflight.error_tail = Get-StackErrorTail $paths
		$preflight.reason = "Local Vulkan provider exited during startup with code $($process.ExitCode)."
		Write-StackResult $preflight 1
	}
	if (Test-StackHealth $preflight.endpoint) {
		$preflight.status = 'started'
		$preflight.health_ready = $true
		$preflight.reason = "Local Vulkan provider is healthy with process $($process.Id). CPU policy, validation, and journaling remain authoritative."
		Write-StackResult $preflight
	}
} while ([DateTime]::UtcNow -lt $deadline)

$preflight.status = 'starting'
$preflight.health_ready = $false
$preflight.error_tail = Get-StackErrorTail $paths
$preflight.reason = "Provider process $($process.Id) is still alive but did not become healthy within $startupTimeout seconds."
Write-StackResult $preflight 1
