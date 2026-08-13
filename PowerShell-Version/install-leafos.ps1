#!/usr/bin/env pwsh
<#
.SYNOPSIS
  Safe LeafOS user-space application installer.

.DESCRIPTION
  Plans by default. Apply copies only the LeafOS application into a detached
  user prefix, creates PowerShell and CMD launchers, and writes an integrity
  manifest. It never downloads models, starts a provider, edits profiles, or
  changes a runtime route. User PATH changes require -AddToUserPath.
#>

[CmdletBinding()]
param(
	[ValidateSet('plan', 'apply', 'verify')]
	[string]$Action = 'plan',
	[string]$Prefix = (Join-Path $env:LOCALAPPDATA 'LeafOS'),
	[switch]$AddToUserPath,
	[switch]$Force
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$SourceRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$InstallRoot = Join-Path $Prefix 'app'
$BinRoot = Join-Path $Prefix 'bin'
$ManifestPath = Join-Path $Prefix 'install-manifest.json'
$IncludedRoots = @('Bash-Version', 'PowerShell-Version', 'ProjectLeaf', 'markdowns', 'procedures')
$IncludedFiles = @(
	'VERSION',
	'leafos.ps1',
	'leafos.sh',
	'leafos.root.json',
	'Validate-RootContract.ps1',
	'LEAFOS-CONTINUAL-BLOOM-PRIMARY-REFERENCE.md',
	'LEAFOS-CONTINUAL-BLOOM-PRIMARY-REFERENCE.formatless.tex'
)
$ExcludedNames = @('.git', '.vs', '.venv', '__pycache__', '.pytest_cache', '.mypy_cache', 'reports', 'tmp', 'build', 'dist', 'models', 'cache', 'caches', 'artifacts', 'runs', 'logs', 'output', 'sandbox', 'tests')
$RequiredLauncherNames = @('leafos.ps1', 'leaf.ps1', 'flower.ps1', 'leafos.cmd', 'leaf.cmd', 'flower.cmd')
$InstallSafety = @(
	'no model download or metadata resolve',
	'no provider start or runtime-route change',
	'no shell profile mutation',
	$(if ($AddToUserPath) { 'user PATH update requested for apply' } else { 'no PATH mutation' }),
	'apply requires explicit action'
)

function Test-UserPathEntry {
	$userPath = [System.Environment]::GetEnvironmentVariable('Path', 'User')
	$wanted = $BinRoot.TrimEnd('\', '/')
	return [bool](@($userPath -split ';' | Where-Object {
		$_.Trim().TrimEnd('\', '/') -ieq $wanted
	}).Count)
}

function Add-LeafBinToUserPath {
	if (Test-UserPathEntry) { return $false }
	$userPath = [System.Environment]::GetEnvironmentVariable('Path', 'User')
	$nextPath = if ($userPath) { "$BinRoot;$userPath" } else { $BinRoot }
	[System.Environment]::SetEnvironmentVariable('Path', $nextPath, 'User')
	if (-not (($env:Path -split ';') | Where-Object {
		$_.Trim().TrimEnd('\', '/') -ieq $BinRoot.TrimEnd('\', '/')
	})) {
		$env:Path = "$BinRoot;$env:Path"
	}
	return $true
}

function Get-InstallFiles {
	Get-ChildItem -LiteralPath $SourceRoot -Recurse -File | Where-Object {
		$parts = $_.FullName.Substring($SourceRoot.Length).TrimStart('\', '/') -split '[\\/]'
		$included = ($parts.Count -eq 1 -and $parts[0] -in $IncludedFiles) -or
			($parts.Count -gt 1 -and $parts[0] -in $IncludedRoots)
		$included -and -not ($parts | Where-Object { $_ -in $ExcludedNames })
	}
}

function Get-InstallPlan {
	$files = @(Get-InstallFiles)
	[pscustomobject]@{
		schema = 'leafos.application-install.v1'
		action = $Action
		source_root = $SourceRoot
		prefix = $Prefix
		install_root = $InstallRoot
		bin_root = $BinRoot
		manifest = $ManifestPath
		file_count = $files.Count
		entrypoint = (Join-Path $BinRoot 'leafos.ps1')
		entrypoints = @($RequiredLauncherNames | ForEach-Object { Join-Path $BinRoot $_ })
		path_integration = $(if ($AddToUserPath) { 'add bin root to user PATH during apply' } else { 'print opt-in instructions only' })
		safety = $InstallSafety
	}
}

function Test-InstalledLeafOS {
	if (-not (Test-Path -LiteralPath $ManifestPath -PathType Leaf)) {
		throw "Install manifest not found: $ManifestPath"
	}
	$manifest = Get-Content -LiteralPath $ManifestPath -Raw | ConvertFrom-Json
	foreach ($item in @($manifest.files)) {
		$path = Join-Path $InstallRoot $item.path
		if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
			throw "Installed file missing: $($item.path)"
		}
		if ((Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash -ne $item.sha256) {
			throw "Installed file hash mismatch: $($item.path)"
		}
	}
	foreach ($name in $RequiredLauncherNames) {
		$entrypoint = Join-Path $BinRoot $name
		if (-not (Test-Path -LiteralPath $entrypoint -PathType Leaf)) {
			throw "LeafOS launcher missing: $entrypoint"
		}
	}
	[pscustomobject]@{
		verified = $true
		file_count = @($manifest.files).Count
		entrypoint = (Join-Path $BinRoot 'leafos.ps1')
		entrypoints = @($RequiredLauncherNames | ForEach-Object { Join-Path $BinRoot $_ })
		on_user_path = (Test-UserPathEntry)
	}
}

$plan = Get-InstallPlan
if ($Action -eq 'plan') {
	$plan | ConvertTo-Json -Depth 6
	exit 0
}

if ($Action -eq 'verify') {
	Test-InstalledLeafOS | ConvertTo-Json -Depth 4
	exit 0
}

if ((Test-Path -LiteralPath $InstallRoot) -and -not $Force) {
	throw "Install root already exists: $InstallRoot. Review with -Action plan, then use -Action apply -Force to replace it."
}

$null = New-Item -ItemType Directory -Force -Path $Prefix, $BinRoot
if (Test-Path -LiteralPath $InstallRoot) {
	Remove-Item -LiteralPath $InstallRoot -Recurse -Force
}
$null = New-Item -ItemType Directory -Force -Path $InstallRoot

$manifestFiles = foreach ($file in Get-InstallFiles) {
	$relative = $file.FullName.Substring($SourceRoot.Length).TrimStart('\', '/')
	$target = Join-Path $InstallRoot $relative
	$null = New-Item -ItemType Directory -Force -Path (Split-Path $target -Parent)
	Copy-Item -LiteralPath $file.FullName -Destination $target -Force
	[ordered]@{ path = $relative -replace '\\', '/'; sha256 = (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash }
}

$installedLeaf = Join-Path $InstallRoot 'PowerShell-Version\leaf.ps1'
if (-not (Test-Path -LiteralPath $installedLeaf -PathType Leaf)) {
	throw "Installed LeafOS entrypoint missing: $installedLeaf"
}
$installedLeafEscaped = $installedLeaf.Replace("'", "''")
$powerShellLauncher = @"
#!/usr/bin/env pwsh
& '$installedLeafEscaped' @args
exit `$LASTEXITCODE
"@
foreach ($name in @('leafos.ps1', 'leaf.ps1', 'flower.ps1')) {
	$powerShellLauncher | Set-Content -LiteralPath (Join-Path $BinRoot $name) -Encoding UTF8
}
$cmdLauncher = @'
@echo off
pwsh -NoProfile -File "%~dp0leafos.ps1" %*
exit /b %ERRORLEVEL%
'@
foreach ($name in @('leafos.cmd', 'leaf.cmd', 'flower.cmd')) {
	$cmdLauncher | Set-Content -LiteralPath (Join-Path $BinRoot $name) -Encoding ASCII
}
$launcher = Join-Path $BinRoot 'leafos.ps1'

$pathChanged = $false
if ($AddToUserPath) {
	$pathChanged = Add-LeafBinToUserPath
}

[ordered]@{
	schema = 'leafos.application-install.v1'
	installed_at = (Get-Date).ToUniversalTime().ToString('o')
	source_root = $SourceRoot
	prefix = $Prefix
	install_root = $InstallRoot
	launcher = $launcher
	launchers = @($RequiredLauncherNames)
	add_to_user_path = [bool]$AddToUserPath
	user_path_changed = [bool]$pathChanged
	safety = $plan.safety
	files = @($manifestFiles)
} | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $ManifestPath -Encoding UTF8

Test-InstalledLeafOS | Out-Null
Write-Host 'LeafOS application install complete.' -ForegroundColor Green
Write-Host "Launcher: $launcher"
Write-Host "Verify:   & '$PSCommandPath' -Action verify -Prefix '$Prefix'"
Write-Host "Run now:  & '$launcher' q"
if ($AddToUserPath) {
	Write-Host 'Quick command: leafos q' -ForegroundColor Cyan
	Write-Host 'The current process and user PATH now include the LeafOS bin directory.'
}
else {
	Write-Host 'Optional PATH integration:' -ForegroundColor Cyan
	Write-Host "  & '$PSCommandPath' -Action apply -Prefix '$Prefix' -Force -AddToUserPath"
	Write-Host "  or, for this shell only: `$env:Path = '$BinRoot;' + `$env:Path"
}
Write-Host 'Models, providers, runtime routes, and shell profiles were not modified.' -ForegroundColor Yellow
