#!/usr/bin/env pwsh
<#
Create a one-shot handoff bundle from the PowerShell version surface.

Examples:

  .\oneshot.ps1 --oneshot .. C:\R\LeafOS-OneShot
  .\oneshot.ps1
#>

[CmdletBinding()]
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Args = @()
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$Leaf = Join-Path $PSScriptRoot 'leaf.ps1'
& $Leaf oneshot @Args
if ($?) { exit 0 }
exit 1
