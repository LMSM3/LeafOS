Import-Module (Join-Path $PSScriptRoot 'FlowerOSEmoji\FlowerOSEmoji.psd1') -Force

'# Get detailed info for a specific on-brand emoji'
Get-Emoji -Emoji '🌸' | Format-List

'# Search by Unicode hex code point'
Get-Emoji -HexCodePoint '1F338' | Format-Table Emoji, Name, ShortCode, HexCodePoint, Group, SubGroup

'# Search by decimal code point'
Get-Emoji -Decimal 127800 | Format-Table Emoji, Name, ShortCode, HexCodePoint, Group, SubGroup

'# Find by shortcode'
Get-Emoji -ShortCode ':herb:' | Format-Table Emoji, Name, ShortCode, HexCodePoint

'# Search by keyword'
Get-Emoji -SearchTerm 'fork' | Format-Table Emoji, Name, ShortCode, Group, SubGroup

'# List all emojis in a group or subgroup'
Get-Emoji -Group 'Food & Drink' | Select-Object -First 12 | Format-Table Emoji, Name, ShortCode, SubGroup
Get-Emoji -SubGroup 'food-vegetable' | Format-Table Emoji, Name, ShortCode

'# Retrieve the complete emoji list'
(Get-AllEmoji | Measure-Object).Count
