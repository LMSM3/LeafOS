# WO-027 - Universal Run Telemetry And Hardware Utilization Log

## Identity

- Owner/context: LeafOS run observability and hardware utilization
- Current day: Day 1
- Release target: 0.2.2 run logging bridge, 0.3 operator dashboard input
- Branch: local workspace
- Scope boundary: `core/python/leaf_telemetry.py`, `core/python/leaf_agent_loop.py`, `core/bench/*bench.py`, `core/runtime/continual_live.py`, `schemas/leafos.universal-run-log.v1.schema.json`, `config/universal_run_log.columns.json`
- Authority: user request for rich JSON tied to all runs, focused on hardware underuse

## Purpose

Runs are not using the available hardware well enough. The first fix is not more
model routing; it is a universal log that every run writes so hardware starvation
becomes visible.

Every run should append one JSONL stream:

```text
<run-dir>/universal-run-log.jsonl
```

Each line is a `leafos.universal_run_log.event` object. The event records run
identity, stack selection, provider health, instance counts, brain/coder token
rates, GPU/CPU utilization, memory, I/O, scheduler pressure, validation status,
and artifacts.

## Primary Columns

The first operator table should use these columns from
`config/universal_run_log.columns.json`:

```text
#                         $.sequence
# instances initiated      $.instances.initiated
# instances alive          $.instances.alive
brain tk/s                 $.throughput.brain_generation_tk_s
coder tk/s                 $.throughput.coder_generation_tk_s
GPU %                      $.hardware.gpu.utilization_percent
CPU %                      $.hardware.cpu.utilization_percent
VRAM GB                    $.hardware.gpu.vram_used_gb
RAM GB                     $.hardware.memory.ram_used_gb
W                          $.hardware.gpu.power_watts
queue                      $.scheduler.queue_depth
validation                 $.quality.validation_status
```

The first derived warnings should be:

```text
gpu_starved: instances alive > 0 and GPU % < 35 for three consecutive samples
cpu_bound: CPU % > 85 and GPU % < 50
coder_idle: coder instance alive but coder tk/s is null or zero
brain_coder_ratio: brain tk/s divided by coder tk/s when both are positive
```

## JSON Contract

Schema:

```text
schemas/leafos.universal-run-log.v1.schema.json
```

Sample event:

```text
config/universal_run_log.sample.json
```

Column config:

```text
config/universal_run_log.columns.json
```

## Integration Plan

1. [done] Extend `leaf_telemetry.py` with `make_universal_event()`,
   `append_universal_event()`, and `summarize_universal_log()`.
2. [done] Add `leafctl telemetry universal-sample RUN_DIR` and
   `leafctl telemetry universal-summary RUN_DIR_OR_LOG`.
3. [done] Wire `leaf_agent_loop.py` to append:
   `run_start`, `task_start`, `sample`, `validation`, `checkpoint`, and `run_end`.
4. [done] Wire `fullstackbench.py` and `continual_live.py` to emit
    universal samples into their run directories.
5. [done] Add hardware collectors:
   CPU percent, process CPU percent, RAM, GPU percent, VRAM, temperature, power,
   NVMe read/write throughput, and counter availability.
6. [done] Add a rollup report that flags GPU starvation, CPU binding, provider churn,
   and idle coder/brain lanes.

## Acceptance Criteria

- [x] Every new `agent-loop` run creates `universal-run-log.jsonl`.
- [x] Every realbench and fullstackbench run appends at least one universal run sample.
- [x] Every successful continual-live request appends throughput and provider
      status samples; startup/request failures append `run_error` evidence.
- [x] A run with no GPU counters still writes a valid event with
      `availability.gpu_counters = not_collected`.
- [x] `instances.initiated` and `instances.alive` are present on every sample.
- [x] Brain and coder token rates are separate fields, not one blended rate.
- [x] GPU %, CPU %, VRAM GB, RAM GB, queue depth, and validation status are
      available as dashboard columns.
- [x] The summarizer can detect `gpu_starved`, `cpu_bound`, and `coder_idle`.

## Status

[W] WO-027: Universal run telemetry and hardware utilization log
[D] Day 1: contract, collectors, producer wiring, and rollup complete
[I] DONE
[V] PASS: `python -B tests/test_telemetry.py` (7 tests),
    `python -B tests/test_agent_loop.py` (8 tests), full-stack
    telemetry end-to-end runs, CLI sampling/summary, Python AST, Bash syntax,
    and PowerShell AST. Long continual-live real-provider duration not run.
[P] LOCAL
[N] Feed `universal-run-log.jsonl` into the top-level operator dashboard and
    use 4/8/64-minute real-provider runs to tune utilization thresholds.

## Operator Commands

```powershell
pwsh -NoProfile -File bin\leafctl.ps1 telemetry universal-sample C:\Games\runs\manual --run-kind manual --json
pwsh -NoProfile -File bin\leafctl.ps1 telemetry universal-summary C:\Games\runs\manual
```

Each live sample is best-effort and null-safe. On the verification host the
collector successfully read CPU and process utilization, RAM, RTX 4070 GPU
utilization, VRAM, GPU temperature, GPU power, and Windows physical-disk read,
write, and latency counters. Unavailable counters remain null and carry an
explicit availability state.

## Evidence Log

- 2026-07-19: ordered JSONL append and null-safe unavailable-counter test - PASS.
- 2026-07-19: GPU-starved, CPU-bound, coder-idle, and brain-idle rollup tests - PASS.
- 2026-07-19: agent-loop lifecycle telemetry and report warnings - PASS.
- 2026-07-19: Full-stack benchmark telemetry emission - PASS.
- 2026-07-19: Windows `leafctl.ps1 telemetry` sampling and summary route - PASS.

## Out Of Scope

- Changing model weights or training.
- Treating telemetry as authority for file mutation.
- Requiring GPU counters on machines where they are unavailable.
- Exporting private hidden reasoning. The log records external run facts only.
