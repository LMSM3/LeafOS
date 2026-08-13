param(
    [string]$Uri = 'https://www.unicode.org/Public/emoji/latest/emoji-test.txt'
)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$ModulePath = Join-Path $Root 'FlowerOSEmoji\FlowerOSEmoji.psd1'
$DataPath = Join-Path $Root 'data\emoji-test.txt'

Import-Module $ModulePath -Force
Update-EmojiCache -Uri $Uri -Destination $DataPath
