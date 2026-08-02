& {
    $ErrorActionPreference = 'Stop'

    # ------------------------------------------------------------------------
    # Flower Pack 1.2.0 - registry-aware Pack 1 download wrapper
    # Paste directly into PowerShell 7.
    # ------------------------------------------------------------------------

    $PackId = 1

    $FlowerPackRoots = @(
        'C:\flower-pack-1.2.0\flower-pack-1.2.0',
        'C:\flower-pack-1.2.0'
    )

    $ModelRoot             = 'C:\R\LeafOS0.2.1\models'
    $FallbackExpectedGiB   = 250.1
    $ProgressSampleSeconds = 10
    $AnimationDelayMs      = 120

    $Esc   = [char]27
    $Reset = "$Esc[0m"

    $Colors = @(
        217, 211, 231, 228, 229, 221, 182, 227, 181,
        175, 147, 195, 215, 216, 210, 222, 146
    )

    # Generated at runtime so the pasted source remains ASCII-safe.
    $Glyphs = @(
        [char]0x2698,
        [char]0x2618,
        [char]0x273F,
        [char]0x2740,
        [char]0x2741,
        [char]0x2742
    )

    function Get-FirstProperty {
        param(
            [Parameter(Mandatory)]$Object,
            [Parameter(Mandatory)][string[]]$Names
        )

        foreach ($name in $Names) {
            $property = $Object.PSObject.Properties[$name]

            if (
                $null -ne $property -and
                $null -ne $property.Value
            ) {
                return $property.Value
            }
        }

        return $null
    }

    function Show-FlowerLoading {
        param(
            [Parameter(Mandatory)][string]$Message,
            [int]$Cycles = 2
        )

        $oldCursor = $true

        try {
            try {
                $oldCursor = $Host.UI.RawUI.CursorVisible
                $Host.UI.RawUI.CursorVisible = $false
            }
            catch {
                $oldCursor = $true
            }

            for ($cycle = 0; $cycle -lt $Cycles; $cycle++) {
                for ($index = 0; $index -lt $Glyphs.Count; $index++) {
                    $glyph = $Glyphs[$index]

                    $colorIndex = (
                        ($cycle * $Glyphs.Count) + $index
                    ) % $Colors.Count

                    $color = $Colors[$colorIndex]

                    Write-Host -NoNewline (
                        "`r{0}[2K{0}[38;5;{1}m  {2}  {3}{4}" -f
                        $Esc,
                        $color,
                        $glyph,
                        $Message,
                        $Reset
                    )

                    Start-Sleep -Milliseconds $AnimationDelayMs
                }
            }

            Write-Host (
                "`r{0}[2K{0}[38;5;195m[+] {1}{2}" -f
                $Esc,
                $Message,
                $Reset
            )
        }
        finally {
            try {
                $Host.UI.RawUI.CursorVisible = $oldCursor
            }
            catch {
            }
        }
    }

    function Format-Duration {
        param([double]$Seconds)

        if (
            [double]::IsNaN($Seconds) -or
            [double]::IsInfinity($Seconds) -or
            $Seconds -lt 0
        ) {
            return '--:--:--'
        }

        $duration = [TimeSpan]::FromSeconds($Seconds)

        if ($duration.TotalDays -ge 1) {
            return '{0}d {1:00}:{2:00}:{3:00}' -f
                [math]::Floor($duration.TotalDays),
                $duration.Hours,
                $duration.Minutes,
                $duration.Seconds
        }

        return '{0:00}:{1:00}:{2:00}' -f
            [math]::Floor($duration.TotalHours),
            $duration.Minutes,
            $duration.Seconds
    }

    function Get-RegistryPlan {
        param(
            [Parameter(Mandatory)][string]$Root,
            [Parameter(Mandatory)][int]$RequestedPackId
        )

        $modelsPath = Join-Path $Root (
            'share\floweros\registry\models.json'
        )

        $packsPath = Join-Path $Root (
            'share\floweros\registry\packs.json'
        )

        if (
            -not (Test-Path -LiteralPath $modelsPath -PathType Leaf) -or
            -not (Test-Path -LiteralPath $packsPath -PathType Leaf)
        ) {
            return $null
        }

        $modelsDocument = Get-Content `
            -LiteralPath $modelsPath `
            -Raw |
            ConvertFrom-Json

        $packsDocument = Get-Content `
            -LiteralPath $packsPath `
            -Raw |
            ConvertFrom-Json

        $modelsProperty = $modelsDocument.PSObject.Properties['models']
        $packsProperty  = $packsDocument.PSObject.Properties['packs']

        $models = if ($null -ne $modelsProperty) {
            @($modelsProperty.Value)
        }
        else {
            @($modelsDocument)
        }

        $packs = if ($null -ne $packsProperty) {
            @($packsProperty.Value)
        }
        else {
            @($packsDocument)
        }

        $pack = $packs |
            Where-Object {
                $id = Get-FirstProperty `
                    -Object $_ `
                    -Names @('id', 'pack_id')

                [string]$id -eq [string]$RequestedPackId
            } |
            Select-Object -First 1

        if ($null -eq $pack) {
            throw "Pack $RequestedPackId was not found in packs.json."
        }

        $entries = @(
            Get-FirstProperty `
                -Object $pack `
                -Names @('entries', 'items', 'models')
        )

        $resolvedEntries = [System.Collections.Generic.List[object]]::new()
        $artifactMap = @{}

        foreach ($entry in $entries) {
            $modelId = [string](
                Get-FirstProperty `
                    -Object $entry `
                    -Names @('model_id', 'modelId')
            )

            $quantId = [string](
                Get-FirstProperty `
                    -Object $entry `
                    -Names @('quant_id', 'quantId')
            )

            $role = [string](
                Get-FirstProperty `
                    -Object $entry `
                    -Names @('role', 'name')
            )

            $model = $models |
                Where-Object {
                    $candidateId = Get-FirstProperty `
                        -Object $_ `
                        -Names @('id', 'model_id')

                    [string]$candidateId -eq $modelId
                } |
                Select-Object -First 1

            if ($null -eq $model) {
                throw "Registry model not found: $modelId"
            }

            $quantizations = @(
                Get-FirstProperty `
                    -Object $model `
                    -Names @(
                        'quantizations',
                        'quants',
                        'artifacts'
                    )
            )

            $quant = $quantizations |
                Where-Object {
                    $candidateId = Get-FirstProperty `
                        -Object $_ `
                        -Names @('id', 'quant_id')

                    [string]$candidateId -eq $quantId
                } |
                Select-Object -First 1

            if ($null -eq $quant) {
                throw (
                    "Registry quantization not found: " +
                    "$modelId / $quantId"
                )
            }

            $filename = [string](
                Get-FirstProperty `
                    -Object $quant `
                    -Names @('filename', 'file_name', 'file_match')
            )

            $sizeBytesValue = Get-FirstProperty `
                -Object $quant `
                -Names @('size_bytes', 'bytes')

            $sizeGiBValue = Get-FirstProperty `
                -Object $quant `
                -Names @(
                    'size_gib',
                    'size_gb',
                    'estimated_download_gib',
                    'nominal_size'
                )

            $sizeBytes = [int64]0

            if ($null -ne $sizeBytesValue) {
                $sizeBytes = [int64]$sizeBytesValue
            }
            if ($null -ne $sizeGiBValue) {
                $parsedSize = $null

                if (
                    [double]::TryParse(
                        [string]$sizeGiBValue,
                        [ref]$parsedSize
                    )
                ) {
                    $sizeBytes = [int64]($parsedSize * 1GB)
                }
                else {
                    $sizeMatch = [regex]::Match(
                        [string]$sizeGiBValue,
                        '([0-9]+(?:\.[0-9]+)?)\s*(GB|GiB|MB|MiB|TB|TiB)'
                    )

                    if ($sizeMatch.Success) {
                        $value = [double]$sizeMatch.Groups[1].Value
                        $unit  = $sizeMatch.Groups[2].Value.ToUpperInvariant()

                        switch -Regex ($unit) {
                            'MB|MiB' { $sizeBytes = [int64]($value * 1MB) }
                            'GB|GiB' { $sizeBytes = [int64]($value * 1GB) }
                            'TB|TiB' { $sizeBytes = [int64]($value * 1TB) }
                        }
                    }
                }
            }

            $repositoryRef = [string](
                Get-FirstProperty `
                    -Object $model `
                    -Names @(
                        'repository_ref',
                        'repo',
                        'repository'
                    )
            )

            $artifactKey = "$modelId|$quantId"

            if (-not $artifactMap.ContainsKey($artifactKey)) {
                $artifactMap[$artifactKey] = [pscustomobject]@{
                    ModelId      = $modelId
                    QuantId      = $quantId
                    Repository   = $repositoryRef
                    Filename     = $filename
                    ExpectedBytes = $sizeBytes
                }
            }

            $resolvedEntries.Add(
                [pscustomobject]@{
                    Role       = $role
                    ModelId    = $modelId
                    QuantId    = $quantId
                    Repository = $repositoryRef
                    Filename   = $filename
                    SizeGiB    = if ($sizeBytes -gt 0) {
                        $sizeBytes / 1GB
                    }
                    else {
                        $null
                    }
                }
            )
        }

        $artifacts = @($artifactMap.Values)

        $expectedBytes = [int64](
            (
                $artifacts |
                Measure-Object -Property ExpectedBytes -Sum
            ).Sum
        )

        if ($expectedBytes -le 0) {
            $packSize = Get-FirstProperty `
                -Object $pack `
                -Names @(
                    'expected_size_gib',
                    'estimated_download_gib',
                    'size_gib',
                    'nominal_size'
                )

            if ($null -ne $packSize) {
                $parsedPackSize = $null

                if (
                    [double]::TryParse(
                        [string]$packSize,
                        [ref]$parsedPackSize
                    )
                ) {
                    $expectedBytes = [int64]($parsedPackSize * 1GB)
                }
                else {
                    $packSizeMatch = [regex]::Match(
                        [string]$packSize,
                        '([0-9]+(?:\.[0-9]+)?)\s*(GB|GiB|MB|MiB|TB|TiB)'
                    )

                    if ($packSizeMatch.Success) {
                        $value = [double]$packSizeMatch.Groups[1].Value
                        $unit  = $packSizeMatch.Groups[2].Value.ToUpperInvariant()

                        switch -Regex ($unit) {
                            'MB|MiB' { $expectedBytes = [int64]($value * 1MB) }
                            'GB|GiB' { $expectedBytes = [int64]($value * 1GB) }
                            'TB|TiB' { $expectedBytes = [int64]($value * 1TB) }
                        }
                    }
                }
            }
        }

        $fileNames = [System.Collections.Generic.HashSet[string]]::new(
            [System.StringComparer]::OrdinalIgnoreCase
        )

        foreach ($artifact in $artifacts) {
            if (-not [string]::IsNullOrWhiteSpace($artifact.Filename)) {
                $leafName = [System.IO.Path]::GetFileName(
                    $artifact.Filename
                )

                [void]$fileNames.Add($leafName)
            }
        }

        if ($fileNames.Count -eq 0 -and $expectedBytes -gt 0) {
            [void]$fileNames.Add('*.gguf')
            [void]$fileNames.Add('*.bin')
            [void]$fileNames.Add('*.safetensors')
            [void]$fileNames.Add('*.part')
        }

        $packName = [string](
            Get-FirstProperty `
                -Object $pack `
                -Names @('name', 'display_name')
        )

        return [pscustomobject]@{
            PackId           = $RequestedPackId
            PackName         = $packName
            Entries          = @($resolvedEntries)
            Artifacts        = $artifacts
            ExpectedBytes    = $expectedBytes
            ExpectedGiB      = $expectedBytes / 1GB
            TrackedFileNames = $fileNames
            RegistrySource   = $packsPath
        }
    }

    function Get-TrackedState {
        param(
            [Parameter(Mandatory)][string]$Path,
            [Parameter(Mandatory)]
            [System.Collections.Generic.HashSet[string]]$TrackedNames
        )

        $totalBytes = [int64]0
        $fileCount  = 0
        $activeFile = ''
        $latestTime = [datetime]::MinValue

        if (-not (Test-Path -LiteralPath $Path -PathType Container)) {
            return [pscustomobject]@{
                Bytes      = [int64]0
                FileCount  = 0
                ActiveFile = ''
            }
        }

        $trackAllFiles = $TrackedNames.Count -eq 0
        $trackedPatterns = @($TrackedNames)

        foreach (
            $filePath in
            [System.IO.Directory]::EnumerateFiles(
                $Path,
                '*',
                [System.IO.SearchOption]::AllDirectories
            )
        ) {
            try {
                $file = [System.IO.FileInfo]::new($filePath)
                $name = $file.Name
                $matched = $trackAllFiles

                if (-not $matched) {
                    foreach ($pattern in $trackedPatterns) {
                        if (
                            $name -like $pattern -or
                            $name.Contains(
                                $pattern,
                                [System.StringComparison]::OrdinalIgnoreCase
                            )
                        ) {
                            $matched = $true
                            break
                        }
                    }

                    if (
                        -not $matched -and
                        $name.EndsWith(
                            '.part',
                            [System.StringComparison]::OrdinalIgnoreCase
                        )
                    ) {
                        $baseName = $name.Substring(
                            0,
                            $name.Length - 5
                        )

                        foreach ($pattern in $trackedPatterns) {
                            if (
                                $baseName -like $pattern -or
                                $baseName.Contains(
                                    $pattern,
                                    [System.StringComparison]::OrdinalIgnoreCase
                                )
                            ) {
                                $matched = $true
                                break
                            }
                        }
                    }
                }

                if (-not $matched) {
                    continue
                }

                $totalBytes += $file.Length
                $fileCount++

                if ($file.LastWriteTimeUtc -gt $latestTime) {
                    $latestTime = $file.LastWriteTimeUtc
                    $activeFile = $file.Name
                }
            }
            catch {
            }
        }

        return [pscustomobject]@{
            Bytes      = $totalBytes
            FileCount  = $fileCount
            ActiveFile = $activeFile
        }
    }

    function Get-LogTail {
        param(
            [Parameter(Mandatory)][string[]]$Paths,
            [int]$Lines = 20
        )

        foreach ($path in $Paths) {
            if (
                Test-Path -LiteralPath $path -PathType Leaf
            ) {
                Write-Host ''
                Write-Host "[log] $path"

                Get-Content `
                    -LiteralPath $path `
                    -Tail $Lines `
                    -ErrorAction SilentlyContinue
            }
        }
    }

    $oldCursor = $true
    $process = $null

    try {
        Clear-Host

        try {
            $oldCursor = $Host.UI.RawUI.CursorVisible
        }
        catch {
            $oldCursor = $true
        }

        Write-Host ''
        Write-Host (
            "{0}[38;5;217m" +
            "Flower Pack 1.2.0 - Registry-Aware Installer" +
            "{1}" -f
            $Esc,
            $Reset
        )
        Write-Host ''

        Show-FlowerLoading `
            -Message 'Locating Flower Pack launcher...' `
            -Cycles 2

        Start-Sleep -Seconds 1

        $FlowerPackRoot = $FlowerPackRoots |
            Where-Object {
                $candidate = Join-Path $_ 'flower-pack.ps1'

                Test-Path `
                    -LiteralPath $candidate `
                    -PathType Leaf
            } |
            Select-Object -First 1

        if ([string]::IsNullOrWhiteSpace($FlowerPackRoot)) {
            throw (
                'flower-pack.ps1 was not found under any configured ' +
                'Flower Pack directory.'
            )
        }

        $Launcher = Join-Path $FlowerPackRoot 'flower-pack.ps1'

        Write-Host "[+] Flower Pack root: $FlowerPackRoot"
        Start-Sleep -Seconds 1

        Show-FlowerLoading `
            -Message 'Reading model and pack registries...' `
            -Cycles 3

        Start-Sleep -Seconds 1

        $plan = Get-RegistryPlan `
            -Root $FlowerPackRoot `
            -RequestedPackId $PackId

        if ($null -eq $plan) {
            $fallbackNames = [System.Collections.Generic.HashSet[string]]::new(
                [System.StringComparer]::OrdinalIgnoreCase
            )
            [void]$fallbackNames.Add('*.gguf')
            [void]$fallbackNames.Add('*.bin')
            [void]$fallbackNames.Add('*.safetensors')
            [void]$fallbackNames.Add('*.part')

            $plan = [pscustomobject]@{
                PackId           = $PackId
                PackName         = "Pack $PackId"
                Entries          = @()
                Artifacts        = @()
                ExpectedBytes    = [int64](
                    $FallbackExpectedGiB * 1GB
                )
                ExpectedGiB      = $FallbackExpectedGiB
                TrackedFileNames = $fallbackNames
                RegistrySource   = 'fallback'
            }

            Write-Warning (
                'Structured registry was not found. ' +
                'Using fallback size and directory-wide tracking.'
            )
        }
        else {
            Write-Host "[+] Registry: $($plan.RegistrySource)"
        }

        if ($plan.ExpectedBytes -le 0) {
            $plan.ExpectedBytes = [int64](
                $FallbackExpectedGiB * 1GB
            )

            $plan.ExpectedGiB = $FallbackExpectedGiB
        }

        Write-Host "[+] Pack: $($plan.PackId) $($plan.PackName)"
        Write-Host (
            '[+] Unique artifacts: {0}' -f
            $plan.Artifacts.Count
        )
        Write-Host (
            '[+] Expected payload: {0:N2} GiB' -f
            $plan.ExpectedGiB
        )

        if ($plan.Entries.Count -gt 0) {
            Write-Host ''
            Write-Host 'Pack plan:'

            $plan.Entries |
                Select-Object `
                    Role,
                    ModelId,
                    QuantId,
                    @{
                        Name = 'GiB'
                        Expression = {
                            if ($null -eq $_.SizeGiB) {
                                '?'
                            }
                            else {
                                '{0:N2}' -f $_.SizeGiB
                            }
                        }
                    } |
                Format-Table -AutoSize
        }

        Start-Sleep -Seconds 1

        Show-FlowerLoading `
            -Message 'Preparing LeafOS model directory...' `
            -Cycles 2

        Start-Sleep -Seconds 1

        New-Item `
            -ItemType Directory `
            -Path $ModelRoot `
            -Force |
            Out-Null

        $env:FLOWER_MODEL_ROOT = $ModelRoot

        Write-Host "[+] Model root: $ModelRoot"
        Start-Sleep -Seconds 1

        Show-FlowerLoading `
            -Message 'Checking existing model artifacts...' `
            -Cycles 2

        Start-Sleep -Seconds 1

        $storeRoot = Join-Path $ModelRoot 'store'
        $trackRoot = Join-Path $ModelRoot "packs\pack-$PackId"

        foreach (
            $requiredRoot in @(
                $trackRoot,
                $storeRoot
            )
        ) {
            if (-not (Test-Path -LiteralPath $requiredRoot -PathType Container)) {
                New-Item -ItemType Directory -Path $requiredRoot -Force | Out-Null
            }
        }

        $initialState = Get-TrackedState `
            -Path $storeRoot `
            -TrackedNames $plan.TrackedFileNames

        $initialBytes  = $initialState.Bytes
        $previousBytes = $initialBytes
        $previousSampleTime = Get-Date
        $startTime = Get-Date
        $smoothedMiBs = 0.0

        $progressMode = if (
            $plan.TrackedFileNames.Count -gt 0
        ) {
            'registry'
        }
        else {
            'session'
        }

        Write-Host (
            '[+] Existing tracked data: {0:N2} GiB' -f
            ($initialBytes / 1GB)
        )

        Write-Host "[+] Progress mode: $progressMode"
        Write-Host "[+] Scan interval: $ProgressSampleSeconds seconds"
        Start-Sleep -Seconds 1

        Show-FlowerLoading `
            -Message 'Starting resumable download engine...' `
            -Cycles 3

        Start-Sleep -Seconds 1

        $timestamp = Get-Date -Format 'yyyyMMdd-HHmmss'
        $stdoutLog = Join-Path $env:TEMP (
            "flower-pack-$PackId-$timestamp.stdout.log"
        )
        $stderrLog = Join-Path $env:TEMP (
            "flower-pack-$PackId-$timestamp.stderr.log"
        )

        $arguments = @(
            '-NoProfile',
            '-ExecutionPolicy', 'Bypass',
            '-File', ('"{0}"' -f $Launcher),
            'install',
            [string]$PackId,
            '--yes'
        )

        if ([string]::IsNullOrWhiteSpace($env:FLOWER_PACK_RETRIES)) {
            $env:FLOWER_PACK_RETRIES = '12'
        }

        $startParameters = @{
            FilePath               = 'pwsh'
            ArgumentList           = $arguments
            WorkingDirectory       = $FlowerPackRoot
            PassThru               = $true
            NoNewWindow            = $true
            RedirectStandardOutput = $stdoutLog
            RedirectStandardError  = $stderrLog
        }

        $process = Start-Process @startParameters

        Write-Host ''
        Write-Host '[+] Pack download is active.'
        Write-Host "[+] Output log: $stdoutLog"
        Write-Host "[+] Error log:  $stderrLog"
        Write-Host ''

        try {
            $Host.UI.RawUI.CursorVisible = $false
        }
        catch {
        }

        $nextSample = Get-Date

        # initialization / waiting bar so the user sees activity
        # before the first measured sample completes.
        $spinnerChars = '|/-\'
        $spinnerIndex = 0
        $warmupSeconds = [math]::Min(
            $ProgressSampleSeconds,
            3
        )
        $warmupEnd = (Get-Date).AddSeconds($warmupSeconds)

        while (
            (-not $process.HasExited) -and
            ((Get-Date) -lt $warmupEnd)
        ) {
            $spinner = $spinnerChars[
                $spinnerIndex % $spinnerChars.Length
            ]
            $spinnerIndex++

            Write-Host -NoNewline (
                "`r{0}[2K{1}[38;5;195m[{2}] Pack download initializing..." -f
                $Esc,
                $Esc,
                $spinner
            )

            Start-Sleep -Milliseconds 120
            $process.Refresh()
        }

        if (-not $process.HasExited) {
            Write-Host (
                "`r{0}[2K{0}[38;5;195m[+] Pack download initialized.{1}" -f
                $Esc,
                $Reset
            )
        }

        while (-not $process.HasExited) {
            $now = Get-Date

            if ($now -ge $nextSample) {
                $state = Get-TrackedState `
                    -Path $storeRoot `
                    -TrackedNames $plan.TrackedFileNames

                $sampleSeconds = [math]::Max(
                    0.1,
                    ($now - $previousSampleTime).TotalSeconds
                )

                $intervalBytes = [math]::Max(
                    [int64]0,
                    [int64]($state.Bytes - $previousBytes)
                )

                $currentMiBs = (
                    $intervalBytes / 1MB
                ) / $sampleSeconds

                if ($smoothedMiBs -le 0) {
                    $smoothedMiBs = $currentMiBs
                }
                else {
                    $smoothedMiBs = (
                        0.35 * $currentMiBs
                    ) + (
                        0.65 * $smoothedMiBs
                    )
                }

                $sessionBytes = [math]::Max(
                    [int64]0,
                    [int64]($state.Bytes - $initialBytes)
                )

                $elapsedSeconds = [math]::Max(
                    1,
                    ($now - $startTime).TotalSeconds
                )

                $averageMiBs = (
                    $sessionBytes / 1MB
                ) / $elapsedSeconds

                $completedBytes = if (
                    $progressMode -eq 'registry'
                ) {
                    $state.Bytes
                }
                else {
                    $sessionBytes
                }

                $percent = [math]::Min(
                    100,
                    (
                        $completedBytes /
                        $plan.ExpectedBytes
                    ) * 100
                )

                $remainingBytes = [math]::Max(
                    [int64]0,
                    [int64]($plan.ExpectedBytes - $completedBytes)
                )

                $etaSeconds = if ($smoothedMiBs -gt 0.01) {
                    $remainingBytes / (
                        $smoothedMiBs * 1MB
                    )
                }
                else {
                    [double]::PositiveInfinity
                }

                $eta = Format-Duration `
                    -Seconds $etaSeconds

                $elapsed = Format-Duration `
                    -Seconds $elapsedSeconds

                $color = $Colors[
                    ([int]$elapsedSeconds) % $Colors.Count
                ]

                $glyph = $Glyphs[
                    ([int]$elapsedSeconds) % $Glyphs.Count
                ]

                $activeName = if (
                    [string]::IsNullOrWhiteSpace(
                        $state.ActiveFile
                    )
                ) {
                    'waiting for file activity'
                }
                else {
                    $state.ActiveFile
                }

                if ($activeName.Length -gt 48) {
                    $activeName = (
                        $activeName.Substring(0, 45) + '...'
                    )
                }

                $status = (
                    '{0}  {1,8:N2} MiB/s | ' +
                    'smooth {2,8:N2} | avg {3,8:N2} | ' +
                    '{4,7:N2}/{5:N2} GiB | ' +
                    '{6,6:N2}% | ETA {7} | {8}'
                ) -f
                    $glyph,
                    $currentMiBs,
                    $smoothedMiBs,
                    $averageMiBs,
                    ($completedBytes / 1GB),
                    $plan.ExpectedGiB,
                    $percent,
                    $eta,
                    $activeName

                Write-Host -NoNewline (
                    "`r{0}[2K{0}[38;5;{1}m{2}{3}" -f
                    $Esc,
                    $color,
                    $status,
                    $Reset
                )

                $previousBytes = $state.Bytes
                $previousSampleTime = $now
                $nextSample = $now.AddSeconds(
                    $ProgressSampleSeconds
                )
            }

            Start-Sleep -Seconds 1
            $process.Refresh()
        }

        $process.WaitForExit()

        Write-Host (
            "`r{0}[2K" -f $Esc
        )

        if ($process.ExitCode -ne 0) {
            Get-LogTail `
                -Paths @($stderrLog, $stdoutLog) `
                -Lines 30

            throw (
                "Flower Pack exited with code " +
                "$($process.ExitCode)."
            )
        }

        Start-Sleep -Seconds 1

        Show-FlowerLoading `
            -Message 'Finalizing installation state...' `
            -Cycles 2

        Start-Sleep -Seconds 1

        $finalState = Get-TrackedState `
            -Path $storeRoot `
            -TrackedNames $plan.TrackedFileNames

        $totalSeconds = [math]::Max(
            1,
            ((Get-Date) - $startTime).TotalSeconds
        )

        $downloadedThisRun = [math]::Max(
            [int64]0,
            [int64]($finalState.Bytes - $initialBytes)
        )

        $finalAverageMiBs = (
            $downloadedThisRun / 1MB
        ) / $totalSeconds

        Write-Host ''
        Write-Host (
            "{0}[38;5;195m" +
            "[+] Pack $PackId installation completed." +
            "{1}" -f
            $Esc,
            $Reset
        )

        Write-Host (
            '[+] Downloaded this run: {0:N2} GiB' -f
            ($downloadedThisRun / 1GB)
        )

        Write-Host (
            '[+] Tracked pack data: {0:N2} GiB' -f
            ($finalState.Bytes / 1GB)
        )

        Write-Host (
            '[+] Average rate: {0:N2} MiB/s' -f
            $finalAverageMiBs
        )

        Write-Host (
            '[+] Elapsed: {0}' -f
            (Format-Duration -Seconds $totalSeconds)
        )

        Write-Host "[+] Model root: $ModelRoot"
        Write-Host "[+] Output log: $stdoutLog"
        Write-Host ''
    }
    catch {
        Write-Host (
            "`r{0}[2K" -f $Esc
        )

        Write-Host ''
        Write-Host (
            "{0}[38;5;210m" +
            "[ERROR] Pack $PackId installation failed." +
            "{1}" -f
            $Esc,
            $Reset
        )

        Write-Host "  $($_.Exception.Message)"
        Write-Host ''

        if ($null -ne $process -and -not $process.HasExited) {
            try {
                $process.Kill($true)
            }
            catch {
            }
        }
    }
    finally {
        try {
            $Host.UI.RawUI.CursorVisible = $oldCursor
        }
        catch {
        }
    }
}
