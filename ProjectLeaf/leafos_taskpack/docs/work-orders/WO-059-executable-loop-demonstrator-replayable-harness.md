# WO-059 — Executable Loop Demonstrator and Replayable Project Harness

## Identity

- Owner/context: liamm / LeafOS coherent-loop integration proof
- Current day: Day 0 (supplied plan normalized; execution not started)
- Release target: LeafOS 0.2.2 executable loop milestone
- Branch: `agent/organic-0.9.4-snapshot`
- Depends on: WO-051 allocator, WO-057 surface, WO-058 mapping, LOOP5 freeze rules, and LOOP6 outcome ledger
- Scope boundary: one retained small fixture repository, isolated workspaces, typed tasks, live inference, replay/recovery, rollback, acceptance, and demonstration report

## Purpose

Run the one-to-one loop against a deliberately small fixture repository before using it for a broad scientific-codebase campaign.

## Fixture shape

```text
[project.example]/
  src/
    calculator.*
  tests/
  project.leaf.json
  intentionally_broken_case
```

The actual fixture paths, language, baseline commit, and defect are bound after inspection. Starter files are immutable and the defect must be bounded enough to validate deterministically.

## Canonical demonstration

```bash
leafos project inspect [project.example]

leafos loop plan [project.example] \
  --instruction "Correct the bounded defect while preserving existing tests."

leafos loop run <task-id>
leafos loop status <task-id>
leafos allocation verify [project.example]
leafos evidence inspect <task-id>
leafos task accept <task-id>
```

The task-domain alias is demonstrated for parity:

```bash
plz status <task-id>
plz explain <task-id>
plz accept <task-id>
```

Only one route performs acceptance; the second verifies idempotent canonical behavior.

## Typed task and allocation architecture

- `test.loop_demonstrator.v1` composes registered inspection, candidate, implementation, validation, evidence, recovery, and acceptance tasks without replacing their individual result types.
- Every child task enters the rebuildable allocation heap with dependency, resource, budget, lease, authority, and evidence contracts.
- Authoritative events reconstruct tasks, allocation, checkpoints, and legal next actions after cache deletion.
- A single report binds registry, mapping, event-head, fixture, candidate, model, validator, bundle, and final-tree digests.

## Live-inference requirement

At least one candidate/interpretation stage performs bounded live inference using a real local GGUF through the proven WO-054/WO-055 path. Mock output cannot close the demonstration. Deterministic tests, diff/scope policy, hashes, and CCIS—not the model—decide acceptance.

## Demonstration paths

### Passing and explicit acceptance

Create objective, candidates, selection, plan, allocation, workspace, command/test, evaluation, decision, transition, and result evidence. Verify the canonical repository remains unchanged until explicit acceptance.

### Interrupt and replay

Interrupt at multiple canonical states, delete disposable allocation/task projections, replay append-only events, restore leases/checkpoints, and resume from the last valid state without duplicate events.

### Reject and restore

Reject a candidate and restore the exact original project hash, staged/untracked set, and permissions while retaining evidence and a deterministic next action.

## Acceptance criteria

- [ ] A clean retained fixture has a committed baseline and one bounded defect.
- [ ] The real CLI submits and executes one typed change through every frozen canonical state.
- [ ] A real live-inference child retains prompt/output/model/runtime/resource evidence.
- [ ] WO-051 allocation tasks, dependencies, claims, leases, and ordering are exercised.
- [ ] Interrupt/replay/resume succeeds at multiple states without manual repair.
- [ ] Reject/rollback restores the exact original project hash and retained evidence.
- [ ] Passing acceptance requires explicit `leafos task accept` or equivalent `plz accept` authority.
- [ ] Repeated acceptance is idempotent; stale-base acceptance blocks.
- [ ] CLI, JSON, diagram, events, allocation, checkpoint, filesystem, and evidence views agree.
- [ ] A single demonstration report records success, failures, resource use, replay, and unresolved gaps.

## Status

[W] WO-059: executable loop demonstrator + replayable fixture harness
[D] Day 0: supplied plan normalized; no fixture execution started
[I] TODO
[V] NONE: expected paths defined; no retained WO-059 outcome exists
[P] LOCAL: planning document only; no fixture mutation, model load, or acceptance
[N] After WO-058, bind a clean fixture baseline and admit the read-only inspection task first

## Evidence log

- 2026-08-03: Imported supplied fixture shape, canonical CLI path, replay/resume, rejection, restoration, and acceptance requirements.
- 2026-08-03: Bound the demonstration to LOOP6 honest outcome states and live-inference evidence.

## Carry-forward

- WO-060 opens only after this controlled fixture passes without manual state repair.
- [WO-017/MOE-003–MOE-009](WO-017-small-scale-moe-hardware-orchestration.md) must pass a bounded version of this harness—including replay, interruption, cancellation, cleanup, rejection, and explicit acceptance—before the MoE lane enters broad workloads.
- LOOP6 records corresponding core outcomes; failures remain evidence, not erased history.

## Out of scope

- Broad scientific-codebase improvement.
- Automatic merge/acceptance or unregistered task handlers.
- A demonstration using prerecorded model output.
