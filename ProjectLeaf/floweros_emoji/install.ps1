param(
    [string]$Scope = 'CurrentUser',
    [switch]$NoImport
)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$ModuleName = 'FlowerOSEmoji'

if ($Scope -ne 'CurrentUser') {
    throw "Only CurrentUser installation is supported by this portable installer."
}

$moduleRoot = if ($PSVersionTable.PSEdition -eq 'Core') {
    Join-Path $HOME 'Documents\PowerShell\Modules'
} else {
    Join-Path $HOME 'Documents\WindowsPowerShell\Modules'
}

$target = Join-Path $moduleRoot $ModuleName
New-Item -ItemType Directory -Force -Path $target | Out-Null
Copy-Item -LiteralPath (Join-Path $Root 'FlowerOSEmoji\FlowerOSEmoji.psd1') -Destination $target -Force
Copy-Item -LiteralPath (Join-Path $Root 'FlowerOSEmoji\FlowerOSEmoji.psm1') -Destination $target -Force

$dataTarget = Join-Path $target 'data'
New-Item -ItemType Directory -Force -Path $dataTarget | Out-Null
Copy-Item -LiteralPath (Join-Path $Root 'data\emoji.json') -Destination $dataTarget -Force
if (Test-Path -LiteralPath (Join-Path $Root 'data\emoji-test.txt')) {
    Copy-Item -LiteralPath (Join-Path $Root 'data\emoji-test.txt') -Destination $dataTarget -Force
}

if (-not $NoImport) {
    Import-Module $ModuleName -Force
    Get-EmojiDataInfo
}

Write-Host "Installed FlowerOSEmoji. Try: Get-Emoji -Emoji '🌸'" -ForegroundColor Green
