# WO-004-C-02 -- export.ps1
# PowerShell export wrapper for the WO-004-C wakeup module.
# User-facing intent: agent-export WO-004-C
param([string]$WorkOrder = "WO-004-C")
$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot
$stamp = Get-Date -Format "yyyy-MM-dd_HH-mm-ss"
$out = "exports"
$stage = ".leaf_export_staging"
New-Item -ItemType Directory -Force -Path $out, $stage | Out-Null
Remove-Item "$stage\*" -Recurse -Force -ErrorAction SilentlyContinue
$items = @("wakeup.py","wakeup.sh","tickers.txt","README.md","tests","docs","agent_node.json","symbolic_training.jsonl","completion_map.json","completion_tree.txt","runs\latest\wakeup_result.json","runs\wakeup_log.csv")
foreach ($p in $items) {
  if (Test-Path $p) { Copy-Item $p -Destination $stage -Recurse -Force }
}
$zip = Join-Path $out ("{0}_wakeup_{1}_verified.zip" -f $WorkOrder, $stamp)
if (Test-Path $zip) { Remove-Item $zip -Force }
Compress-Archive -Path "$stage\*" -DestinationPath $zip -Force
Remove-Item $stage -Recurse -Force
Write-Host "export complete: $zip"
