#Requires -Version 7.0
#Requires -PSEdition Core
[CmdletBinding()]
param(
	[switch]$Turbo,
	[int]$MaxRestarts = 10
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$repoRoot    = 'C:\R\LeafOS0.2.2'
$modelRoot   = Join-Path $repoRoot 'models'
$storeRoot   = Join-Path $modelRoot 'store'
$scriptDir   = Join-Path $repoRoot 'ProjectLeaf' 'install' 'windows'
$downloader  = Join-Path $scriptDir 'download-pack-aria2.py'
$wrapper     = Join-Path $scriptDir 'install-blue-banyan.ps1'
$logFile     = Join-Path $repoRoot 'download-completion.log'
$errLogFile  = Join-Path $repoRoot 'download-completion.err.log'
$stateFile   = Join-Path $repoRoot 'download-completion.state.json'

function Write-Log {
	param([string]$Message)
	$line = "[{0:u}] {1}" -f [DateTime]::UtcNow, $Message
	Add-Content -Path $logFile -Value $line
	Write-Host $line
}

# Ensure store exists
if (-not (Test-Path $storeRoot)) {
	New-Item -ItemType Directory -Path $storeRoot -Force | Out-Null
}

$state = @{ Restarts = 0; LastStart = $null; Completed = $false }
if (Test-Path $stateFile) {
	try { $state = Get-Content $stateFile | ConvertFrom-Json -AsHashtable } catch {}
}

$argList = @('--no-install')
if ($Turbo) { $argList += '--turbo' }

while (-not $state.Completed -and $state.Restarts -lt $MaxRestarts) {
	$state.LastStart = [DateTime]::UtcNow.ToString('u')
	$state.Restarts++
	$state | ConvertTo-Json | Set-Content $stateFile

	Write-Log "Starting download attempt $($state.Restarts) / $MaxRestarts"
	try {
		$psi = New-Object System.Diagnostics.ProcessStartInfo
		$psi.FileName               = 'python'
		$psi.Arguments              = '"' + $downloader + '" ' + ($argList -join ' ')
		$psi.WorkingDirectory       = $repoRoot
		$psi.RedirectStandardOutput = $true
		$psi.RedirectStandardError  = $true
		$psi.UseShellExecute        = $false
		$psi.CreateNoWindow         = $true

		$proc = [System.Diagnostics.Process]::Start($psi)
		if (-not $proc) { throw "Failed to start python downloader." }

		# Stream logs live
		$stdout = $proc.StandardOutput
		$stderr = $proc.StandardError
		while (-not $stdout.EndOfStream) {
			$line = $stdout.ReadLine()
			if ($line) {
				Add-Content -Path $logFile -Value $line
				Write-Host $line
			}
		}
		$stderrLines = $stderr.ReadToEnd()
		if ($stderrLines) {
			Add-Content -Path $errLogFile -Value $stderrLines
		}
		$proc.WaitForExit()

		if ($proc.ExitCode -eq 0) {
			$state.Completed = $true
			$state | ConvertTo-Json | Set-Content $stateFile
			Write-Log 'Download process reported success. Proceeding to final verification.'
		} else {
			Write-Log ("Downloader exited with code {0}. Will retry if allowed." -f $proc.ExitCode)
			Start-Sleep -Seconds 30
		}
	} catch {
		Write-Log "ERROR: $_"
		Start-Sleep -Seconds 30
	}
}

if (-not $state.Completed) {
	Write-Log "Download did not complete after $MaxRestarts attempts. Manual intervention required."
	exit 1
}

# Final verification / install via the permanent wrapper
Write-Log 'Running Flower Pack verification step via install-blue-banyan.ps1.'
try {
	& pwsh -NoProfile -ExecutionPolicy Bypass -File $wrapper *>&1 | Tee-Object -FilePath $logFile -Append
	Write-Log 'Final verification step finished.'
	exit 0
} catch {
	Write-Log "Final verification failed: $_"
	exit 1
}
