# LeafOS Usage Guide

This guide is for running the current two-surface LeafOS tree from a terminal.
Use the surface that matches your shell:

| Shell | Start directory | Command style |
|---|---|---|
| PowerShell 7+ | `PowerShell-Version/` | `.\leaf.ps1 status` |
| Bash, WSL, macOS, Linux, Git Bash | `Bash-Version/` | `bash leaf.sh status` |

The version folders are friendly entrypoints. They delegate into
`ProjectLeaf/leafos_taskpack`, where the main implementation lives.

## First five minutes

PowerShell:

```powershell
cd C:\Users\liamm\OneDrive\Documents\LeafOS\PowerShell-Version
pwsh -File .\install.ps1
.\leaf.ps1 status
.\leaf.ps1 doctor
.\leaf.ps1 runtime select
.\leaf.ps1 web-state --json
```

Bash:

```bash
cd /path/to/LeafOS/Bash-Version
bash install.sh
bash leaf.sh status
bash leaf.sh doctor
bash leaf.sh runtime select
bash leaf.sh web-state --json
```

Use `status` for a quick online check, `doctor` for dependency/layout checks,
`runtime select` to inspect the active main/scheduler/coder/persona selection,
and `web-state --json` when you want machine-readable runtime metadata.

## Daily command map

| Goal | PowerShell | Bash |
|---|---|---|
| Show help | `.\leaf.ps1 help` | `bash leaf.sh help` |
| Check readiness | `.\leaf.ps1 doctor` | `bash leaf.sh doctor` |
| Show runtime choice | `.\leaf.ps1 runtime select` | `bash leaf.sh runtime select` |
| Emit runtime JSON | `.\leaf.ps1 runtime select --json` | `bash leaf.sh runtime select --json` |
| Inspect web/runtime state | `.\leaf.ps1 web-state --json` | `bash leaf.sh web-state --json` |
| Run local chat wrapper | `.\leaf.ps1 chat-local` | `bash leaf.sh chat-local` |
| Build handoff bundle | `.\oneshot.ps1 --oneshot .. C:\R\LeafOS-OneShot` | `bash oneshot.sh --oneshot .. ./LeafOS-OneShot` |
| Check model artifacts | `.\leaf.ps1 download doctor` | `bash leaf.sh download doctor` |

## Model download safety

LeafOS model acquisition is intentionally plan-first:

```text
catalog/status/doctor = local-only
plan                  = offline JSON plan
resolve               = remote metadata and revision pins only
apply                 = model weight download boundary
```

PowerShell model workflow:

```powershell
.\real-models.ps1                 # status + safe offline plan
.\real-models.ps1 -Resolve        # metadata only
.\real-models.ps1 -Resolve -Apply -Yes
```

Bash model workflow:

```bash
bash real-models.sh
bash real-models.sh --resolve
bash real-models.sh --resolve --apply --yes
```

One-command automation keeps the same boundary:

```powershell
.\install-real.ps1       # preview, no model download
.\install-real.ps1 -Yes  # resolve + download/resume + verify
```

```bash
bash install-real.sh        # preview, no model download
bash install-real.sh --yes  # resolve + download/resume + verify
```

The default runtime profile is `runtime-default`. It prepares:

- `gemma4-coder` at `Q4_K_M` for coding work only.
- `gemma4-opus-assistant` at `Q4_K_M` for main assistant and scheduler duties.

Runtime role rule: Gemma/Fable coder is not allowed to be the main or scheduler
model. Main and scheduler duties use Opus or another model from the main-model
pool.

Model storage is chosen in this order:

1. An explicit command argument.
2. `LEAF_MODEL_DIR`.
3. Existing GGUF cache under `ProjectLeaf/leaf_model_installer/models`.
4. The catalog default, `~/.leaf/models`.

## llama.cpp Vulkan provider

For a full agentic stack, llama.cpp should run as a persistent HTTP provider.
Do not use `chat-local` for that role; it starts `llama-cli` for a foreground
conversation and exits when the turn is done.

Windows PowerShell:

```powershell
cd C:\Users\liamm\OneDrive\Documents\LeafOS\PowerShell-Version
.\serve-llamacpp.ps1 --backend vulkan --model fable --ctx 4096
```

If the Vulkan build lives elsewhere:

```powershell
.\serve-llamacpp.ps1 --llama-dir C:\llama-vulkan --backend vulkan --model fable
```

In another shell, route the LeafOS provider adapter to that server:

```powershell
$env:LEAF_PROVIDER_MODE = 'llamacpp'
$env:LEAF_BRAIN_PROVIDER = 'llamacpp'
$env:LEAF_CODER_PROVIDER = 'llamacpp'
$env:LEAF_LLAMACPP_URL = 'http://127.0.0.1:8080'
```

Then test the provider:

```bash
cd ProjectLeaf/leafos_taskpack
LEAF_PROVIDER_MODE=llamacpp ./bin/leafctl provider test llamacpp
```

The launcher checks `llama-server --list-devices`. If it reports no devices
while `vulkaninfo` sees your GPU, the selected llama.cpp package is CPU-only;
use a Windows x64 Vulkan llama.cpp build and pass it with `--llama-dir`.

## Minimal browser surface

