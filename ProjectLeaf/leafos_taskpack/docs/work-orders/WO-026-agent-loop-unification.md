# WO-026 - Agentic Loop Unification, Five-Part Plan

## Identity

- Owner/context: LeafOS top-level agentic workflow
- Current day: Day 2
- Release target: 0.2.2 local loop stabilization, then 0.3 orchestration merge
- Branch: local workspace
- Scope boundary: `bin/leafctl`, `bin/leafctl.ps1`, `core/python/leaf_agent_loop.py`, `config/agent_loop_profiles.json`, `share/templates/projects`, `runs/agent-loop`, `tests`
- Authority: user request to continue unification over a roughly five-part plan

## Purpose

LeafOS already has the right ingredients: oneshot bundles, task files, graph loop
execution, sandbox staging, dual-brain harness state, and stack/provider routing.
The gap is the top-level noninteractive loop that a user can start on a directory
and inspect later without relying on chat context.

In this work order, **stack** means all models downloaded and locally available
to this LeafOS instance. The provider serves selected stack entries; it is not
the stack itself.

This work order unifies those pieces into one local operator command:

```powershell
pwsh -NoProfile -File C:\R\LeafOS0.2.2\ProjectLeaf\leafos_taskpack\bin\leafctl.ps1 agent-loop-start --target C:\Games --projects chess3D,generic-python-sim --profile local-games --yes
```

The loop should create or reuse a workspace, schedule tasks, route plans, execute
safe steps, run validations, checkpoint results, report status, and resume from
disk. Provider output is treated as proposal material. CPU-side validators and
local policy remain the authority for filesystem mutation, game moves, and
accepted checkpoints.

## Part 1 - Operator Entry and Sandbox Factory

Build the top-level operator surface first.

Deliverables:

- `leafctl agent-loop-start --target DIR --projects LIST --profile NAME`
- `leafctl sandbox-create --target DIR --projects LIST`
- dry-run support that prints planned directories, files, queue entries, and
  validation commands without writing
- `--yes` support for noninteractive creation
- project skeleton templates for `chess3D`, `generic-c-game`, and
  `generic-python-sim`

Acceptance criteria:

- [x] A dry-run against a temp `C:\Games`-like directory writes no files.
- [x] A real run creates the target workspace and requested project folders.
- [x] Existing project folders are not overwritten unless `--force` is passed.
- [x] Each created project has `README.md`, `WORK_ORDER.md`, `project_state.json`,
      `run_tests.ps1`, `run_tests.sh`, `src` or `core`, `tests`, and `reports`.

## Part 2 - Durable Run State and Task Queue

Make every loop inspectable and resumable from files alone.

Canonical run layout:

```text
runs\agent-loop\<run-id>\
  run.json
  queue.json
  state.json
  events.jsonl
  journal.jsonl
  checkpoint.json
  report.md
  artifacts\
  workspaces\
```

Task states:

```text
queued -> planning -> planned -> executing -> validating -> checkpointed -> complete
queued -> blocked
executing -> failed -> repair_queued
validating -> failed -> repair_queued
```

Acceptance criteria:

- [x] `agent-loop-status` reads status without starting a model or mutating files.
- [x] `run.json` records target, profile, provider mode, projects, start time,
      safety policy, max attempts, and max minutes.
- [x] `queue.json` records task dependencies and validation commands.
- [x] `events.jsonl` records ordered event sequences.
- [x] `checkpoint.json` records last event sequence, queue digest, completed task
      IDs, provider mode, and stop reason.
- [x] Resume refuses corrupt, missing, or out-of-order event streams.

## Part 3 - Planner and Executor Contract

Connect queued work to the existing provider route, but keep execution bounded.

Flow:

```text
task record -> planner prompt -> structured provider proposal -> validated plan
-> dry-run preview -> bounded execution -> validation -> checkpoint or repair task
```

Rules:

- Model/provider output is never executed directly.
- Mock/offline provider remains the default test path.
- llama.cpp/Vulkan provider is allowed only through configured loopback endpoints.
- Plans must be structured and schema-validated before any step runs.
- Commands must run inside allowlisted workdirs.
- Long commands must have timeouts.

Acceptance criteria:

- [x] A mock provider task creates a valid plan.
- [x] Malformed provider output fails closed.
- [x] `agent-loop-tick` can process exactly one task boundary for predictable
      unattended operation.
- [x] Passing validation writes a checkpoint.
- [x] Failing validation writes failure evidence and queues one repair task.
- [x] Timeout writes a timeout event and leaves status readable.

## Verified Non-Game Repository Inlet Slice

The repository inlet is now the preferred non-game entry point for this work
order. It remains deliberately bounded to the existing single validation
command; multi-step mutation is not claimed complete here.

- [x] An existing repository can be started without creating a game template.
- [x] A repository work order can be supplied through `--work-order`.
- [x] Work-order path, title, byte count, and SHA-256 are persisted in `run.json`.
- [x] The queued task links to the persisted work-order path.
- [x] Work orders outside the repository safety boundary are rejected.
- [x] Focused repository-inlet and agent-loop tests pass (`18` tests).

## Part 4 - Game Benchmark Integration

Use games as the first real benchmark because they expose the full loop:
planning, action, validation, scoring, iteration, and observable improvement.

Chess3D first:

- start with skeleton board/rules engine
- add deterministic legal move generation
- add bot match and state export
- add visualization later, after the loop runner is stable

Acceptance criteria:

- [x] `chess3D` can be created under a target workspace.
- [x] The loop can run a short chess3D baseline without GPU provider startup.
- [x] Benchmark artifacts land under the run directory.
- [x] Benchmark artifacts are also copied or summarized into project `reports`.
- [x] Validation results are attached to task evidence.
- [x] Regression results create repair tasks rather than silent acceptance.

