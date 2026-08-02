# LeafOS Usage Guide

This guide is for running the current two-surface LeafOS tree from a terminal.
Use the surface that matches your shell:

| Shell | Start directory | Command style |
|---|---|---|
| PowerShell 7+ | `PowerShell-Version/` | `.\leaf.ps1 status` |
| Bash, WSL, macOS, Linux, Git Bash | `Bash-Version/` | `bash leaf.sh status` |

The version folders are friendly entrypoints. They delegate into
`ProjectLeaf/leafos_taskpack`, where the main implementation lives.

## Root command surface

Run the reusable-tool root command when you want one stable command path from
the repository root:

| Goal | PowerShell | Bash |
|---|---|---|
| Check root contract | `.\leafos.ps1 validate-root` | `bash leafos.sh validate-root` |
| Check runtime status | `.\leafos.ps1 status` | `bash leafos.sh status` |
| Check runtime readiness | `.\leafos.ps1 doctor` | `bash leafos.sh doctor` |

All other arguments are delegated unchanged to the existing matching surface.

## Quick syntax

After a user-space install, use `leafos` from any directory. From the source
root, substitute `.\leafos.ps1` in PowerShell or `bash leafos.sh` in Bash.
The shortcut layer expands fixed command tokens and forwards all remaining
arguments unchanged.

| Shortcut | Expansion | Behavior |
|---|---|---|
| `leafos` | `home` | Read-only FlowerOS Home |
| `leafos q` | `quick` | Concise plain-text command card; add `--json` for tooling |
| `leafos h` | `home` | Home explicitly |
| `leafos s` | `status` | Fast status |
| `leafos d` | `doctor` | Readiness check |
| `leafos r` | `runtime select` | Active runtime selection |
| `leafos p` | `provider-stack check` | Local provider check |
| `leafos t` | `trace latest` | Latest observable run trace |
| `leafos ref` | `reference` | Primary Markdown and formatless TeX paths |
| `leafos b` | `bloom status` | Verify and show the durable Monday instance |
| `leafos m` | `flower-monitor` | Interactive read-only hardware monitor |
| `leafos c` | `chat` | Interactive local chat |
| `leafos go` | `live` | Guided project onboarding |

Use `leafos help` for the complete command surface. The `q`, `h`, `s`, `d`,
`r`, `p`, `t`, `ref`, and `b` routes are read-only.

## First five minutes

PowerShell:

```powershell
cd C:\R\LeafOS0.2.1\PowerShell-Version
pwsh -File .\install.ps1
..\leafos.ps1 q
..\leafos.ps1 s
..\leafos.ps1 d
..\leafos.ps1 r
.\leaf.ps1 web-state --json
.\leaf.ps1 fullstackbench
```

Bash:

```bash
cd /path/to/LeafOS/Bash-Version
bash install.sh
bash ../leafos.sh q
bash ../leafos.sh s
bash ../leafos.sh d
bash ../leafos.sh r
bash leaf.sh web-state --json
bash leaf.sh fullstackbench
```

Use `status` for a quick online check, `doctor` for dependency/layout checks,
`runtime select` to inspect the active main/scheduler/coder/persona selection,
`web-state --json` when you want machine-readable runtime metadata, and
`fullstackbench` for a raw no-download stack benchmark.

## Daily command map

| Goal | PowerShell | Bash |
|---|---|---|
| Show help | `.\leaf.ps1 help` | `bash leaf.sh help` |
| Check readiness | `.\leaf.ps1 doctor` | `bash leaf.sh doctor` |
| Show runtime choice | `.\leaf.ps1 runtime select` | `bash leaf.sh runtime select` |
| Emit runtime JSON | `.\leaf.ps1 runtime select --json` | `bash leaf.sh runtime select --json` |
| Inspect web/runtime state | `.\leaf.ps1 web-state --json` | `bash leaf.sh web-state --json` |
| Initialize durable Monday | `..\leafos.ps1 bloom init` | `bash ../leafos.sh bloom init` |
| Verify durable Monday | `..\leafos.ps1 b --json` | `bash ../leafos.sh b --json` |
| Run raw full-stack benchmark | `.\leaf.ps1 fullstackbench` | `bash leaf.sh fullstackbench` |
| Run local chat wrapper | `.\leaf.ps1 chat-local` | `bash leaf.sh chat-local` |
| Build handoff bundle | `.\oneshot.ps1 --oneshot .. C:\R\LeafOS-OneShot` | `bash oneshot.sh --oneshot .. ./LeafOS-OneShot` |
| Check model artifacts | `.\leaf.ps1 download doctor` | `bash leaf.sh download doctor` |

The bounded Continual Bloom runtime starts with one persona only:
**Monday — Rescue and Analysis**. Its transcript is hash chained, claims remain
unverified until native evidence supports or refutes them, checkpoints require
new validation, and recovery ignores KV cache. See
`ProjectLeaf/leafos_taskpack/docs/CONTINUAL_BLOOM_RUNTIME.md` for the command
and file contracts.

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

## Monitoring long-running work with `leafos vtop`

LeafOS launches background work such as model downloads and chat servers as
ordinary processes. When you want a live view of what those processes are doing,
use the built-in `leafos vtop` helper as a secondary monitor.

Watch every leaf-related process for 10 seconds:

```powershell
leafos vtop --duration-seconds 10
```

Watch continuously until you press `Ctrl+C`:

```powershell
leafos vtop
```

This command is a thin, cross-platform live process table. It is not part of
the core LeafOS runtime; it is a recommended secondary action when you are
waiting on a model download, a chat server, or a long-running agent task and
want more detail than the log tails provide.

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
./bin/leafctl agent-report spine-check
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
clean handoff folder.

PowerShell:

```powershell
cd C:\R\LeafOS0.2.1\PowerShell-Version
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
./bin/leafctl fullstackbench
```

Python helper layer:

```bash
python3 bin/leafpy doctor
python3 bin/leafpy status
python3 bin/leafpy platform
python3 bin/leafpy versions
```

Build C loader samples:

```bash
cd ProjectLeaf/leafos_taskpack
make
./build/leaf_loader_demo_v2 --no-ansi
```

## Troubleshooting

### Windows PowerShell reports a parser error in `leafctl.ps1`

LeafOS uses PowerShell 7 syntax in its delegated command surface. Use an
installed `pwsh` executable, or run the friendly launcher directly from
Windows PowerShell 5.1:

```powershell
.\leaf.ps1 status
```

The launcher automatically hands the command to PowerShell 7. If `pwsh` is not
installed, install PowerShell 7 and retry. Bash and WSL users should use the
Bash surface instead.

### Bash scripts report `$'\r': command not found`

This indicates CRLF line endings were passed to Bash. Convert the affected
script to LF line endings, then retry through the isolated Bash surface:

```bash
bash --noprofile --norc leafos.sh validate-root
```

Do not use an interactive shell for diagnostics when shell profile scripts add
unrelated startup behavior.

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

- `README.md`: root project map and safest starting commands.
- `INSTALLATION.md`: install commands for each terminal surface.
- `ProjectLeaf/leafos_taskpack/docs/USER_GUIDE.md`: deeper taskpack features.
- `ProjectLeaf/leafos_taskpack/docs/MODEL_INSTALLATION.md`: model installer contract.
- `ProjectLeaf/leaf_model_installer/README.md`: canonical model acquisition package.
