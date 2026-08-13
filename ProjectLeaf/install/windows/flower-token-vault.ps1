#Requires -Version 7.0
$ErrorActionPreference = 'Stop'
$VaultDir = "$env:USERPROFILE\.cache\huggingface"
$Exe = 'C:\R\LeafOS0.2.2\ProjectLeaf\install\windows\token_vault.exe'
$Src = 'C:\R\LeafOS0.2.2\ProjectLeaf\install\windows\token_vault.c'

function Build-Vault {
	New-Item -ItemType Directory -Path $VaultDir -Force | Out-Null
	$gcc = Get-Command gcc.exe -ErrorAction SilentlyContinue
	if (-not $gcc) { throw 'gcc.exe not found. Install MSYS2 UCRT64 gcc.' }
	& $gcc.Source $Src -o $Exe -lcrypt32
	if ($LASTEXITCODE -ne 0) { throw 'token_vault compile failed.' }
	Write-Host "[+] Compiled $Exe"
}

function Save-Tokens {
	if (-not (Test-Path $Exe)) { Build-Vault }
	& $Exe save
}

function Get-Token {
	param([ValidateSet('read','write')][string]$Kind)
	if (-not (Test-Path $Exe)) { throw "Vault not built. Run Save-Tokens first." }
	& $Exe get $Kind
}

switch ($args[0]) {
	'build'   { Build-Vault }
	'save'    { Save-Tokens }
	'get'     { Get-Token -Kind $args[1] }
	default   { Write-Host "Usage: flower-token-vault.ps1 [build|save|get read|get write]" }
}
