# LeafOS Resident Stack

The resident stack keeps a live project available after its queue temporarily empties. It accepts new objectives while work is active, validates each iteration, checkpoints evidence, and derives another bounded improvement while its renewable budget permits.

The stack means all downloaded and locally available models in this LeafOS instance.

The supervisor controls availability and task admission timing. It does not
approve model output or execute files itself; those responsibilities stay in
the typed inlet and CPU-side validator.

## Start

```powershell
.\bin\leafctl.ps1 live C:\R\MyProject
.\bin\leafctl.ps1 live C:\R\MyNewProject --new --yes --budget 64
```

`leafctl live` enables the resident supervisor by default. `--mode auto|quiet|full` selects the initial resource profile. `--no-resident` retains the older worker that exits when its current queue reaches a terminal state.

The initial approval gate remains unchanged. Without `--yes`, planning can continue but mutation waits for operator approval. Resident refill cannot expand the approved project root, command allowlist, failure budget, change budget, or task boundary.

## Resource Behavior

The default idle targets are 80 percent total CPU and 90 percent GPU utilization. They apply only while useful matching work exists.

- `auto-idle`: 80 percent CPU and 90 percent GPU targets.
- `auto-ramp`: gradual recovery after recent local input.
- `auto-interactive`: 60 percent CPU and 75 percent GPU targets.
- `quiet`: 35 percent CPU and 50 percent GPU targets.
- `full`: 90 percent CPU and 98 percent GPU targets, subject to hard safety limits.
- `pressure`: new claims stop for responsiveness, RAM, VRAM, temperature, provider, pause, drain, or stop conditions.

The governor uses smoothed counters, five-percent hysteresis, and a cooldown between concurrency changes. Missing counters remain unknown. LeafOS never starts duplicate inference or meaningless CPU work to make utilization look higher.

Repository mutation remains serialized. The governor exports `LEAF_CPU_SLOTS`, `OMP_NUM_THREADS`, and `CMAKE_BUILD_PARALLEL_LEVEL` to validation/build subprocesses so CPU-aware tools can use the approved slot budget without allowing concurrent edits to one worktree. On Windows, automatic and quiet workers run below normal process priority so foreground applications win contention.

### Host-Sized Model Route

The active provider route must leave enough RAM and VRAM for the executor, tests, TUI, and foreground applications. On the reference RTX 4070 host with 12 GB VRAM and 48 GB system RAM, the resident coding route uses `Gemma4-Coder/gemma4-coding-Q3_K_M.gguf` through llama.cpp Vulkan. Sustained Q4 and larger assistant-model trials reached the hard RAM-pressure profile during real resident runs. Q3 retained schema-constrained planning while leaving more headroom for the CPU side of the loop.

This is a host profile, not a change to the meaning of stack. The stack still means every downloaded and locally available model in the instance; the provider configuration selects which member is active for a particular lane. Keep the RAM and VRAM gates enabled when choosing a larger quant.

GLM-5.2 is now deprecated for local use. `config/medium_moe_policy.json`
defines the replacement research direction: named MoE candidates in the
47-156B total-parameter band, with active topology and artifact identity
recorded separately. No candidate is active merely because it falls in that
range. The current Q3 route stays in service until a candidate passes the 4,
8, and 64 minute evidence gates and receives operator approval.

The new policy does not add SSD offload management. Model weights may be
memory-mapped by llama.cpp and backed by the operating-system page cache, but
LeafOS does not currently pin or stream experts across SSD, RAM, and VRAM.
See `docs/MEDIUM_MOE_MODEL_POLICY.md` for the exact contract.

## Active Window

Plain objectives still add work directly. Resource commands are optional:

```text
:improve
:add deterministic maritime trading
:mode quiet
:mode auto
:targets cpu 80 gpu 90
:budget 64m
:pause
:resume
:drain
:stop
```

The TUI displays the resident profile, decision reason, current and target utilization, CPU/GPU headroom, supervisor PID, queue classes, provider health, responsiveness, and remaining budgets. Closing the TUI with `q` closes only the window.

All commands cross the authenticated typed inlet. Renderers cannot edit run files, policy, queues, or the project and cannot execute command text as shell input. `:stop` retains the confirmed stop flow.

## Lifecycle CLI

```powershell
.\bin\leafctl.ps1 resident status active --json
.\bin\leafctl.ps1 resident mode active quiet
.\bin\leafctl.ps1 resident targets active --cpu 70 --gpu 85
.\bin\leafctl.ps1 resident budget active 120
.\bin\leafctl.ps1 resident pause active
.\bin\leafctl.ps1 resident resume active
.\bin\leafctl.ps1 resident drain active
.\bin\leafctl.ps1 resident stop active
```

`pause` finishes the current safe unit and stops new claims. `drain` rejects new work and finishes accepted work. `stop` records cancellation intent and uses the existing tracked-process termination boundary. `resume` ensures exactly one resident supervisor is available.

## Budgets

The default policy permits:

- 64 unattended minutes.
- 8 automatically generated improvements.
- 3 failures.
- 64 changed files recorded by the checkpoint.

Exhaustion enters `awaiting_budget`. An operator can renew time with `:budget MINUTES` or the lifecycle CLI. Repeated failure, blocked approval, missing provider output, or absence of a defensible next improvement does not generate filler work.

## Recovery And Evidence

The resident supervisor has a separate lease from the task worker. Restarts reuse queue and checkpoint facts and cannot claim an active task twice. Queue updates, task persistence, events, and universal telemetry use cross-process locks around their read-modify-write boundary.

Provider recovery runs outside the supervisor loop. It uses one tracked recovery process and 5, 15, and 30-second backoff intervals. A failed provider remains visibly degraded and never becomes mock output or CPU-generated model text.

Each run adds:

```text
resident-state.json
resident.lock
resident.log
provider-recovery.log
```

`resident-state.json` contains policy, budgets, usage, the latest deterministic decision, and stable reason codes. Resource transitions are also written to `events.jsonl` and `universal-run-log.jsonl`; high-frequency TUI samples remain presentation-only.

## Resident Demonstration

```powershell
.\bin\leafctl.ps1 resident start --profile 4m --target C:\R\MyProject
.\bin\leafctl.ps1 resident start --profile 8m --target C:\R\MyProject
.\bin\leafctl.ps1 resident start --profile 64m --target C:\R\MyProject
```

The resident supervisor starts from a generic three-file seed if `--target` does not exist. It exercises provider planning, continual queue refill, operator task admission, quiet/auto transitions, validation, drain, and reconnectable evidence. `--target PATH` uses an existing project instead.

For scheduler contract testing only:

```powershell
.\bin\leafctl.ps1 resident start --contract-only --iterations 3
```

Contract mode is explicitly labeled and does not claim real provider inference. Real profiles write per-phase CPU/GPU distributions, responsiveness percentiles, task outcomes, queue evidence, and provider state beneath `runs/resident-demo`.

The 4-minute profile is the fast real-provider acceptance run. The 8-minute profile adds a second operator-input phase. The 64-minute profile is the provider-longevity and recovery soak; it should be run before declaring the entire WO-038 soak matrix complete.
