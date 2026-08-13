# Loop Monitor

`leafctl loop monitor` is the hands-off observation surface for a persistent
LeafOS run. It reads the existing run status, worker lease, event journal,
checkpoint, queue, and telemetry summary. It does not submit tasks, change
controls, or rewrite run evidence.

## Modes

```powershell
.\bin\leafctl.ps1 loop monitor active --interactive
.\bin\leafctl.ps1 loop monitor active --noninteractive --jsonl
.\bin\leafctl.ps1 loop monitor active --json
```

Automatic mode uses interactive output only when both standard input and
standard output are terminals. Redirected or service execution uses compact
JSONL. `--interactive` and `--noninteractive` make the choice explicit.

`--json` emits one indented `leafos.loop_monitor.snapshot` object and exits.
`--jsonl` emits one compact snapshot per polling interval. `--once` can be
combined with either mode. `--after SEQ` starts event replay at a known
sequence, and `--cursor-file PATH` persists the latest observed sequence
outside the run directory for reconnecting detached monitors.

## Health And Exit Codes

The snapshot includes the run state, current task, event cursor, new events,
worker PID/liveness, heartbeat age, stale-heartbeat reason, validation status,
and next action. The default heartbeat timeout is 90 seconds.

| Code | Meaning |
|---:|---|
| 0 | Snapshot accepted or run completed/drained. |
| 2 | Run is blocked or stopped. |
| 3 | Worker lease is stale or the worker is unexpectedly absent. |
| 4 | The monitor reached its requested `--timeout`. |
| 130 | The operator interrupted monitoring with Ctrl+C. |

The monitor is observational. Control remains with the existing `pause`,
`resume`, `stop`, `drain`, `approve`, and typed task commands.
