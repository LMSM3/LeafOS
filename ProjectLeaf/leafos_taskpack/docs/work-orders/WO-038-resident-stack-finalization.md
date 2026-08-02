# WO-038: Resident Stack Finalization

## Continual Scheduler And Adaptive Resource Governor

Machine-readable authority: `WO-038-resident-stack-finalization.json`

Status: implementation complete; real 4-minute profile passed; 8-minute and 64-minute soaks pending

## Objective

Finalize the live agentic stack as a resident workstation service. The stack must remain available, accept tasks while other tasks are running, continually claim and validate eligible work, and use available CPU and GPU productively without making the computer unpleasant to use.

The default high-throughput targets are approximately 80 percent total CPU and 90 percent GPU utilization while useful work is available. These are adaptive targets, not promises to create artificial load. Recent operator input, foreground pressure, memory limits, provider health, temperatures, and validation boundaries may lower dispatch pressure immediately.

In this document, the stack means all downloaded and locally available models in this LeafOS instance.

## Final Operating Model

```text
leafctl live PROJECT
        |
        v
resident supervisor ---- operator/TUI input
        |                       |
        v                       v
durable priority queue <--- typed task admission
        |
        v
resource governor ---> claim / defer / reduce / recover
        |
        +--> GPU stack: planning and coding proposals
        +--> CPU lanes: execution, tests, validation, indexing
        |
        v
checkpoint + report + next bounded improvement
```

The operator should be able to start one live project and then continue using the computer. New objectives may be entered at any time. They are added durably and do not interrupt a command at an unsafe boundary. Operator tasks take priority at the next claim boundary.

Minimal commands remain optional. A project may begin as a mature repository, a partial implementation, documentation only, or a three-file README, skeleton, and JSON seed. When no objective is supplied, LeafOS derives one bounded next improvement from project facts, the latest validation, and the previous completion report.

## Existing Baseline

WO-038 builds on working components rather than creating a second loop:

- Persistent version-2 run directories, priority queues, dependencies, checkpoints, and reports.
- Worker leases and recovery after process interruption.
- Typed task admission plus pause, resume, stop, drain, approve, retry, cancel, and reprioritize controls.
- A persistent llama.cpp Vulkan provider with health checks.
- Universal CPU, GPU, VRAM, RAM, temperature, power, throughput, and instance telemetry.
- Python and native TUI renderers using an authenticated loopback control bridge.
- `leafctl live PROJECT`, inferred objectives, repeated improvement tasks, and Catan2-aware validation.

The missing behavior is closed-loop resource control, resident queue supervision, bounded automatic queue refill, foreground awareness, provider recovery policy, and a TUI view that explains every scheduling decision.

## Resource Policy

### Profiles

| Profile | CPU target | GPU target | Intended behavior |
|---|---:|---:|---|
| `auto-idle` | 80% | 90% | Useful backlog exists and recent foreground activity is low. |
| `auto-interactive` | 55-65% | 65-80% | Recent keyboard or mouse input reserves immediate workstation headroom. |
| `pressure` | claim gate closed | claim gate closed | Memory, thermal, power, provider, or responsiveness limit is active. Current safe work may finish. |
| `quiet` | configurable, low | configurable, low | Explicit operator preference for background operation. |
| `full` | configurable, high | configurable, high | Explicit operator preference, still subject to hard safety limits. |

Targets apply only while matching productive work exists. LeafOS must never start meaningless work, duplicate inference, or spin a CPU loop to improve a utilization number.

### Governor Inputs

- CPU total and LeafOS process utilization.
- GPU utilization, VRAM use, temperature, power, and provider process health.
- RAM pressure and optional disk queue pressure.
- Brain and coder throughput.
- Eligible queue depth, active lane, and task resource hints.
- Time since local keyboard or mouse input.
- Foreground responsiveness probe and scheduler decision latency.
- Current approval, pause, drain, stop, retry, and budget state.

### Governor Decisions

