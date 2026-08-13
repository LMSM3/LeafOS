# Agent Task: create a gated runnable Python project with CLI, tests, and verification gates

Slug: `create-a-gated-runnable-python-project-with-cli-tests-and-verification-gates`
Created: `2026-07-12T09:12:04Z`

## Title

create a gated runnable Python project with CLI, tests, and verification gates

## Scope

- Describe the smallest useful coding outcome.
- Keep changes auditable and reversible.

## Steps

1. Run doctor to verify project layout.
2. Run smoke tests to confirm baseline.
3. Implement the task.
4. Run smoke tests again to confirm nothing regressed.

## Goal

What does done look like? State it in one or two sentences.

## Constraints

- Prefer shell and C.
- Do not run destructive commands.
- Produce a dry-run command plan before execution.

## Files likely touched

```text
bin/
core/
config/
docs/
tests/
```

## Acceptance checks

```bash
./bin/leafctl doctor
./tests/smoke.sh
```

## Notes

This task file is meant for human review before any agent or script acts on it.
