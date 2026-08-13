# FlowerOS Usage Surface / LeafOS Engine

**Version 0.9.3 | Resident local agentic stack**

FlowerOS is the operator-facing usage surface. LeafOS is its persistent execution and evidence engine. A user may provide a detailed work order, a short objective, or no objective at all. LeafOS inventories the project, creates bounded work, asks the configured local model provider for structured proposals, executes only through CPU-side policy, validates the result, checkpoints evidence, and remains available for another iteration.

In LeafOS documentation, **stack** means all downloaded and locally available models in this instance. The active provider route selects one stack entry for a lane; it does not redefine the stack.

## Start A Project

From the canonical `C:\R\LeafOS0.2.3` root in Windows PowerShell:

```powershell
.\leafos.ps1
.\leafos.ps1 q
.\leafos.ps1 provider-stack check
.\leafos.ps1 live
```

The no-argument launcher opens the read-only FlowerOS Home. `leafos.ps1` routes
through the FlowerOS operator surface while durable schemas and engine objects
keep their `leafos.*` names.

The installed quick surface uses the same tokens from any directory:
`leafos q` for the concise command card, `leafos d` for doctor, `leafos r` for
runtime selection, `leafos ref` for the primary reference, `leafos b` for the
verified Monday state, and `leafos help` for the complete command list.

### High-frequency hardware monitor

`core/monitor/flower.c` provides the FlowerOS 60 Hz terminal CPU, RAM, and disk
display on Linux and WSL. The launcher binds `LEAFOS_ROOT` to the canonical
`C:\R\LeafOS0.2.3` checkout (seen as `/mnt/c/R/LeafOS0.2.3` inside WSL), reads
the actual release from its root `VERSION`, and shows free space on the
filesystem that contains the stack. The first run builds
`build/flower-monitor` with `cc`, `gcc`, or `clang`; later runs rebuild only
when the C source changes. Press `q` or Ctrl-C to exit.

For a scriptable snapshot instead of the interactive display:

```powershell
.\leafos.ps1 flower-monitor --once
.\leafos.ps1 flower-monitor --json
.\leafos.ps1 flower-monitor --root-path
.\leafos.ps1 flower-monitor --root C:\R\AnotherLeafOS
```

The `--root` path is interpreted inside Linux/WSL. Use `/mnt/c/...` when
calling the Bash surface directly.

The same monitor is available through every supported command layer:

```text
ProjectLeaf/leafos_taskpack/bin/flower-monitor
ProjectLeaf/leafos_taskpack/bin/flowerctl monitor
ProjectLeaf/leafos_taskpack/bin/leafctl flower-monitor
ProjectLeaf/leafos_taskpack/bin/flower.ps1 monitor
ProjectLeaf/leafos_taskpack/bin/leafctl.ps1 flower-monitor
Bash-Version/leaf.sh flower-monitor
PowerShell-Version/leaf.ps1 flower-monitor
leafos.sh flower-monitor
leafos.ps1 flower-monitor
```

From Windows, the PowerShell routes bridge into WSL because the monitor reads
Linux `/proc` metrics and uses POSIX terminal control. Run `make flower-monitor`
to build it explicitly.

Run `.\leafos.ps1 live` to open guided onboarding: choose **new** or **existing**, select a top-level directory and project name, paste a README and skeleton for a new project, choose the project-only sandbox, optionally queue KV-cache optimization work, review the normalized request, and type `CREATE` or `OPEN`. The resulting project enters the same resident loop and active TUI as every other inlet route.

KV-cache `investigate`, `enable`, and `disable` choices are high-value queued work, not immediate edits to the shared llama.cpp process. The run records the requested preference as `applied: false`, queues a priority-1 task after baseline intake, and requires compatibility detection, validation, rollback, and throughput/VRAM evidence before the state may become applied.

Open a known project directly when no wizard is needed:

```powershell
.\leafos.ps1 live C:\R\MyProject
```

Bash, MSYS2, WSL, Linux, or macOS:

```bash
./leafos.sh provider-stack check
./leafos.sh live /path/to/MyProject
```