- Admit or defer the next task claim.
- Select a CPU, GPU, or mixed lane.
- Raise or lower CPU worker concurrency.
- Apply a bounded delay before the next provider request.
- Keep one healthy provider warm without launching duplicate model instances.
- Enter interactive, pressure, recovery, paused, draining, or waiting state.
- Explain the decision with a stable reason code visible in telemetry and the TUI.

Use an exponentially weighted utilization window, hysteresis, and a cooldown between concurrency changes. A single noisy sample must not repeatedly start and stop workers. Normal throttling occurs at task or provider-request boundaries; hard thermal, memory, stop, and cancellation conditions may terminate a tracked subprocess through the existing inlet authority.

## Continual Queue Policy

1. Accept typed tasks while another task is executing.
2. Persist admission before acknowledging it to the TUI.
3. Claim only tasks whose dependencies, approval, path policy, and resource lane are ready.
4. Prefer operator-authored tasks, then repair tasks, then automatically derived improvements.
5. Finish the active safe unit before changing ordinary priorities.
6. When eligible depth reaches zero, inspect the last report and validation evidence.
7. Derive one next improvement only when continual mode and its budget permit it.
8. Validate, checkpoint, and report every iteration before another improvement is generated.
9. Enter `waiting` when no safe, useful improvement can be justified.
10. Enter `awaiting_budget` when the unattended time, iteration, failure, or change budget is exhausted.

Automatic refill is bounded autonomy, not an infinite permission grant. The initial live-project approval authorizes only declared roots, command allowlists, resource ceilings, and a renewable work budget. Queue corruption, repeated failure, missing provider output, or uncertain scope fails closed.

## Planned TUI Experience

The active window should always show:

- Resident state: active, interactive, throttled, waiting, paused, draining, or recovering.
- Current and target CPU/GPU utilization.
- Queue depth split into ready, blocked, active, repair, and generated work.
- Provider instance count, health, VRAM, and brain/coder throughput.
- Current resource profile and the reason for the latest governor decision.
- Remaining time, iteration, failure, and change budgets.
- Foreground headroom and latest responsiveness measurement.

The existing plain objective input remains the shortest task entry. Planned optional controls are:

```text
:improve [objective]
:again
:mode auto|quiet|full
:targets cpu 80 gpu 90
:budget 64m
:pause
:resume
:drain
:stop
```

Settings must become typed inlet requests. Neither renderer may edit policy files, mutate queues, or execute shell text directly.

## Five-Part Implementation Plan

### Part 1: Policy Contract And Deterministic Governor

Create a versioned resource-policy schema and a pure governor function. Given a policy, queue facts, hardware sample, activity state, and previous decision, it returns a typed decision and reason code.

Deliverables:

- `schemas/leafos.resource-policy.v1.schema.json`
- `core/python/leaf_resource_governor.py`
- Default policy with 80 percent CPU and 90 percent GPU idle targets.
- Fake-clock and recorded-sample tests for hysteresis, cooldown, safety limits, and missing counters.
- Decision events and universal telemetry fields without high-frequency journal noise.

Gate: deterministic tests prove that the governor reduces pressure during user activity, never increases pressure under a hard limit, and never invents unavailable hardware values.

### Part 2: Resident Supervisor And Queue Refill

Add one supervisor above the existing worker. It owns lifecycle and resource decisions but continues to use the current inlet for queue mutation and task execution.

Deliverables:

- `core/python/leaf_resident_supervisor.py`
- A renewable resident lease distinct from per-command process leases.
- Durable waiting, interactive, throttled, recovering, and awaiting-budget states.
- Admission during execution and atomic acknowledgement.
- Bounded automatic next-improvement generation from accepted evidence.
- Recovery after supervisor restart without duplicate task claims.

Gate: tasks added during a long validation run survive restart, retain priority and dependencies, and execute exactly once.

### Part 3: Foreground Headroom And Provider Recovery

Connect Windows input-idle detection, responsiveness probes, telemetry, and provider liveness to the governor. Keep platform-specific probes optional and fail to a conservative profile when unavailable.

Deliverables:

