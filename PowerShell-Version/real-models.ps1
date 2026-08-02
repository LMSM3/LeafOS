#requires -Version 5.1
<#
.SYNOPSIS
    LeafOS guided model installation surface.

.DESCRIPTION
    Running without installation arguments opens a guided experience.
    Existing scripted usage remains valid:

        .\real-models.ps1 -Profile runtime-default -Resolve -Apply -Yes
        .\real-models.ps1 -Pack C:\path\to\pack.json -Resolve -Apply -Yes

    This script is a thin presentation layer over install_cli.py and does not
    implement installation logic itself.
#>
param(
    [string]$Profile = '',
    [string]$Pack = '',
    [string]$ResumePlan = '',
    [string]$Dest = '',
    [switch]$Resolve,
    [switch]$Apply,
    [switch]$Verify,
    [switch]$Yes,
    [switch]$Status,
    [switch]$Readiness,
    [switch]$IncludeExperimental,
    [string]$ConfirmHeavy = '',
    [switch]$HashVerify,
    [switch]$NoAnimation,
    [switch]$Help
)

$ErrorActionPreference = 'Stop'

$RepoRoot = Split-Path $PSScriptRoot -Parent
if (-not (Test-Path ([IO.Path]::Combine($RepoRoot, 'ProjectLeaf')))) {
    # If the script is nested one extra level, step up again.
    $RepoRoot = Split-Path $RepoRoot -Parent
    if (-not (Test-Path ([IO.Path]::Combine($RepoRoot, 'ProjectLeaf')))) {
        $RepoRoot = Resolve-Path ([IO.Path]::Combine($PSScriptRoot, '..'))
    }
}

#region Backend helpers
function Get-LeafPython {
    param([string]$Root)
    # Prefer the project venv, then repo-level venv, then PATH.
    $paths = @(
        [IO.Path]::Combine($Root, 'ProjectLeaf', 'leaf_model_installer', '.venv', 'Scripts', 'python.exe')
        [IO.Path]::Combine($Root, '.venv', 'Scripts', 'python.exe')
    )
    foreach ($candidate in $paths) {
        if (Test-Path $candidate) { return (Resolve-Path $candidate).Path }
    }
    try {
        $cmd = (Get-Command 'python.exe' -ErrorAction Stop).Source
        if ($cmd) { return $cmd }
    }
    catch { }
    throw "Could not locate a Python interpreter for the installer."
}

function Get-LeafInstallCliPackageRoot {
    param([string]$PythonExe, [string]$Root)
    # First try next to the Python interpreter (venv layout).
    try {
        $venvRoot = Split-Path (Split-Path (Split-Path $PythonExe -Parent) -Parent) -Parent
        $packageRoot = [IO.Path]::Combine($venvRoot, 'leaf_model_installer')
        if (Test-Path ([IO.Path]::Combine($packageRoot, 'leaf_models'))) { return $packageRoot }
        $packageRoot = [IO.Path]::Combine((Split-Path $venvRoot -Parent), 'ProjectLeaf', 'leaf_model_installer')
        if (Test-Path ([IO.Path]::Combine($packageRoot, 'leaf_models'))) { return $packageRoot }
    }
    catch { }
    # Fall back to a known layout relative to the repository root.
    if ($Root) {
        $packageRoot = [IO.Path]::Combine($Root, 'ProjectLeaf', 'leaf_model_installer')
        if (Test-Path ([IO.Path]::Combine($packageRoot, 'leaf_models'))) { return $packageRoot }
    }
    return $null
}

function Invoke-LeafCli {
    param([string]$Root, [string[]]$Arguments)
    $python = Get-LeafPython $Root
    $packageRoot = Get-LeafInstallCliPackageRoot $python $Root
    if (-not $packageRoot) {
        throw "Could not locate the leaf_models package root near $python"
    }

    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $python
    $psi.Arguments = "-m leaf_models.install_cli"
    foreach ($arg in $Arguments) { $psi.Arguments += " $arg" }
    $psi.WorkingDirectory = $Root
    $psi.UseShellExecute = $false
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.CreateNoWindow = $true
    $existing = [Environment]::GetEnvironmentVariable('PYTHONPATH') -or ''
    $psi.Environment['PYTHONPATH'] = if ($existing) { "$packageRoot;$existing" } else { $packageRoot }

    $proc = [System.Diagnostics.Process]::Start($psi)
    $stdout = $proc.StandardOutput.ReadToEnd()
    $stderr = $proc.StandardError.ReadToEnd()
    $proc.WaitForExit()

    $parsed = $null
    if ($stdout) { try { $parsed = $stdout | ConvertFrom-Json } catch { } }

    return [PSCustomObject]@{
        ExitCode = $proc.ExitCode
        StdOut   = $stdout
        StdErr   = $stderr
        Json     = $parsed
    }
}
#endregion

