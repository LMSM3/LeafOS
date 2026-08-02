# core/powershell/LeafOS.psm1
# LeafOS PowerShell Module -- Windows, WSL, macOS  (requires pwsh 7+)

#region Platform

function Get-LeafPlatform {
    [CmdletBinding()] param()
    $arch = [System.Runtime.InteropServices.RuntimeInformation]::ProcessArchitecture.ToString().ToLower()
    $info = [ordered]@{ OS=''; Arch=$arch; Name=''; IsWSL=$false; IsMac=$false; IsWin=$false; IsLinux=$false }
    if ($IsWindows) {
        $info.OS    = 'windows'
        $info.Name  = [System.Environment]::OSVersion.VersionString
        $info.IsWin = $true
    } elseif ($IsMacOS) {
        $info.OS    = 'mac'
        $info.Name  = "macOS $(& sw_vers -productVersion 2>$null)"
        $info.IsMac = $true
    } elseif ($IsLinux) {
        $pv = Get-Content /proc/version -ErrorAction SilentlyContinue
        if ($pv -match 'microsoft|wsl') { $info.OS = 'wsl'; $info.IsWSL = $true }
        else                            { $info.OS = 'linux'; $info.IsLinux = $true }
        $info.Name = (Get-Content /etc/os-release -EA SilentlyContinue |
            Where-Object { $_ -match '^PRETTY_NAME=' } |
            ForEach-Object { ($_ -replace '^PRETTY_NAME=|"','') } |
            Select-Object -First 1)
        if (-not $info.Name) { $info.Name = 'Linux' }
    }
    [pscustomobject]$info
}

#endregion

#region Brand

function Write-LeafMsg {
    param([string]$Msg, [string]$Level='info', [string]$Project='LeafOS')
    $icon = if ($IsWindows) { '*' } else { [char]0x1F33F }
    switch ($Level) {
        'warn'  { Write-Host "$icon ${Project}: $Msg" -ForegroundColor Yellow }
        'error' { Write-Error "$icon ${Project}: $Msg" }
        default {
            Write-Host "$icon " -NoNewline
            Write-Host $Project -NoNewline -ForegroundColor Green
            Write-Host ": $Msg"
        }
    }
}

#endregion

#region Logging

function Write-LeafLog {
    param(
        [string]$Message,
        [ValidateSet('DEBUG','INFO','WARN','ERROR')] [string]$Level = 'INFO',
        [string]$LogPath = ''
    )
    if (-not $LogPath) { $LogPath = Join-Path $env:LEAF_ROOT 'logs' 'session.log' }
    $entry = [ordered]@{ ts=(Get-Date -Format 'yyyy-MM-ddTHH:mm:ssZ'); level=$Level; msg=$Message; src='leafctl.ps1' } |
             ConvertTo-Json -Compress
    Add-Content -Path $LogPath -Value $entry -Encoding UTF8 -EA SilentlyContinue
}

#endregion

#region Version Detection

function Get-LeafVersions {
    [CmdletBinding()]
    param([hashtable]$Required = @{ pwsh='7.0'; python='3.8'; bash='4.0'; gcc='9.0' })

    function _ver($raw) { if ($raw -match '(\d+\.\d+)') { $Matches[1] } else { '0.0' } }
    function _gte($have,$need) {
        try { [version]"$have" -ge [version]"$need" } catch { $false }
    }

    $r = [ordered]@{}
    $r['pwsh']   = $PSVersionTable.PSVersion.ToString()
    $pyRaw = (& { python3 --version 2>&1 } 2>$null) ?? (& { python --version 2>&1 } 2>$null)
    $r['python'] = _ver "$pyRaw"
    $bashRaw = (& { bash --version 2>&1 } 2>$null | Select-Object -First 1)
    $r['bash']   = _ver "$bashRaw"
    $gccRaw  = (& { gcc --version 2>&1 } 2>$null | Select-Object -First 1) ??
               (& { clang --version 2>&1 } 2>$null | Select-Object -First 1)
    $r['gcc']    = _ver "$gccRaw"

    Write-Host ('{0,-14} {1,-12} {2,-12} {3}' -f 'Component','Found','Required','Status')
    Write-Host ('-' * 52)
    foreach ($k in $r.Keys) {
        $found  = $r[$k]; $needed = $Required[$k]
        $status = if ($needed -and (_gte $found $needed)) { 'ok' } elseif ($found -ne '0.0') { 'WARN' } else { 'missing' }
        $col    = @{ ok='Green'; WARN='Yellow'; missing='Red' }[$status]
        Write-Host ('{0,-14} {1,-12} {2,-12}' -f $k,$found,($needed ?? 'any')) -NoNewline
        Write-Host " $status" -ForegroundColor $col
    }
}

