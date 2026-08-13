# WO-057 — Unified Loop CLI and Visual State Contract

## Identity

- Owner/context: liamm / LeafOS loop product surface
- Current day: Day 0 (supplied plan normalized; implementation not started)
- Release target: LeafOS 0.2.2 coherent loop implementation
- Branch: `agent/organic-0.9.4-snapshot`
- Depends on: WO-051–WO-056 and WO-LOOP1–WO-LOOP6 contracts
- Scope boundary: root/taskpack CLI routing, typed read models, human/JSON rendering, project/loop/task/allocation/evidence status, help, and visual-state fixtures

## Purpose

Make the loop look and feel like one coherent program before treating diagrams as executable specifications. The nested objective, candidate, implementation, scientific-evaluation, and CCIS gate layers must be visible without inventing new terminology or a second state authority.

## Canonical command surface

```bash
leafos loop plan [project.example]
leafos loop run <task-id>
leafos loop status <task-id>
leafos loop inspect <task-id>
leafos loop resume <task-id>
leafos loop reject <task-id>
leafos task accept <task-id>
```

The documented task-domain alias is equivalent:

```bash
plz plan [project.example]
plz run <task-id>
plz status <task-id>
plz explain <task-id>
plz accept <task-id>
```

`plz` injects only the canonical `task` domain. It cannot change task digests, defaults, authority, approval, output, evidence, or exit codes.

### Plan-command distinction

`leafos loop plan [project.example]` plans the visible nested loop for a project. `leafos task plan [project.example]`—and therefore `plz plan [project.example]`—creates one reviewable typed task. The command registry must either preserve that distinction with different result types or declare one route a documented semantic alias. Shipping two commands with overlapping, unexplained behavior fails WO-057.

## Typed task architecture

- `system.unified_loop_surface.verify.v1` compares command registry, projected loop state, human/JSON output, evidence references, exit status, and legal next action.
- Read-only commands consume typed projections and cannot append task, allocation, evidence, Git, or worktree mutations.
- Mutating commands submit registered typed tasks through native admission and the rebuildable WO-051 allocator.
- The renderer receives a typed result; it does not infer state from filenames, prose logs, spinners, or terminal color.

## Live-inference representation

Live inference means a real local GGUF is loaded, a real prompt is submitted, CPU/GPU computation generates fresh tokens, and actual timing/output/resource evidence is retained. The visual state must distinguish `ALLOCATED`, `MODEL_LOADING`, `INFERENCING`, `STREAMING`, `VALIDATING`, `CLEANING_UP`, and gate outcomes when those events actually occur. Mock, preflight, and fallback evidence remain visibly classified and cannot appear as live inference.

## Visual state contract

Human and `--json` views derive from one record containing:

- project, task, candidate, run, checkpoint, and decision identities;
- canonical runtime state and last authoritative event;
- completed, active, waiting, blocked, and remaining stages;
- requested/reserved/consumed/remaining resources;
- live-inference evidence class and model/backend identity when applicable;
- validation/evaluation/evidence summaries;
- canonical repository mutation status;
- one legal next action;
- stable result disposition and exit code.

Project status connects tasks, allocation, evidence, checkpoints, pending acceptance, and canonical tree state. A stopped state without exactly one legal next action fails the surface contract.

## Acceptance criteria

- [ ] Canonical command vocabulary and argument order are shared by help, handlers, JSON, examples, and tests.
- [ ] `plz` and canonical task commands have digest/result/output/exit/approval parity.
- [ ] `loop plan` versus `task plan` has an explicit registry decision, result contract, help explanation, and non-ambiguous examples.
- [ ] State names agree across CLI, JSON, events, diagrams, schemas, and file projections.
- [ ] Human and JSON output render the same typed result.
- [ ] Progress displays objective, candidate, implementation, validation, evidence, gate, and cleanup honestly.
- [ ] Every stopped state displays exactly one legal next action.
- [ ] Project status connects tasks, resources, evidence, checkpoints, canonical mutation, and acceptance.
- [ ] Plain/NO_COLOR/redirected output remains meaningful on supported Windows and Unix shells.
- [ ] A read-only CLI fixture demonstrates the complete projected loop without changing a repository.
- [ ] Live inference, mock transport, deterministic fixture, and preflight-only states are visually distinct.

## Implementation sequence

1. Freeze the command/state/result/exit-code vocabulary from LOOP1, LOOP2, and LOOP4.
2. Implement one typed loop/project read model over authoritative events and verified projections.
3. Route canonical task commands and `plz` through the same dispatcher.
4. Implement human, JSON, verbose, redirected, and NO_COLOR projections from one result.
5. Add project status and one-legal-next-action resolution.
6. Bind real live-inference phases without treating animation frames as state.
7. Add read-only fixtures, semantic JSON checks, snapshots, and cross-shell parity tests.
8. Freeze the surface for WO-058 mapping.

## Status

[W] WO-057: unified loop CLI + visual state contract
[D] Day 0: supplied plan normalized; implementation not started
[I] TODO
[V] DISCOVERY: LOOP1–LOOP6 vocabulary, alias, resource, result, and outcome contracts reconciled
[P] LOCAL: planning document only; no CLI/runtime mutation or publication
[N] Implement the typed read model and canonical command registry before visual formatting

## Evidence log

- 2026-08-03: Imported supplied WO-057 purpose, commands, progress stages, project status, and read-only fixture requirement.
- 2026-08-03: Existing synthesis WO-057 preserved as WO-061 to remove the numbering collision.

## Carry-forward

- WO-058 maps every visible state and action to real runtime contracts.
- WO-059 executes this surface against a retained fixture.
- [WO-017/MOE-007 and MOE-009](WO-017-small-scale-moe-hardware-orchestration.md) project resource profiles, routes, leases, headroom, and expert state through this same typed read model; they may not add a private TUI state store.
- LOOP4 remains the result/error/accessibility authority; WO-057 implements its CLI projection.

## Out of scope

- Diagram/runtime mapping implementation owned by WO-058.
- Repository mutation demonstration owned by WO-059.
- Automatic acceptance or model-generated execution authority.
- A private CLI state store.