`serve-leaf` is a tiny browser/API surface over the current file-backed tree.
It shows a LeafOS terminal dashboard with status, hardware monitor readings or
clear estimates, recent events, examples, and JSON task submission into a local
inbox. It also exposes high-frequency two-way text lanes using browser
Server-Sent Events for output and HTTP POST for input. It does not execute tasks
or implement multi-node relay logic yet.

PowerShell:

```powershell
cd C:\Users\liamm\OneDrive\Documents\LeafOS\PowerShell-Version
.\serve-leaf.ps1
.\serve-leaf.ps1 --host 0.0.0.0 --port 8765 --stream-hz 20 --no-open
```

Bash:

```bash
cd /path/to/LeafOS/Bash-Version
bash serve-leaf.sh
bash serve-leaf.sh --host 0.0.0.0 --port 8765 --stream-hz 20 --no-open
```

Use `127.0.0.1` for local-only access. Use `0.0.0.0` only when you intentionally
want LAN reachability; the minimal server has no authentication.

Text stream API:

```text
GET  /api/monitor
GET  /api/text/stream?hz=20
POST /api/text        {"text":"hello","source":"browser"}
GET  /api/brain/stream?hz=20
POST /api/brain       {"text":"brain frame","source":"brain"}
```

The browser labels the brain lane as `0.0.0.2`, but that is a lane label rather
than a bind address. Passing `--host 0.0.0.2` is normalized to `0.0.0.0`.

## Agent task pipeline

The 0.2 task pipeline works without a live model when you use the mock route.
Run it from `ProjectLeaf/leafos_taskpack` if you want to work directly with the
source CLI:

```bash
cd ../ProjectLeaf/leafos_taskpack
./bin/leafctl agent-task "create a hello world C project"
./bin/leafctl agent-route tasks/create-a-hello-world-c-project.md --mock
./bin/leafctl agent-dry-run tasks/create-a-hello-world-c-project.generated.plan.sh
./bin/leafctl agent-run tasks/create-a-hello-world-c-project.generated.plan.sh --yes
./bin/leafctl agent-report demo
```

The safety pattern is always the same:

1. Create or load a task file.
2. Route it into a plan.
3. Dry-run the plan.
4. Validate the plan.
5. Execute only with explicit consent.
6. Write a report.

Run the spine test when you want to prove that full loop:

```bash
cd ProjectLeaf/leafos_taskpack
bash tests/spine.sh
```

## Portable handoff bundle

Use `oneshot` when you want a small starter package for another machine or a
clean demo folder.

PowerShell:

```powershell
cd C:\Users\liamm\OneDrive\Documents\LeafOS\PowerShell-Version
.\oneshot.ps1 --oneshot .. C:\R\LeafOS-OneShot
```

Bash:

```bash
cd /path/to/LeafOS/Bash-Version
bash oneshot.sh --oneshot .. ./LeafOS-OneShot
```

The bundle includes README files, instructions, small sample data, and a zip.
It is separate from full model downloads.

## Useful source-tree commands

The main taskpack CLI has more commands than the friendly surfaces expose in
their short READMEs. From `ProjectLeaf/leafos_taskpack`:

```bash
./bin/leafctl help
./bin/leafctl platform
./bin/leafctl versions
./bin/leafctl loaders
./bin/leafctl runtime models --json
./bin/leafctl provider-status
./bin/leafctl dashboard --json
```

Python helper layer:

```bash
python3 bin/leafpy doctor
python3 bin/leafpy status
python3 bin/leafpy platform
python3 bin/leafpy versions
```

Build C loader demos:

```bash
cd ProjectLeaf/leafos_taskpack
make
./build/leaf_loader_demo_v2 --no-ansi
```

## Troubleshooting

### `leaf.ps1` or `leaf.sh` cannot find the source command

Make sure the root still contains `ProjectLeaf/leafos_taskpack/bin/leafctl`.
The top-level version folders are wrappers; they do not duplicate the full
source tree.

### `doctor` says `jq` is missing

Runtime, graph, and structured JSON commands require `jq` on the Bash side.
Install `jq`, then rerun:

```bash
bash leaf.sh doctor
```

### A model command looks like it might download

Only the `apply` phase downloads weights. In the friendly scripts, that means:

- PowerShell: `-Apply -Yes`
- Bash: `--apply --yes`

Everything before that is local planning or metadata inspection.

### Existing model files are not being found

Set `LEAF_MODEL_DIR` to the folder that contains your model directories, or put
GGUF files under `ProjectLeaf/leaf_model_installer/models` so LeafOS can prefer
that local cache.

PowerShell:

```powershell
$env:LEAF_MODEL_DIR = 'D:\LeafModels'
.\leaf.ps1 download doctor
```

Bash:

```bash
export LEAF_MODEL_DIR=/mnt/d/LeafModels
bash leaf.sh download doctor
```

## Where to read next

- `../README.md`: root project map and safest starting commands.
- `INSTALLATION.md`: install commands for each terminal surface.
- `releases/STAGE.md`: release status and evidence gates.
- `ProjectLeaf/leafos_taskpack/docs/USER_GUIDE.md`: deeper taskpack features.
- `ProjectLeaf/leafos_taskpack/docs/MODEL_INSTALLATION.md`: model installer contract.
- `ProjectLeaf/leaf_model_installer/README.md`: canonical model acquisition package.
