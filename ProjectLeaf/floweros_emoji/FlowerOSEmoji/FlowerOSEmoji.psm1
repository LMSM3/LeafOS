Set-StrictMode -Version Latest

$script:EmojiDataCache = $null
$script:EmojiDataInfo = $null
$script:LocalDataRoot = Join-Path $PSScriptRoot 'data'
$script:SiblingDataRoot = Join-Path $PSScriptRoot '..\data'
$script:DataRoot = if (Test-Path -LiteralPath $script:LocalDataRoot) { $script:LocalDataRoot } else { $script:SiblingDataRoot }
$script:DataPath = Join-Path $script:DataRoot 'emoji.json'
$script:RawDataPath = Join-Path $script:DataRoot 'emoji-test.txt'
$script:UnicodeEmojiLatestUrl = 'https://www.unicode.org/Public/emoji/latest/emoji-test.txt'

function ConvertTo-FlowerEmojiShortCode {
    param([Parameter(Mandatory)][string]$Name)

    $short = $Name.ToLowerInvariant()
    $short = $short -replace '&', ' and '
    $short = $short -replace '[^\p{L}\p{Nd}]+', '_'
    $short = $short.Trim('_')
    return ":${short}:"
}

function Normalize-FlowerEmojiHex {
    param([Parameter(Mandatory)][string]$HexCodePoint)

    $parts = $HexCodePoint -replace 'U\+', '' -replace '0x', '' -split '[\s,;_-]+'
    $normalized = foreach ($part in $parts) {
        if ([string]::IsNullOrWhiteSpace($part)) { continue }
        $part.Trim().ToUpperInvariant().PadLeft(4, '0')
    }
    return ($normalized -join ' ')
}

function ConvertFrom-FlowerEmojiTestLine {
    param(
        [Parameter(Mandatory)][string]$Line,
        [Parameter(Mandatory)][string]$Group,
        [Parameter(Mandatory)][string]$SubGroup,
        [Parameter(Mandatory)][string]$Version
    )

    if ($Line -notmatch '^\s*([0-9A-F ]+)\s*;\s*([^#]+?)\s*#\s*(\S+)\s+E([0-9.]+)\s+(.+?)\s*$') {
        return $null
    }

    $hex = Normalize-FlowerEmojiHex $Matches[1]
    $decimals = @()
    foreach ($part in ($hex -split ' ')) {
        $decimals += [Convert]::ToInt32($part, 16)
    }
    $name = $Matches[5].Trim()
    $shortCode = ConvertTo-FlowerEmojiShortCode $name
    $keywords = @(
        $name.ToLowerInvariant() -split '[^a-z0-9]+'
        $Group.ToLowerInvariant() -split '[^a-z0-9]+'
        $SubGroup.ToLowerInvariant() -split '[^a-z0-9]+'
    ) | Where-Object { $_ } | Select-Object -Unique

    [pscustomobject]@{
        Emoji = $Matches[3]
        Name = $name
        ShortCode = $shortCode
        HexCodePoint = $hex
        DecimalCodePoint = if ($decimals.Count -eq 1) { $decimals[0] } else { $null }
        DecimalCodePoints = $decimals
        Status = $Matches[2].Trim()
        Group = $Group
        SubGroup = $SubGroup
        EmojiVersion = "E$($Matches[4])"
        DataVersion = $Version
        Keywords = $keywords
    }
}

function Import-FlowerEmojiTestData {
    param([Parameter(Mandatory)][string]$Path)

    if (-not (Test-Path -LiteralPath $Path)) {
        throw "Emoji source file not found: $Path"
    }

    $version = 'unknown'
    $group = ''
    $subGroup = ''
    $items = New-Object System.Collections.Generic.List[object]

    foreach ($line in [System.IO.File]::ReadLines((Resolve-Path -LiteralPath $Path))) {
        if ($line -match '^#\s*Version:\s*(.+?)\s*$') {
            $version = $Matches[1].Trim()
            continue
        }
        if ($line -match '^#\s*group:\s*(.+?)\s*$') {
            $group = $Matches[1].Trim()
            continue
        }
        if ($line -match '^#\s*subgroup:\s*(.+?)\s*$') {
            $subGroup = $Matches[1].Trim()
            continue
        }
        if ($line -notmatch '^\s*[0-9A-F]') {
            continue
        }
        $item = ConvertFrom-FlowerEmojiTestLine -Line $line -Group $group -SubGroup $subGroup -Version $version
        if ($null -ne $item) {
            $items.Add($item)
        }
    }

    [pscustomobject]@{
        Source = $script:UnicodeEmojiLatestUrl
        Version = $version
        GeneratedAt = (Get-Date).ToString('s')
        Count = $items.Count
        Emoji = $items
    }
}

function Load-FlowerEmojiData {
    if ($null -ne $script:EmojiDataCache) {
        return $script:EmojiDataCache
    }

    if (-not (Test-Path -LiteralPath $script:DataPath)) {
        if (Test-Path -LiteralPath $script:RawDataPath) {
            $parsed = Import-FlowerEmojiTestData -Path $script:RawDataPath
            $script:EmojiDataInfo = $parsed | Select-Object Source, Version, GeneratedAt, Count
            $script:EmojiDataCache = $parsed.Emoji.ToArray()
            return $script:EmojiDataCache
        }
        throw "Emoji data was not found. Run Update-EmojiCache or reinstall FlowerOSEmoji."
    }

    $json = Get-Content -LiteralPath $script:DataPath -Raw -Encoding UTF8 | ConvertFrom-Json
    $script:EmojiDataInfo = $json | Select-Object Source, Version, GeneratedAt, Count
    $script:EmojiDataCache = $json.Emoji
    return $script:EmojiDataCache
}