Inside the active TUI, press `n` to run the same new/existing project wizard and switch the window to the selected project. `--new` remains a noninteractive convenience that uses built-in seed text:

```powershell
.\bin\leafctl.ps1 live C:\R\MyNewProject --new --template generic --yes --budget 64
```

`leafctl live` inspects or creates the project, starts or reattaches a durable version-2 run, starts the resident supervisor, and opens the active TUI. An objective and specialized commands are optional.

## Instruction Flow

```text
directory + optional objective
            |
            v
read-only project intake
            |
            v
typed work order and durable priority queue
            |
            v
PLAN -> APPROVE -> EXECUTE -> VALIDATE -> CHECKPOINT -> REPORT
  ^                                                   |
  |                                                   v
  +------------- bounded repair or next improvement --+
```

- The provider proposes a schema-constrained plan; it never receives direct filesystem or shell authority.
- The CPU-side inlet validates paths, commands, approvals, attempts, dependencies, budgets, and process ownership.
- Operator tasks have priority at the next safe claim boundary.
- Validation failures create bounded repair work and preserve the failure evidence.
- The resident supervisor may derive one next improvement only inside the approved project boundary and renewable budget.
- Private model chain-of-thought is neither displayed nor persisted. The TUI shows plans, progress events, decisions, tool activity, accepted output, and validation evidence.

## Active Window

Plain objectives are enough. Commands are optional:

```text
n                         new/open project wizard
:improve
:improve add deterministic replay
:again
:make the current interface easier to inspect
:mode quiet
:mode auto
:targets cpu 80 gpu 90
:budget 64m
:pause
:resume
:drain
:stop
```

`q` closes only the TUI. It does not stop the resident stack. `:drain` finishes accepted work and rejects new admission. `:stop` uses a confirmed typed-control flow.

## Resource Behavior

The default idle targets are approximately 80 percent total CPU and 90 percent GPU while useful matching work exists. They are adaptive targets, not synthetic load requirements. Recent local input, latency, RAM, VRAM, temperature, provider health, pause, drain, and stop state can reduce or close dispatch.

On the reference RTX 4070 host, the active coding route is Gemma4-Coder Q3 through llama.cpp Vulkan. The Q3 route leaves execution and foreground headroom that larger routes did not. See [Resident Stack Usage](docs/RESIDENT_STACK_USAGE.md) for profiles, budgets, reason codes, recovery, and host sizing.

GLM-5.2 is deprecated as a local route. The current research policy prefers evidence-gated MoE candidates in the 47-156B total-parameter band, while keeping the proven incumbent active until a named artifact passes 4, 8, and 64 minute qualification. See [Medium MoE Model Policy](docs/MEDIUM_MOE_MODEL_POLICY.md). SSD access remains llama.cpp mmap backed by the OS page cache; LeafOS-managed expert tiering is not implemented.

## Operator Commands

```powershell
# Project and TUI
.\bin\leafctl.ps1 live C:\R\MyProject
.\bin\leafctl.ps1 tui --run active

# Resident lifecycle
.\bin\leafctl.ps1 resident status active --json
.\bin\leafctl.ps1 resident mode active quiet
.\bin\leafctl.ps1 resident targets active --cpu 70 --gpu 85
.\bin\leafctl.ps1 resident budget active 120
.\bin\leafctl.ps1 resident pause active
.\bin\leafctl.ps1 resident resume active
.\bin\leafctl.ps1 resident drain active

# Run and task controls
.\bin\leafctl.ps1 loop status active
.\bin\leafctl.ps1 loop attach active
.\bin\leafctl.ps1 loop monitor active --interactive
.\bin\leafctl.ps1 loop monitor active --noninteractive --jsonl --cursor-file .\monitor.cursor
.\bin\leafctl.ps1 loop task submit active .\config\task-control.submit.sample.json

# Provider and tests
.\bin\leafctl.ps1 provider-stack status --json
.\bin\leafctl.ps1 test visual --plain
.\bin\leafctl.ps1 test visual --match provider --live-stack --plain
```

Use `agent-loop-start --target DIR --work-order FILE --profile local-coding --yes` when a machine-readable work order should be the initial authority instead of inferred project intent.