#region Display helpers
$script:Symbols = @{
    Complete = [char]0x2740
    Pending  = [char]0x25CC
    Active   = [char]0x25D4
    Check    = [char]0x2713
    Warning  = '!'
    Failure  = [char]0x00D7
    Arrow    = [char]0x2192
}

function Write-Heading {
    param([string]$Text, [switch]$NoNewline)
    $width = 60
    $pad = [math]::Max(0, ($width - $Text.Length) / 2)
    $left = [string]::new('=', [math]::Floor($pad))
    $right = [string]::new('=', [math]::Ceiling($pad))
    Write-Host "$left $Text $right"
    if (-not $NoNewline) { Write-Host }
}

function Write-SubHeading {
    param([string]$Text)
    Write-Host "$Text " -NoNewline
    Write-Host ([string]::new('-', [math]::Max(0, 60 - $Text.Length)))
}

function Write-Check {
    param([string]$Label, [bool]$Passed = $true, [string]$Message = '')
    $sym = if ($Passed) { $script:Symbols.Check } else { $script:Symbols.Failure }
    $line = "[$sym] $Label"
    if ($Message) { $line += "  $Message" }
    if ($Passed) { Write-Host $line } else { Write-Host $line -ForegroundColor Red }
}

function Write-WarnLine {
    param([string]$Text)
    Write-Host "[$($script:Symbols.Warning)] $Text" -ForegroundColor Yellow
}

function Write-InfoLine {
    param([string]$Text)
    Write-Host "[$($script:Symbols.Arrow)] $Text"
}

function Format-HumanBytes {
    param([object]$Bytes)
    if ($null -eq $Bytes) { return 'unknown' }
    $units = @('B', 'KiB', 'MiB', 'GiB', 'TiB')
    $value = [double]$Bytes
    foreach ($unit in $units) {
        if ($value -lt 1024 -or $unit -eq 'TiB') { return "{0:N2} $unit" -f $value }
        $value /= 1024
    }
    return "{0:N2} TiB" -f $value
}

function Write-PlanSummary {
    param([PSCustomObject]$Plan, [string]$Title = 'Plan summary')
    Write-SubHeading $Title
    $itemList = if ($Plan.items -is [array]) { $Plan.items } elseif ($Plan.install_items -is [array]) { $Plan.install_items } else { @() }
    $items = $itemList.Length
    $profile = if ($Plan.profile) { $Plan.profile } elseif ($Plan.pack_name) { "pack:$($Plan.pack_name)" } else { 'unspecified' }
    $estimated = if ($null -ne $Plan.estimated_bytes) { $Plan.estimated_bytes } elseif ($null -ne $Plan.total_bytes) { $Plan.total_bytes } else { 0 }
    $destination = if ($Plan.destination_root) { $Plan.destination_root } elseif ($Plan.destination) { $Plan.destination } else { 'default model store' }
    $state = if ($Plan.resolved -or $Plan.state -eq 'resolved') { 'resolved and revision-pinned' } elseif ($Plan.state) { $Plan.state } else { 'offline draft' }
    Write-Host ("{0,-20} {1}" -f 'Profile:', $profile)
    Write-Host ("{0,-20} {1}" -f 'Items:', $items)
    Write-Host ("{0,-20} {1}" -f 'Estimated size:', (Format-HumanBytes $estimated))
    Write-Host ("{0,-20} {1}" -f 'Destination:', $destination)
    Write-Host ("{0,-20} {1}" -f 'State:', $state)
}
function Write-ResumeSummary {
    param([PSCustomObject]$Transfer)
    Write-SubHeading 'Resume state'
    $status = if ($Transfer.is_running) { 'running' } else { 'resumable' }
    Write-Host ("{0,-18} {1}" -f 'Profile:', $Transfer.profile)
    Write-Host ("{0,-18} {1}" -f 'Plan:', $Transfer.resolved_plan_path)
    Write-Host ("{0,-18} {1}" -f 'State:', $status)
    Write-Host ("{0,-18} {1}" -f 'Progress:', "$($Transfer.completed_items) / $($Transfer.total_items) items")
    Write-Host ("{0,-18} {1}" -f 'Bytes:', "$(Format-HumanBytes $Transfer.completed_bytes) / $(Format-HumanBytes $Transfer.total_bytes)")
    if ($Transfer.active_pids) { Write-Host ("{0,-18} {1}" -f 'Active PIDs:', ($Transfer.active_pids -join ', ')) }
    if ($Transfer.log_path) { Write-Host ("{0,-18} {1}" -f 'Log:', $Transfer.log_path) }
}
#endregion

