#Requires -Version 7.0
$ErrorActionPreference = 'Stop'
$Vault = 'C:\R\LeafOS0.2.2\ProjectLeaf\install\windows\flower-token-vault.ps1'
$Downloader = 'C:\R\LeafOS0.2.2\ProjectLeaf\install\windows\download-pack-hftransfer.py'

Write-Host '[+] Unlocking vault...'
$tok = pwsh -NoProfile -ExecutionPolicy Bypass -File $Vault get read | Select-Object -Last 1
Write-Host "[+] Got read token (len=$($tok.Length), start=$($tok.Substring(0,4)))"
Write-Host '[+] Starting Pack 1 download...'
& py -3.13 $Downloader --pack-id 1 --hf-token $tok --turbo
