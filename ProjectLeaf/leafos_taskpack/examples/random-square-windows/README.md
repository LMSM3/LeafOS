# Random Square Windows Example Skill

This example launches one PowerShell terminal window per second. Each child
window displays a 10-by-10 grid of 100 two-column ASCII squares using one random
ANSI 256-colour background.

The default invocation is preview-only. Launching windows requires the explicit
`-ConfirmLaunch` switch.

## Preview

```powershell
pwsh -NoProfile -File .\Show-RandomSquares.ps1
```

## Launch the demonstration

```powershell
pwsh -NoProfile -File .\Show-RandomSquares.ps1 -ConfirmLaunch
```

## Useful bounds

```powershell
# Five windows, two seconds apart, held for ten seconds each.
pwsh -NoProfile -File .\Show-RandomSquares.ps1 `
	-Count 5 -DelaySeconds 2 -HoldSeconds 10 -ConfirmLaunch

# PowerShell preview without launching processes.
pwsh -NoProfile -File .\Show-RandomSquares.ps1 -ConfirmLaunch -WhatIf
```

`-Count` is limited to 100, and the default count is 100 to match the complete
demonstration. The child windows use `pwsh` when available and fall back to
Windows PowerShell.
