# Reusable PowerShell 5-compatible host resolver for LeafOS launchers.
[CmdletBinding()]
param(
    [int]$MinimumMajor = 5,
    [switch]$AllowCurrent
)

function Resolve-LeafPowerShellHost {
    [CmdletBinding()]
    param(
        [int]$MinimumMajor = 5,
        [switch]$AllowCurrent
    )

    $candidates = New-Object System.Collections.Generic.List[object]
    $seen = @{}
    function Add-Candidate {
        param([string]$Path, [string]$Source)
        if (-not $Path) { return }
        try { $fullPath = [IO.Path]::GetFullPath($Path) } catch { $fullPath = $Path }
        if ($seen.ContainsKey($fullPath.ToLowerInvariant())) { return }
        if (-not (Test-Path -LiteralPath $fullPath -PathType Leaf)) { return }
        $seen[$fullPath.ToLowerInvariant()] = $true
        $candidates.Add([pscustomobject]@{ path = $fullPath; source = $Source })
    }

    if ($AllowCurrent -and $PSVersionTable.PSVersion.Major -ge $MinimumMajor) {
        try {
            Add-Candidate -Path ([Diagnostics.Process]::GetCurrentProcess().MainModule.FileName) -Source 'current-process'
        } catch { }
    }
    foreach ($name in @('pwsh', 'pwsh.exe', 'powershell', 'powershell.exe')) {
        foreach ($command in @(Get-Command $name -CommandType Application -All -ErrorAction SilentlyContinue)) {
            Add-Candidate -Path $command.Source -Source "PATH:$name"
        }
    }
    foreach ($known in @(
        $(if ($env:ProgramFiles) { Join-Path $env:ProgramFiles 'PowerShell\7\pwsh.exe' }),
        $(if ($env:ProgramFiles) { Join-Path $env:ProgramFiles 'PowerShell\7-preview\pwsh.exe' }),
        $(if ($env:LOCALAPPDATA) { Join-Path $env:LOCALAPPDATA 'Microsoft\WindowsApps\pwsh.exe' }),
        $(if ($env:WINDIR) { Join-Path $env:WINDIR 'System32\WindowsPowerShell\v1.0\powershell.exe' })
    )) {
        Add-Candidate -Path $known -Source 'known-location'
    }
    try {
        foreach ($item in @(Get-ChildItem 'HKLM:\SOFTWARE\Microsoft\PowerShellCore\InstalledVersions' -ErrorAction Stop)) {
            $installLocation = (Get-ItemProperty $item.PSPath -ErrorAction SilentlyContinue).InstallLocation
            if ($installLocation) { Add-Candidate -Path (Join-Path $installLocation 'pwsh.exe') -Source 'registry' }
        }
    } catch { }

    # EncodedCommand avoids the quoting differences between powershell.exe,
    # pwsh.exe, Windows process launch, MSYS, and WSL interop. Both Windows
    # PowerShell and PowerShell use UTF-16LE for -EncodedCommand.
    $probeText = '$edition = if ($PSVersionTable.ContainsKey("PSEdition")) { $PSVersionTable.PSEdition } else { "Desktop" }; $PSVersionTable.PSVersion.ToString() + "|" + $edition'
    $probeCommand = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($probeText))
    $probes = New-Object System.Collections.Generic.List[object]
    foreach ($candidate in $candidates) {
        try {
            $raw = & $candidate.path -NoLogo -NoProfile -NonInteractive -EncodedCommand $probeCommand 2>$null
            $exitCode = $LASTEXITCODE
            $parts = "$raw".Trim() -split '\|', 2
            $version = [version]("$($parts[0])")
            $probe = [pscustomobject]@{
                command = $candidate.path
                version = $version.ToString()
                edition = if ($parts.Count -gt 1) { $parts[1] } else { 'Desktop' }
                source = $candidate.source
                usable = ($exitCode -eq 0 -and $version.Major -ge $MinimumMajor)
            }
            $probes.Add($probe)
            if ($probe.usable) { return $probe }
        } catch {
            $probes.Add([pscustomobject]@{
                command = $candidate.path; version = '0.0'; edition = 'unknown'
                source = $candidate.source; usable = $false
            })
        }
    }
    $attempted = @($probes | ForEach-Object { $_ })
    return [pscustomobject]@{
        command = ''; version = '0.0'; edition = 'missing'; source = 'none'; usable = $false
        attempted = $attempted
    }
}

if ($MyInvocation.InvocationName -ne '.') {
    Resolve-LeafPowerShellHost -MinimumMajor $MinimumMajor -AllowCurrent:$AllowCurrent |
        ConvertTo-Json -Depth 5 -Compress
}
