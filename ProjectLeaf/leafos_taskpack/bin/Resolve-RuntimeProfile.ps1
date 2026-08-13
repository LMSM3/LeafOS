#!/usr/bin/env pwsh
<#
.SYNOPSIS
	WO-019 tranche 019-A: PowerShell wrapper for the canonical runtime
	capability manifest resolver.

.DESCRIPTION
	This script MUST NOT re-implement profile resolution logic. Gate G2
	requires that Bash and PowerShell emit byte-equivalent canonical JSON
	for the same configuration; that is only guaranteed if both wrappers
	delegate to the single Python resolver
	(core/runtime/profile_resolver.py). This script locates a Python
	interpreter, forwards arguments, and streams stdout/stderr/exit-code
	through unchanged.

.PARAMETER Profile
	Named runtime profile (interactive|continual|overnight|compat-4k).

.PARAMETER Provider
	Provider identifier, e.g. llama.cpp.

.PARAMETER Model
	Resolved model id or file path.

.PARAMETER Ctx
	Command-line context-size override.

.PARAMETER Tokens
	Command-line max-output-tokens override.

.PARAMETER ReasoningBudget
	Command-line reasoning-budget override.

.PARAMETER ProfilesFile
	Path to config/runtime-profiles.json. Defaults to the file alongside
	this script's repo layout.

.EXAMPLE
	./Resolve-RuntimeProfile.ps1 -Profile continual -Provider llama.cpp -Model C:\models\gemma4.gguf
#>
[CmdletBinding()]
param(
	[Parameter(Mandatory = $true)]
	[string]$Profile,

	[Parameter(Mandatory = $true)]
	[string]$Provider,

	[string]$Model,

	[Nullable[int]]$Ctx,

	[Nullable[int]]$Tokens,

	[Nullable[int]]$ReasoningBudget,

	[string]$ProfilesFile
)

$ErrorActionPreference = "Stop"

$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$taskpackRoot = Split-Path -Parent $here
$resolverScript = Join-Path $taskpackRoot "core/runtime/profile_resolver.py"

if (-not $ProfilesFile) {
	$ProfilesFile = Join-Path $taskpackRoot "config/runtime-profiles.json"
}

if (-not (Test-Path $resolverScript)) {
	Write-Error "canonical profile resolver not found: $resolverScript"
	exit 2
}

$python = Get-Command python3 -ErrorAction SilentlyContinue
if (-not $python) {
	$python = Get-Command python -ErrorAction SilentlyContinue
}
if (-not $python) {
	Write-Error "no python3/python interpreter found on PATH"
	exit 2
}

$pyArgs = @(
	$resolverScript,
	"--profiles-file", $ProfilesFile,
	"--profile", $Profile,
	"--provider", $Provider
)

if ($Model) { $pyArgs += @("--model", $Model) }
if ($null -ne $Ctx) { $pyArgs += @("--ctx", $Ctx) }
if ($null -ne $Tokens) { $pyArgs += @("--tokens", $Tokens) }
if ($null -ne $ReasoningBudget) { $pyArgs += @("--reasoning-budget", $ReasoningBudget) }

& $python.Source @pyArgs
exit $LASTEXITCODE
