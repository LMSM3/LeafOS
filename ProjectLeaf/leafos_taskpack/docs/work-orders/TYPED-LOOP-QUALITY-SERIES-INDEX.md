# Typed Loop Quality and Rebuildable Allocation — Series Index

## Decision

This series converts the recent test sections 15–19 and the supplied coherent-loop sequence into an implementation order for debugging, real llama.cpp evaluation, containment, unified product surfaces, executable demonstration, scientific trial, and improvement proposals. Every unit of work is a versioned typed task. Scheduling uses a rebuildable allocation heap derived from append-only events; deleting the heap must never delete task truth.

The series extends the CCIS task envelope in WO-002, the queue-control intent in WO-035, and the native admission boundary in WO-044. It does not create a competing task authority.

[WO-017](WO-017-small-scale-moe-hardware-orchestration.md) now supplies the small-scale MoE architecture as a parallel lane. Its MOE-001–MOE-010 subtrack reuses the authorities in this series and does not renumber WO-050–WO-061, replace the WO-051 allocator, or create another acceptance path.

## Live-inference objective

**Live inference means loading an actual local GGUF model with `llama-cli` or `llama-server`, submitting a real prompt, performing CPU/GPU computation at that moment, receiving newly generated tokens, and recording the real output, timing, errors, and resource behavior.** Mocked HTTP responses, prerecorded output, file-existence checks, configuration validation, and deterministic policy fallbacks are not live inference.

Live inference is the explicit operational goal of this series. WO-051/WO-052 create its trustworthy task and evidence foundations, WO-053 proves prerequisites without claiming inference, WO-054 performs bounded live CLI inference, WO-055 performs live streaming inference, and WO-056 contains failures. LOOP1–LOOP6 define the coherent command, mapping, resource, result, demonstration, and outcome contracts. WO-057 implements the unified surface, WO-058 enforces one-to-one mapping, WO-059 runs the controlled demonstrator, WO-060 opens the broad MATLABC++ trial, and WO-061 converts comparable verified measurements into improvement propositions.

## Parallel small-scale MoE lane — WO-017

The MoE lane is deliberately cross-cutting:

| MoE subtrack | Reused series authority | Gate before production claim |
|---|---|---|
| MOE-001 inventory/benchmark | WO-018, WO-047, WO-053 | Full identity and supported CPU/GPU/MoE measurements; statistics before promotion |
| MOE-002 contracts | WO-051, WO-052 | Production schemas and failure fixtures pass |
| MOE-003 scheduler extension | WO-051 | Same journal/reducer/heap authority; deterministic replay |
| MOE-004 GPU lease | WO-051, WO-056 | Exclusive ownership, external occupancy, cancellation, cleanup, and recovery pass |
| MOE-005 provider adapters | WO-053–WO-056 | Real preflight, inference, streaming, timeout, and health evidence pass |
| MOE-006 top-1/top-2 router | WO-051, WO-058 | Eligibility before scoring; rationale and escalation replay |
| MOE-007 resource governor | WO-051, WO-057 | Interactive/balanced/throughput headroom and hysteresis pass |
| MOE-008 evidence/repair | WO-052, WO-061 | Hard gates remain non-compensable; bounded repair lineage passes |
| MOE-009 read-only TUI | WO-057, WO-058 | Same states/events/results; control remains separate |
| MOE-010 overnight lane | WO-059–WO-061 | Frozen snapshot in; proposals out; no live-tree mutation |

The isolated MOE-001 demo is evidence input, not a production implementation. It performed no live inference, used no full model hash, and had no GPU-capable provider, so it cannot close WO-053–WO-056 or authorize placement promotion.

## Source crosswalk