#endregion

#region Loaders

$script:Frames = @{
    dots    = @('.','..','...','....','...','..','.')
    bar     = @('[    ]','[=   ]','[==  ]','[=== ]','[====]')
    orbit   = @('|','/','-','\')
    braille = @([char]0x280B,[char]0x2819,[char]0x2839,[char]0x2838,[char]0x283C,
                [char]0x2834,[char]0x2826,[char]0x2827,[char]0x2807,[char]0x280F)
    bounce  = @([char]0x2581,[char]0x2582,[char]0x2583,[char]0x2584,[char]0x2585,
                [char]0x2586,[char]0x2587,[char]0x2588,[char]0x2587,[char]0x2586)
    arrow   = @([char]0x2190,[char]0x2196,[char]0x2191,[char]0x2197,
                [char]0x2192,[char]0x2198,[char]0x2193,[char]0x2199)
}

function Invoke-LeafLoader {
    param(
        [string]$Name='orbit', [string]$Label='loading', [string]$Project='LeafOS',
        [int]$DurationMs=1400, [int]$FrameMs=80
    )
    $frames = $script:Frames[$Name] ?? $script:Frames['dots']
    $n      = $frames.Count
    $steps  = [Math]::Max(1,[int]($DurationMs/$FrameMs))
    $icon   = if ($IsWindows) { '*' } else { [char]0x1F33F }
    for ($i=0; $i -lt $steps; $i++) {
        Write-Host "`r$icon $Project [$Label] $($frames[$i % $n])  " -NoNewline
        Start-Sleep -Milliseconds $FrameMs
    }
    Write-Host "`r$icon $Project [$Label] done       "
}

function Get-LeafLoaders { $script:Frames.Keys | Sort-Object | ForEach-Object { Write-Host "  $_" } }

#endregion

#region Doctor

function Invoke-LeafDoctor {
    param([string]$Root='')
    if (-not $Root) { $Root = if ($env:LEAF_ROOT) { $env:LEAF_ROOT } else { Split-Path (Split-Path $PSScriptRoot) } }
    $dirs  = 'bin','core','config','share','logs','tests','docs'
    $files = 'config/brand.conf','config/loaders.conf','config/glyphs.conf','core/brand/brand.sh','core/log/log.sh','core/loaders/loaders.sh','core/glyphs/glyphs.sh'
    $ok = $true
    foreach ($d in $dirs) {
        if (-not (Test-Path (Join-Path $Root $d) -PathType Container)) {
            Write-LeafMsg "missing dir: $d/" -Level warn; $ok = $false
        }
    }
    foreach ($f in $files) {
        $fp = Join-Path $Root ($f -replace '/','\')
        if (-not (Test-Path $fp -PathType Leaf)) {
            Write-LeafMsg "missing file: $f" -Level warn; $ok = $false
        }
    }
    if ($ok) { Write-LeafMsg 'layout usable'; Write-LeafLog 'doctor passed (powershell)' }
    else     { Write-LeafLog 'doctor found issues (powershell)' -Level WARN }
    return $ok
}

#endregion

#region Glyphs

$script:LeafGlyphs = $null
$script:LeafSessionVerified = $false   # set only by Invoke-LeafVerify on pass
$script:LeafGlyphCategories = @(
    'identity', 'growth', 'flower', 'flow', 'model', 'verify',
    'status', 'loading', 'io', 'data', 'cosmetic'
)
$script:LeafGlyphSeverities = @('none', 'info', 'ok', 'warn', 'error')

function _Write-LeafMachineLog {
    param([string]$Kind, [string]$Result, [string]$Msg)
    $root    = if ($env:LEAF_ROOT) { $env:LEAF_ROOT } else { Split-Path (Split-Path $PSScriptRoot) }
    $logdir  = Join-Path $root 'logs'
    $logfile = Join-Path $logdir 'glyphs.jsonl'
    $null    = New-Item $logdir -ItemType Directory -Force -ErrorAction SilentlyContinue
    $line = [ordered]@{
        ts = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ss.fffZ')
        kind = $Kind
        result = $Result
        msg = $Msg
    } | ConvertTo-Json -Compress
    Add-Content -Path $logfile -Value $line -Encoding UTF8 -EA SilentlyContinue
}

function Import-LeafGlyphs {
    [CmdletBinding()] param([string]$Path = '')
    if (-not $Path) {
        $root = if ($env:LEAF_ROOT) { $env:LEAF_ROOT } else { Split-Path (Split-Path $PSScriptRoot) }
        $Path = Join-Path $root 'config/glyphs.conf'
    }
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "glyph registry not found: $Path"
    }
    $tbl = [ordered]@{}
    $lineNumber = 0
    foreach ($line in [System.IO.File]::ReadAllLines($Path, [Text.Encoding]::UTF8)) {
        $lineNumber++
        if ($line -match '^\s*(#|$)') { continue }
        $fields = [regex]::Split($line, '\|')
        if ($fields.Count -ne 6) {
            throw "glyph registry error at line ${lineNumber}: expected exactly six fields"
        }
        $alias, $codepointText, $category, $severity, $ascii, $meaning = $fields
        if ($alias -notmatch '^[a-z][a-z0-9]*(\.[a-z0-9]+)*$') {
            throw "glyph registry error at line ${lineNumber}: invalid alias '$alias'"
        }
        if ($tbl.Contains($alias)) {
            throw "glyph registry error at line ${lineNumber}: duplicate alias '$alias'"
        }
        if ($category -notin $script:LeafGlyphCategories) {
            throw "glyph registry error at line ${lineNumber}: invalid category '$category'"
        }
        if ($severity -notin $script:LeafGlyphSeverities) {
            throw "glyph registry error at line ${lineNumber}: invalid severity '$severity'"
        }
        if (-not $codepointText -or -not $ascii -or -not $meaning) {
            throw "glyph registry error at line ${lineNumber}: codepoints, ascii, and meaning are required"
        }
        if ($ascii.ToCharArray() | Where-Object { [int]$_ -lt 32 -or [int]$_ -gt 126 }) {
            throw "glyph registry error at line ${lineNumber}: ASCII fallback must contain printable ASCII only"
        }
        $codepoints = @($codepointText -split '\s+' | Where-Object { $_ })
        foreach ($codepoint in $codepoints) {
            if ($codepoint -notmatch '^[0-9A-F]{4,6}$') {
                throw "glyph registry error at line ${lineNumber}: invalid codepoint '$codepoint'"
            }
            $scalar = [Convert]::ToInt32($codepoint, 16)
            if ($scalar -le 0 -or $scalar -gt 0x10FFFF) {
                throw "glyph registry error at line ${lineNumber}: codepoint out of range '$codepoint'"
            }
            if ($scalar -ge 0xD800 -and $scalar -le 0xDFFF) {
                throw "glyph registry error at line ${lineNumber}: surrogate codepoint '$codepoint'"
            }
        }
        $tbl[$alias] = [pscustomobject]@{
            Alias = $alias
            Codepoints = [string[]]$codepoints
            Category = $category
            Severity = $severity
            Ascii = $ascii
            Meaning = $meaning
        }
    }
    if ($tbl.Count -eq 0) { throw 'glyph registry error: registry is empty' }
    $script:LeafGlyphs = $tbl
}

function Get-LeafGlyphObject {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$Alias,
        [switch]$Ascii
    )
    if (-not $script:LeafGlyphs) { Import-LeafGlyphs }
    $row = $script:LeafGlyphs[$Alias]
    if (-not $row) { throw "unknown glyph alias: $Alias" }
    $asciiMode = $Ascii -or $env:LEAF_NO_EMOJI -eq '1' -or $env:NO_EMOJI -eq '1'
    $rendered = if ($asciiMode) {
        $row.Ascii
    } else {
        -join ($row.Codepoints | ForEach-Object {
            [char]::ConvertFromUtf32([Convert]::ToInt32($_, 16))
        })
    }
    [pscustomobject][ordered]@{
        leafos_object = 'leafos.glyph'
        version = 1
        alias = $row.Alias
        glyph = $rendered
        codepoints = [string[]]$row.Codepoints
        category = $row.Category
        severity = $row.Severity
        ascii = $row.Ascii
        meaning = $row.Meaning
        render_mode = if ($asciiMode) { 'ascii' } else { 'unicode' }
    }
}

