# WO-051 — Typed Task Architecture and Rebuildable Allocation Heap

## Identity

- Owner/context: liamm / LeafOS CCIS and loop architecture
- Current day: Day 1 (foundation implemented and validated)
- Release target: LeafOS 0.2.2 loop-quality foundation
- Branch: `agent/organic-0.9.4-snapshot`
- Scope boundary: `ccis/contracts/allocation/*`, `ccis/kernel/task_registry.py`, `ccis/kernel/allocation_*`, `ccis/tests/*`, and `.leafos/ccis/allocation/*`

## Objective

Make every loop action a versioned typed task and make scheduling a deterministic, rebuildable projection over append-only allocation events.

## Live-inference intent

Live inference means loading a real local GGUF model, submitting a real prompt, computing new tokens on CPU/GPU at that moment, and retaining actual output, timing, errors, and resource evidence. WO-051 does not run it yet; it must make live-inference tasks first-class, typed, budgeted, resource-allocated work rather than an untracked subprocess.

## Acceptance criteria

- [x] Strict schemas exist for typed tasks, typed results, allocation events, snapshots, leases, resource claims, dependencies, budgets, and retry policy.
- [x] A registry binds each task type/version to a native handler and result schema; unknown or model-supplied handlers fail closed.
- [x] Canonical task digests bind objective, target, authority, budget, validators, inputs, and provenance.
- [x] The contracts can represent model, accelerator, token/context, timeout, process, port, streaming, and evidence requirements for live inference without arbitrary handler or shell authority.
- [x] Append-only allocation events are authoritative and hash-chained.
- [x] A pure reducer rebuilds task, dependency, resource, and lease state without filesystem or process side effects.
- [x] Delayed and ready heaps use stable keys and produce identical ordering after deletion/rebuild.
- [x] Eligibility, priority aging, and lease expiry depend on recorded logical-clock events, never silent ambient-time mutation.
- [x] Exclusive resource conflicts prevent double lease; expired leases are requeued only by event.
- [x] Snapshots bind source sequence/event hash, registry digest, reducer version, and ordered projection digests.
- [x] Corrupt cache/snapshot is discarded and rebuilt; corrupt authoritative events halt allocation.
- [x] One existing CCIS command validator runs through an adapter while the original path remains compatible.
- [x] Existing 15 CCIS tests pass alongside allocation replay, ordering, tamper, dependency, and lease tests.

## Status

[W] WO-051: typed tasks + rebuildable allocation heap
[D] Day 1: strict contracts, registry, event authority, reducer, heaps, leases, and validator adapter implemented
[I] DONE: typed allocation foundation is integrated with the existing CCIS command validator
[V] PASS: 24 CCIS tests (15 existing + 9 allocation) and Python compilation
[P] LOCAL: validated in the existing dirty worktree; no stage, commit, merge, or canonical acceptance performed
[N] WO-052 completed after operator direction; retain WO-051 as the allocation foundation and stop before WO-053 review

## Evidence log

- 2026-08-03: Chosen as the immediate next plan; heap authority explicitly limited to a derived cache.
- 2026-08-03: Deterministic two-heap ordering, explicit priority-aging events, typed leases, and resource claims designed.
- 2026-08-03: Added five strict allocation contracts and a 21-entry task-type registry; only allocation rebuild and the CCIS command-validator adapter possess native handlers.
- 2026-08-03: Added an append-only allocation journal, pure reducer, stable ready/delayed heap keys, explicit logical-clock/aging/expiry events, exclusive claims, and digest-bound disposable snapshots.
- 2026-08-03: Demonstrated byte-identical projection rebuild after cache deletion, automatic corrupt-cache replacement, and fail-closed authoritative-event tamper handling.
- 2026-08-03: Routed a real subprocess validator through typed admission, lease acquisition, isolated workspace execution, typed result persistence, and lease release while preserving the original validator API.
- 2026-08-03: All 23 CCIS tests passed in 15.013 seconds; the allocation-focused eight passed independently after final contract tightening.
- 2026-08-03: Admitted WO-017 by extending the registry from 21 to 32 entries. Eleven new MoE task types are handlerless `reserved` records; 9 focused allocation tests and all 24 CCIS tests passed, and no persisted typed task required migration from the prior registry digest.
- 2026-08-03: Operator authorized the WO-052 pivot. The evidence-integrity reservation was implemented without adding a second journal, heap, lease truth, or acceptance path; WO-052 closed at 31 passing CCIS tests.

## Carry-forward

- WO-052–WO-061 may not invent private queue records; they must submit registered task types and consume typed results.
- [WO-017](WO-017-small-scale-moe-hardware-orchestration.md) applies the same rule to MOE-001–MOE-010. MOE-002–MOE-004 and MOE-006–MOE-007 may extend contracts, reducer inputs, claims, and projections, but no MoE subtrack may own a second journal, heap, lease truth, or acceptance path.
- Executor concurrency remains one until replay and lease invariants pass.

## Out of scope

- Executing live llama.cpp inference or starting a server; those occur in WO-054/WO-055 after this foundation exists.
- Automatic acceptance, merge, commit, or repair of evidence.
- SQLite as an authoritative store.
