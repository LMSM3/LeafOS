# LeafOS root launcher.
# Uses the automatic $args variable instead of an explicit param block so that
# subcommand flags such as --out and --error are not mistaken for PowerShell
# common parameters (-OutVariable, -ErrorVariable, etc.).
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# Ensure UTF-8 console I/O so glyphs and non-ASCII status text render correctly
# on Windows hosts whose default code page differs from UTF-8.
try {
    [System.Console]::OutputEncoding = [System.Text.Encoding]::UTF8
    [System.Console]::InputEncoding  = [System.Text.Encoding]::UTF8
    $OutputEncoding                  = [System.Text.Encoding]::UTF8
} catch {
    # Encoding helpers may fail in constrained hosts; continue gracefully.
}

$root = $PSScriptRoot
if ($args.Count -gt 0 -and $args[0] -eq 'validate-root') {
	& (Join-Path $root 'Validate-RootContract.ps1')
	if ($?) { exit 0 }
	exit 1
}

& (Join-Path $root 'PowerShell-Version\leaf.ps1') @args
exit $LASTEXITCODE