| Source section | Concern | Work order | Typed task |
|---|---|---|---|
| Retroactive presentation repair | Fail-closed PowerShell subsystem indication and pack-identity binding | [WO-050-R1](WO-050-R1-pack-glyph-subsystem-evidence-repair.md) | `leafos.subsystem_indicator_evidence.v1` projection; no scheduler handler |
| Retroactive host repair | PowerShell 5/5.1/7 and Bash/WSL indicator compatibility | [WO-050-R2](WO-050-R2-indicator-shell-compatibility-repair.md) | Host resolver, doctor report, path translation, and reusable triage procedure |
| Small-scale MoE architecture | Inventory, placement, expert routing, resource governance, and bounded consolidation | [WO-017](WO-017-small-scale-moe-hardware-orchestration.md) | Reserved `bench.moe.*`, `route.moe.expert.v1`, and `system.moe_*` tasks; all handlerless and fail-closed |
| Immediate architecture | Typed tasks and rebuildable scheduling | [WO-051](WO-051-typed-task-allocation-heap.md) | `system.allocation.rebuild.v1` |
| 15 | Refuse a tampered evidence bundle | [WO-052](WO-052-evidence-integrity-debugger.md) | `debug.evidence_integrity.v1` |
| 16 | Real llama.cpp binary/model/backend preflight | [WO-053](WO-053-llamacpp-capability-preflight.md) | `probe.llamacpp.capability.v1` |
| 17 | Live grammar-bound `llama-cli` inference | [WO-054](WO-054-llamacpp-grammar-evaluation.md) | `eval.llamacpp.grammar.v1` |
| 18 | Real `llama-server` streaming round trip | [WO-055](WO-055-llamacpp-stream-quality.md) | `eval.llamacpp.stream.v1` |
| 19 | Timeout becomes BLOCKED and owned processes are contained | [WO-056](WO-056-process-timeout-containment.md) | `debug.process_containment.v1` |
| Coherence checkpoint | One diagram/CLI/runtime/event/evidence vocabulary | [WO-LOOP1](WO-LOOP1-coherent-loop-surface-runtime-contract.md) | `system.loop_surface.verify.v1` |
| Command checkpoint | Canonical task grammar and `plz` alias parity | [WO-LOOP2](WO-LOOP2-canonical-command-grammar-plz-alias.md) | `system.command_surface.verify.v1` |
| Resource checkpoint | Complete budgets and inspectable allocation | [WO-LOOP3](WO-LOOP3-resource-allocation-experience.md) | `system.resource_doctrine.verify.v1` |
| Result checkpoint | Typed human/JSON/error/progress accessibility | [WO-LOOP4](WO-LOOP4-result-error-progress-accessibility.md) | `system.result_surface.verify.v1` |
| Demonstration checkpoint | Full live path and contract freeze | [WO-LOOP5](WO-LOOP5-full-path-live-inference-contract-freeze.md) | `system.loop_demonstration.v1` |
| Outcome checkpoint | Sixteen real repository/scientific test segments | [WO-LOOP6](WO-LOOP6-real-repository-scientific-outcome-tests.md) | `test.loop_acceptance.v1`, `test.scientific_outcome.v1`, `test.scientific_invariance.v1`, `test.outcome_ledger.verify.v1` |
| Surface implementation | Unified loop CLI and visual state | [WO-057](WO-057-unified-loop-cli-visual-state-contract.md) | `system.unified_loop_surface.verify.v1` |
| Mapping implementation | Diagram/state/event/command one-to-one gate | [WO-058](WO-058-one-to-one-diagram-state-event-command-mapping.md) | `system.loop_mapping.verify.v1` |
| Controlled demonstration | Executable replayable fixture harness | [WO-059](WO-059-executable-loop-demonstrator-replayable-harness.md) | `test.loop_demonstrator.v1` |
| Scientific trial | MATLABC++ interpretation-kernel campaign | [WO-060](WO-060-matlabcpp-interpretation-kernel-trial.md) | `trial.scientific_codebase.v1` |
| Synthesis | Rank improvements from measured evidence | [WO-061](WO-061-loop-quality-improvement-propositions.md) | `proposal.loop_improvement.v1` |

WO-050-R1 is a repaired status projection, not a new live-inference gate. It
supplies bounded process-presence and pack-binding evidence to later surfaces
without renumbering or opening WO-051–WO-061.

## Typed task architecture

### Task definition

Each task is immutable after admission and contains:

| Field | Purpose |
|---|---|
| `task_id`, `task_type`, `schema_version` | Stable identity and registry lookup |
| `objective` | Invariants, tolerances, and stopping conditions inherited from CCIS |
| `target` and `inputs` | Typed references; no implicit working directory |
| `authority` | Who may admit, execute, validate, accept, retry, or cancel |
| `budget` | Attempts, wall time, tokens, memory, process count, and optional GPU claim |
| `dependencies` | Required task/result IDs and their minimum dispositions |
| `resource_claims` | Named, bounded, exclusive/shared resources |
| `retry_policy` | Retryable reasons, backoff, and terminal attempt count |
| `validators` | Typed validators and required result contracts |
| `output_contract` | Exact result type produced on every disposition |
| `provenance` | Source WO, source event, registry digest, and input digests |

