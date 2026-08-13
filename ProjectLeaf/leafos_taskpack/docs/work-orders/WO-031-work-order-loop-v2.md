# WO-031: Verify Work-Order Loop V2

## Identity

WO-031

## Objective

Verify the general work-order intake, plan-v2 policy, bounded executor, acceptance checks, and checkpoint evidence without modifying repository files.

## Scope

- `core/python/leaf_work_order.py`
- `tests/test_work_order_loop.py`

## Constraints

- Do not propose mutation steps.
- Use only commands declared by the companion JSON.
- Keep provider authority proposal-only.

## Allowed paths

- `core/python/leaf_work_order.py`
- `tests/test_work_order_loop.py`

## Required steps

- Inspect the declared implementation and tests.
- Produce and validate a plan-v2 proposal.
- Run the declared acceptance command.
- Record file hashes and checkpoint evidence.
- Write the final report.

## Acceptance criteria

- The six-task work-order queue completes.
- Plan-v2 policy rejects undeclared actions.
- The test command passes.
- No repository file is mutated.

The machine-readable authority for this work order is `WO-031-work-order-loop-v2.json`.