## Part 5 - Observability and Dual-Brain Provider Closure

Expose what is happening under the hood as durable external loop events. This is
not raw hidden model chain-of-thought; it is the inspectable reasoning/action
surface LeafOS can safely record: task summaries, plan choices, tool actions,
validation results, memory writes, stack selection, provider health,
checkpoints, and failures.

Operator commands:

```text
leafctl agent-loop-status <run-dir>
leafctl agent-loop-tick <run-dir>
leafctl agent-loop-resume <run-dir> --yes
leafctl agent-loop-stop <run-dir> --after-current-step
leafctl agent-loop-report <run-dir>
```

Provider policy:

- `provider-mode off`: CPU/mock only
- `provider-mode auto`: try GPU/llama.cpp, degrade to CPU/mock when allowed
- `provider-mode required`: fail early if provider executable, model, or endpoint
  is missing

Acceptance criteria:

- [x] Status shows run id, current project, current task, provider mode, last
      event, last checkpoint, stack entry, validation status, and next action.
- [x] Report summarizes completed tasks, failed tasks, repair tasks, and
      artifacts.
- [x] Report summarizes provider failures and benchmark deltas.
- [x] Provider required mode fails before creating a half-started loop when the
      Vulkan/llama.cpp config is incomplete.
- [x] Provider auto mode records startup failure and continues if policy allows.
- [x] The dual-brain harness can read/write loop task state instead of keeping a
      separate private task state format.

## Implementation Order

1. Add `core/python/leaf_agent_loop.py` with `create`, `status`, `tick`, `resume`,
   and `report` subcommands.
2. Add `config/agent_loop_profiles.json` with `local-games`, `cpu-only`, and
   `provider-auto` profiles.
3. Add project templates under `share/templates/projects`.
4. Wire `bin/leafctl.ps1` and `bin/leafctl` commands.
5. Add tests for dry-run, create, status read-only, queue state, validation pass,
   validation fail, timeout, and resume.

## Status

[W] WO-026: Agentic loop unification
[D] Day 2: planner, benchmark, telemetry, and dual-harness closure
[I] DONE
[V] PASS: `python -B tests/test_agent_loop.py` (10 tests),
    `bash tests/agent_loop.sh`, `python -B tests/test_dual_harness.py` (7 tests),
    Python AST parse, Bash syntax, and PowerShell AST parse
[P] LOCAL
[N] Handoff to WO-027 dashboards and longer real-provider utilization runs.

## Implemented Slice

The first working top-level loop is available through:

```powershell
pwsh -NoProfile -File C:\R\LeafOS0.2.2\ProjectLeaf\leafos_taskpack\bin\leafctl.ps1 agent-loop-start --target C:\Games --projects chess3D,generic-python-sim --profile local-games --yes
pwsh -NoProfile -File C:\R\LeafOS0.2.2\ProjectLeaf\leafos_taskpack\bin\leafctl.ps1 agent-loop-status C:\Games
pwsh -NoProfile -File C:\R\LeafOS0.2.2\ProjectLeaf\leafos_taskpack\bin\leafctl.ps1 agent-loop-tick C:\Games
pwsh -NoProfile -File C:\R\LeafOS0.2.2\ProjectLeaf\leafos_taskpack\bin\leafctl.ps1 agent-loop-stop C:\Games --after-current-step
pwsh -NoProfile -File C:\R\LeafOS0.2.2\ProjectLeaf\leafos_taskpack\bin\leafctl.ps1 agent-loop-resume C:\Games --yes
pwsh -NoProfile -File C:\R\LeafOS0.2.2\ProjectLeaf\leafos_taskpack\bin\leafctl.ps1 agent-loop-report C:\Games
```

Implemented files:

```text
core/python/leaf_agent_loop.py
config/agent_loop_profiles.json
share/templates/projects/chess3D/TEMPLATE.md
share/templates/projects/generic-c-game/TEMPLATE.md
share/templates/projects/generic-python-sim/TEMPLATE.md
tests/test_agent_loop.py
tests/agent_loop.sh
```

Run artifacts:

```text
runs/agent-loop/<run-id>/run.json
runs/agent-loop/<run-id>/queue.json
runs/agent-loop/<run-id>/state.json
runs/agent-loop/<run-id>/events.jsonl
runs/agent-loop/<run-id>/journal.jsonl
runs/agent-loop/<run-id>/checkpoint.json
runs/agent-loop/<run-id>/report.md
runs/agent-loop/<run-id>/artifacts/
```

The current tick executor handles one queued baseline task per call. Provider
output is represented as a structured proposal and remains proposal-only. Plans
must preserve the queued command, stay inside the task workdir, contain one
bounded step, and remain within the queued timeout. Malformed proposals are
rejected and create repair tasks; no raw provider text is executed.

Task evidence now includes a copy of validation summaries under the project
`reports` directory. The dual-brain
harness can point `agent_loop_run_dir` at a run and update its canonical
`queue.json` directly; task arrays are no longer copied into private harness
state in that mode.

## Evidence Log

- 2026-07-19: planner contract and malformed-proposal fail-closed test - PASS.
- 2026-07-19: Validation report promotion and regression repair gate - PASS.
- 2026-07-19: provider-auto degraded fallback recording - PASS.
- 2026-07-19: shared dual-harness/agent-loop queue integration - PASS.

## Out of scope

- Raw hidden chain-of-thought export.
- Real model weight training.
- Unrestricted shell execution.
- Starting GPU providers implicitly in dry-run mode.
- Full graphical TUI; this WO should land the inspectable CLI first.
