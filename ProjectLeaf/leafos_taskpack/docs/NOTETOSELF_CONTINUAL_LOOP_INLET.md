# Continual Loop Inlet Maintenance Note

Status: the original inlet, typed-task, native-TUI, and resident-finalization slices are implemented. This file now tracks intentional compatibility debt rather than planned core architecture.

## Current Contract

- `leafctl live PATH` is the top-level project inlet and starts the resident supervisor by default.
- Every instruction converges on the version-2 run, typed queue, plan-v2 provider proposal, CPU executor, validation, checkpoint, and report path.
- Operator tasks may be admitted while work is active and take priority at the next safe claim boundary.
- Automatic refill is evidence-derived and bounded by project scope, time, iterations, failures, and changed files.
- One supervisor lease and one worker lease prevent duplicate ownership.
- Resource claims are governed by foreground activity, responsiveness, CPU/GPU targets, RAM/VRAM, temperature, provider health, and lifecycle controls.
- The Python and native TUI renderers consume one normalized snapshot and send authenticated named controls.
- A missing or malformed required provider response fails visibly. No synthetic plan is substituted.
- Public phase summaries are observable; private chain-of-thought is not persisted.

## Test-Only Mock Debt

| Location | Why it remains | Removal gate |
|---|---|---|
| `core/providers/providers.sh` `_leaf_adapter_mock` | Deterministic provider contract tests. | Recorded/live fixtures cover success, malformed output, timeout, stream termination, and recovery. |
| `core/orchestration/orchestrate.sh` `_orch_mock_plan` | Stable early three-input executor fixture. | Replace with checked-in schema-valid plan and response artifacts. |
| Provider test scripts using `--provider mock` | Validate the gated test adapter. | Remove with the adapter after equivalent recorded contracts exist. |
| Telemetry schema value `mock` | Reads historical run logs. | Keep read compatibility; production must not emit it. |

Production runs do not select these fixtures implicitly. CPU fallback may perform declared validation; it does not claim model-generated edits.

## Current Follow-Up Work

1. Run and retain the real 8-minute and 64-minute WO-038 Catan2 resident profiles.
2. Replace remaining mock-provider tests with recorded or live llama.cpp contracts where deterministic coverage remains equivalent.
3. Add richer TUI task composition and search without granting renderer mutation authority.
4. Continue model-route tuning under the RAM/VRAM gates rather than raising hard limits.
5. Keep old run and telemetry schemas readable while preventing historical values from becoming current defaults.

## Canonical References

- `DOCUMENTATION_MAP.md`
- `ARCHITECTURE.md`
- `AGENTIC_CLI.md`
- `LOOP_INLET_USAGE.md`
- `RESIDENT_STACK_USAGE.md`
- `TUI_USAGE.md`
- `reports/work-orders/WO-038-COMPLETION-REPORT.md`
