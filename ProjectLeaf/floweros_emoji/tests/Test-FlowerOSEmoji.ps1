$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
Import-Module (Join-Path $Root 'FlowerOSEmoji\FlowerOSEmoji.psd1') -Force

$blossom = Get-Emoji -Emoji '🌸'
if (-not $blossom -or $blossom.HexCodePoint -ne '1F338') {
    throw 'Get-Emoji -Emoji failed for 🌸.'
}

$hex = Get-Emoji -HexCodePoint '1F338'
if (-not $hex -or $hex.Emoji -ne '🌸') {
    throw 'Get-Emoji -HexCodePoint failed for 1F338.'
}

$decimal = Get-Emoji -Decimal 127800
if (-not $decimal -or $decimal.Emoji -ne '🌸') {
    throw 'Get-Emoji -Decimal failed for 127800.'
}

$herb = Get-Emoji -ShortCode ':herb:'
if (-not $herb -or $herb.Emoji -ne '🌿') {
    throw 'Get-Emoji -ShortCode failed for :herb:.'
}

$fork = @(Get-Emoji -SearchTerm 'fork')
if ($fork.Count -lt 1) {
    throw 'Get-Emoji -SearchTerm failed for fork.'
}

$food = @(Get-Emoji -Group 'Food & Drink')
if ($food.Count -lt 1) {
    throw 'Get-Emoji -Group failed for Food & Drink.'
}

$veg = @(Get-Emoji -SubGroup 'food-vegetable')
if ($veg.Count -lt 1) {
    throw 'Get-Emoji -SubGroup failed for food-vegetable.'
}

$all = @(Get-AllEmoji)
if ($all.Count -lt 1000) {
    throw 'Get-AllEmoji returned too few records.'
}

Get-EmojiDataInfo | Format-List
Write-Host 'FlowerOSEmoji tests passed.' -ForegroundColor Green
