# Overnight Sandbox Runbook

> Historical GLM-5.2 experiment. Its sandbox and reporting lessons remain
> useful, but the model route and rate gates are deprecated. Current model
> qualification is defined in `MEDIUM_MOE_MODEL_POLICY.md`.

Before adapting these sandbox procedures for a current model candidate, inspect
the read-only Medium-MoE runtime status described in
[`MEDIUM_MOE_MODEL_POLICY.md`](MEDIUM_MOE_MODEL_POLICY.md). The current
4/8/64-minute qualification sequence supersedes this document's GLM-specific
schedule; this historical runbook must not be used to activate a provider.

`overnight-01` is a six-assignment, sequential run intended to determine whether slow GLM-5.2 inference produces validated useful work over an extended run.

## Schedule and stop rule

Each assignment has a 182-minute budget. The six task windows total 1,092 minutes. Five transitions add 60 seconds of cleanup and 20 seconds of model-free loading animation each, for a total nominal duration of 1,572 minutes (26 hours 12 minutes). This is longer than one overnight period.

| Sequence | Assignment | Type |
|---:|---|---|
| 1 | `coding-cli` | Nearly empty coding fixture |
| 2 | `coding-library` | Nearly empty coding fixture |
| 3 | `coding-parser` | Nearly empty coding fixture |
| 4 | `game-chess` | Staged deterministic bot-versus-bot simulation |
| 5 | `game-catan` | Staged deterministic bot-versus-bot simulation |
| 6 | `game-ticket-to-ride` | Staged deterministic bot-versus-bot simulation |

Every assignment needs a validated checkpoint by minute 30. Stop it early with `unproductive_no_validated_checkpoint` if that checkpoint is absent. Do not spend the remaining budget merely waiting for text generation.

## Between-project transition

After each completed or stopped assignment, run the transition before starting the next project:

```powershell
pwsh -File bin/leaf-sandbox.ps1 transition --execute
```

The transition performs a 60-second cleanup interval followed by a 20-second loading animation. It does not delete source files, download a model, or invoke inference. Preview it without waiting using:

```powershell
pwsh -File bin/leaf-sandbox.ps1 transition
```

## Validate and preview

The commands below do not start a model and do not copy any sources:

```powershell
pwsh -File bin/leaf-sandbox.ps1 validate
pwsh -File bin/leaf-sandbox.ps1 plan
```

## Stage isolated copies

Staging copies each fixture or game source into `sandbox/overnight-01/work/`. The original game projects under `FF/LeafOS/projects` are never modified by the runner.

```powershell
pwsh -File bin/leaf-sandbox.ps1 stage --yes
```

To inspect a single assignment before copying it:

```powershell
pwsh -File bin/leaf-sandbox.ps1 stage --task game-chess
```

To stage only that assignment after review:

```powershell
pwsh -File bin/leaf-sandbox.ps1 stage --task game-chess --yes
```

The runner refuses to overwrite an existing staged directory. Delete or archive a staged task only after preserving its `RUN_REPORT.json` and validation logs.

## Worker contract

The staging CLI intentionally does not launch a model. A later worker integration must run only inside the selected `work/<task-id>` directory and must:

1. Read that task's JSON work order before editing files.
2. Write a first validated checkpoint before minute 30.
3. Run the task's stated validation commands before reporting completion.
4. Write `RUN_REPORT.json` with the command log, changed files, test result, elapsed time, and stop reason.
5. Avoid network access, dependency installation, model downloads, and changes outside the staged task directory.
6. Run the transition command before handing control to the next assignment.

The game work orders are deliberately constrained to their existing abstract, deterministic simulations. The model may reproduce a seeded bot-versus-bot run and improve a small report or test, but it must not attempt a full-rule game rewrite during this evaluation.

## Productive result criteria

The final count is not total generated tokens. Record, for every task:

- whether the 30-minute checkpoint was reached;
- whether validation passed;
- whether a patch was accepted, rejected, or intentionally omitted;
- elapsed time and stop reason; and
- the number of validated useful changes.

Compare the resulting 26-hour-12-minute run output with the GLM-5.2 rate and telemetry report described in [GLM52_OVERNIGHT_RUNBOOK.md](GLM52_OVERNIGHT_RUNBOOK.md).

## Rich telemetry and tensor tracking

The telemetry contract is defined in `schemas/overnight_telemetry.schema.json`. Record JSONL events for run start/end, task start/end, checkpoints, samples, validation, transitions, recovery, and tensor snapshots. Use `null` for a counter that was not available and explain the reason in `availability`; do not encode unavailable hardware data as zero.

The sandbox CLI exposes the telemetry path:

```powershell
pwsh -File bin/leaf-sandbox.ps1 telemetry append --log runs/overnight-01/telemetry.jsonl --event config/overnight_telemetry.sample.json
pwsh -File bin/leaf-sandbox.ps1 telemetry summary --log runs/overnight-01/telemetry.jsonl --output runs/overnight-01/summary.json
```

Tensor tracking is optional and requires the inference backend or an adapter to emit metadata. It should record:

- tensor name, layer, and expert ID when available;
- shape, dtype, and byte size;
- placement: CPU, GPU, RAM hot cache, NVMe, or unknown;
- transfer bytes and transfer time; and
- the event/task/run association.

For an adapter-provided tensor snapshot:

```powershell
pwsh -File bin/leaf-sandbox.ps1 telemetry tensor `
  --log runs/overnight-01/telemetry.jsonl `
  --run-id overnight-01 `
  --task-id game-chess `
  --tensor runs/overnight-01/tensor.snapshot.json
```

The generic runner cannot reliably discover tensor placement or expert routing from ordinary `llama.cpp` text output. Missing tensor fields must remain unavailable rather than inferred. Backend instrumentation is required for authoritative per-tensor transfer and residency measurements.
