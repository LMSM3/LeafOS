# WO-056 — Timeout Containment and Allocation Recovery

## Identity

- Owner/context: liamm / loop process safety and restart quality
- Current day: Day 0 (planned after WO-055)
- Release target: LeafOS 0.2.2 durable loop recovery
- Branch: `agent/organic-0.9.4-snapshot`
- Scope boundary: owned child-process lifecycle, Windows process-tree containment, lease expiry, typed BLOCKED results

## Source

Section 19: timed-out live inference must become `BLOCKED`, leave no owned descendants or port claims, and remain restartable.

## Live-inference intent

Live inference here is an actual model process performing CPU/GPU token generation, not a sleeping test stub alone. Fast deterministic fixtures may test edge cases, but acceptance requires at least one bounded timeout or cancellation exercise against an owned real llama.cpp inference process, with model-load cost and cleanup evidence retained.

## Acceptance criteria

- [ ] `debug.process_containment.v1` runs an owned process group/job with bounded startup, execution, and termination deadlines.
- [ ] On Windows, descendant cleanup uses a tested job/process-tree mechanism; Unix uses an owned process group.
- [ ] Timeout emits a typed `BLOCKED` result with last output, phase, PID identity, termination actions, and retry classification.
- [ ] At least one opt-in test contains or cancels a real live-inference process; stub-only containment tests cannot close the WO.
- [ ] Process exit, port release, file-handle closure, and accelerator/lease release are verified independently.
- [ ] Crash/restart replay detects expired leases and requeues only within the declared attempt budget.
- [ ] A stale PID cannot authorize termination of an unrelated reused PID.
- [ ] Forced cleanup failure escalates and prevents automatic retry.

## Status

[W] WO-056: process-tree timeout containment + allocator recovery
[D] Day 0: queued behind WO-055
[I] TODO
[V] DISCOVERY: current validator timeout fails closed but does not prove Windows descendant cleanup
[P] LOCAL: plan only
[N] After WO-055, harden and prove cross-platform process-tree timeout containment

## Carry-forward

- [WO-LOOP1](WO-LOOP1-coherent-loop-surface-runtime-contract.md) follows this WO as a coherence checkpoint: containment states, events, evidence, CLI output, diagram nodes, and the legal next action must agree before the numbered WO-057–WO-060 implementation sequence.
- [WO-017/MOE-004 and MOE-005](WO-017-small-scale-moe-hardware-orchestration.md) must use this owned process-tree, timeout, cleanup, stale-PID, lease-release, and recovery path. The isolated demo runner is not production process authority.

## Out of scope

- Killing unowned llama.cpp processes or services.
- Unbounded retry after resource or cleanup failure.
