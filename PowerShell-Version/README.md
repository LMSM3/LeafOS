# LeafOS PowerShell Version

This is the PowerShell-facing LeafOS surface.

Start here if you are on Windows or prefer `pwsh`. The command surface targets
PowerShell 7+. When `leaf.ps1` is launched from Windows PowerShell 5.1, it
automatically relaunches under an installed `pwsh` executable.

## Install / check readiness

```powershell
cd C:\R\LeafOS0.2.2\PowerShell-Version
pwsh -File .\install.ps1
```

## Usage

```powershell
..\leafos.ps1 q
..\leafos.ps1
..\leafos.ps1 d
..\leafos.ps1 r
..\leafos.ps1 ref
.\leaf.ps1 status
.\leaf.ps1 doctor
.\leaf.ps1 runtime select
.\leaf.ps1 web-state
.\leaf.ps1 oneshot --oneshot .. C:\R\LeafOS-OneShot
```

For the full command map and common workflows, read
[`../markdowns/USAGE.md`](../markdowns/USAGE.md). For the reusable-tool
ownership and configuration boundaries, read
[`../markdowns/ROOT_CONTRACT.md`](../markdowns/ROOT_CONTRACT.md).

## Model defaults

Real model check plus safe offline plan:

```powershell
.\real-models.ps1
```

Resolve metadata only:

```powershell
.\real-models.ps1 -Resolve
```

Download or resume only after review:

```powershell
.\real-models.ps1 -Resolve -Apply -Yes
```

Full real installation automation:

```powershell
.\install-real.ps1       # preview
.\install-real.ps1 -Yes  # resolve + download/resume + verify
```

Download doctor:

```powershell
.\leaf.ps1 download doctor
```

This hashes local model artifacts, waits one second, then prints each model
file's size and location. It performs no downloads.

Web/runtime state:

```powershell
.\leaf.ps1 web-state --json
.\leaf.ps1 web-state --refresh-metadata --write
```

The default coding language is Python. The web-state command uses cached or
steady-state fallback metadata unless `--refresh-metadata` is explicitly set.

Runtime role rule: Fable/Gemma4-Coder is coding-only; Opus or another
main-model-pool model owns main and scheduler duties.

No command in this folder downloads model weights unless you explicitly cross
the `-Apply -Yes` boundary.

Compatibility alias:

```powershell
.\models.ps1
```