function Get-LeafGlyph {
    [CmdletBinding()] param([Parameter(Mandatory)][string]$Alias, [switch]$Ascii)
    (Get-LeafGlyphObject -Alias $Alias -Ascii:$Ascii).glyph
}

function Get-LeafGlyphList {
    [CmdletBinding()] param([string]$Category = '', [switch]$Ascii)
    if (-not $script:LeafGlyphs) { Import-LeafGlyphs }
    $script:LeafGlyphs.Values |
        Where-Object { -not $Category -or $_.Category -eq $Category } |
        Sort-Object Alias |
        ForEach-Object { Get-LeafGlyphObject -Alias $_.Alias -Ascii:$Ascii }
}

function Get-LeafGlyphRegistry {
    [CmdletBinding()] param([string]$Category = '', [switch]$Ascii)
    $glyphs = @(Get-LeafGlyphList -Category $Category -Ascii:$Ascii)
    [pscustomobject][ordered]@{
        leafos_object = 'leafos.glyph_registry'
        version = 1
        category = $Category
        count = $glyphs.Count
        render_mode = if ($Ascii -or $env:LEAF_NO_EMOJI -eq '1' -or $env:NO_EMOJI -eq '1') {
            'ascii'
        } else {
            'unicode'
        }
        glyphs = $glyphs
    }
}