The registry maps each `task_type@schema_version` to its schema, native handler, result schema, legal transitions, allowed resources, and validator policy. Handler names are registry-owned and cannot be supplied by a model response.

### Lifecycle

```text
DECLARED -> ADMITTED -> QUEUED -> ELIGIBLE -> LEASED -> RUNNING
                                      |          |          |
                                      |          |          +-> SUCCEEDED
                                      |          |          +-> REVISE
                                      |          |          +-> REJECTED
                                      |          |          +-> BLOCKED
                                      |          |          +-> ESCALATED
                                      |          +-> QUEUED (expired lease event)
                                      +-> BLOCKED (dependency/resource reason)
```

Every transition is an append-only allocation event. A result is not accepted merely because a process exited zero; its result contract and declared validators must pass.

## Rebuildable allocation heap

### Authority rule

`allocation-events.jsonl` is authoritative. `heap.snapshot.json`, indexes, SQLite, and in-memory heaps are caches only. On startup, digest mismatch, missing snapshot, or operator request, the allocator replays the event stream and reconstructs the same eligible set and ordering.

### Projection design

The allocator maintains two derived min-heaps:

1. `delayed_heap`: `(not_before, enqueue_seq, task_id)` for admitted work that is not yet eligible.
2. `ready_heap`: `(-priority, deadline_or_max, enqueue_seq, task_id)` for eligible work.

Fairness changes are explicit `task.priority_aged` events. Eligibility advances only when the allocator appends an `allocation.clock_observed` event; ambient wall-clock time may request that event but cannot silently change the projection. Replay therefore uses the recorded logical clock. The stable `task_id` tie-breaker prevents platform-dependent ordering.

Leases are event-backed records with `lease_id`, allocator identity, resource claims, issue/expiry times, and task digest. Expired leases return to the queue only through a recorded `lease.expired` event following a logical-clock observation. A task with an exclusive `gpu:0` or `tcp-port:<n>` claim cannot be leased concurrently with a conflicting task.

Every snapshot records `source_seq`, `source_event_hash`, `registry_digest`, `reducer_version`, and the ordered ready/delayed/lease digests. These fields make a stale or foreign projection detectable before allocation.

### Planned layout

```text
.leafos/ccis/allocation/
  allocation-events.jsonl       # authoritative, hash chained
  heap.snapshot.json             # disposable projection
  leases.snapshot.json           # disposable projection
  rebuild-report.json            # last replay evidence
ccis/contracts/allocation/
  typed-task.schema.json
  typed-result.schema.json
  allocation-event.schema.json
  allocation-snapshot.schema.json
  task-type-registry.json
ccis/kernel/
  task_registry.py
  allocation_reducer.py
  allocation_heap.py
  allocation_lease.py
```

## Ten-step immediate plan — WO-051

1. Freeze the typed-task, typed-result, allocation-event, and snapshot contracts.
2. Reserve and version the twenty task types in this series, registering each native handler only when its implementation WO opens; reject unknown type/version pairs throughout.
3. Add canonical serialization and digest binding for admitted task instances.
4. Implement the append-only, hash-chained allocation event store.
5. Implement the pure reducer from events to task, dependency, resource, and lease state.
6. Build delayed and ready heaps from the reducer output with deterministic ordering.
7. Add resource-conflict checks and event-backed leases without executing tasks yet.
8. Add snapshot save/load, digest verification, deletion recovery, and full rebuild reports.
9. Adapt one existing CCIS command validator into the typed task path without removing the current path.
10. Prove clean replay, corrupt-snapshot recovery, event-tamper refusal, stable ordering, and existing 15-test compatibility before opening WO-052.

## Series order and gates

