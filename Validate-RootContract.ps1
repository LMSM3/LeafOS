[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$root = $PSScriptRoot
$metadataPath = Join-Path $root 'leafos.root.json'
$metadata = Get-Content -LiteralPath $metadataPath -Raw | ConvertFrom-Json
$contractPath = Join-Path $root $metadata.root_contract

$requiredPaths = @(
	$metadata.documentation.primary_reference,
	$metadata.documentation.primary_reference_tex,
	$metadata.documentation.product_map,
	$metadata.documentation.usage,
	$metadata.documentation.installation,
	$metadata.documentation.root_contract,
	$metadata.surfaces.powershell.directory,
	$metadata.surfaces.bash.directory,
	$metadata.program.powershell,
	$metadata.program.bash,
	$metadata.program.implementation,
	$metadata.program.immutable_brand_manifest,
	$metadata.change_loop.ccis_cli,
	$metadata.change_loop.scientific_loop,
	$metadata.change_loop.typed_task_registry,
	$metadata.change_loop.series_index,
	$metadata.change_loop.next_work_order,
	'VERSION',
	'ProjectLeaf/leafos_taskpack/VERSION',
	$metadata.source_tree,
	$metadata.configuration_authorities.runtime,
	$metadata.configuration_authorities.providers
)

foreach ($relativePath in $requiredPaths) {
	$path = Join-Path $root $relativePath
	if (-not (Test-Path -LiteralPath $path)) {
		throw "Root contract target is missing: $relativePath"
	}
}

if (-not (Test-Path -LiteralPath $contractPath -PathType Leaf)) {
	throw 'ROOT_CONTRACT.md is missing.'
}

$rootVersion = (Get-Content -LiteralPath (Join-Path $root 'VERSION') -Raw).Trim()
$taskpackVersion = (Get-Content -LiteralPath (Join-Path $root 'ProjectLeaf\leafos_taskpack\VERSION') -Raw).Trim()
if ($rootVersion -notmatch '^\d+\.\d+\.\d+$') {
	throw "Root VERSION is not numeric semantic versioning: $rootVersion"
}
if ($rootVersion -ne $taskpackVersion -or $rootVersion -ne [string]$metadata.version) {
	throw "Version authorities disagree: root=$rootVersion taskpack=$taskpackVersion metadata=$($metadata.version)"
}
if ([version]$rootVersion -lt [version]'0.2.2') {
	throw 'LeafOS version must not be older than the normalized 0.2.2 baseline.'
}

$taskRegistryPath = Join-Path $root $metadata.change_loop.typed_task_registry
$taskRegistry = Get-Content -LiteralPath $taskRegistryPath -Raw | ConvertFrom-Json
$requiredLoopTaskTypes = @(
	'probe.llamacpp.capability',
	'eval.llamacpp.grammar',
	'eval.llamacpp.stream'
)
foreach ($taskType in $requiredLoopTaskTypes) {
	if (-not ($taskRegistry.entries | Where-Object { $_.task_type -eq $taskType -and $_.task_version -eq 1 })) {
		throw "Typed change-loop registry is missing: $taskType@1"
	}
}

$manifestPath = Join-Path $root $metadata.program.immutable_brand_manifest
$manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
if ($manifest.immutable -ne $true) {
	throw 'Brand asset manifest is not marked immutable.'
}
$assetPath = [IO.Path]::GetFullPath((Join-Path $root $manifest.path))
$rootPrefix = [IO.Path]::GetFullPath($root).TrimEnd(
	[IO.Path]::DirectorySeparatorChar,
	[IO.Path]::AltDirectorySeparatorChar
) + [IO.Path]::DirectorySeparatorChar
if (-not $assetPath.StartsWith($rootPrefix, [StringComparison]::OrdinalIgnoreCase)) {
	throw 'Immutable asset escapes the LeafOS root.'
}
if (-not (Test-Path -LiteralPath $assetPath -PathType Leaf)) {
	throw "Immutable asset is missing: $($manifest.path)"
}
$asset = Get-Item -LiteralPath $assetPath
$digest = (Get-FileHash -LiteralPath $assetPath -Algorithm SHA256).Hash
if ($digest -ne [string]$manifest.sha256 -or $asset.Length -ne [long]$manifest.bytes) {
	throw "Immutable asset verification failed: $($manifest.path)"
}
$readme = Get-Content -LiteralPath (Join-Path $root 'README.md') -Raw
if (-not $readme.Contains([string]$manifest.path) -or -not $readme.Contains('leafos-program:brand-asset:start')) {
	throw 'Root README does not reference the immutable asset.'
}

[pscustomobject]@{
	Status = 'passed'
	SchemaVersion = $metadata.schema_version
	Version = $rootVersion
	AssetVerified = $true
	RootContract = $metadata.root_contract
	PrimaryReference = $metadata.documentation.primary_reference
	Surfaces = @($metadata.surfaces.psobject.Properties.Name)
	SourceTree = $metadata.source_tree
	ChangeLoop = 'ccis'
} | ConvertTo-Json -Compress