function Write-LeafAlert {
    [CmdletBinding()] param([ValidateSet('info','ok','warn','error')][string]$Severity = 'warn', [string]$Message = '')
    $glyph = Get-LeafGlyph 'leaf.alert'
    $map = @{ info='Cyan'; ok='Green'; warn='Yellow'; error='Red' }
    $label = @{ info='info'; ok='ok'; warn='warning'; error='error' }[$Severity]
    Write-Host "$glyph $label`: " -ForegroundColor $map[$Severity] -NoNewline
    Write-Host $Message
    _Write-LeafMachineLog -Kind alert -Result $Severity -Msg $Message
}

function Invoke-LeafVerify {
    # Run a scriptblock as the verification check.
    # Only emits leaf.verify and sets the session flag on success.
    # On failure: emits leaf.fail + leaf.alert error. Never lies.
    [CmdletBinding()] param([Parameter(Mandatory)][scriptblock]$Check, [string]$Label = 'check')
    $ok = $false
    try { & $Check; $ok = $true } catch { $ok = $false }
    if ($ok) {
        $script:LeafSessionVerified = $true
        $g = Get-LeafGlyph 'leaf.verify'
        Write-Host "$g verified: $Label"
        _Write-LeafMachineLog -Kind verify -Result ok -Msg $Label
    } else {
        $script:LeafSessionVerified = $false
        $g = Get-LeafGlyph 'leaf.fail'
        Write-Host "$g failed: $Label" -ForegroundColor Red
        _Write-LeafMachineLog -Kind verify -Result fail -Msg $Label
        Write-LeafAlert -Severity error -Message "check failed: $Label"
        throw "LeafVerify failed: $Label"
    }
}

