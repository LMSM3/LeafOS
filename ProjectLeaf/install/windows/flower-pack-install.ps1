# leafos-flower-pack-install.ps1
# Windows bootstrap installer for the LeafOS flower-pack release.
# Usage:   pwsh -NoProfile -ExecutionPolicy Bypass -File .\flower-pack-install.ps1
# Override release host: $env:LEAF_RELEASE_HOST = 'https://releases.example.com'
# Override version:      $env:LEAF_FLOWER_PACK_VER = '1.2.0'

$ErrorActionPreference = 'Stop'

$Ver  = $env:LEAF_FLOWER_PACK_VER
if (-not $Ver) { $Ver = '1.2.0' }

$Base = $env:LEAF_RELEASE_HOST
if (-not $Base) { $Base = 'https://releases.leafos.local' }

$Root = Join-Path 'C:' "flower-pack-$Ver"
$Zip  = Join-Path $env:TEMP "flower-pack-$Ver.zip"
$Sum  = Join-Path $env:TEMP "flower-pack-$Ver.zip.sha256"

function Cleanup {
	Remove-Item $Zip -Force -ErrorAction SilentlyContinue
	Remove-Item $Sum -Force -ErrorAction SilentlyContinue
}

try {
	Write-Host "Downloading flower-pack $Ver from $Base ..."
	Invoke-WebRequest "$Base/flower-pack-$Ver.zip" -OutFile $Zip
	Invoke-WebRequest "$Base/flower-pack-$Ver.zip.sha256" -OutFile $Sum

	$Expected = ((Get-Content $Sum -Raw) -split '\s+')[0].ToUpper()
	$Actual   = (Get-FileHash $Zip -Algorithm SHA256).Hash.ToUpper()

	if ($Actual -ne $Expected) {
		throw "SHA-256 mismatch: expected $Expected, got $Actual"
	}

	Write-Host "SHA-256 verified. Installing to $Root ..."
	Remove-Item $Root -Recurse -Force -ErrorAction SilentlyContinue
	Expand-Archive $Zip -DestinationPath $Root -Force

	# Flatten the common inner directory produced by some archive tools.
	$Inner = Join-Path $Root "flower-pack-$Ver"
	if (Test-Path $Inner) {
		Copy-Item "$Inner\*" $Root -Recurse -Force
		Get-ChildItem $Inner -Force -Hidden | Copy-Item -Destination $Root -Recurse -Force
		Remove-Item $Inner -Recurse -Force
	}

	Set-Location $Root
	Get-ChildItem -Recurse -File | Unblock-File

	if (Test-Path '.\repair-install.ps1') {
		pwsh -NoProfile -ExecutionPolicy Bypass -File '.\repair-install.ps1'
	} else {
		Write-Warning 'repair-install.ps1 not found; skipping repair step.'
	}

	Write-Host "flower-pack $Ver installed at $Root"
} finally {
	Cleanup
}
