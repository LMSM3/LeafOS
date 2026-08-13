# FlowerOSEmoji

FlowerOSEmoji adds PowerShell emoji lookup commands backed by the official
Unicode emoji test data.

The included cache was generated from:

```text
https://www.unicode.org/Public/emoji/latest/emoji-test.txt
```

## Commands

```powershell
# Get detailed info for a specific on-brand emoji
Get-Emoji -Emoji '🌸'

# Search by Unicode hex code point
Get-Emoji -HexCodePoint '1F338'

# Search by decimal code point
Get-Emoji -Decimal 127800

# Find by shortcode
Get-Emoji -ShortCode ':herb:'

# Search by keyword
Get-Emoji -SearchTerm 'fork'

# List all emojis in a group or subgroup
Get-Emoji -Group 'Food & Drink'
Get-Emoji -SubGroup 'food-vegetable'

# Retrieve the complete emoji list
Get-AllEmoji
```

## Install

From this folder:

```powershell
.\install.ps1
Import-Module FlowerOSEmoji
```

Portable import without installation:

```powershell
Import-Module .\FlowerOSEmoji\FlowerOSEmoji.psd1
```

## Update the Unicode Cache

```powershell
Import-Module .\FlowerOSEmoji\FlowerOSEmoji.psd1 -Force
Update-EmojiCache
Get-EmojiDataInfo
```

## Notes

`ShortCode` values are generated from the Unicode CLDR names. The module favors
official Unicode names over platform-specific aliases.

`Get-AllEmoji` returns the complete parsed Unicode list by default, including
component records such as skin tone modifiers. Add `-ExcludeComponents` when you
want a keyboard-style list.
