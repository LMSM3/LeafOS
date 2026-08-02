# WO-035: Typed Task Control

Machine-readable authority: `WO-035-typed-task-control.json`

## Objective

Turn the post-inlet interface into a practical continual-loop control surface with schema-constrained task submission, priority, retry, approval, cancellation, and observable child-process state.

## Boundary

The CLI and TUI emit typed requests only. The inlet validates task identity and policy, records accepted requests in the native LMEM journal, and mutates the durable queue. The existing plan-v2 provider proposes work; the allowlisted CPU executor remains authoritative. All downloaded and locally available models in this instance are the stack.

## Acceptance

- A one-line noninteractive command submits a bounded JSON task.
- Priority affects runnable task claim order.
- Retry remains within the declared attempt budget.
- Cancellation is confirmed in the TUI and interrupts a matching child process promptly.
- Task and run controls are hash-chained in `control.lmem`.
- Active child PID and task ID are visible in status and TUI snapshots.
- Native controls require the authenticated loopback transport and validated task fields.
- CPU fallback validates without claiming model-generated edits.
