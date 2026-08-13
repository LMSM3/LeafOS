# LeafOS installation instructions

Choose one surface. This file covers setup and safety boundaries; use
[USAGE.md](USAGE.md) as the canonical day-to-day command map after the install
check passes.

## A.) PowerShell Version

Best for Windows and direct PowerShell use.

LeafOS targets PowerShell 7+. The friendly `leaf.ps1` launcher can be called
from Windows PowerShell 5.1 when `pwsh` is installed; it automatically
relaunches the command under PowerShell 7. The installer itself should be run
with `pwsh`.

```powershell
cd C:\path\to\LeafOS\PowerShell-Version
pwsh -File .\install.ps1
```

Then:

```powershell
.\leaf.ps1 status; sleep 2; .\real-models.ps1 -Resolve -Apply -Yes  # download boundary
.\leaf.ps1 doctor;
.\leaf.ps1 runtime select; sleep 2
.\leaf.ps1 web-state --json; sleep 2
.\leaf.ps1 fullstackbench; sleep 2
```

Create a portable handoff:

```powershell
.\oneshot.ps1 --oneshot .. C:\R\LeafOS-OneShot
```

Model readiness:

```powershell
.\real-models.ps1
```

Resolve metadata only:

```powershell
.\real-models.ps1 -Resolve
```

Download or resume after review:

```powershell
.\real-models.ps1 -Resolve -Apply -Yes
```

Full real installation automation:

```powershell
.\install-real.ps1
.\install-real.ps1 -Yes
```

Optional detached user-space application install:

```powershell
.\install-leafos.ps1 -Action plan
.\install-leafos.ps1 -Action apply
.\install-leafos.ps1 -Action verify
```

The application installer creates `leafos`, `leaf`, and `flower` launchers for
PowerShell and CMD. It does not edit PATH unless the apply command explicitly
includes `-AddToUserPath`. It never edits a PowerShell profile.

## B.) Bash Version

Best for Linux, macOS, WSL, MSYS2, or Git Bash.

```bash
cd /path/to/LeafOS/Bash-Version
bash install.sh
```

Then:

```bash
bash leaf.sh status
bash leaf.sh doctor
bash leaf.sh runtime select
bash leaf.sh web-state --json
bash leaf.sh fullstackbench
```

Create a portable handoff:

```bash
bash oneshot.sh --oneshot .. ./LeafOS-OneShot
```

Model readiness:

```bash
bash real-models.sh
```

Resolve metadata only:

```bash
bash real-models.sh --resolve
```

Download or resume after review:

```bash
bash real-models.sh --resolve --apply --yes
```

Full real installation automation:

```bash
bash install-real.sh
bash install-real.sh --yes
```

## Safety rules

- Planning is offline.
- Resolve reads remote metadata only.
- Apply is the model download boundary.
- Apply requires explicit confirmation:
  - PowerShell: `-Apply -Yes`
  - Bash: `--apply --yes`
- The experimental 120B model is not part of `runtime-default`.
- Existing GGUFs in `ProjectLeaf/leaf_model_installer/models` are detected so
  partially completed downloads can be resumed instead of restarted.
- Runtime role rule:
  - Fable/Gemma4-Coder is coding-only.
  - Opus or another main-model-pool model owns main and scheduler duties.

## After installation

Read [USAGE.md](USAGE.md) for the practical command map. With the detached
application bin directory on PATH, the shortest available syntax is:

PowerShell:

```powershell
leafos       # Home
leafos q     # concise command card
leafos d     # doctor
leafos r --json
leafos ref
```

Bash:

```bash
leafos       # Home
leafos q     # concise command card
leafos d     # doctor
leafos r --json
leafos ref
```

From the source checkout, use the same shortcut tokens through
`.\leafos.ps1` or `bash leafos.sh`.

If you want to exercise the task pipeline without a live model, run the mock
spine test from the preserved source tree:

```bash
cd ProjectLeaf/leafos_taskpack
bash tests/spine.sh
```

## Root layout

```text
PowerShell-Version/  user-facing PowerShell surface
Bash-Version/        user-facing Bash surface
ProjectLeaf/         preserved source tree
```
