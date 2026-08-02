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

[pscustomobject]@{
	Status = 'passed'
	SchemaVersion = $metadata.schema_version
	RootContract = $metadata.root_contract
	PrimaryReference = $metadata.documentation.primary_reference
	Surfaces = @($metadata.surfaces.psobject.Properties.Name)
	SourceTree = $metadata.source_tree
} | ConvertTo-Json -Compress
