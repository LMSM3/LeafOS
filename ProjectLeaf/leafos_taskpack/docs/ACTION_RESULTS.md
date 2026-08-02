# LeafOS 0.4 Action Result Artifacts

Status: compatibility artifact contract for the embedded 0.4 graph/action
runner. Current version-2 resident runs primarily use `artifacts/`,
`events.jsonl`, `checkpoint.json`, and `report.md`; see `ARCHITECTURE.md`.
Action results remain valid when that older runner is invoked.

Every embedded action dispatched through `agent_run_action` writes one atomic
JSON result artifact after it completes.

## Location

```text
runs/<run-id>/action-results/<node-id>.json
```

The node identifier is normalized for a safe file name. The artifact is written
through a temporary file and renamed only after JSON generation succeeds.

## Schema

```json
{
  "node": "verify_readme",
  "action": "fs.require_file",
  "status": "passed",
  "exit_code": 0,
  "started_at": "2026-07-16T22:47:12Z",
  "finished_at": "2026-07-16T22:47:12Z"
}
```

`status` is `passed` only when the dispatched action returns exit code `0`.
Unknown actions and failed actions produce `failed` artifacts with their
non-zero exit code.

## Debugging a node

```bash
jq . runs/latest/action-results/<node-id>.json
```

Use the artifact with `actions.jsonl`, the graph node status, and `report.md`
to reconstruct a run without relying on terminal scrollback. The dedicated
offline regression test is `tests/actions.sh`.