function New-LeafCheckpoint {
    # Create a checkpoint. Refused unless Invoke-LeafVerify passed in this session.
    [CmdletBinding()] param([string]$Label = 'checkpoint')
    if (-not $script:LeafSessionVerified) {
        Write-LeafAlert -Severity error -Message 'checkpoint refused: Invoke-LeafVerify must pass first'
        throw 'LeafCheckpoint: verification required'
    }
    $g = Get-LeafGlyph 'leaf.checkpoint'
    Write-Host "$g checkpoint: $Label"
    _Write-LeafMachineLog -Kind checkpoint -Result create -Msg $Label
    $script:LeafSessionVerified = $false   # consumed; next checkpoint needs a new verify
}

#endregion

#region Runtime

function Get-LeafRuntimeConfig {
    [CmdletBinding()] param([string]$Root = '')
    if (-not $Root) { $Root = if ($env:LEAF_ROOT) { $env:LEAF_ROOT } else { Split-Path (Split-Path $PSScriptRoot) } }
    $path = Join-Path $Root 'config/runtime.json'
    if (-not (Test-Path $path -PathType Leaf)) { throw "runtime config not found: $path" }
    Get-Content -LiteralPath $path -Raw -Encoding UTF8 | ConvertFrom-Json
}

function Get-LeafPersonas {
    [CmdletBinding()] param([string]$Root = '')
    (Get-LeafRuntimeConfig -Root $Root).leafos_runtime.persona_registry
}

function New-LeafRuntimeSelection {
    [CmdletBinding()]
    param(
        [string]$MainModel = '',
        [string]$SchedulerModel = '',
        [string]$CoderModel = '',
        [string]$CodingLanguage = '',
        [string]$CodingModelChoice = '',
        [string]$CodingTier = '',
        [string]$Persona = '',
        [string]$Mode = '',
        [string]$Root = ''
    )

    $cfg = Get-LeafRuntimeConfig -Root $Root
    $rt = $cfg.leafos_runtime
    if (-not $MainModel)  { $MainModel = $rt.defaults.main_model }
    if (-not $SchedulerModel) { $SchedulerModel = $rt.defaults.scheduler_model }
    if (-not $CoderModel) { $CoderModel = $rt.defaults.coder_model }
    if (-not $CodingLanguage) { $CodingLanguage = if ($env:LEAF_CODING_LANGUAGE) { $env:LEAF_CODING_LANGUAGE } else { $rt.defaults.coding_language } }
    if (-not $CodingModelChoice) { $CodingModelChoice = if ($env:LEAF_CODING_MODEL_CHOICE) { $env:LEAF_CODING_MODEL_CHOICE } else { $rt.defaults.coding_model_choice } }
    if (-not $CodingTier) { $CodingTier = if ($env:LEAF_CODING_TIER) { $env:LEAF_CODING_TIER } else { $rt.defaults.coding_tier } }
    if (-not $Persona)    { $Persona = $rt.defaults.persona }
    if (-not $Mode)       { $Mode = $rt.defaults.mode }

    $mainObj = @($rt.main_models | Where-Object { $_.key -eq $MainModel -or $_.repo -eq $MainModel } | Select-Object -First 1)
    $schedulerObj = @($rt.main_models | Where-Object { $_.key -eq $SchedulerModel -or $_.repo -eq $SchedulerModel } | Select-Object -First 1)
    $coderObj = @($rt.coder_models | Where-Object { $_.key -eq $CoderModel -or $_.repo -eq $CoderModel } | Select-Object -First 1)
    $personaObj = @($rt.persona_registry | Where-Object { $_.key -eq $Persona } | Select-Object -First 1)

    if (-not $mainObj)    { throw "Unknown main model: $MainModel" }
    if (-not $schedulerObj) { throw "Unknown scheduler model: $SchedulerModel" }
    if (-not $coderObj)   { throw "Unknown coder model: $CoderModel" }
    if (-not $personaObj) { throw "Unknown persona: $Persona" }
    if ($Mode -notin $rt.modes) { throw "Unknown runtime mode: $Mode" }

    $codingModelKey = if ($rt.role_policy.coding_model_key) { $rt.role_policy.coding_model_key } else { 'gemma4-coder' }
    if ($coderObj[0].key -ne $codingModelKey) { throw "Coder model must be $codingModelKey" }
    if ($CodingModelChoice -ne $codingModelKey) { throw "Coding model choice must be $codingModelKey" }
    if ($CodingLanguage -notin @($rt.role_policy.allowed_coding_languages)) { throw "Unsupported coding language: $CodingLanguage" }
    $codingTierObj = @($coderObj[0].tiers | Where-Object { $_.name -eq $CodingTier } | Select-Object -First 1)
    if (-not $codingTierObj) { throw "Unknown coding tier for $($coderObj[0].key): $CodingTier" }
    if ($mainObj[0].key -eq $codingModelKey) { throw 'Fable/Gemma4-Coder cannot be main model' }
    if ($schedulerObj[0].key -eq $codingModelKey) { throw 'Fable/Gemma4-Coder cannot be scheduler model' }

    $workerList = [System.Collections.Generic.List[object]]::new()
    if ($personaObj[0].code_policy -ne 'avoid_unless_stuck') {
        foreach ($tier in @($coderObj[0].tiers)) { [void]$workerList.Add($tier) }
    }

    [pscustomobject]@{
        SchemaVersion = $cfg.schema_version
        MainModel = $mainObj[0]
        SchedulerModel = $schedulerObj[0]
        CoderModel = $coderObj[0]
        CodingChoice = [pscustomobject]@{
            language = $CodingLanguage
            model_key = $CodingModelChoice
            tier = $CodingTier
            tier_config = $codingTierObj[0]
            backend = 'python'
            source = 'runtime-default-or-env'
        }
        Persona = $personaObj[0]
        Mode = $Mode
        LanguageHint = $CodingLanguage
        Workers = $workerList
        CareMode = $personaObj[0].care_mode
        ContractVersion = $rt.output_contract.version
        RolePolicy = $rt.role_policy
    }
}

