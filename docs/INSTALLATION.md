# LeafOS installation instructions

Choose one surface.

## A.) PowerShell Version

Best for Windows and direct PowerShell use.

```powershell
cd C:\Users\liamm\OneDrive\Documents\LeafOS\PowerShell-Version
pwsh -File .\install.ps1
```

Then:

```powershell
.\leaf.ps1 status
.\leaf.ps1 doctor
.\leaf.ps1 runtime select
.\demo.ps1 -SkipModelPlan
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
bash demo.sh
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

Read [USAGE.md](USAGE.md) for the practical command map. The shortest useful
checks are:

PowerShell:

```powershell
.\leaf.ps1 help
.\leaf.ps1 doctor
.\leaf.ps1 runtime select --json
.\leaf.ps1 web-state --json
```

Bash:

```bash
bash leaf.sh help
bash leaf.sh doctor
bash leaf.sh runtime select --json
bash leaf.sh web-state --json
```

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
