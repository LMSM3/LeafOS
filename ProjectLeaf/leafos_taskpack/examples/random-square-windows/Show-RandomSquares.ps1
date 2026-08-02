[CmdletBinding(SupportsShouldProcess)]
param(
	[ValidateRange(1, 100)]
	[int]$Count = 100,

	[ValidateRange(0, 60)]
	[int]$DelaySeconds = 1,

	[ValidateRange(0, 3600)]
	[int]$HoldSeconds = 5,

	[switch]$ConfirmLaunch,
	[switch]$Child,

	[ValidateRange(16, 231)]
	[int]$Color = 16
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Write-SquareGrid {
	param(
		[ValidateRange(16, 231)]
		[int]$ColorIndex,

		[ValidateRange(0, 3600)]
		[int]$Seconds
	)

	$escape = [char]27
	$square = "$escape[48;5;${ColorIndex}m  $escape[0m"
	for ($row = 0; $row -lt 10; $row++) {
		Write-Host (($square * 10))
	}
	Write-Host "Color index: $ColorIndex"

	if ($Seconds -gt 0) {
		Start-Sleep -Seconds $Seconds
	}
}

if ($Child) {
	Write-SquareGrid -ColorIndex $Color -Seconds $HoldSeconds
	exit 0
}

if (-not $ConfirmLaunch) {
	Write-Host "Preview only: this skill would launch $Count terminal windows at one-second intervals."
	Write-Host "Each window displays 100 squares in a random ANSI colour and remains open for $HoldSeconds second(s)."
	Write-Host "Re-run with -ConfirmLaunch to launch the windows, or use -WhatIf for PowerShell preview semantics."
	exit 0
}

$pwsh = Get-Command pwsh -ErrorAction SilentlyContinue
if (-not $pwsh) {
	$pwsh = Get-Command powershell -ErrorAction SilentlyContinue
}
if (-not $pwsh) {
	throw 'Neither pwsh nor powershell was found.'
}

$scriptPath = $MyInvocation.MyCommand.Path
$random = [Random]::new()

for ($index = 1; $index -le $Count; $index++) {
	$colorIndex = $random.Next(16, 232)
	$arguments = @(
		'-NoProfile'
		'-ExecutionPolicy'
		'Bypass'
		'-File'
		$scriptPath
		'-Child'
		'-Color'
		$colorIndex
		'-HoldSeconds'
		$HoldSeconds
	)

	if ($PSCmdlet.ShouldProcess("terminal window $index of $Count", "launch random square grid")) {
		Start-Process -FilePath $pwsh.Source -ArgumentList $arguments -WindowStyle Normal | Out-Null
	}

	if ($index -lt $Count -and $DelaySeconds -gt 0) {
		Start-Sleep -Seconds $DelaySeconds
	}
}

Write-Host "Launched $Count terminal window(s)."