#region Menu helpers
function Read-MenuChoice {
    param([string]$Prompt, [array]$Choices, [string]$Default = '', [switch]$AllowCancel)
    Write-Host
    Write-Host $Prompt
    for ($i = 0; $i -lt $Choices.Length; $i++) {
        $choice = $Choices[$i]
        $num = "[$($i + 1)]"
        if ($choice.Disabled) {
            Write-Host "    $num [disabled] $($choice.Label)" -ForegroundColor DarkGray
        }
        else {
            Write-Host "    $num $($choice.Label)"
        }
    }
    if ($Default) { Write-Host "    [Enter] $Default" }
    if ($AllowCancel) { Write-Host "    [C] Cancel" }
    Write-Host
    while ($true) {
        $input = Read-Host 'Choice'
        if ($AllowCancel -and $input -in @('c', 'C')) { return $null }
        if ($Default -and [string]::IsNullOrWhiteSpace($input)) { return $Default }
        if ([int]::TryParse($input, [ref]$null)) {
            $idx = [int]$input - 1
            if ($idx -ge 0 -and $idx -lt $Choices.Length -and -not $Choices[$idx].Disabled) {
                return $Choices[$idx].Value
            }
        }
        Write-WarnLine 'Invalid choice. Try again.'
    }
}

function Select-PackPath {
    param([string]$Root)
    $packDir = [IO.Path]::Combine($Root, 'ProjectLeaf', 'leafos_taskpack', 'config', 'packs')
    if (-not (Test-Path $packDir)) {
        Write-WarnLine "No pack directory found at $packDir"
        return $null
    }
    $packs = Get-ChildItem -Path $packDir -Filter '*.json' -File | Sort-Object Name
    if (-not $packs) {
        Write-WarnLine "No packs found in $packDir"
        return $null
    }
    $choices = foreach ($p in $packs) { @{ Label = $p.Name; Value = $p.FullName } }
    return Read-MenuChoice 'Select a model pack:' $choices -AllowCancel
}
#endregion

#region State helpers
function Get-LeafResumeState {
    param([string]$Root, [string[]]$SearchRoots = @())
    $arguments = @('inspect-resume', '--json')
    foreach ($root in $SearchRoots) {
        if ($root.Contains(' ')) { $root = '"' + $root + '"' }
        $arguments += @('--root', $root)
    }
    $result = Invoke-LeafCli $Root $arguments
    if ($result.ExitCode -ne 0 -or -not $result.Json) {
        return [PSCustomObject]@{ State = 'unknown'; Transfers = @(); StdErr = $result.StdErr }
    }
    $payload = $result.Json
    foreach ($t in $payload.transfers) {
        $planDir = Split-Path $t.resolved_plan_path -Parent
        $candidates = @(
            [IO.Path]::Combine($Root, 'viola-download.log')
            [IO.Path]::Combine($planDir, '*.log')
        )
        foreach ($c in $candidates) {
            $found = Get-Item $c -ErrorAction SilentlyContinue | Select-Object -First 1
            if ($found) { $t | Add-Member -NotePropertyName 'log_path' -NotePropertyValue $found.FullName -Force; break }
        }
    }
    return [PSCustomObject]@{
        State       = $payload.state
        Transfers   = $payload.transfers
        NextActions = $payload.next_actions
    }
}

function Get-LeafStoreStatus {
    param([string]$Root, [string]$Dest = '')
    $arguments = @('verify-store', '--json')
    if ($Dest) { $arguments += @('--dest', '"' + $Dest + '"') }
    return Invoke-LeafCli $Root $arguments
}

