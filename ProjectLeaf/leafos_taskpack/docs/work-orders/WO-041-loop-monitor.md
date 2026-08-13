# WO-041 - Hands-Off Loop Monitor

Status: complete
Machine-readable authority: `WO-041-loop-monitor.json`

## Identity

[W] WO-041: Hands-off monitoring for interactive and non-interactive loop shells
[D] Late-stage usage phase after WO-039; monitoring friction is now the scoped operator improvement
[I] DONE
[V] PASS
[P] LOCAL
[N] Use the monitor against future resident runs; no implementation carry-forward

## Objective

Provide one read-only loop monitor that can render a terminal view when
attached to an interactive shell and emit stable JSONL snapshots when run
detached, redirected, or under automation. Both modes must read the same
LeafOS run authority and preserve reconnectable event cursors.

## Acceptance Criteria

- [x] `leafctl loop monitor` auto-selects interactive output only for attached TTYs.
- [x] `--interactive`, `--noninteractive`, `--json`, `--jsonl`, and `--once` are explicit and deterministic.
- [x] JSON snapshots identify the run, state, event cursor, new events, worker lease, heartbeat age, and stale reason.
- [x] `--cursor-file` persists a reconnect cursor outside the run directory.
- [x] Stale, blocked/stopped, timeout, success, and Ctrl+C outcomes have documented exit codes.
- [x] Bash and PowerShell wrappers reach the same Python monitor authority.
- [x] Monitoring does not mutate the run directory or invoke task/control commands.
- [x] Focused loop, dispatch, and schema tests pass.

## Out Of Scope

- Task submission or run control from the monitor.
- A second scheduler, queue, journal, checkpoint, or TUI authority.
- Version hopping, provider lifecycle changes, or changes to historical run evidence.

## Evidence Log

- 2026-07-24: Added shared `loop monitor` command with automatic TTY detection, explicit interactive/non-interactive modes, JSON/JSONL output, bounded polling, heartbeat health, stale detection, exit codes, and external reconnect cursors.
- 2026-07-24: Verified Bash and PowerShell `loop monitor --help` routes reach the same Python inlet implementation.
- 2026-07-24: `python tests/test_loop_inlet.py` passed 14 tests.
- 2026-07-24: `python tests/test_leafctl_dispatch.py` passed 8 tests.
- 2026-07-24: `python tests/test_work_order_loop.py` passed 10 tests.
- 2026-07-24: `PYTHONPATH=. python tests/test_live_project.py` passed 19 tests.
- 2026-07-24: `python tests/test_model_profiles.py` passed 4 tests.
- 2026-07-24: Monitor schema, WO JSON, and Python compilation checks passed.
- 2026-07-24: Read-only snapshot of the existing active run emitted `leafos.loop_monitor.snapshot`, state `blocked`, cursor `39`, heartbeat reason `no_worker_lease`, and the documented failure exit code.

## Real Dated Run Snippets

Recorded from fresh local runs on 2026-07-24 in
`C:\R\LeafOS0.2.2\ProjectLeaf\leafos_taskpack`:

```text
> python -B tests/test_loop_inlet.py
Ran 14 tests in 3.677s
OK

> python -B tests/test_leafctl_dispatch.py
Ran 8 tests in 40.374s
OK

> bash ./bin/leafctl loop monitor --help
usage: leaf_loop_inlet.py monitor [-h] [--after AFTER] [--interval INTERVAL]

> pwsh -NoProfile -File .\bin\leafctl.ps1 loop monitor --help
usage: leaf_loop_inlet.py monitor [-h] [--after AFTER] [--interval INTERVAL]
```

Operational read-only check, also run on 2026-07-24:

```text
> bash ./bin/leafctl loop monitor active --json --once
state: blocked; event_cursor: 39; heartbeat.reason: no_worker_lease
exit code: 2
```

The final snippet is an observed state of the existing run, not a test
failure in the monitor implementation.
