# WO-058 — One-to-One Diagram, State, Event, and Command Mapping

## Identity

- Owner/context: liamm / LeafOS executable loop specification
- Current day: Day 0 (supplied plan normalized; implementation not started)
- Release target: LeafOS 0.2.2 loop mapping gate
- Branch: `agent/organic-0.9.4-snapshot`
- Depends on: WO-057 unified surface and WO-LOOP1 one-to-one contract
- Scope boundary: canonical mapping registry, state/transition diagrams, validators, generated documentation, and mapping tests

## Purpose

Ensure every box and arrow in the canonical loop diagram corresponds to real state, typed tasks, events, commands, evidence, failure outcomes, and legal next actions.

## Central rule

```text
one diagram node = one named runtime state or bounded operation
one diagram arrow = one validated transition
one transition = one append-only event
one event = one evidence-bearing reason
one stopped state = one legal next action
```

A diagram node without runtime implementation is fictional. A runtime state absent from the diagram is hidden behavior. Neither can pass the canonical mapping gate.

## Typed mapping architecture

`system.loop_mapping.verify.v1` validates a versioned machine-readable mapping whose records contain:

```text
node identifier
display name
runtime state or bounded operation
task type and version
native handler
input schema
result schema
required authority
resource claims
entry event
exit event
transition policy
required evidence
failure outcomes
legal next actions
CLI presentation
diagram presentation
```

The mapping registry is authoritative for diagram generation/verification, but not for runtime state. Runtime events remain authoritative and allocation views remain rebuildable projections.

## Live-inference mapping

Real llama.cpp work must map model preflight, allocation, loading, prompt submission, token generation/streaming, validation, cancellation/timeout, cleanup, and evidence. Preflight and mocked transport are separate nodes or evidence classes and may not be visually collapsed into live inference. GPU/model/port claims and owned process identity are visible mapping fields.

## Canonical paths

The primary path includes `CREATED`, `SNAPSHOTTED`, `OBJECTIVE_DEFINED`, `INSPECTING`, `CANDIDATES_GENERATED`, `CANDIDATE_SELECTED`, `PLANNED`, `ALLOCATED`, `MUTATING`, `VALIDATING`, `EVALUATED`, `GATED`, and outcome/acceptance states.

Revise, reject, block, escalate, interrupt, resume, rollback, stale-base, integrity-failure, resource-wait, and live-inference containment paths are equally canonical and must not be hidden in footnotes.

## Acceptance criteria

- [ ] Every canonical node has a permanent identifier and complete mapping record.
- [ ] Every diagram arrow maps to one legal transition policy and emitted event type.
- [ ] Revise, reject, block, escalate, interrupt, resume, rollback, and acceptance paths are represented.
- [ ] Authoritative events/state and derived allocation/progress views are visually distinct.
- [ ] Live-inference phases and evidence classes map one-to-one to actual runtime events.
- [ ] Diagrams are generated from or verified against registry/state definitions.
- [ ] A test fails for a registered state, transition, task type, event, or stopped outcome missing from the diagram.
- [ ] A test fails for a fictional diagram operation without implementation.
- [ ] CLI labels and legal next actions match WO-057 output exactly.
- [ ] Mapping replay produces the same graph for the same registry/event policy digests.

## Implementation sequence

1. Inventory registered states, transitions, task types, handlers, schemas, events, and evidence.
2. Define the strict mapping schema and stable node/arrow identifiers.
3. Bind primary, failure, recovery, acceptance, and live-inference paths.
4. Generate a canonical machine graph and human diagram from the mapping.
5. Verify WO-057 CLI labels/next actions against the same records.
6. Add missing-runtime, fictional-node, missing-arrow, and drift tests.
7. Publish mapping/diagram digests in diagnostics and evidence.
8. Freeze the graph consumed by WO-059.

## Status

[W] WO-058: one-to-one diagram/state/event/command mapping
[D] Day 0: supplied plan normalized; implementation not started
[I] TODO
[V] DISCOVERY: LOOP1 mapping doctrine and WO-057 surface requirements reconciled
[P] LOCAL: planning document only; no generated diagram or registry mutation
[N] After WO-057, define the strict mapping schema and inventory every registered runtime state

## Evidence log

- 2026-08-03: Imported the supplied one-node/one-operation and one-arrow/one-transition rules.
- 2026-08-03: Added typed mapping verification and explicit live-inference/failure-path coverage.

## Carry-forward

- WO-059 may execute only a path represented by the frozen mapping.
- [WO-017/MOE-006–MOE-009](WO-017-small-scale-moe-hardware-orchestration.md) must map route eligibility, top-1/top-2 escalation, GPU lease, provider load/drain, resource-profile actions, evidence gates, and read-only views one-to-one before integration.
- New states or commands require mapping/test updates before integration.

## Out of scope

- Treating diagrams as state authority.
- Hand-maintained decorative diagrams that bypass mapping validation.
- Runtime handlers or allocator implementations owned by earlier WOs.
