# WO-LOOP3 — Resource Doctrine and Allocation Experience

## Identity

- Owner/context: liamm / LeafOS coherent loop experience
- Current day: Day 0 (plan compiled; implementation not started)
- Release target: LeafOS 0.2.2 coherent loop stage
- Branch: `agent/organic-0.9.4-snapshot`
- Series position: after WO-LOOP2 and before WO-LOOP4
- Scope boundary: typed budgets, resource claims, allocation projections, logical-clock events, replay diagnostics, and resource-facing CLI output

## Objective

Operationalize resource doctrine so every task previews a complete budget, receives auditable claims and leases, reports consumption honestly, and can rebuild allocation state from authoritative events.

## Relationship to LOOP1

LOOP1 requires one visible allocation stage and one legal next action. LOOP3 makes that stage real, inspectable, and consistent with the WO-051 rebuildable allocation heap rather than presenting an ornamental progress estimate.

## Live-inference intent

Live inference is the hardest resource case and therefore a required fixture: model identity, context, token limits, CPU threads, GPU/VRAM, RAM, model calls, ports, wall time, startup allowance, evidence storage, cancellation, and cleanup headroom must be declared before the model loads.

## Typed task contract

- `system.resource_doctrine.verify.v1` compares admitted budgets, allocator events, leases, measurements, projections, and replay output.
- Inputs bind task digest, registry digest, resource-policy version, host-facts digest, logical-clock cursor, and allocation event head.
- Results separate `requested`, `reserved`, `consumed`, and `remaining` for every resource class and identify estimated versus measured values.
- Resource insufficiency returns a typed `resource_unavailable` or `BLOCKED` result with one legal next action; it never silently degrades live inference.

## LOOP6 test adoption

[WO-LOOP6](WO-LOOP6-real-repository-scientific-outcome-tests.md) exercises LOOP3 through C04 event/cache disagreement, C06 budget enforcement, C08 interruption/lease recovery, and the model/resource claims used by R11. These results must rebuild from authoritative events with the same eligibility and lease state.

## Acceptance criteria

- [ ] Budget schemas cover wall time, attempts, CPU, GPU/VRAM, RAM, storage, context, tokens, model calls, compiler/simulator time, evidence, rollback, integration, interface work, and human review.
- [ ] Planning output presents requested resources and tolerances before execution.
- [ ] Admission refuses budgets that omit validation, evidence, and recovery reserves unless explicitly marked prototype-only.
- [ ] Exclusive claims prevent conflicting leases; shared claims declare capacity and accounting policy.
- [ ] Logical-clock events control eligibility, aging, and expiry; ambient time does not silently change task state.
- [ ] `allocation show`, `replay`, and `verify` use the same reducer and stable ordering-key explanation.
- [ ] Deleting projections and caches reconstructs identical task eligibility, ordering, dependencies, claims, and leases from events.
- [ ] Corrupt caches rebuild automatically; corrupt authoritative events halt with a precise recovery command.
- [ ] Live-inference fixtures show model-load reservation, actual peak use when observable, token/time consumption, cancellation reserve, and released resources.
- [ ] Status distinguishes resource waiting from execution progress and never animates an indefinite hidden wait.

## Implementation sequence

1. Freeze resource class, unit, estimate-source, and measurement-quality vocabularies.
2. Extend typed task budgets and result contracts without introducing a private allocation record.
3. Implement budget completeness and prototype-only admission policies.
4. Project requested/reserved/consumed/remaining values from allocation and runtime events.
5. Expose stable ordering keys, conflicts, leases, and logical time through read-only commands.
6. Add live-inference resource fixtures plus deterministic low-cost allocator fixtures.
7. Prove replay equivalence, cache recovery, authoritative tamper refusal, and lease release.
8. Hand the shared result fields to LOOP4.

## Owned doctrine clauses

