#!/usr/bin/env pwsh
<#
LeafOS on-rails interactive model installer.

This is the guided, menu-driven installer. It attaches to the same backend as
real-models.ps1 and models-install:

  plan (or plan-pack) -> resolve -> download/resume -> verify

Safe by default: it prompts before resolving and again before downloading.
Use -Yes to run unattended once a source is chosen.

Examples:
  .\install-onrails.ps1                       # interactive wizard
  .\install-onrails.ps1 -Pack ..\config\packs\viola-nocturne.json -Yes
  .\install-onrails.ps1 -Profile runtime-default -Yes
#>

[CmdletBinding()]
param(
	[string]$Profile = '',
	[string]$Pack = '',
	[switch]$Yes,
	[switch]$PlanOnly,
	[switch]$NonInteractive,
	[switch]$NoAnimation,
	[string]$ModelDir = '',
	[string]$ReportDir = ''
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$Root = Resolve-Path (Join-Path $PSScriptRoot '..')
$TaskPack = Join-Path $Root 'ProjectLeaf\leafos_taskpack'
$Installer = Join-Path $Root 'ProjectLeaf\leaf_model_installer'
$CatalogPath = Join-Path $Installer 'leaf_models\model_catalog.json'
$PackGlob = Join-Path $TaskPack 'config\packs\*.json'
$DirectDownloader = Join-Path $Root '_download_direct_from_resolved.py'

if (-not $ReportDir) {
	$ReportDir = Join-Path $PSScriptRoot ('reports\install-onrails-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
}
$null = New-Item -ItemType Directory -Force -Path $ReportDir
$LogPath = Join-Path $ReportDir 'install-onrails.log'

function Write-InstallLog {
	param([string]$Message)
	Add-Content -LiteralPath $LogPath -Value ("[{0}] {1}" -f (Get-Date -Format o), $Message) -Encoding UTF8
}

function Resolve-LeafModelDir {
	param([string]$Requested)
	if ($Requested) { return [pscustomobject]@{ Path = $Requested; Reason = 'explicit -ModelDir' } }
	if ($env:LEAF_MODEL_DIR) { return [pscustomobject]@{ Path = $env:LEAF_MODEL_DIR; Reason = 'LEAF_MODEL_DIR' } }
	$legacy = Join-Path $Installer 'models'
	$found = Get-ChildItem -LiteralPath $legacy -Recurse -File -Filter '*.gguf' -ErrorAction SilentlyContinue | Select-Object -First 1
	if ($found) { return [pscustomobject]@{ Path = $legacy; Reason = 'detected existing GGUF cache' } }
	return [pscustomobject]@{ Path = (Join-Path $HOME '.leaf\models'); Reason = 'catalog default' }
}

function Resolve-LeafPython {
	$candidates = @(
		(Join-Path $Installer '.venv\Scripts\python.exe'),
		(Join-Path $Installer '.venv\bin\python.exe')
	)
	$python = @($candidates | Where-Object { Test-Path $_ -PathType Leaf } | Select-Object -First 1)[0]
	if (-not $python) {
		$python = if (Get-Command python -ErrorAction SilentlyContinue) { (Get-Command python).Source } else { $null }
	}
	if (-not $python) { throw 'Python not found.' }
	return $python
}

function Invoke-InstallCli {
	param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Args)
	$python = Resolve-LeafPython
	$old = $env:PYTHONPATH
	try {
		$env:PYTHONPATH = if ($old) { "$Installer;$old" } else { "$Installer" }
		& $python -B -m leaf_models.install_cli @Args 2>&1 | ForEach-Object {
			Write-Host $_
			Write-InstallLog $_
		}
		if ($LASTEXITCODE -ne 0) { throw "install_cli failed with exit code ${LASTEXITCODE}: $($Args -join ' ')" }
	}
	finally {
		$env:PYTHONPATH = $old
	}
}

function Write-LeafHeader {
	Clear-Host
	Write-Host ''
	Write-Host '      .-.-.       LeafOS On-Rails Model Installer' -ForegroundColor Green
	Write-Host '   .-''  |  ''-.    profile or pack -> resolve -> apply -> verify' -ForegroundColor DarkGreen
	Write-Host '  /  .--+--.  \   Windows / Hugging Face / GGUF' -ForegroundColor Cyan
	Write-Host '      \ | /' -ForegroundColor DarkGreen
	Write-Host '       \|/' -ForegroundColor Green
	Write-Host ''
}

function Show-MethodAnimation {
	param([Parameter(Mandatory)][string]$Message)
	if ($NoAnimation) {
		Write-Host "  -> $Message"
		return
	}
	$frames = @('[.   ]', '[..  ]', '[... ]', '[....]', '[ ...]', '[  ..]', '[   .]')
	foreach ($frame in $frames) {
		Write-Host "`r  $frame $Message" -NoNewline -ForegroundColor Cyan
		Start-Sleep -Milliseconds 70
	}
	Write-Host "`r  [ OK ] $Message" -ForegroundColor Green
}

function Select-MenuItem {
	param(
		[Parameter(Mandatory)][string]$Title,
		[Parameter(Mandatory)][object[]]$Items,
		[Parameter(Mandatory)][scriptblock]$Label
	)
	Write-Host ''
	Write-Host $Title -ForegroundColor Yellow
	for ($i = 0; $i -lt $Items.Count; $i++) {
		Write-Host ("  [{0}] {1}" -f ($i + 1), (& $Label $Items[$i]))
	}
	while ($true) {
		$raw = Read-Host "Select 1-$($Items.Count)"
		$number = 0
		if ([int]::TryParse($raw, [ref]$number) -and $number -ge 1 -and $number -le $Items.Count) {
			return $Items[$number - 1]
		}
		Write-Host 'Invalid selection.' -ForegroundColor Red
	}
}

function Get-ProfileSources {
	if (-not (Test-Path $CatalogPath -PathType Leaf)) { return @() }
	$catalog = Get-Content -Raw -LiteralPath $CatalogPath | ConvertFrom-Json -AsHashtable
	$modelsBySlot = @{}
	foreach ($model in $catalog['models']) {
		$modelsBySlot[$model['slot']] = $model
	}
	$sources = foreach ($profileName in $catalog['profiles'].Keys) {
		$profile = $catalog['profiles'][$profileName]
		$gib = 0.0
		foreach ($slot in $profile['slots']) {
			$model = $modelsBySlot[$slot]
			if (-not $model) { continue }
			$quant = $model['default_quant']
			$variant = $model['variants'][$quant]
			if ($variant) { $gib += $variant['estimated_bytes'] / 1GB }
		}
		[pscustomobject]@{
			Type = 'Profile'
			Name = $profileName
			Path = $null
			PackPath = $null
			EstimatedGiB = $gib
		}
	}
	return @($sources | Sort-Object Name)
}

function Get-PackSources {
	$packFiles = Get-ChildItem -Path $PackGlob -Filter '*.json' -ErrorAction SilentlyContinue
	$sources = foreach ($file in $packFiles) {
		try {
			$json = Get-Content -Raw -LiteralPath $file.FullName | ConvertFrom-Json
			$items = @($json.install.items)
			$gib = 0.0
			if ($items.Count -gt 0 -and (Test-Path $CatalogPath -PathType Leaf)) {
				$catalog = Get-Content -Raw -LiteralPath $CatalogPath | ConvertFrom-Json -AsHashtable
				$modelsByKey = @{}
				foreach ($model in $catalog['models']) { $modelsByKey[$model['key']] = $model }
				$seen = @{}
				foreach ($item in $items) {
					$model = $modelsByKey[$item['catalog_key']]
					if (-not $model) { continue }
					$variant = $model['variants'][$item['quant']]
					if (-not $variant) { continue }
					$dedupeKey = "$($item['catalog_key'])|$($item['quant'])"
					if ($seen.ContainsKey($dedupeKey)) { continue }
					$seen[$dedupeKey] = $true
					$gib += $variant['estimated_bytes'] / 1GB
				}
			}
			[pscustomobject]@{
				Type = 'Pack'
				Name = $json.display_name
				Path = $file.FullName
				PackPath = $file.FullName
				EstimatedGiB = $gib
			}
		}
		catch {
			Write-Host "WARN: could not read pack $($file.FullName): $_" -ForegroundColor DarkYellow
		}
	}
	return @($sources | Sort-Object Name)
}

function Get-InstallSources {
	$profileSources = Get-ProfileSources
	$packSources = Get-PackSources
	return @($packSources) + @($profileSources)
}

function Format-Estimate {
	param([double]$GiB)
	if ($GiB -le 0) { return 'unknown size' }
	return ('{0:N1} GiB' -f $GiB)
}

function Request-Confirmation {
	param([string]$Prompt, [string]$Keyword)
	if ($Yes) { return $true }
	if ($NonInteractive) { return $false }
	$answer = Read-Host $Prompt
	return ($answer -ceq $Keyword)
}

$ModelSelection = Resolve-LeafModelDir -Requested $ModelDir
$ModelDir = $ModelSelection.Path

Write-LeafHeader
Write-Host "model dir: $ModelDir" -ForegroundColor Cyan
Write-Host "reason:    $($ModelSelection.Reason)" -ForegroundColor DarkGray
Write-Host ''

$source = $null
if ($Pack) {
	if (-not (Test-Path $Pack -PathType Leaf)) { throw "Pack not found: $Pack" }
	$source = [pscustomobject]@{ Type = 'Pack'; Name = ([System.IO.Path]::GetFileNameWithoutExtension($Pack)); Path = (Resolve-Path $Pack).Path; PackPath = (Resolve-Path $Pack).Path; EstimatedGiB = 0 }
}
elseif ($Profile) {
	$source = [pscustomobject]@{ Type = 'Profile'; Name = $Profile; Path = $null; PackPath = $null; EstimatedGiB = 0 }
}
else {
	$sources = Get-InstallSources
	if ($sources.Count -eq 0) { throw 'No install sources found. Ensure the catalog and packs exist.' }
	$source = Select-MenuItem -Title 'Choose a model installation source' -Items $sources -Label {
		param($x)
		$label = if ($x.Type -eq 'Pack') { 'pack ' } else { 'profile ' }
		"$label : $($x.Name)  ($(Format-Estimate -GiB $x.EstimatedGiB))"
	}
	Write-LeafHeader
}

$timestamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$safeName = ($source.Name -replace '[^A-Za-z0-9._-]', '_')
$Plan = Join-Path $ReportDir "leaf-$safeName-plan.json"
$Resolved = Join-Path $ReportDir "leaf-$safeName-resolved.json"
$VerifyReport = Join-Path $ReportDir "leaf-$safeName-verify.json"

Write-Host "Source: $($source.Type) - $($source.Name)" -ForegroundColor Cyan

# Optionally re-estimate from catalog for packs/profiles selected by parameter.
if ($source.EstimatedGiB -eq 0) {
	$matched = @(Get-InstallSources | Where-Object { $_.Type -eq $source.Type -and $_.Name -eq $source.Name })
	if ($matched.Count -gt 0) { $source = $matched[0] }
}

Show-MethodAnimation "Writing offline plan"
if ($source.Type -eq 'Pack') {
	Invoke-InstallCli plan-pack $source.PackPath --dest $ModelDir --out $Plan
}
else {
	Invoke-InstallCli plan --profile $source.Name --dest $ModelDir --out $Plan
}
Write-Host "Plan file: $Plan" -ForegroundColor DarkGray

$planJson = Get-Content -Raw -LiteralPath $Plan | ConvertFrom-Json
$estimateBytes = 0
if ($planJson.items) {
	foreach ($item in $planJson.items) {
		$estimateBytes += ($item.estimated_bytes | Measure-Object -Sum).Sum
	}
}
Write-Host ''
Write-Host 'PLAN SUMMARY' -ForegroundColor Magenta
Write-Host "  Items:       $($planJson.items.Count)"
Write-Host "  Destination: $ModelDir"
Write-Host "  Estimate:    $(Format-Estimate -GiB ($estimateBytes / 1GB))"
Write-Host ''

if ($PlanOnly) {
	Write-Host 'Plan-only mode; nothing was downloaded.' -ForegroundColor Yellow
	exit 0
}

if (-not (Request-Confirmation -Prompt 'Type PREPARE to resolve exact files (metadata only)' -Keyword 'PREPARE')) {
	Write-Host 'Cancelled without network resolution.' -ForegroundColor Yellow
	exit 0
}

Show-MethodAnimation 'Resolving exact files'
Invoke-InstallCli resolve $Plan --out $Resolved
Write-Host "Resolved plan: $Resolved" -ForegroundColor DarkGray

$resolvedJson = Get-Content -Raw -LiteralPath $Resolved | ConvertFrom-Json
$resolvedBytes = 0
foreach ($item in $resolvedJson.items) {
	foreach ($file in $item.expected_files) { $resolvedBytes += $file.bytes }
}
Write-Host "Resolved total: $(Format-Estimate -GiB ($resolvedBytes / 1GB))" -ForegroundColor Cyan

if (-not (Request-Confirmation -Prompt 'Type DOWNLOAD to begin the resumable transfer' -Keyword 'DOWNLOAD')) {
	Write-Host 'Download cancelled. Plan and resolved plan were retained.' -ForegroundColor Yellow
	exit 0
}

if (-not (Test-Path $DirectDownloader -PathType Leaf)) {
	throw "Direct downloader not found: $DirectDownloader"
}

$python = Resolve-LeafPython
Show-MethodAnimation 'Starting resumable download engine'
Write-Host ''
Write-Host '------------------------------------------------------------' -ForegroundColor DarkGray

$downloadArgs = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command',
	("& '{0}' -u '{1}' '{2}'" -f $python, $DirectDownloader, $Resolved))
