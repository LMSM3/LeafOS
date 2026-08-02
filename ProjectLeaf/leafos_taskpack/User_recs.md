# LeafOS User Recommendations

Windows-first, PowerShell 7 guide for installing LeafOS, configuring the
local stack, starting a non-interactive run, and launching the passive HTML
analysis view.

The commands below are designed for a local taskpack checkout. They do not
download model weights unless the explicit `models-install ... apply ... --yes`
command is run.

## 1. Set A PowerShell Session

Open PowerShell 7 and keep the main values in variables. `$T` is an unattended
run budget in minutes; it is not a token count or a report refresh interval.

```powershell
$T = 64
$ReportInterval = 30
$Repo = 'C:\R\LeafOS0.2.1\ProjectLeaf\leafos_taskpack'
$Project = 'C:\R\MyProject'
$Prefix = Join-Path $env:LOCALAPPDATA 'leafos'
$ModelDir = Join-Path $env:LOCALAPPDATA 'leafos\models'

Set-Location $Repo
$env:LEAF_ROOT = $Repo
$env:LEAF_MODEL_DIR = $ModelDir

if ($PSVersionTable.PSVersion.Major -lt 7) {
    throw 'PowerShell 7 or newer is required.'
}

$Python = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $Python) {
    throw 'Python 3 is required. Install Python and reopen PowerShell.'
}
```

If local script policy blocks a repository script, allow scripts only for the
current PowerShell process:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

## 2. Install The PowerShell Copy

The installer copies the taskpack to `$Prefix\share\leafos`, installs the
`LeafOS` PowerShell module, and adds `$Prefix\bin` to the user PATH. The PATH
change applies to new shells, so this guide uses the installed script path
directly in the current shell.

```powershell
$Installer = Join-Path $Repo 'bin\install_demo.ps1'
& $Installer -Prefix $Prefix

$LeafRoot = Join-Path $Prefix 'share\leafos'
$LeafCtl = Join-Path $LeafRoot 'bin\leafctl.ps1'
$ReportTool = Join-Path $LeafRoot 'core\python\leaf_live_report.py'
$SandboxTool = Join-Path $LeafRoot 'bin\leaf-sandbox.ps1'

& $LeafCtl doctor
& $LeafCtl versions
```

For development against the checkout instead of the installed copy, use:

```powershell
$LeafRoot = $Repo
$LeafCtl = Join-Path $LeafRoot 'bin\leafctl.ps1'
$ReportTool = Join-Path $LeafRoot 'core\python\leaf_live_report.py'
$SandboxTool = Join-Path $LeafRoot 'bin\leaf-sandbox.ps1'
```

## 3. Configure And Verify

Run the read-only checks first. A provider check can report `not_ready` when no
local model/server is configured; that is not a model download.

Packs are installed as a unit but activated one group at a time. Add `--pack mwtf`
only if you intend to install the full Multi-Workload Telluric Foundation pack
(up to ~200 GB).

```powershell
& $LeafCtl runtime validate
& $LeafCtl model-profile validate --json
& $LeafCtl provider-stack check --json
& $LeafCtl web-state --json --write
```

The provider and runtime authorities are:

```text
config\vulkan-provider-stack.json
config\runtime-profiles.json
config\runtime.json
```

Do not edit scattered command constants to change a model route. Inspect the
runtime selection and provider status first:

```powershell
& $LeafCtl runtime select --json
& $LeafCtl provider-stack status --json
```

## 4. Plan Models Before Applying Downloads

Model installation is an explicit four-step boundary: catalog, plan, resolve,
then review and apply.

```powershell
$Plan = Join-Path $Repo 'leaf-runtime-plan.json'
$ResolvedPlan = Join-Path $Repo 'leaf-runtime-plan.resolved.json'

& $LeafCtl models-install catalog
& $LeafCtl models-install plan `
    --profile runtime-default `
    --dest $ModelDir `
    --out $Plan