function Select-FlowerEmojiStatus {
    param(
        [Parameter(ValueFromPipeline)][object]$InputObject,
        [switch]$FullyQualifiedOnly,
        [switch]$ExcludeComponents
    )
    process {
        if ($FullyQualifiedOnly -and $InputObject.Status -ne 'fully-qualified') {
            return
        }
        if ($ExcludeComponents -and $InputObject.Status -eq 'component') {
            return
        }
        $InputObject
    }
}

function Get-AllEmoji {
    [CmdletBinding()]
    param(
        [string]$Group,
        [string]$SubGroup,
        [ValidateSet('component', 'fully-qualified', 'minimally-qualified', 'unqualified')]
        [string]$Status,
        [switch]$FullyQualifiedOnly,
        [switch]$ExcludeComponents
    )

    $data = Load-FlowerEmojiData
    $result = $data
    if ($Group) {
        $result = $result | Where-Object { $_.Group -like "*$Group*" }
    }
    if ($SubGroup) {
        $result = $result | Where-Object { $_.SubGroup -like "*$SubGroup*" }
    }
    if ($Status) {
        $result = $result | Where-Object { $_.Status -eq $Status }
    }
    $result | Select-FlowerEmojiStatus -FullyQualifiedOnly:$FullyQualifiedOnly -ExcludeComponents:$ExcludeComponents
}

function Get-Emoji {
    [CmdletBinding(DefaultParameterSetName = 'Emoji')]
    param(
        [Parameter(ParameterSetName = 'Emoji', Position = 0)]
        [string]$Emoji,

        [Parameter(ParameterSetName = 'HexCodePoint')]
        [string]$HexCodePoint,

        [Parameter(ParameterSetName = 'Decimal')]
        [int[]]$Decimal,

        [Parameter(ParameterSetName = 'ShortCode')]
        [string]$ShortCode,

        [Parameter(ParameterSetName = 'SearchTerm')]
        [string]$SearchTerm,

        [Parameter(ParameterSetName = 'Group')]
        [string]$Group,

        [Parameter(ParameterSetName = 'SubGroup')]
        [string]$SubGroup,

        [ValidateSet('component', 'fully-qualified', 'minimally-qualified', 'unqualified')]
        [string]$Status,

        [switch]$FullyQualifiedOnly,
        [switch]$ExcludeComponents
    )

    $allParams = @{}
    if ($PSBoundParameters.ContainsKey('Status')) { $allParams.Status = $Status }
    if ($FullyQualifiedOnly) { $allParams.FullyQualifiedOnly = $true }
    if ($ExcludeComponents) { $allParams.ExcludeComponents = $true }
    $data = Get-AllEmoji @allParams

    switch ($PSCmdlet.ParameterSetName) {
        'Emoji' {
            if ([string]::IsNullOrEmpty($Emoji)) { return $data }
            return $data | Where-Object { $_.Emoji -eq $Emoji }
        }
        'HexCodePoint' {
            $hex = Normalize-FlowerEmojiHex $HexCodePoint
            return $data | Where-Object { $_.HexCodePoint -eq $hex }
        }
        'Decimal' {
            $decimalText = ($Decimal -join ',')
            return $data | Where-Object { ($_.DecimalCodePoints -join ',') -eq $decimalText }
        }
        'ShortCode' {
            $normalized = $ShortCode.Trim()
            if (-not $normalized.StartsWith(':')) { $normalized = ":$normalized" }
            if (-not $normalized.EndsWith(':')) { $normalized = "${normalized}:" }
            return $data | Where-Object { $_.ShortCode -eq $normalized }
        }
        'SearchTerm' {
            $term = $SearchTerm.ToLowerInvariant()
            return $data | Where-Object {
                $_.Emoji -eq $SearchTerm -or
                $_.Name.ToLowerInvariant().Contains($term) -or
                $_.ShortCode.ToLowerInvariant().Contains($term) -or
                $_.Group.ToLowerInvariant().Contains($term) -or
                $_.SubGroup.ToLowerInvariant().Contains($term) -or
                $_.HexCodePoint.ToLowerInvariant().Contains($term) -or
                @($_.Keywords) -contains $term
            }
        }
        'Group' {
            $groupParams = $allParams.Clone()
            $groupParams.Group = $Group
            return Get-AllEmoji @groupParams
        }
        'SubGroup' {
            $subGroupParams = $allParams.Clone()
            $subGroupParams.SubGroup = $SubGroup
            return Get-AllEmoji @subGroupParams
        }
    }
}

function Update-EmojiCache {
    [CmdletBinding()]
    param(
        [string]$Uri = $script:UnicodeEmojiLatestUrl,
        [string]$Destination = $script:RawDataPath
    )

    $dataDir = Split-Path -Parent $Destination
    if (-not (Test-Path -LiteralPath $dataDir)) {
        New-Item -ItemType Directory -Force -Path $dataDir | Out-Null
    }

    Invoke-WebRequest -Uri $Uri -OutFile $Destination -UseBasicParsing
    $parsed = Import-FlowerEmojiTestData -Path $Destination
    $jsonPath = Join-Path $dataDir 'emoji.json'
    $parsed | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $jsonPath -Encoding UTF8
    $script:EmojiDataCache = $parsed.Emoji.ToArray()
    $script:EmojiDataInfo = $parsed | Select-Object Source, Version, GeneratedAt, Count
    $script:EmojiDataInfo
}

function Get-EmojiDataInfo {
    [CmdletBinding()]
    param()

    Load-FlowerEmojiData | Out-Null
    $script:EmojiDataInfo
}

Export-ModuleMember -Function Get-Emoji, Get-AllEmoji, Update-EmojiCache, Get-EmojiDataInfo