| Order | Work order | Entry gate | Exit gate |
|---|---|---|---|
| 1 | WO-051 | WO-002 Day 1 evidence is stable | Heap can be deleted and rebuilt byte-equivalently from events |
| 2 | WO-052 | Typed task/result registry works | Tamper location and refusal reason are evidenced without repair mutation |
| 3 | WO-053 | Debug evidence task works | Opt-in local llama.cpp/model/backend capability task passes or fails explicitly |
| 4 | WO-054 | Valid capability result authorizes model loading | Deterministic grammar-bound live inference is captured through the CCIS validator |
| 5 | WO-055 | Owned server lifecycle can be allocated | Real streaming produces latency, chunk, and cleanup evidence |
| 6 | WO-056 | Streaming lifecycle evidence exists | Timeout kills the owned process tree, releases claims, and yields BLOCKED |
| 6.5 | WO-LOOP1 | WO-054–WO-056 runtime evidence exists | Diagram, CLI, typed tasks, events, evidence, and legal next actions agree |
| 6.6 | WO-LOOP2 | LOOP1 vocabulary mapping exists | Canonical `leafos task` and `plz` routes have digest/result/exit parity |
| 6.7 | WO-LOOP3 | LOOP2 task grammar is stable | Budgets, claims, leases, consumption, and replay are complete and inspectable |
| 6.8 | WO-LOOP4 | LOOP3 resource result fields are stable | Human/JSON/error/progress/accessibility projections agree |
| 6.9 | WO-LOOP5 | LOOP1–LOOP4 contracts pass focused gates | Retained live-inference success/interruption/rejection/acceptance paths are proven |
| 6.95 | WO-LOOP6 | LOOP5 freeze identifies retained runs and fixture hashes | Sixteen tests have honest PASS/FAIL/BLOCKED/NOT_RUN records; T01–T08 provide the first real pack |
| 7 | WO-057 | LOOP1–LOOP6 specifications are coherent | Unified CLI/read model, `plz` parity, visual states, and legal next actions pass |
| 8 | WO-058 | WO-057 surface is stable | Every canonical diagram node/arrow maps to runtime/events/evidence/commands |
| 9 | WO-059 | WO-058 mapping gate passes | Controlled fixture executes, replays, resumes, rejects, restores, and accepts |
| 10 | WO-060 | WO-059 passes without manual state repair | One bounded MATLABC++ task completes with deterministic scientific validation |
| 11 | WO-061 | LOOP6/WO-059/WO-060 provide comparable verified outcomes | Ranked proposals cite evidence and require explicit CCIS admission |

### MOE parallel gates

| Parallel gate | Entry | Exit |
|---|---|---|
| WO-017 admission — complete | Finalized design and isolated demo evidence exist | Scope accepted; eleven task types reserved without handlers; registry tests pass |
| MOE-001/002 productionization | WO-017 admitted | Full-identity measurement inputs and production contracts pass without copying demo authority |
| MOE-003–MOE-008 runtime integration | WO-051–WO-056 owning gates pass | Scheduler, lease, provider, router, governor, and evidence paths replay and contain failure |
| MOE-009 product integration | WO-057/WO-058 contracts pass | Read-only MoE views match canonical state/event/result mappings |
| MOE-010 consolidation | WO-059 controlled harness passes | Frozen-snapshot proposals are evidenced and require later CCIS admission |

## Quality dimensions

The final evaluator reports integrity, capability truthfulness, structured-output validity, time to first token, inter-token jitter, completion rate, cancellation latency, cleanup leakage, replay determinism, and run-to-run variance. It records raw measurements and scoring-policy version separately so a score can be recomputed later.

## Series status

[W] WO-051–061 + WO-LOOP1–LOOP6: typed loop debugging, coherent implementation, scientific trial, and improvement series
[D] Day 0: architecture and ordered work-plan compiled; implementation not started
[I] TODO: WO-051 is the immediate implementation target
[V] DISCOVERY: source tests 15–19, existing CCIS contracts, and earlier typed-control WOs reconciled
[P] LOCAL: planning documents only; no staging, commit, provider launch, or model load
[N] Implement WO-051 contracts and the pure allocation reducer before adding a live executor

## Series status update — 2026-08-03

[W] WO-017/MOE-001–MOE-010 in parallel with WO-051–WO-061 and WO-LOOP1–WO-LOOP6
[D] Day 1 foundation: MOE-001 GPU-fit captured; resolved-placement evidence choice open
[I] PARTIAL: reservations, identity, strict CPU, and GPU-fit DONE; CPU-MoE measurements and WO-052–WO-061 runtime work TODO
[V] PASS: GPU-fit margin/utilization/evidence, demo 19/19 on Python 3.13/3.14, and CCIS 24/24; resolved placement/promotion statistics NOT_RUN
[P] LOCAL: dirty worktree and retained benchmark evidence; no stage, commit, handler binding, promotion, or acceptance
[N] Decide whether to capture resolved provider placement (recommended) before the half CPU-MoE entry