& $LeafCtl models-install resolve $Plan --out $ResolvedPlan
& $LeafCtl models-install show $ResolvedPlan
```

Only after reviewing the resolved artifacts and paths:

```powershell
& $LeafCtl models-install apply $ResolvedPlan --yes
```

For a model-free passive report, leave the provider off and skip this model
download section entirely.

## 5. Start A Non-Interactive Run

For an existing project, start or attach without opening the TUI. The result is
JSON, so the run directory can be captured for the HTML report.

```powershell
$Live = & $LeafCtl live $Project `
    --provider off `
    --mode quiet `
    --budget $T `
    --no-tui `
    --json | ConvertFrom-Json

$RunRoot = $Live.run_dir
$Live | ConvertTo-Json -Depth 12
```

For a new three-file project, add the explicit seed and approval flags:

```powershell
$Live = & $LeafCtl live $Project `
    --new `
    --template generic `
    --provider off `
    --mode quiet `
    --budget $T `
    --yes `
    --no-tui `
    --json | ConvertFrom-Json

$RunRoot = $Live.run_dir
```

Use `--provider auto` or `--provider required` only after the provider check
passes and the model/server configuration is intentionally enabled.

Check the run without an interactive surface:

```powershell
& $LeafCtl loop status $RunRoot --json
& $LeafCtl loop monitor $RunRoot --noninteractive --json --once
```

## 6. Use The Integrated Passive-Report Command

The recommended composition connects run creation, validation, run-directory
selection, and the passive HTML projection through one non-interactive command.
It does not create a second reporting system.

Start a new run and capture the generated report paths:

```powershell
$Result = & $LeafCtl passive-report `
    -StartProject `
    -Project $Project `
    -Provider off `
    -BudgetMinutes $T `
    -Json | ConvertFrom-Json

$RunRoot = $Result.run_root
$Html = $Result.html
Start-Process $Html
```

For an existing run, render the current durable state and open it:

```powershell
$Result = & $LeafCtl passive-report -RunRoot $RunRoot -Open -Json | ConvertFrom-Json
$Result | ConvertTo-Json -Depth 12
```

For continuous model-free refreshes, keep the command non-interactive:

```powershell
& $LeafCtl passive-report `
    -RunRoot $RunRoot `
    -Watch `
    -ReportIntervalMinutes $ReportInterval `
    -Json
```

The wrapper delegates to the existing `leaf-sandbox.ps1` supervisor in watch
mode and to the existing `leaf_live_report.py` renderer for the HTML artifact.

## 7. Launch The Passive HTML Analysis Directly

The pure HTML renderer is model-free and read-only. It reads the run's
`journal.lje`, `telemetry.jsonl`, and `actions.jsonl`; it does not start a
provider or mutate the run.

```powershell
$Html = Join-Path $RunRoot 'LIVE_REPORT.html'
& $Python $ReportTool $RunRoot --output $Html
if ($LASTEXITCODE -ne 0) {
    throw "HTML report generation failed with exit code $LASTEXITCODE"
}

Start-Process $Html
```

The generated file is:

```text
<run directory>\LIVE_REPORT.html
```

To regenerate it later without starting any worker or model:

```powershell
& $Python $ReportTool $RunRoot --output (Join-Path $RunRoot 'LIVE_REPORT.html')
```

## 8. Optional Continuous Model-Free Reporting

The sandbox reporting supervisor adds the HTML report plus the model-free
Monday affect PDF. It is non-interactive when `--no-open` is supplied. `$T`
remains the run budget; `$ReportInterval` controls report refresh cadence.

```powershell
& $SandboxTool `
    --sandbox $RunRoot `
    report `
    --watch `
    --interval-minutes $ReportInterval `
    --no-open
```

This writes `LIVE_REPORT.html` and timestamped files under
`$RunRoot\reports\monday_affect`. PDF generation requires Chrome or Chromium;
the HTML-only command in section 6 does not.

## Recommended Operating Boundary

- Use `$T = 64` for a 64-minute unattended budget, then inspect the durable run.
- Keep `$ReportInterval = 30` unless a different refresh cadence is needed.
- Use `--no-tui --json` for automation and `loop monitor --noninteractive` for observation.
- Use the pure HTML renderer when you want passive analysis only.
- Treat `LIVE_REPORT.html` as a derived view; the run directory remains the authority.
- Keep provider, model, approval, path, queue, checkpoint, and validation policy in the existing LeafOS authorities.
- Do not expose the report server to WAN, enable UPnP, or place credentials in the run directory.
