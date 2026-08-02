# LeafOS Continual Loop Inlet

`leafctl loop` controls a persistent repository run backed by the local stack, a durable queue, checkpoints, and a reconnectable event stream. Work orders are the default architecture; the one-command validation inlet remains available for compatibility.

The inlet is the authority boundary. Resident scheduling and both TUI
renderers call into it; none maintain a parallel queue or execution path.

## Start

The shortest project route initializes or reattaches the run and opens the active TUI:

```powershell
.\bin\leafctl.ps1 live C:\R\MyProject
```

The objective is optional. `leafctl live C:\Games\catan2 --new` can begin from a README, skeleton, and JSON seed. See `docs/LIVE_PROJECT_TUI.md`.

Start a work-order run:

```powershell
.\bin\leafctl.ps1 agent-loop-start `
  --target C:\R\LeafOS0.2.1\ProjectLeaf\leafos_taskpack `
  --work-order docs\work-orders\WO-031-work-order-loop-v2.md `
  --profile local-coding `
  --yes
```

This creates the dependency chain `inspect -> plan -> approve -> execute -> validate -> report`. A Markdown work order may use a same-name JSON companion as its machine-readable authority.

Mutation is disabled unless the work order explicitly sets `allow_mutation` to `true`. When `approval_mode` is `required`, `--yes` pre-approves bounded mutation steps; otherwise the run stops at the approval task and can continue with `loop approve active`.

### Compatibility Validation

Options must appear before `--check`. Everything after `--check` is passed as an argument array without a shell.

```powershell
.\bin\leafctl.ps1 loop start C:\R\MyRepo --check python -m unittest discover -s tests
```

The compatibility form verifies or starts the configured Vulkan llama.cpp provider, creates a run under `runs\agent-loop`, and launches a background worker. It does not write LeafOS control files into `C:\R\MyRepo`.

Run in the current terminal when direct event output is preferred:

```powershell
.\bin\leafctl.ps1 loop start C:\R\MyRepo --foreground --check python -m pytest -q
```

Use `--provider off` for an explicitly model-free CPU validation policy. Use `--provider auto` to attempt the local stack and fall back to that policy. The default, `required`, fails closed when the provider cannot start.

## Observe

```powershell
.\bin\leafctl.ps1 loop status active
.\bin\leafctl.ps1 loop attach active
.\bin\leafctl.ps1 loop attach active --after 120 --json
```

`attach` follows until the run reaches a terminal state. `--after` resumes after a previously recorded event sequence. `--json` emits JSON Lines suitable for another interface.

The `THOUGHT` events are recorded phase summaries and progress counts. LeafOS does not claim or persist private model chain-of-thought.

## Control

```powershell
.\bin\leafctl.ps1 loop pause active
.\bin\leafctl.ps1 loop resume active
.\bin\leafctl.ps1 loop drain active
.\bin\leafctl.ps1 loop approve active
.\bin\leafctl.ps1 loop stop active
.\bin\leafctl.ps1 loop report active
```

`pause` stops new task claims after the current step. `resume` restarts a worker when needed. `approve` releases a work order blocked at its mutation gate. `drain` disables queue admission and finishes accepted work. `stop` records cancellation intent and terminates the tracked active subprocess before stopping the worker.

## Typed Tasks

Submit a repository-bounded task in one line:

```powershell
.\bin\leafctl.ps1 loop task submit active .\config\task-control.submit.sample.json
```

The request follows `schemas/leafos.task-control-request.v1.schema.json`. It declares objective, allowed paths, acceptance commands, stack role, priority, dependencies, timeout, retry budget, mutation policy, and approval policy. A submitted task is normalized into `runs/.../work-orders/TASK-ID.json`; the existing plan-v2 provider and allowlisted executor remain authoritative.

```powershell
.\bin\leafctl.ps1 loop task prioritize active TASK-0001 0
.\bin\leafctl.ps1 loop task approve active TASK-0001
.\bin\leafctl.ps1 loop task retry active TASK-0001
.\bin\leafctl.ps1 loop task cancel active TASK-0001
```

Priority `0` is highest and `9` is lowest. Retry cannot exceed the task's declared budget. Cancel writes a durable request, publishes a cancellation marker, and terminates a matching tracked child process. CPU fallback tasks run declared validation without pretending to perform model-generated edits.

## Run Files

Each run contains `run.json`, `queue.json`, `state.json`, `events.jsonl`, `checkpoint.json`, `report.md`, `universal-run-log.jsonl`, provider request and response artifacts, command output, and a short-lived `worker.lock` lease. Typed control requests are hash-chained in `control.lmem`; a running command is described by the short-lived `active-process.json` lease.

## Terminal Interface

Open the active run:

```powershell
.\bin\leafctl.ps1 tui
```

Open a specific run or render one noninteractive frame:

```powershell
.\bin\leafctl.ps1 tui --run wo-031-live-v2-telemetry
.\bin\leafctl.ps1 tui --run active --once --page hardware
```

The TUI reads the inlet's normalized snapshot and never derives authority from formatted logs. `Tab`, `Shift+Tab`, and `1` through `7` switch pages. `q` closes only the interface. `r`, `x`, `[`/`]`, and `A` control the selected task through the typed inlet. `p` routes pause or resume, `a` routes run approval, and `:stop` requires typing `STOP` before a stop request is sent.

`--json` emits the normalized `leafos.tui.snapshot` contract for a future native renderer or another read-only interface.