- Foreground activity adapter with injectable test clock and samples.
- CPU worker concurrency control at safe boundaries.
- GPU request pacing and provider-slot policy bounded by VRAM.
- Provider keepalive plus bounded restart backoff and an explicit degraded state.
- Thermal, memory, and responsiveness trip reasons.

Gate: synthetic input switches to the interactive profile promptly; idle recovery ramps gradually; provider failure cannot create duplicate model instances or silently fall back to fake output.

### Part 4: Active Window Controls And Explanation

Extend the normalized TUI snapshot, Python renderer, native renderer, and authenticated controller with resident-state controls and queue admission feedback.

Deliverables:

- Resource targets, profile, headroom, budgets, queue classes, and reason codes in the snapshot schema.
- TUI controls for mode, targets, budget, pause, resume, drain, and stop.
- Immediate acknowledgement containing the durable task ID for new input.
- A visible distinction between closing the TUI and stopping the resident stack.
- Reconnect to the same live state after the TUI is closed and reopened.

Gate: malformed, unauthenticated, overlong, and shell-like control payloads fail closed; disconnecting either renderer does not interrupt the stack.

### Part 5: Catan2 Soak, Tuning, And Final Cleanup

Use Catan2 as the final resident-stack benchmark. Start from both the current medium codebase and a fresh three-file Catan2 seed. Let LeafOS repeatedly improve game complexity while new operator objectives are added through the TUI.

Run profiles:

- 4 minutes: startup, task admission, one provider proposal, validation, and checkpoint smoke test.
- 8 minutes: repeated queue execution, live operator input, profile transition, and reconnect test.
- 64 minutes: provider longevity, adaptive utilization, bounded auto-refill, recovery, and evidence soak.

Final cleanup removes superseded scheduler paths, duplicate lifecycle logic, and fixtures replaced by recorded or real-provider contracts. Historical telemetry remains readable.

Gate: the 64-minute run produces multiple validated Catan2 increments without lost tasks, duplicate execution, unsafe path expansion, provider duplication, or UI-induced interruption.

## Measurement And Acceptance

- The resident stack accepts and durably acknowledges a task while another task is active.
- Closing and reopening the TUI does not stop work or lose the event cursor.
- With productive backlog and an idle workstation, GPU-active windows normally remain within 80-98 percent and CPU-work windows normally remain within 65-85 percent after warmup.
- Utilization is reported separately for inference, execution, validation, waiting, and user-active periods; averages must not hide idle or throttled time.
- Recent local input lowers pressure without losing provider state or task progress.
- Foreground responsiveness remains inside the benchmark threshold selected in Part 1 and is reported at p50, p95, and maximum.
- Pressure and recovery decisions include stable reason codes and timestamps.
- Provider crashes use bounded backoff, never spawn duplicate stack instances, and become visibly degraded after the retry budget.
- Every generated improvement has a source report, bounded objective, dependency, validation gate, checkpoint, and completion report.
- Exhausted budgets, repeated failures, or absent safe work result in waiting or blocked state rather than invented activity.
- No private chain-of-thought is displayed or persisted.
- Focused tests, the complete visual suite, native C build, and 4/8/64-minute Catan2 demonstrations pass.

## Non-Goals

- Guaranteeing exact utilization when the workload cannot use the hardware.
- Keeping the GPU busy with duplicate or speculative requests that do not advance a task.
- Granting the TUI shell, filesystem, queue-file, or policy-file authority.
- Running unlimited self-generated work without a renewable budget and declared project boundary.
- Replacing the existing inlet, journal, work-order, validation, or checkpoint contracts.

## Completion Evidence

WO-038 is complete only when its report contains:

- The final policy and reason-code tables.
- Unit and integration test counts.
- Native and Python TUI control evidence.
- Provider process and restart evidence.
- CPU/GPU phase distributions rather than one blended average.
- Foreground responsiveness percentiles.
- Queue admission, restart, reconnect, pause, drain, and recovery evidence.
- Catan2 4-minute, 8-minute, and 64-minute run directories and validated improvement summaries.