This WO owns clauses 17–33 and 40–52 from the supplied **LeafOS Coherent Experience and Resource Doctrine**. Other LOOP WOs may reference these clauses but may not redefine them.

- **D17.** Every typed task must declare its expected wall time, iteration budget, resource claims, and stopping conditions.
- **D18.** Resource estimates must be presented before execution rather than discovered through overheating hardware.
- **D19.** LeafOS must distinguish requested resources, reserved resources, consumed resources, and remaining resources.
- **D20.** CPU, GPU, RAM, storage, context, model calls, and human-review time must be tracked as separate resources.
- **D21.** Allocation must include enough headroom for validation, documentation, rollback, and final presentation.
- **D22.** A task budget that funds implementation but not testing is incomplete.
- **D23.** A task budget that funds testing but not evidence production is incomplete.
- **D24.** A task budget that funds evidence but not recovery is incomplete.
- **D25.** A task budget that leaves no time for interface polish must be marked as prototype-only.
- **D26.** Planning should reserve explicit time for naming, formatting, command help, examples, and error messages.
- **D27.** Product consistency is part of completion, not decorative work added after the “real” engineering.
- **D28.** Every work plan should contain an integration pass after isolated functionality succeeds.
- **D29.** The integration pass must verify command naming, state transitions, file placement, documentation, and output formatting.
- **D30.** Every task result must state whether it is isolated, integrated, validated, accepted, or merely generated.
- **D31.** LeafOS must not describe generated code as complete before it has been connected to the surrounding program.
- **D32.** New subsystems must reuse existing task, result, evidence, allocation, and error contracts.
- **D33.** A subsystem may not invent a private queue record because its author found the shared schema mildly inconvenient.
- **D40.** `leafos allocation show [project.example]` must display the current derived allocation state without mutating it.
- **D41.** `leafos allocation replay [project.example]` must rebuild allocation state from authoritative events.
- **D42.** `leafos allocation verify [project.example]` must compare the live projection with a clean replay.
- **D43.** Rebuilding the allocation heap must produce the same ready and delayed ordering every time.
- **D44.** Stable ordering keys must be visible through diagnostic output rather than buried inside implementation trivia.
- **D45.** Priority changes must occur through recorded events, never through silent ambient-time mutation.
- **D46.** Lease expiry must occur through a recorded logical-clock event.
- **D47.** A task must not become eligible merely because the operating system clock advanced while LeafOS was asleep.
- **D48.** Exclusive resource claims must prevent two tasks from receiving the same resource simultaneously.
- **D49.** Expired leases must be requeued only after the authoritative expiry event exists.
- **D50.** Allocation caches and snapshots are disposable projections, not truth wearing a database costume.
- **D51.** Corrupt caches must be discarded and rebuilt automatically.
- **D52.** Corrupt authoritative events must halt allocation and produce a precise recovery command.

## Status

[W] WO-LOOP3: resource budgets + allocation UX
[D] Day 0: plan compiled; implementation not started
[I] TODO
[V] DISCOVERY: WO-051 heap doctrine, LOOP1 allocation surface, and resource clauses were mapped
[P] LOCAL: planning document only; unrelated worktree changes remain unstaged
[N] After LOOP2 command parity, define resource units and budget completeness before changing scheduler behavior

## Evidence log

- 2026-08-03: Allocated doctrine clauses 17–33 and 40–52 to this WO without duplication.
- 2026-08-03: Defined `system.resource_doctrine.verify.v1` as the typed verification task for this scope.

## Carry-forward

- LOOP4 must render these resource fields identically in human and JSON output.
- LOOP5 reserves the full demonstration budget before execution and compares estimates with actual consumption.
- WO-061 may score resource efficiency only when measurement quality and host/model digests are comparable.

## Out of scope

- Using SQLite, snapshots, or heaps as authoritative allocation history.
- Overcommitting exclusive accelerator or port resources.
- Silent CPU/mock fallback when a task requires live GPU inference.
- Autonomous budget escalation without authority.