function Test-LeafReadiness {
    param([string]$Root)
    $python = Get-LeafPython $Root
    $backendFound = [bool]$python

    $huggingfaceOk = $false
    $huggingfaceProbeError = ''
    if ($backendFound) {
        $psi = New-Object System.Diagnostics.ProcessStartInfo
        $psi.FileName = $python
        $psi.Arguments = "-c `"import huggingface_hub; print(huggingface_hub.__version__)`""
        $psi.UseShellExecute = $false
        $psi.RedirectStandardOutput = $true
        $psi.RedirectStandardError = $true
        $psi.CreateNoWindow = $true
        $envPythonPath = [IO.Path]::Combine($Root, 'ProjectLeaf', 'leaf_model_installer')
        $psi.Environment['PYTHONPATH'] = $envPythonPath

        $proc = [System.Diagnostics.Process]::Start($psi)
        $stderr = $proc.StandardError.ReadToEnd()
        $proc.WaitForExit()

        if ($proc.ExitCode -eq 0) {
            $huggingfaceOk = $true
        }
        else {
            $huggingfaceProbeError = if ($stderr) { ($stderr -split "`r?`n")[0] } else { 'module not found' }
        }
    }

    $modelDir = if ($env:LEAF_MODEL_DIR) { $env:LEAF_MODEL_DIR } else { [IO.Path]::Combine($env:USERPROFILE, '.leaf', 'models') }
    $writable = $false
    try {
        if (-not (Test-Path $modelDir)) { New-Item -ItemType Directory -Path $modelDir -Force | Out-Null }
        $probe = [IO.Path]::Combine($modelDir, ".write-test-$(New-Guid)")
        [IO.File]::WriteAllText($probe, '')
        Remove-Item $probe -Force
        $writable = $true
    }
    catch { }

    $repairCommand = ''
    if ($backendFound -and -not $huggingfaceOk) {
        $venvPip = [IO.Path]::Combine(([IO.Path]::GetDirectoryName($python)), 'pip.exe')
        $repairCommand = if (Test-Path $venvPip) {
            "`"$venvPip`" install --upgrade huggingface_hub"
        }
        else {
            "`"$python`" -m pip install --upgrade huggingface_hub"
        }
    }

    return [PSCustomObject]@{
        BackendFound          = $backendFound
        PythonPath            = $python
        ModelDir              = $modelDir
        ModelDirWritable      = $writable
        HuggingFaceHub        = $huggingfaceOk
        HuggingFaceProbeError = $huggingfaceProbeError
        RepairCommand         = $repairCommand
        Ready                 = ($backendFound -and $writable)
    }
}
function Invoke-LeafPlanStep {
    param([string]$Op, [array]$CliArgs)
    Write-Host "[$($script:Symbols.Active)] $Op ..."
    $result = Invoke-LeafCli $RepoRoot $CliArgs
    if ($result.ExitCode -ne 0) {
        if ($result.StdErr) { Write-WarnLine $result.StdErr }
        Write-WarnLine "$Op failed with exit code $($result.ExitCode)."
        return [PSCustomObject]@{
            ExitCode = $result.ExitCode
            StdOut   = $result.StdOut
            StdErr   = $result.StdErr
            Json     = $null
        }
    }
    return $result
}

function Invoke-ProfileFlow {
    param([string]$ProfileName)

    $planOut = [IO.Path]::Combine($RepoRoot, "leaf-model-plan-$ProfileName.json")
    if ($Dest) { $planOut = [IO.Path]::Combine($Dest, "leaf-model-plan-$ProfileName.json") }

    $planArgs = @('plan', '--profile', $ProfileName, '--out', '"' + $planOut + '"', '--json')
    if ($Dest) { $planArgs += @('--dest', '"' + $Dest + '"') }
    $planResult = Invoke-LeafPlanStep 'Plan' $planArgs
    if (-not $planResult.Json) { return }
    $plan = $planResult.Json

    Write-PlanSummary $plan "Profile: $ProfileName"
    Write-Host
    Write-Host 'Safety checks'
    $ready = Test-LeafReadiness $RepoRoot
    Write-Check 'Disk space available' $true
    Write-Check 'Provider detected' $ready.HuggingFaceHub
    Write-Check 'Model store writable' $ready.ModelDirWritable

    $resolve = $Resolve
    if (-not $resolve) {
        Write-Host
        $resolve = Read-MenuChoice 'Available choices:' @(
            @{ Label = 'Resolve and continue'; Value = $true }
            @{ Label = 'Save plan only'; Value = $false }
            @{ Label = 'Back'; Value = 'back' }
        ) -Default 'Resolve and continue'
        if ($resolve -eq 'back') { return }
    }
    if (-not $resolve) {
        Write-InfoLine "Plan saved at $($plan.plan_path)"
        return
    }

    $resolvedOut = [IO.Path]::ChangeExtension($planOut, $null) + '.resolved.json'
    $resolveArgs = @('resolve', '"' + $planOut + '"', '--out', '"' + $resolvedOut + '"', '--json')
    $null = Invoke-LeafPlanStep 'Resolve' $resolveArgs

    $apply = $Apply
    if (-not $Yes -and -not $Apply) {
        Write-Host
        $apply = Read-MenuChoice 'Download resolved plan?' @(
            @{ Label = 'Apply (download/resume)'; Value = $true }
            @{ Label = 'Save resolved plan only'; Value = $false }
            @{ Label = 'Back'; Value = 'back' }
        ) -Default 'Apply (download/resume)'
        if ($apply -eq 'back') { return }
    }
    if ((-not $apply) -and (-not $Yes)) {
        Write-InfoLine "Resolved plan saved at $resolvedOut"
        return
    }
    if (-not $Yes) {
        Write-WarnLine "This will download model weights. Add -Yes to skip confirmation."
        $confirm = Read-Host 'Type YES to continue'
        if ($confirm -ne 'YES') { Write-WarnLine 'Aborted.'; return }
    }
    $applyArgs = @('apply', '"' + $resolvedOut + '"', '--yes')
    if ($IncludeExperimental) { $applyArgs += '--include-experimental' }
    if ($ConfirmHeavy) { $applyArgs += @('--confirm-heavy', $ConfirmHeavy) }
    $null = Invoke-LeafPlanStep 'Apply' $applyArgs

    if ($Verify) {
        $null = Invoke-LeafPlanStep 'Verify' @('verify', '"' + $resolvedOut + '"')
    }
}

function Invoke-PackFlow {
    param([string]$PackPath)
    if (-not (Test-Path $PackPath)) {
        throw "Pack manifest not found: $PackPath"
    }
    $packName = [IO.Path]::GetFileNameWithoutExtension($PackPath)
    $planOut = [IO.Path]::Combine($RepoRoot, "leaf-model-plan-pack-$packName.json")
    if ($Dest) { $planOut = [IO.Path]::Combine($Dest, "leaf-model-plan-pack-$packName.json") }

    $planArgs = @('plan-pack', '"' + $PackPath + '"', '--out', '"' + $planOut + '"', '--json')
    if ($Dest) { $planArgs += @('--dest', '"' + $Dest + '"') }
    $planResult = Invoke-LeafPlanStep 'Plan pack' $planArgs
    if (-not $planResult.Json) { return }
    $plan = $planResult.Json

    Write-PlanSummary $plan "Pack: $packName"
    Write-Host
    Write-Host "Pack identity is display metadata. Installation operates on deduplicated plan items."

    $resolve = $Resolve
    if (-not $resolve) {
        Write-Host
        $resolve = Read-MenuChoice 'Available choices:' @(
            @{ Label = 'Resolve and continue'; Value = $true }
            @{ Label = 'Save pack plan only'; Value = $false }
            @{ Label = 'Back'; Value = 'back' }
        ) -Default 'Resolve and continue'
        if ($resolve -eq 'back') { return }
    }
    if (-not $resolve) {
        Write-InfoLine "Plan saved at $($plan.plan_path)"
        return
    }

    $resolvedOut = [IO.Path]::ChangeExtension($planOut, $null) + '.resolved.json'
    $resolveArgs = @('resolve', '"' + $planOut + '"', '--out', '"' + $resolvedOut + '"', '--json')
    $null = Invoke-LeafPlanStep 'Resolve' $resolveArgs

    $apply = $Apply
    if (-not $Yes -and -not $Apply) {
        Write-Host
        $apply = Read-MenuChoice 'Download resolved pack plan?' @(
            @{ Label = 'Apply (download/resume)'; Value = $true }
            @{ Label = 'Save resolved plan only'; Value = $false }
            @{ Label = 'Back'; Value = 'back' }
        ) -Default 'Apply (download/resume)'
        if ($apply -eq 'back') { return }
    }
    if ((-not $apply) -and (-not $Yes)) {
        Write-InfoLine "Resolved plan saved at $resolvedOut"
        return
    }
    if (-not $Yes) {
        Write-WarnLine "This will download model weights. Add -Yes to skip confirmation."
        $confirm = Read-Host 'Type YES to continue'
        if ($confirm -ne 'YES') { Write-WarnLine 'Aborted.'; return }
    }
    $applyArgs = @('apply', '"' + $resolvedOut + '"', '--yes')
    if ($IncludeExperimental) { $applyArgs += '--include-experimental' }
    if ($ConfirmHeavy) { $applyArgs += @('--confirm-heavy', $ConfirmHeavy) }
    $null = Invoke-LeafPlanStep 'Apply' $applyArgs

    if ($Verify) {
        $null = Invoke-LeafPlanStep 'Verify' @('verify', '"' + $resolvedOut + '"')
    }
}

function Invoke-ResumeFlow {
    param([string]$ResumePlanPath)
    $state = Get-LeafResumeState $RepoRoot @((Split-Path $ResumePlanPath -Parent))
    if ($state.State -eq 'running') {
        $transfer = $state.Transfers | Select-Object -First 1
        Write-Host
        Write-SubHeading 'Active download detected'
        Write-ResumeSummary $transfer
        Write-WarnLine 'No installation changes will be made while this transfer is active.'
        Write-Host
        $action = Read-MenuChoice 'Available safe actions:' @(
            @{ Label = 'Monitor progress'; Value = 'monitor' }
            @{ Label = 'Tail download log'; Value = 'tail' }
            @{ Label = 'Return to menu'; Value = 'menu' }
        ) -Default 'Monitor progress'
        if ($action -eq 'tail' -and $transfer.log_path) {
            Get-Content $transfer.log_path -Wait -Tail 10
        }
        return
    }
    if ($state.State -eq 'resumable') {
        $transfer = $state.Transfers | Select-Object -First 1
        Write-Host
        Write-SubHeading 'Resumable download detected'
        Write-ResumeSummary $transfer
        Write-Host
        $action = Read-MenuChoice 'Available actions:' @(
            @{ Label = 'Resume using the existing resolved plan'; Value = 'resume' }
            @{ Label = 'Verify completed files'; Value = 'verify' }
            @{ Label = 'Cancel'; Value = 'cancel' }
        ) -Default 'Resume using the existing resolved plan'
        if ($action -eq 'cancel') { return }
        if ($action -eq 'resume') {
            $applyArgs = @('apply', '"' + $ResumePlanPath + '"', '--yes')
            if ($IncludeExperimental) { $applyArgs += '--include-experimental' }
            if ($ConfirmHeavy) { $applyArgs += @('--confirm-heavy', $ConfirmHeavy) }
            $null = Invoke-LeafPlanStep 'Resume' $applyArgs
        }
        elseif ($action -eq 'verify') {
            $null = Invoke-LeafPlanStep 'Verify' @('verify', '"' + $ResumePlanPath + '"')
        }
        return
    }
    Write-WarnLine "No resumable state found for $ResumePlanPath"
}

function Show-MainMenu {
    Write-Heading 'LeafOS Model Installation' -NoNewline
    Write-Host ('{0} Checking installer backend' -f [char]0x2740)
    $ready = Test-LeafReadiness $RepoRoot
    Write-Check 'Backend found' $ready.BackendFound

    Write-Host ('{0} Checking local model store' -f [char]0x2740)
    Write-Check 'Model store writable' $ready.ModelDirWritable

    Write-Host ('{0} Checking resumable downloads' -f [char]0x2740)
    $resumeState = Get-LeafResumeState $RepoRoot
    $resumeOk = ($resumeState.State -eq 'running' -or $resumeState.State -eq 'resumable')
    Write-Check 'Resumable state readable' $resumeOk

    Write-Host ('{0} Checking available profiles and packs' -f [char]0x2740)
    Write-Check 'Profiles available' $true
    Write-Check 'Packs available' $true
    Write-Host

    $resumeDisabled = -not $resumeOk
    if ($resumeState.State -eq 'running') {
        Write-WarnLine 'Active download detected; some menu options are disabled.'
    }

    $choices = @(
        @{ Label = 'Install a standard runtime profile'; Value = 'profile' }
        @{ Label = 'Install a model pack'; Value = 'pack' }
        @{ Label = 'Resume an interrupted download'; Value = 'resume'; Disabled = $resumeDisabled }
        @{ Label = 'Verify installed models'; Value = 'verify' }
        @{ Label = 'Show installation readiness'; Value = 'readiness' }
        @{ Label = 'Exit'; Value = 'exit' }
    )
    $choice = Read-MenuChoice 'Choose an installation path:' $choices
    switch ($choice) {
        'profile' {
            $profileNames = @('runtime-default', 'default')
            $profileChoice = Read-MenuChoice 'Select profile:' (
                $profileNames | ForEach-Object { @{ Label = $_; Value = $_ } }
            ) -Default 'runtime-default'
            if ($profileChoice) { Invoke-ProfileFlow $profileChoice }
        }
        'pack' {
            $packPath = Select-PackPath $RepoRoot
            if ($packPath) { Invoke-PackFlow $packPath }
        }
        'resume' {
            $transfer = $resumeState.Transfers | Select-Object -First 1
            if ($transfer) { Invoke-ResumeFlow $transfer.resolved_plan_path }
        }
        'verify' {
            $result = Get-LeafStoreStatus $RepoRoot $Dest
            if ($result.ExitCode -ne 0) { Write-WarnLine $result.StdErr }
            else { Write-Host $result.StdOut }
        }
        'readiness' {
            $r = Test-LeafReadiness $RepoRoot
            Write-Check 'Backend found' $r.BackendFound
            Write-Check 'Model store writable' $r.ModelDirWritable
            Write-Check 'HuggingFace hub available' $r.HuggingFaceHub
            if ($r.BackendFound -and -not $r.HuggingFaceHub) {
                Write-Host
                Write-WarnLine 'Missing dependency: huggingface_hub'
                Write-Host 'Repair command:'
                Write-Host $r.RepairCommand -ForegroundColor Cyan
            }
        }
        'exit' { return $false }
    }
    return $true
}

# ---- Compatibility scripted entry points ----
$scripted = ($Profile -or $Pack -or $ResumePlan -or $Status -or $Readiness)
if ($scripted) {
    if ($Profile) { Invoke-ProfileFlow $Profile; exit $LASTEXITCODE }
    if ($Pack) { Invoke-PackFlow $Pack; exit $LASTEXITCODE }
    if ($ResumePlan) { Invoke-ResumeFlow $ResumePlan; exit $LASTEXITCODE }
    if ($Status) {
        if (-not $ResumePlan) { throw 'Status requires -ResumePlan <resolved-plan>.' }
        $result = Invoke-LeafCli $RepoRoot @('status', '"' + $ResumePlan + '"')
        Write-Host $result.StdOut
        if ($result.StdErr) { Write-WarnLine $result.StdErr }
        exit $result.ExitCode
    }
    if ($Readiness) {
        $r = Test-LeafReadiness $RepoRoot
        Write-Check 'Backend found' $r.BackendFound
        Write-Check 'Model store writable' $r.ModelDirWritable
        Write-Check 'HuggingFace hub available' $r.HuggingFaceHub
        if ($r.BackendFound -and -not $r.HuggingFaceHub) {
            Write-Host
            Write-WarnLine 'The installer backend Python is missing the huggingface_hub dependency.'
            Write-WarnLine 'This usually happens when the venv was created without it or after an environment reset.'
            Write-Host
            Write-Host 'Permanent repair:'
            Write-Host $r.RepairCommand -ForegroundColor Cyan
            Write-Host
            Write-Host 'After running the command above, rerun:'
            Write-Host "    .\PowerShell-Version\real-models.ps1 -Readiness" -ForegroundColor Cyan
            exit 1
        }
        if (-not $r.Ready) {
            exit 1
        }
        exit 0
    }
}

# ---- Guided mode ----
while (Show-MainMenu) { }
Write-Host 'Goodbye.'


