# WO-040 - Version Hopping

Status: deferred; not executed
Machine-readable authority: `WO-040-version-hopping.json`

## Identity

[W] WO-040: Version hopping across LeafOS and FlowerOS release planes
[D] Late stage after WO-039: operator usage surface is active; version navigation is the next release-control layer
[I] DEFERRED: not started by operator instruction
[V] DEFERRED: no implementation or test run claimed
[P] LOCAL
[N] DEFERRED: keep version hopping below the current late-stage release work; resume when explicitly reactivated

## Objective

Create a safe version-hopping lane for the late-stage LeafOS tree. The operator should be able to inspect available version planes, choose a target version profile, preview what would change, and apply only an explicit compatible switch without rewriting historical evidence or confusing FlowerOS surface identity with LeafOS engine contracts.

Version hopping is release navigation, not time travel. It must preserve the current truth that FlowerOS is the operator-facing usage surface and LeafOS remains the execution, policy, journal, provider-routing, validation, checkpoint, and evidence engine.

## Completion Markings

- [ ] Version-hop registry implemented.
- [ ] List, show, plan, check, and apply commands implemented in Bash and PowerShell.
- [ ] Dry-run and explicit approval gates implemented.
- [ ] Compatibility and rollback report implemented.
- [ ] Focused version-hop acceptance tests passed.

This WO is intentionally unstarted. The unchecked markings are a status
boundary, not missing evidence from a completed implementation.

## Version Planes

- Root package identity: root wrappers, `VERSION`, and `leafos.root.json`.
- Taskpack identity: the resident `ProjectLeaf/leafos_taskpack` command engine.
- Work-order identity: version-2 work orders, queue records, checkpoint records, and reports.
- Runtime identity: provider stack entries, model profiles, runtime profiles, and local capability records.
- Evidence identity: historical runs, reports, benchmarks, and completion artifacts.

These planes may be inspected together, but a hop must name which plane it affects. A root package hop must not imply a taskpack capability promotion. A runtime profile hop must not rewrite run history. A schema compatibility hop must not rename durable `leafos.*` objects.

## Required Behavior

- Add a version-hop registry that records known root, taskpack, schema, runtime, and evidence planes.
- Add a command surface for listing, inspecting, planning, checking, and applying a hop.
- Make every hop dry-run first, with explicit operator approval before mutation.
- Emit a compatibility report before apply, including affected files, expected command surface, required tests, and rollback notes.
- Reject hops that would cross denied paths, mutate historical evidence, downgrade required schema support, or silently change model-role policy.
- Preserve FlowerOS as the operator surface and LeafOS as the engine identity.
- Record the selected version profile in a durable file-backed state object rather than changing scattered constants directly.
- Keep historical reports and run directories readable under their original versions.

## Suggested Command Shape

```text
leafctl version-hop list
leafctl version-hop show PROFILE
leafctl version-hop plan PROFILE
leafctl version-hop check PROFILE
leafctl version-hop apply PROFILE --yes
```

PowerShell parity should follow the same command shape through `leafctl.ps1`.

## Acceptance Criteria

- `leafctl version-hop list` shows the current root, taskpack, work-order schema, runtime, and evidence planes.
- `leafctl version-hop plan PROFILE` produces a JSON plan without mutating files.
- `leafctl version-hop check PROFILE` rejects incompatible schema, runtime, provider-role, and path-policy changes.
- `leafctl version-hop apply PROFILE --yes` writes only the approved version-hop state and any declared config updates.
- Existing `leafctl versions`, `leafctl live`, `leafctl tui`, and `flower.ps1 home` behavior remains intact.
- Version-2 work-order runs remain resumable after a hop.
- Historical run and report artifacts are never rewritten as part of a hop.
- Focused dispatch, work-order, live-project, and model-profile tests pass.

## Truth Boundary

Version hopping is not a promotion gate. A hop may select a version profile or compatibility mode, but a stage becomes proven only through the existing evidence rules: passing commands, durable run artifacts, reports, checkpoints, and explicit completion evidence.

## Out Of Scope

- Downloading or deleting model weights.
- Rewriting old work orders, completion reports, run directories, or benchmark evidence.
- Changing private chain-of-thought handling.
- Adding a second scheduler, queue, journal, checkpoint, or TUI authority.
- Multi-node relay migration; cross-node version negotiation belongs to a later relay work order.

## Carry-Forward

Start with read-only registry and dry-run planning when reactivated. Only after the compatibility report is deterministic should apply mode be wired. Keep the first implementation narrow enough that a failed hop leaves the active resident stack unchanged.

## Evidence Log

- 2026-07-22: Operator instructed that version hopping be skipped and deprioritized; no implementation or test run was performed for WO-040.

## Priority

Deferred and deprioritized by operator instruction on 2026-07-22. This work order remains recorded for later release-control work and has not been started.