## Evidence

Every version-2 run is a directory containing the facts needed to inspect and resume it:

```text
run.json                 immutable run identity and target
work-order.json          bounded initial authority
work-orders/             typed operator and generated tasks
queue.json               priority, dependency, attempts, and status
state.json               lifecycle and active-task state
events.jsonl             reconnectable presentation events
control.lmem             hash-chained control journal
resident-state.json      resource policy, decision, budget, and usage
checkpoint.json          validated repository facts and hashes
universal-run-log.jsonl  CPU, GPU, provider, throughput, and task telemetry
artifacts/               plans, provider I/O, command output, and hashes
report.md                completion or current-state report
```

The TUI is a projection of these structured facts. It does not become a second scheduler or mutate run files directly.

## Verification

```powershell
.\bin\leafctl.ps1 test visual --plain
.\bin\leafctl.ps1 resident start --contract-only --iterations 3
.\bin\leafctl.ps1 resident start --profile 4m --provider required
```

The current discovery suite contains 199 tests. Generic resident projects are the recommended demonstration target.

## Optional And Historical Surfaces

The following remain supported or useful, but they are not the primary project workflow:

- `agent-task`, `agent-route`, `agent-dry-run`, and `agent-run`: the finite 0.2 task-plan spine.
- `agent-graph`, `agent-loop`, and `agent-orchestrate`: earlier graph and three-input execution surfaces.
- `oneshot`: portable handoff-bundle generation; it does not start a live loop.
- `node`, `nodes`, `task`, `serve`, and `download`: optional SSH/LAN distribution subsystem.
- `dashboard`: legacy node/cluster status projection. `tui` is the active agent-run interface.
- `realbench`: conversation and raw-inference benchmark. `resident start` is the resident project-improvement surface.

Historical work orders and completion reports preserve the terminology and behavior of their implementation date. They are evidence, not current operator instructions.

## Documentation

- [Documentation Map](docs/DOCUMENTATION_MAP.md): authority, reading order, and historical boundaries.
- [Quick Start](docs/QUICKSTART.md): first live project and basic controls.
- [Architecture](docs/ARCHITECTURE.md): subsystem and authority boundaries.
- [Agentic CLI](docs/AGENTIC_CLI.md): instruction parsing and execution contract.
- [Live Project TUI](docs/LIVE_PROJECT_TUI.md): minimal active-window syntax.
- [Continual Loop Inlet](docs/LOOP_INLET_USAGE.md): run lifecycle and typed tasks.
- [Continual Bloom Runtime](docs/CONTINUAL_BLOOM_RUNTIME.md): durable Monday transcript, claims, evidence, checkpoints, and recovery.
- [Terminal Interface](docs/TUI_USAGE.md): pages, keys, renderer boundary, and snapshots.
- [Resident Stack Usage](docs/RESIDENT_STACK_USAGE.md): scheduling, resource policy, recovery, and benchmarks.
- [Model Installation](docs/MODEL_INSTALLATION.md): stack acquisition and selection.
- [User Recommendations](User_recs.md): PowerShell install, `$T` budgets, non-interactive runs, and passive HTML reports.
- [Medium MoE Model Policy](docs/MEDIUM_MOE_MODEL_POLICY.md): candidate contract, provenance, SSD truth, and qualification gates.
- [Test Observatory](docs/TEST_OBSERVATORY_USAGE.md): visual and live-provider test evidence.
- [WO-038 Completion Report](reports/work-orders/WO-038-COMPLETION-REPORT.md): implementation and real-run evidence.

## Platform Support

| Platform | Primary shell | Runtime notes |
|---|---|---|
| Windows | PowerShell 7 | Canonical resident host; MSYS2 supplies Bash/Python/C tooling. |
| WSL/Linux | Bash | Core CLI and Python loop supported; foreground probes degrade conservatively. |
| macOS | Bash + PowerShell optional | Core CLI supported; Vulkan/provider configuration is host-specific. |

Use `leafctl help`, `leafctl doctor`, `leafctl platform`, and `leafctl versions` to inspect the local installation.
