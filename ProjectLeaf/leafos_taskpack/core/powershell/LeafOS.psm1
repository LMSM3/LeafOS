# core/powershell/LeafOS.psm1
# LeafOS PowerShell Module -- Windows, WSL, macOS.
# The pack-indicator functions intentionally remain compatible with Windows
# PowerShell 5/5.1. Other command surfaces may still require PowerShell 7+.

$script:LeafIsWindows = [Environment]::OSVersion.Platform -eq [PlatformID]::Win32NT
$script:LeafIsLinux = -not $script:LeafIsWindows -and (Test-Path -LiteralPath '/proc/version')
$script:LeafIsMacOS = -not $script:LeafIsWindows -and -not $script:LeafIsLinux
$script:LeafEscape = [char]27

#region Platform

function Get-LeafPlatform {
    [CmdletBinding()] param()
    $arch = [System.Runtime.InteropServices.RuntimeInformation]::ProcessArchitecture.ToString().ToLower()
    $info = [ordered]@{ OS=''; Arch=$arch; Name=''; IsWSL=$false; IsMac=$false; IsWin=$false; IsLinux=$false }
    if ($script:LeafIsWindows) {
        $info.OS    = 'windows'
        $info.Name  = [System.Environment]::OSVersion.VersionString
        $info.IsWin = $true
    } elseif ($script:LeafIsMacOS) {
        $info.OS    = 'mac'
        $info.Name  = "macOS $(& sw_vers -productVersion 2>$null)"
        $info.IsMac = $true
    } elseif ($script:LeafIsLinux) {
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

# FlowerOS pastel + green palette for PowerShell surfaces.
# Use $env:NO_COLOR=1 to disable; $env:LEAF_COLOR=1 or $env:FORCE_COLOR=1 to force.
$script:LeafColor = @{
    Reset    = "$($script:LeafEscape)[0m"
    Bold     = "$($script:LeafEscape)[1m"
    Dim      = "$($script:LeafEscape)[2m"
    Mint     = "$($script:LeafEscape)[38;2;183;240;199m"
    Leaf     = "$($script:LeafEscape)[38;2;119;221;119m"
    Fern     = "$($script:LeafEscape)[38;2;80;180;80m"
    Forest   = "$($script:LeafEscape)[38;2;34;139;34m"
    Bloom    = "$($script:LeafEscape)[38;2;255;183;197m"
    Lavender = "$($script:LeafEscape)[38;2;204;178;255m"
    Sky      = "$($script:LeafEscape)[38;2;178;223;255m"
    Butter   = "$($script:LeafEscape)[38;2;255;250;181m"
    Peach    = "$($script:LeafEscape)[38;2;255;210;183m"
    Error    = "$($script:LeafEscape)[38;2;255;154;162m"
}

function _leaf_should_use_color {
    if ($env:NO_COLOR -eq '1') { return $false }
    if ($env:LEAF_COLOR -eq '1' -or $env:FORCE_COLOR -eq '1') { return $true }
    $virtualTerminal = $host.UI.PSObject.Properties['SupportsVirtualTerminal']
    return -not ($host.Name -match 'ISE|Code.*Host' -or ($virtualTerminal -and -not $virtualTerminal.Value))
}

function Write-LeafMsg {
    param([string]$Msg, [string]$Level='info', [string]$Project='LeafOS')
    $useColor = _leaf_should_use_color
    $icon = if ($script:LeafIsWindows) { '*' } else { [char]0x1F33F }
    switch ($Level) {
        'warn' {
            if ($useColor) {
                Write-Host "$($script:LeafColor.Butter)$icon${Project}: $Msg$($script:LeafColor.Reset)"
            } else {
                Write-Host "$icon ${Project}: $Msg"
            }
        }
        'error' { Write-Error "$icon ${Project}: $Msg" }
        default {
            if ($useColor) {
                Write-Host "$($script:LeafColor.Mint)$icon $($script:LeafColor.Bold)$Project$($script:LeafColor.Reset)$($script:LeafColor.Mint): $Msg$($script:LeafColor.Reset)"
            } else {
                Write-Host "$icon " -NoNewline
                Write-Host $Project -NoNewline -ForegroundColor Green
                Write-Host ": $Msg"
            }
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
    $pyRaw = (& { python3 --version 2>&1 } 2>$null)
    if (-not $pyRaw) { $pyRaw = (& { python --version 2>&1 } 2>$null) }
    $r['python'] = _ver "$pyRaw"
    $bashRaw = (& { bash --version 2>&1 } 2>$null | Select-Object -First 1)
    $r['bash']   = _ver "$bashRaw"
    $gccRaw = (& { gcc --version 2>&1 } 2>$null | Select-Object -First 1)
    if (-not $gccRaw) { $gccRaw = (& { clang --version 2>&1 } 2>$null | Select-Object -First 1) }
    $r['gcc']    = _ver "$gccRaw"

    Write-Host ('{0,-14} {1,-12} {2,-12} {3}' -f 'Component','Found','Required','Status')
    Write-Host ('-' * 52)
    foreach ($k in $r.Keys) {
        $found  = $r[$k]; $needed = $Required[$k]
        $status = if ($needed -and (_gte $found $needed)) { 'ok' } elseif ($found -ne '0.0') { 'WARN' } else { 'missing' }
        $col    = @{ ok='Green'; WARN='Yellow'; missing='Red' }[$status]
        $requiredText = if ($needed) { $needed } else { 'any' }
        Write-Host ('{0,-14} {1,-12} {2,-12}' -f $k,$found,$requiredText) -NoNewline
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
    $frames = $script:Frames[$Name]
    if (-not $frames) { $frames = $script:Frames['dots'] }
    $n      = $frames.Count
    $steps  = [Math]::Max(1,[int]($DurationMs/$FrameMs))
    $icon   = if ($script:LeafIsWindows) { '*' } else { [char]0x1F33F }
    for ($i=0; $i -lt $steps; $i++) {
        Write-Host "`r$icon $Project [$Label] $($frames[$i % $n])  " -NoNewline
        Start-Sleep -Milliseconds $FrameMs
    }
    Write-Host "`r$icon $Project [$Label] done       "
}

function Get-LeafLoaders { $script:Frames.Keys | Sort-Object | ForEach-Object { Write-Host "  $_" } }

#endregion

#region Doctor

function Get-LeafDoctorReport {
    [CmdletBinding()]
    param([string]$Root='')

    if (-not $Root) {
        $Root = if ($env:LEAF_ROOT) { $env:LEAF_ROOT } else { Split-Path (Split-Path $PSScriptRoot) }
    }
    $Root = [IO.Path]::GetFullPath($Root)
    $checks = [System.Collections.Generic.List[object]]::new()

    $dirs = @('bin','core','config','share','logs','tests','docs')
    $missingDirs = @($dirs | Where-Object { -not (Test-Path (Join-Path $Root $_) -PathType Container) })
    $checks.Add([pscustomobject][ordered]@{
        id = 'layout.directories'; required = $true; ok = ($missingDirs.Count -eq 0)
        detail = if ($missingDirs.Count -eq 0) { 'required project directories are present' } else { 'missing: ' + (($missingDirs | ForEach-Object { "$_/" }) -join ', ') }
        repair = if ($missingDirs.Count -eq 0) { $null } else { 'restore the taskpack checkout; generated runtime data cannot replace source directories' }
    })

    $files = @(
        'config/brand.conf','config/loaders.conf','config/glyphs.conf','config/runtime.json',
        'core/brand/brand.sh','core/log/log.sh','core/loaders/loaders.sh',
        'core/glyphs/glyphs.sh','core/runtime/runtime.sh'
    )
    $missingFiles = @($files | Where-Object { -not (Test-Path (Join-Path $Root $_) -PathType Leaf) })
    $checks.Add([pscustomobject][ordered]@{
        id = 'layout.files'; required = $true; ok = ($missingFiles.Count -eq 0)
        detail = if ($missingFiles.Count -eq 0) { 'required project files are present' } else { 'missing: ' + ($missingFiles -join ', ') }
        repair = if ($missingFiles.Count -eq 0) { $null } else { 'restore the missing tracked files from the taskpack checkout' }
    })

    $python = Get-Command python -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $python) { $python = Get-Command python3 -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1 }
    $checks.Add([pscustomobject][ordered]@{
        id = 'runtime.python'; required = $true; ok = ($null -ne $python)
        detail = if ($python) { "available: $($python.Source)" } else { 'python 3 executable not found' }
        repair = if ($python) { $null } else { 'install Python 3.10+ and ensure python (or python3) is on PATH' }
    })

    $memoryCandidates = [System.Collections.Generic.List[string]]::new()
    if ($env:LEAF_MEMORY_BIN) { $memoryCandidates.Add($env:LEAF_MEMORY_BIN) }
    $memoryCandidates.Add((Join-Path $Root 'build/leaf-memory.exe'))
    $memoryCandidates.Add((Join-Path $Root 'build/leaf-memory'))
    $memoryPath = $memoryCandidates | Where-Object { Test-Path $_ -PathType Leaf } | Select-Object -First 1
    $memoryOk = $false
    $memoryDetail = 'native leaf-memory executable not found'
    if ($memoryPath) {
        $probeJournal = Join-Path ([IO.Path]::GetTempPath()) ("leaf-doctor-$([guid]::NewGuid().ToString('N')).ndjson")
        try {
            $null = New-Item -ItemType File -Path $probeJournal -Force
            $probeOutput = @(& $memoryPath verify --journal $probeJournal 2>&1)
            $memoryOk = ($LASTEXITCODE -eq 0)
            $memoryDetail = if ($memoryOk) { "verification probe passed: $memoryPath" } else { "verification probe failed (exit $LASTEXITCODE): $($probeOutput -join ' ')" }
        } catch {
            $memoryDetail = "native executable could not run: $($_.Exception.Message)"
        } finally {
            Remove-Item -LiteralPath $probeJournal -Force -ErrorAction SilentlyContinue
        }
    }
    $checks.Add([pscustomobject][ordered]@{
        id = 'memory.native'; required = $true; ok = $memoryOk; detail = $memoryDetail
        repair = if ($memoryOk) { $null } else { "run: make -C `"$Root`" all  (or set LEAF_MEMORY_BIN to a verified leaf-memory executable)" }
    })

    $mondayRoot = if ($env:LEAF_MONDAY_INSTANCE) { [IO.Path]::GetFullPath($env:LEAF_MONDAY_INSTANCE) } else { Join-Path $Root 'instances/monday-primary' }
    $mondayFiles = @('persona.json','state.json','events.ndjson','facts.ndjson')
    $missingMonday = @($mondayFiles | Where-Object { -not (Test-Path (Join-Path $mondayRoot $_) -PathType Leaf) })
    $mondayOk = ($missingMonday.Count -eq 0)
    $mondayDetail = if ($mondayOk) { "durable files present: $mondayRoot" } else { 'missing: ' + ($missingMonday -join ', ') }
    if ($mondayOk) {
        try {
            $persona = Get-Content (Join-Path $mondayRoot 'persona.json') -Raw -Encoding UTF8 | ConvertFrom-Json
            $state = Get-Content (Join-Path $mondayRoot 'state.json') -Raw -Encoding UTF8 | ConvertFrom-Json
            $mondayOk = (
                $persona.schema -eq 'leafos.continual-bloom-persona.v1' -and
                $persona.instance_id -eq 'monday-primary' -and
                $persona.identity.key -eq 'monday' -and
                $state.instance_id -eq 'monday-primary'
            )
            $mondayDetail = if ($mondayOk) { "identity and durable state verified: $mondayRoot" } else { 'persona/state identity contract does not describe monday-primary' }
        } catch {
            $mondayOk = $false
            $mondayDetail = "persona/state JSON is invalid: $($_.Exception.Message)"
        }
    }
    $bloomScript = Join-Path $Root 'core/python/leaf_continual_bloom.py'
    if ($mondayOk -and $python -and (Test-Path $bloomScript -PathType Leaf)) {
        try {
            $verifyOutput = @(& $python.Source $bloomScript verify --instance $mondayRoot --json 2>&1)
            $verifyExit = $LASTEXITCODE
            $verification = ($verifyOutput -join "`n") | ConvertFrom-Json
            $mondayOk = ($verifyExit -eq 0 -and $verification.status -eq 'ok')
            $mondayDetail = if ($mondayOk) { "identity, transcript, facts, and state verified: $mondayRoot" } else { "durable verification failed (exit $verifyExit)" }
        } catch {
            $mondayOk = $false
            $mondayDetail = "durable verification failed: $($_.Exception.Message)"
        }
    }
    $checks.Add([pscustomobject][ordered]@{
        id = 'persona.monday'; required = $true; ok = $mondayOk; detail = $mondayDetail
        repair = if ($mondayOk) { $null } else { 'run: leafos bloom init --json' }
    })

    $failed = @($checks | Where-Object { $_.required -and -not $_.ok })
    $ready = ($failed.Count -eq 0)
    [pscustomobject][ordered]@{
        leafos_object = 'leafos.doctor_report'
        version = 1
        status = if ($ready) { 'ready' } else { 'not_ready' }
        ready = $ready
        root = $Root
        capabilities = [pscustomobject][ordered]@{
            cli = (($checks | Where-Object id -eq 'layout.directories').ok -and ($checks | Where-Object id -eq 'layout.files').ok)
            live_project = $ready
        }
        checks = @($checks)
        repairs = @($failed | ForEach-Object { [pscustomobject][ordered]@{ check = $_.id; command = $_.repair } })
    }
}

function Invoke-LeafDoctor {
    [CmdletBinding()]
    param([string]$Root='')
    $report = Get-LeafDoctorReport -Root $Root
    Write-LeafMsg "readiness: $($report.status)"
    $passMark = [char]0x2713
    $failMark = [char]0x2717
    foreach ($check in $report.checks) {
        if ($check.ok) {
            if (_leaf_should_use_color) {
                Write-Host "  $($script:LeafColor.Leaf)$passMark$($script:LeafColor.Reset) $($check.id)  $($script:LeafColor.Dim)$($check.detail)$($script:LeafColor.Reset)"
            } else {
                Write-Host "  [ok] $($check.id)  $($check.detail)"
            }
        } else {
            if (_leaf_should_use_color) {
                Write-Host "  $($script:LeafColor.Error)$failMark$($script:LeafColor.Reset) $($check.id)  $($check.detail)"
                Write-Host "      $($script:LeafColor.Butter)$($check.repair)$($script:LeafColor.Reset)"
            } else {
                Write-Host "  [missing] $($check.id)  $($check.detail)"
                Write-Host "      $($check.repair)"
            }
        }
    }
    if ($report.ready) { Write-LeafLog 'doctor passed (powershell)' }
    else { Write-LeafLog 'doctor found blocking readiness issues (powershell)' -Level WARN }
    return [bool]$report.ready
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
    $asciiMode = $Ascii -or $env:LEAF_NO_EMOJI -eq '1' -or $env:NO_EMOJI -eq '1' -or $env:LEAF_GLYPHS -eq 'ascii'
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
        render_mode = if ($Ascii -or $env:LEAF_NO_EMOJI -eq '1' -or $env:NO_EMOJI -eq '1' -or $env:LEAF_GLYPHS -eq 'ascii') {
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

#region Pack indicator

$script:LeafActivePack = ''
$script:LeafIndicatorCache = $null
$script:LeafIndicatorCacheUntil = [datetime]::MinValue

function _Get-LeafRoot {
    param([string]$Root = '')
    if ($Root) { return [IO.Path]::GetFullPath($Root) }
    if ($env:LEAF_ROOT) { return [IO.Path]::GetFullPath($env:LEAF_ROOT) }
    return [IO.Path]::GetFullPath((Split-Path (Split-Path $PSScriptRoot)))
}

function _Read-LeafJson {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return $null }
    try {
        return Get-Content -LiteralPath $Path -Raw -Encoding UTF8 | ConvertFrom-Json
    } catch {
        return $null
    }
}

function _Get-LeafProperty {
    param([object]$Value, [string[]]$Names)
    if ($null -eq $Value) { return $null }
    foreach ($name in $Names) {
        $property = $Value.PSObject.Properties[$name]
        if ($property -and $null -ne $property.Value -and "$($property.Value)".Trim()) {
            return $property.Value
        }
    }
    return $null
}

function _Get-LeafPackReference {
    param([object]$Value)
    if ($null -eq $Value) { return '' }
    if ($Value -is [string] -or $Value -is [ValueType]) { return "$Value".Trim() }
    $nested = _Get-LeafProperty $Value @('manifest_path', 'path', 'pack_id', 'id', 'name')
    if ($null -eq $nested) { return '' }
    return "$nested".Trim()
}

function _Get-LeafActivePackStatePath {
    param([string]$Root)
    if ($env:LEAF_ACTIVE_PACK_STATE) {
        return [IO.Path]::GetFullPath($env:LEAF_ACTIVE_PACK_STATE)
    }
    return Join-Path $Root 'runs\active-pack.json'
}

function _Get-LeafActiveRunStatePath {
    param([string]$Root)
    if ($env:LEAF_ACTIVE_RUN_STATE) {
        return [IO.Path]::GetFullPath($env:LEAF_ACTIVE_RUN_STATE)
    }
    $canonical = Join-Path $Root 'runs\agent-loop\active.json'
    if (Test-Path -LiteralPath $canonical -PathType Leaf) { return $canonical }
    return Join-Path $Root 'runs\active.json'
}

function _Move-LeafFileReplace {
    param([Parameter(Mandatory)][string]$Source, [Parameter(Mandatory)][string]$Destination)
    # File.Move(source, destination, overwrite) is unavailable on Windows
    # PowerShell 5.1's .NET Framework. File.Replace preserves atomic replacement
    # when a destination exists; File.Move covers first creation on every host.
    if (Test-Path -LiteralPath $Destination -PathType Leaf) {
        [IO.File]::Replace($Source, $Destination, $null)
    } else {
        [IO.File]::Move($Source, $Destination)
    }
}

function _Test-LeafProcessId {
    param([int]$ProcessId)
    if ($ProcessId -le 0) { return $false }
    try {
        $null = Get-Process -Id $ProcessId -ErrorAction Stop
        return $true
    } catch {
        return $false
    }
}

function Get-LeafSubsystemActivity {
    [CmdletBinding()]
    param([string]$Root = '')
    $resolvedRoot = _Get-LeafRoot $Root

    $explicitPid = 0
    if ($env:LEAF_SUBSYSTEM_PID) {
        [void][int]::TryParse($env:LEAF_SUBSYSTEM_PID, [ref]$explicitPid)
    }
    if (_Test-LeafProcessId $explicitPid) {
        return [pscustomobject][ordered]@{
            active = $true
            subsystem = if ($env:LEAF_SUBSYSTEM_NAME) { $env:LEAF_SUBSYSTEM_NAME } else { 'external' }
            process_id = $explicitPid
            source = 'environment-process'
            evidence_grade = 'process'
            reason = "Explicit subsystem process $explicitPid is alive."
        }
    }

    $providerPidPath = Join-Path $resolvedRoot 'runs\vulkan-provider\llama-server.pid'
    if (Test-Path -LiteralPath $providerPidPath -PathType Leaf) {
        $providerPid = 0
        [void][int]::TryParse((Get-Content -LiteralPath $providerPidPath -Raw).Trim(), [ref]$providerPid)
        if (_Test-LeafProcessId $providerPid) {
            return [pscustomobject][ordered]@{
                active = $true
                subsystem = 'llamacpp.vulkan-provider'
                process_id = $providerPid
                source = 'provider-pid'
                evidence_grade = 'process'
                reason = "The owned Vulkan provider process $providerPid is alive."
            }
        }
    }

    $activePointer = _Read-LeafJson (_Get-LeafActiveRunStatePath $resolvedRoot)
    $runDirectory = _Get-LeafPackReference (_Get-LeafProperty $activePointer @('run_dir'))
    if ($runDirectory -and (Test-Path -LiteralPath $runDirectory -PathType Container)) {
        foreach ($leaseName in @('resident.lock', 'worker.lock', 'active-process.json')) {
            $lease = _Read-LeafJson (Join-Path $runDirectory $leaseName)
            $leasePid = 0
            $rawPid = _Get-LeafPackReference (_Get-LeafProperty $lease @('pid'))
            if ($rawPid) { [void][int]::TryParse($rawPid, [ref]$leasePid) }
            if (_Test-LeafProcessId $leasePid) {
                $subsystem = switch ($leaseName) {
                    'resident.lock' { 'leafos.resident-supervisor' }
                    'worker.lock' { 'leafos.loop-worker' }
                    default { 'leafos.task-process' }
                }
                return [pscustomobject][ordered]@{
                    active = $true
                    subsystem = $subsystem
                    process_id = $leasePid
                    source = "active-run:$leaseName"
                    evidence_grade = 'process'
                    reason = "The active run owns live process $leasePid through $leaseName."
                }
            }
        }
    }

    if ($env:LEAF_SUBSYSTEM_ACTIVE -in @('1', 'true', 'yes', 'on')) {
        return [pscustomobject][ordered]@{
            active = $true
            subsystem = if ($env:LEAF_SUBSYSTEM_NAME) { $env:LEAF_SUBSYSTEM_NAME } else { 'demo' }
            process_id = 0
            source = 'environment-demo'
            evidence_grade = 'demo'
            reason = 'LEAF_SUBSYSTEM_ACTIVE requested a demo-only active projection.'
        }
    }

    return [pscustomobject][ordered]@{
        active = $false
        subsystem = ''
        process_id = 0
        source = 'none'
        evidence_grade = 'none'
        reason = 'No live provider, resident, worker, or explicitly owned subsystem process was found.'
    }
}

function Resolve-LeafPackManifest {
    [CmdletBinding()]
    param([Parameter(Mandatory)][string]$Pack, [string]$Root = '')

    $resolvedRoot = _Get-LeafRoot $Root
    $candidate = $Pack.Trim()
    if ($candidate.StartsWith('pack:', [StringComparison]::OrdinalIgnoreCase)) {
        $candidate = $candidate.Substring(5)
    }
    if (-not $candidate) { return $null }

    $path = $null
    if (Test-Path -LiteralPath $candidate -PathType Leaf) {
        $path = (Resolve-Path -LiteralPath $candidate).Path
    } else {
        $relative = Join-Path $resolvedRoot $candidate
        if (Test-Path -LiteralPath $relative -PathType Leaf) {
            $path = (Resolve-Path -LiteralPath $relative).Path
        }
    }

    if (-not $path) {
        $packDirectory = Join-Path $resolvedRoot 'config\packs'
        $direct = Join-Path $packDirectory "$candidate.json"
        if (Test-Path -LiteralPath $direct -PathType Leaf) {
            $path = (Resolve-Path -LiteralPath $direct).Path
        } elseif (Test-Path -LiteralPath $packDirectory -PathType Container) {
            foreach ($file in Get-ChildItem -LiteralPath $packDirectory -Filter '*.json' -File |
                Where-Object { $_.Name -notlike '*.manifest.json' } | Sort-Object Name) {
                $data = _Read-LeafJson $file.FullName
                $manifestId = _Get-LeafPackReference (_Get-LeafProperty $data @('id', 'pack_id'))
                if ($manifestId -eq $candidate) {
                    $path = $file.FullName
                    break
                }
            }
        }
    }
    if (-not $path) { return $null }

    $manifest = _Read-LeafJson $path
    if (-not $manifest) { return $null }
    [pscustomobject][ordered]@{
        Path = [IO.Path]::GetFullPath($path)
        Data = $manifest
    }
}

function _Find-LeafPackCandidate {
    param([string]$Pack, [string]$Root)
    if ($Pack) { return [pscustomobject]@{ Value=$Pack; Source='explicit' } }
    if ($env:LEAF_ACTIVE_PACK) {
        return [pscustomobject]@{ Value=$env:LEAF_ACTIVE_PACK; Source='environment' }
    }
    if ($script:LeafActivePack) {
        return [pscustomobject]@{ Value=$script:LeafActivePack; Source='session' }
    }

    $persisted = _Read-LeafJson (_Get-LeafActivePackStatePath $Root)
    $persistedReference = _Get-LeafPackReference $persisted
    if ($persistedReference) {
        return [pscustomobject]@{ Value=$persistedReference; Source='persisted' }
    }

    $activePointer = _Read-LeafJson (_Get-LeafActiveRunStatePath $Root)
    $runDirectory = _Get-LeafPackReference (_Get-LeafProperty $activePointer @('run_dir'))
    if ($runDirectory -and (Test-Path -LiteralPath $runDirectory -PathType Container)) {
        $run = _Read-LeafJson (Join-Path $runDirectory 'run.json')
        $runReference = _Get-LeafPackReference (_Get-LeafProperty $run @(
            'active_pack', 'selected_pack', 'model_pack', 'pack', 'pack_id'
        ))
        if ($runReference) {
            return [pscustomobject]@{ Value=$runReference; Source='active-run' }
        }
    }

    $runtime = _Read-LeafJson (Join-Path $Root 'config\runtime.json')
    $leafRuntime = _Get-LeafProperty $runtime @('leafos_runtime')
    $defaults = _Get-LeafProperty $leafRuntime @('defaults')
    $runtimeReference = _Get-LeafPackReference (_Get-LeafProperty $defaults @('active_pack', 'pack'))
    if ($runtimeReference) {
        return [pscustomobject]@{ Value=$runtimeReference; Source='runtime-default' }
    }
    return [pscustomobject]@{ Value=''; Source='fallback' }
}

function Get-LeafPackIndicator {
    [CmdletBinding()]
    param([string]$Pack = '', [string]$Root = '', [switch]$Refresh)

    $resolvedRoot = _Get-LeafRoot $Root
    $cacheable = -not $Pack -and -not $Root
    if ($cacheable -and -not $Refresh -and $script:LeafIndicatorCache -and
        [datetime]::UtcNow -lt $script:LeafIndicatorCacheUntil) {
        return $script:LeafIndicatorCache
    }

    $candidate = _Find-LeafPackCandidate $Pack $resolvedRoot
    $resolved = if ($candidate.Value) {
        Resolve-LeafPackManifest -Pack $candidate.Value -Root $resolvedRoot
    } else {
        $null
    }
    $fallbackGlyph = Get-LeafGlyph -Alias 'leaf.active'
    $packId = ''
    $glyph = $fallbackGlyph
    $colour = 'green'
    $manifestPath = ''
    $customized = $false
    $reason = 'No active pack identity resolved; using the canonical leaf glyph.'

    if ($resolved) {
        $manifestPath = $resolved.Path
        $packId = _Get-LeafPackReference (_Get-LeafProperty $resolved.Data @('id', 'pack_id'))
        if (-not $packId -or $packId -notmatch '^[A-Za-z0-9][A-Za-z0-9._-]*$') {
            $packId = [IO.Path]::GetFileNameWithoutExtension($manifestPath)
        }
        $identity = _Get-LeafProperty $resolved.Data @('identity')
        $symbol = _Get-LeafPackReference (_Get-LeafProperty $identity @('symbol'))
        $identityColour = _Get-LeafPackReference (_Get-LeafProperty $identity @('colour'))
        if ($symbol -and $symbol.Length -le 12 -and $symbol -notmatch '[\r\n\x00-\x1F]') {
            $glyph = $symbol
            $customized = $true
        }
        if ($identityColour) { $colour = $identityColour }
        $reason = if ($customized) {
            "Using the glyph declared by pack '$packId'."
        } else {
            "Pack '$packId' has no usable identity.symbol; using the canonical leaf glyph."
        }
    } elseif ($candidate.Value) {
        $reason = "Active pack reference '$($candidate.Value)' did not resolve; using the canonical leaf glyph."
    }

    $activity = Get-LeafSubsystemActivity -Root $resolvedRoot
    $indicatorEnabled = [bool](Get-Variable LeafPackIndicatorEnabled -Scope Global -ErrorAction SilentlyContinue)
    $claims = [Collections.Generic.List[string]]::new()
    if ($activity.active) {
        $claims.Add('subsystem.process.active')
        if ($resolved) { $claims.Add('pack.identity.bound') }
    }
    $evidence = [pscustomobject][ordered]@{
        leafos_object = 'leafos.subsystem_indicator_evidence'
        version = 1
        active = [bool]$activity.active
        subsystem = $activity.subsystem
        process_id = [int]$activity.process_id
        source = $activity.source
        evidence_grade = $activity.evidence_grade
        pack_identity_resolved = [bool]$resolved
        pack_id = $packId
        claims = [string[]]$claims
        does_not_prove = [string[]]@(
            'all_pack_models_loaded',
            'provider_health',
            'capability_authorization'
        )
        observed_at_utc = [datetime]::UtcNow.ToString('o')
        reason = $activity.reason
    }
    $result = [pscustomobject][ordered]@{
        leafos_object = 'leafos.pack_indicator'
        version = 1
        active = [bool]$activity.active
        indicator_enabled = $indicatorEnabled
        pack_id = $packId
        glyph = $glyph
        colour = $colour
        customized = $customized
        source = $candidate.Source
        manifest_path = $manifestPath
        evidence = $evidence
        reason = $reason
    }
    if ($cacheable) {
        $script:LeafIndicatorCache = $result
        $script:LeafIndicatorCacheUntil = [datetime]::UtcNow.AddSeconds(2)
    }
    return $result
}

function Format-LeafPackIndicator {
    [CmdletBinding()]
    param([object]$Indicator = $null, [switch]$RequireActive)
    if (-not $Indicator) { $Indicator = Get-LeafPackIndicator }
    if ($RequireActive -and -not $Indicator.active) { return '' }
    $asciiMode = $env:NO_EMOJI -eq '1' -or $env:LEAF_NO_EMOJI -eq '1' -or $env:LEAF_GLYPHS -eq 'ascii'
    $rendered = if ($asciiMode) {
        if ($Indicator.pack_id) { "[pack:$($Indicator.pack_id)]" } else { Get-LeafGlyph -Alias 'leaf.active' -Ascii }
    } else {
        "$($Indicator.glyph)"
    }
    if (-not (_leaf_should_use_color)) { return $rendered }
    $paletteName = switch ("$($Indicator.colour)".ToLowerInvariant()) {
        { $_ -in @('red', 'pink', 'pastel pink') } { 'Bloom'; break }
        { $_ -in @('orange', 'peach') } { 'Peach'; break }
        { $_ -in @('yellow', 'butter') } { 'Butter'; break }
        { $_ -in @('blue', 'sky') } { 'Sky'; break }
        { $_ -in @('purple', 'violet', 'pastel violet', 'lavender') } { 'Lavender'; break }
        { $_ -in @('gray', 'grey', 'white', 'black') } { 'Mint'; break }
        default { 'Leaf' }
    }
    return "$($script:LeafColor[$paletteName])$rendered$($script:LeafColor.Reset)"
}

function Set-LeafActivePack {
    [CmdletBinding()]
    param([Parameter(Mandatory)][string]$Pack, [string]$Root = '', [switch]$Persist)
    $resolvedRoot = _Get-LeafRoot $Root
    $manifest = Resolve-LeafPackManifest -Pack $Pack -Root $resolvedRoot
    if (-not $manifest) { throw "LeafOS pack not found: $Pack" }
    $script:LeafActivePack = $manifest.Path
    $env:LEAF_ACTIVE_PACK = $manifest.Path
    if ($Persist) {
        $statePath = _Get-LeafActivePackStatePath $resolvedRoot
        $stateDirectory = Split-Path $statePath -Parent
        $null = New-Item -ItemType Directory -Path $stateDirectory -Force
        if (Test-Path -LiteralPath $statePath -PathType Leaf) {
            $existingState = _Read-LeafJson $statePath
            $existingType = _Get-LeafPackReference (_Get-LeafProperty $existingState @('leafos_object'))
            if ($existingType -ne 'leafos.active_pack') {
                throw "Refusing to replace non-LeafOS state file: $statePath"
            }
        }
        $packId = _Get-LeafPackReference (_Get-LeafProperty $manifest.Data @('id', 'pack_id'))
        $payload = [ordered]@{
            leafos_object = 'leafos.active_pack'
            version = 1
            pack_id = $packId
            manifest_path = $manifest.Path
            updated_utc = [datetime]::UtcNow.ToString('o')
        } | ConvertTo-Json
        $temporary = "$statePath.$PID.tmp"
        [IO.File]::WriteAllText($temporary, $payload + [Environment]::NewLine, [Text.Encoding]::UTF8)
        _Move-LeafFileReplace -Source $temporary -Destination $statePath
    }
    $script:LeafIndicatorCache = $null
    return Get-LeafPackIndicator -Pack $manifest.Path -Root $resolvedRoot -Refresh
}

function Clear-LeafActivePack {
    [CmdletBinding()]
    param([string]$Root = '', [switch]$Persist)
    $resolvedRoot = _Get-LeafRoot $Root
    $script:LeafActivePack = ''
    Remove-Item Env:\LEAF_ACTIVE_PACK -ErrorAction SilentlyContinue
    if ($Persist) {
        $statePath = _Get-LeafActivePackStatePath $resolvedRoot
        if (Test-Path -LiteralPath $statePath -PathType Leaf) {
            $existingState = _Read-LeafJson $statePath
            $existingType = _Get-LeafPackReference (_Get-LeafProperty $existingState @('leafos_object'))
            if ($existingType -ne 'leafos.active_pack') {
                throw "Refusing to remove non-LeafOS state file: $statePath"
            }
            Remove-Item -LiteralPath $statePath -Force
        }
    }
    $script:LeafIndicatorCache = $null
    return Get-LeafPackIndicator -Root $resolvedRoot -Refresh
}

function Enable-LeafPackIndicator {
    [CmdletBinding()]
    param([string]$Pack = '', [string]$Root = '')
    if ($Pack) { $null = Set-LeafActivePack -Pack $Pack -Root $Root }
    if ($global:LeafPackIndicatorEnabled) { return Get-LeafPackIndicator -Root $Root -Refresh }
    $currentPrompt = Get-Item Function:\prompt -ErrorAction SilentlyContinue
    $global:LeafPackIndicatorOriginalPrompt = if ($currentPrompt) {
        $currentPrompt.ScriptBlock
    } else {
        { "PS $($executionContext.SessionState.Path.CurrentLocation)> " }
    }
    Set-Item Function:\global:prompt -Value {
        $base = & $global:LeafPackIndicatorOriginalPrompt
        try {
            $mark = Format-LeafPackIndicator -RequireActive
            if ($mark) { return "$mark $base" }
            return $base
        } catch {
            return $base
        }
    }
    $global:LeafPackIndicatorEnabled = $true
    return Get-LeafPackIndicator -Root $Root -Refresh
}

function Disable-LeafPackIndicator {
    [CmdletBinding()] param()
    if ($global:LeafPackIndicatorEnabled -and $global:LeafPackIndicatorOriginalPrompt) {
        Set-Item Function:\global:prompt -Value $global:LeafPackIndicatorOriginalPrompt
    }
    Remove-Variable LeafPackIndicatorOriginalPrompt -Scope Global -ErrorAction SilentlyContinue
    Remove-Variable LeafPackIndicatorEnabled -Scope Global -ErrorAction SilentlyContinue
}

#endregion

#region Quiet child processes

function Invoke-LeafQuietProcess {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$FilePath,
        [string[]]$ArgumentList = @(),
        [string]$WorkingDirectory = '',
        [hashtable]$Environment = @{},
        [ValidateRange(0, 86400)][int]$TimeoutSeconds = 0
    )
    $startInfo = [Diagnostics.ProcessStartInfo]::new()
    $startInfo.FileName = $FilePath
    $startInfo.UseShellExecute = $false
    $startInfo.CreateNoWindow = $true
    $startInfo.RedirectStandardInput = $true
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true
    if ($WorkingDirectory) { $startInfo.WorkingDirectory = [IO.Path]::GetFullPath($WorkingDirectory) }
    foreach ($argument in $ArgumentList) { [void]$startInfo.ArgumentList.Add("$argument") }
    foreach ($key in $Environment.Keys) { $startInfo.Environment["$key"] = "$($Environment[$key])" }

    $process = [Diagnostics.Process]::new()
    $process.StartInfo = $startInfo
    if (-not $process.Start()) { throw "Failed to start quiet process: $FilePath" }
    $process.StandardInput.Close()
    $stdoutTask = $process.StandardOutput.ReadToEndAsync()
    $stderrTask = $process.StandardError.ReadToEndAsync()
    $timedOut = $false
    if ($TimeoutSeconds -gt 0) {
        if (-not $process.WaitForExit($TimeoutSeconds * 1000)) {
            $timedOut = $true
            $process.Kill($true)
            $process.WaitForExit()
        }
    } else {
        $process.WaitForExit()
    }
    [pscustomobject][ordered]@{
        ExitCode = if ($timedOut) { -1 } else { $process.ExitCode }
        StdOut = $stdoutTask.GetAwaiter().GetResult()
        StdErr = $stderrTask.GetAwaiter().GetResult()
        TimedOut = $timedOut
        ProcessId = $process.Id
        CreateNoWindow = $startInfo.CreateNoWindow
        UseShellExecute = $startInfo.UseShellExecute
    }
}

function Start-LeafQuietProcess {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$FilePath,
        [string[]]$ArgumentList = @(),
        [Parameter(Mandatory)][string]$StdOutPath,
        [Parameter(Mandatory)][string]$StdErrPath,
        [string]$WorkingDirectory = ''
    )
    $stdout = [IO.Path]::GetFullPath($StdOutPath)
    $stderr = [IO.Path]::GetFullPath($StdErrPath)
    if ($stdout -eq $stderr) { throw 'Quiet background stdout and stderr logs must be different files.' }
    $null = New-Item -ItemType Directory -Path (Split-Path $stdout -Parent) -Force
    $null = New-Item -ItemType Directory -Path (Split-Path $stderr -Parent) -Force
    $parameters = @{
        FilePath = $FilePath
        ArgumentList = $ArgumentList
        RedirectStandardOutput = $stdout
        RedirectStandardError = $stderr
        PassThru = $true
    }
    if ($WorkingDirectory) { $parameters.WorkingDirectory = [IO.Path]::GetFullPath($WorkingDirectory) }
    if ([Environment]::OSVersion.Platform -eq [PlatformID]::Win32NT) {
        $parameters.WindowStyle = 'Hidden'
    }
    $process = Start-Process @parameters
    [pscustomobject][ordered]@{
        Process = $process
        ProcessId = $process.Id
        StdOutPath = $stdout
        StdErrPath = $stderr
        Hidden = [Environment]::OSVersion.Platform -eq [PlatformID]::Win32NT
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

Export-ModuleMember -Function Get-LeafPlatform, Write-LeafMsg, Write-LeafLog, Get-LeafVersions, Invoke-LeafLoader, Get-LeafLoaders, Get-LeafDoctorReport, Invoke-LeafDoctor, Invoke-LeafStatus, Import-LeafGlyphs, Get-LeafGlyph, Get-LeafGlyphObject, Get-LeafGlyphList, Get-LeafGlyphRegistry, Write-LeafAlert, Invoke-LeafVerify, New-LeafCheckpoint, Get-LeafRuntimeConfig, Get-LeafPersonas, New-LeafRuntimeSelection, New-LeafRuntimeEvent, Resolve-LeafPackManifest, Get-LeafSubsystemActivity, Get-LeafPackIndicator, Format-LeafPackIndicator, Set-LeafActivePack, Clear-LeafActivePack, Enable-LeafPackIndicator, Disable-LeafPackIndicator, Invoke-LeafQuietProcess, Start-LeafQuietProcess
