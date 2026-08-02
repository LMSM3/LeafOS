# LeafOS Quick Start

This guide starts the current resident project stack. The SSH node subsystem is optional and documented separately in `NODES.md`.

## 1. Check The Host

```powershell
Set-Location C:\R\LeafOS0.2.1\ProjectLeaf\leafos_taskpack
.\bin\leafctl.ps1 doctor
.\bin\leafctl.ps1 provider-stack check
```

`provider-stack check` validates the configured llama.cpp executable, local GGUF path, Vulkan backend, endpoint, and lifecycle settings. It does not download a model.

## 2. Open A Project

```powershell
.\bin\leafctl.ps1 live
```

The guided inlet asks whether the project is new or existing. An existing project can be selected from recent runs or entered as a path. For a new project, choose the top-level directory and project folder name, then paste the README and skeleton in separate steps and finish each paste with `.done`. The current sandbox choice is `project-only`, enforced by the CPU path boundary. LeafOS shows the target, template, content sizes, provider, sandbox, optimization requests, approval mode, and exact files before requiring `CREATE`.

The KV-cache selector supports `inherit`, `investigate`, `enable`, and `disable`. Any non-inherit choice queues a priority-1 optimization task after the initial project report. It does not restart or silently edit the shared llama.cpp provider.

Open a known project directly:

```powershell
.\bin\leafctl.ps1 live C:\R\MyProject
```

LeafOS performs bounded read-only intake, derives an objective when none is supplied, creates or reattaches a persistent run, starts the resident supervisor, and opens the TUI.

To inspect without starting work:

```powershell
.\bin\leafctl.ps1 live C:\R\MyProject --inspect --json
```

To initialize a minimal project with built-in seed text instead of pasted intent:

```powershell
.\bin\leafctl.ps1 live C:\Games\catan2 --new --template catan2 --yes --budget 64
```

Existing project files are not overwritten by intake. Generated LeafOS control files live under `runs/agent-loop`, outside the target repository.

## 3. Give Instructions

Inside the active window, type a plain objective or use an optional command:

```text
:improve
:improve add a deterministic trading phase with tests
:again
:make state changes easier to inspect
```

LeafOS converts the instruction into a bounded typed task. The model proposes a plan; CPU-side policy validates and executes declared operations. Every iteration must pass validation before it is checkpointed and reported.

Press `n` at any time to leave the renderer, run guided new/existing onboarding, and reopen the active window on the selected project. Cancelling returns to the current project without changing files.

## 4. Control Resource Use

```text
:mode quiet
:mode auto
:targets cpu 80 gpu 90
:budget 64m
:pause
:resume
:drain
```

Targets apply only to useful work. Foreground activity, responsiveness, RAM, VRAM, temperature, and provider health can reduce dispatch automatically.

## 5. Reconnect Or Inspect

```powershell
.\bin\leafctl.ps1 tui --run active
.\bin\leafctl.ps1 loop status active
.\bin\leafctl.ps1 loop attach active --after 0
.\bin\leafctl.ps1 resident status active --json
```

Pressing `q` closes the TUI without stopping work. `pause` stops new claims at a safe boundary. `drain` finishes accepted work and rejects new admission. `stop` is a confirmed operation.

## 6. Verify The Installation

```powershell
.\bin\leafctl.ps1 test visual --plain
.\bin\leafctl.ps1 test visual --match provider --live-stack --plain
.\bin\leafctl.ps1 catan2-resident --contract-only --iterations 3
```

The live-stack test makes one bounded call to the real local provider and fails if that explicitly requested demonstration cannot complete. Fixture-based tests never silently become evidence of real inference.

## What To Read Next

- `DOCUMENTATION_MAP.md`: current versus historical documents.
- `LIVE_PROJECT_TUI.md`: project intake and active-window syntax.
- `RESIDENT_STACK_USAGE.md`: governor profiles, budgets, recovery, and Catan2 soaks.
- `LOOP_INLET_USAGE.md`: run files, typed tasks, and lifecycle controls.
- `TUI_USAGE.md`: pages, keys, and renderer security boundary.
- `MODEL_INSTALLATION.md`: model acquisition and stack terminology.