function New-LeafRuntimeEvent {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$ResponseType,
        [Parameter(Mandatory)][double]$ConfidenceScore,
        [string]$Content = '',
        [string]$Root = ''
    )
    $rt = (Get-LeafRuntimeConfig -Root $Root).leafos_runtime
    if ($ResponseType -notin $rt.output_contract.allowed_response_types) {
        throw "Invalid runtime response_type: $ResponseType"
    }
    if ($ConfidenceScore -lt 0 -or $ConfidenceScore -gt 1) {
        throw 'confidence_score must be between 0.0 and 1.0'
    }
    [pscustomobject]@{
        response_type = $ResponseType
        content = $Content
        confidence_score = ('{0:0.###}' -f $ConfidenceScore)
    }
}

#endregion

#region Status

function Invoke-LeafStatus {
    param([string]$Root='')
    if (-not $Root) { $Root = $env:LEAF_ROOT }
    $plat = Get-LeafPlatform
    Write-LeafMsg 'LeafOS status'
    Write-Host "  platform : os=$($plat.OS) arch=$($plat.Arch) name=$($plat.Name)"
    Write-Host "  root     : $Root"
    Write-Host "  pwsh     : $($PSVersionTable.PSVersion)"
    try {
        $sel = New-LeafRuntimeSelection -Root $Root
        Write-Host "  runtime  : main=$($sel.MainModel.key) scheduler=$($sel.SchedulerModel.key) coder=$($sel.CoderModel.key) persona=$($sel.Persona.key)"
    } catch {
        Write-Host "  runtime  : unavailable ($($_.Exception.Message))"
    }
    Write-LeafLog 'status (powershell)'
}

#endregion

Export-ModuleMember -Function Get-LeafPlatform, Write-LeafMsg, Write-LeafLog, Get-LeafVersions, Invoke-LeafLoader, Get-LeafLoaders, Invoke-LeafDoctor, Invoke-LeafStatus, Import-LeafGlyphs, Get-LeafGlyph, Get-LeafGlyphObject, Get-LeafGlyphList, Get-LeafGlyphRegistry, Write-LeafAlert, Invoke-LeafVerify, New-LeafCheckpoint, Get-LeafRuntimeConfig, Get-LeafPersonas, New-LeafRuntimeSelection, New-LeafRuntimeEvent