$proc = Start-Process -FilePath pwsh -ArgumentList $downloadArgs -NoNewWindow -PassThru -Wait

Write-Host '------------------------------------------------------------' -ForegroundColor DarkGray

if ($proc.ExitCode -ne 0) {
	throw "Download process exited with code $($proc.ExitCode). Re-run the same command to resume."
}

Show-MethodAnimation 'Verifying downloaded artifacts'
Invoke-InstallCli verify $Resolved --out $VerifyReport
Write-Host "Verification report: $VerifyReport" -ForegroundColor DarkGray

$shards = @(Get-ChildItem -LiteralPath $ModelDir -Recurse -File -Filter '*.gguf' -ErrorAction SilentlyContinue | Sort-Object FullName)
$manifest = [ordered]@{
	schema = 'leafos.model-install.v1'
	installed_at_utc = (Get-Date -Format o)
	type = $source.Type
	source = $source.Name
	source_path = $source.Path
	destination_root = $ModelDir
	plan = $Plan
	resolved_plan = $Resolved
	verification_report = $VerifyReport
	first_shard = if ($shards.Count -gt 0) { $shards[0].FullName } else { $null }
	shard_count = $shards.Count
	total_bytes = [uint64](($shards | Measure-Object Length -Sum).Sum)
}
$ManifestPath = Join-Path $ReportDir 'leafos-install-manifest.json'
$manifest | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $ManifestPath -Encoding UTF8

Write-Host ''
Write-Host 'INSTALL COMPLETE' -ForegroundColor Green
Write-Host "  Shards:   $($shards.Count)"
Write-Host "  Manifest: $ManifestPath"
Write-Host ''
