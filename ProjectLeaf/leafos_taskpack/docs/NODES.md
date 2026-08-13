# LeafOS SSH Node System

This is an optional distribution subsystem. A local resident project does not
need SSH, a registered node, or a node task directory. Start the current
project workflow with `leafctl live PATH`; see `DOCUMENTATION_MAP.md`.

A PC becomes a **node** by installing the Leaf CLI and allowing SSH access. A PC
**drives** nodes by using SSH to send commands, copy task files, and stream logs.

No HTTP API or message broker is required for this subsystem. Its network
layer is:

```text
ssh
scp / rsync
tail -f over ssh
```

SSH is the pipe. Files are the state. The CLI is the control surface.

## Mental model

One `leaf` binary, two roles. The role depends on the command being run.

```text
[ MASTER / distributor ]
		|
		| ssh / scp / tail -f
		v
[ NODE PC / receiver ]
		|
		+-- ~/.leaf/
			+-- node.json
			+-- nodes.json     (only on a machine that drives others)
			+-- inbox/
			+-- queued/
			+-- running/
			+-- done/
			+-- failed/
			+-- logs/
			+-- results/
```

The master does **not** need a server running on the node. The node only needs
to be SSH-reachable with `leaf` installed and a `~/.leaf` workspace.

## Components

| File | Role |
| --- | --- |
| `core/node/leaf_node.py` | Receiver engine: state machine, runners, JSONL logs, results, registry + task-id helpers. Standard library only -- no `jq` on the hot path. |
| `core/node/node.sh` | Brand-aware receiver wrapper (`leaf node ...`, `leaf task start/list/logs/result`). Emits pure JSON when `--json` is passed. |
| `core/remote/remote.sh` | Distributor layer: registry resolution + `local`/`ssh` transport + `leaf nodes ...` and `leaf task submit/watch/pull/cancel`. |
| `bin/leafctl` | Dispatches the `node`, `nodes`, and `task` command groups. |

## Workspace

The workspace root is resolved as `--home` > `$LEAF_HOME` > `~/.leaf`.

## Command surface

### Receiver (runs on the worker)

```bash
leaf node init [--node-id ID] [--role ROLE]
leaf node status [--json]
leaf node hardware [--json]
leaf task start TASK_ID          # run a task already sitting in this node's workspace
leaf task list [--state STATE] [--json]
leaf task logs TASK_ID [--follow]
leaf task result TASK_ID [--json]
leaf task cancel TASK_ID         # local cancel (1 arg)
```

### Distributor (runs on the master)

```bash
leaf nodes add NAME USER@HOST [--transport ssh|local] [--path DIR]
leaf nodes list [--json]
leaf nodes ping NAME
leaf task submit NAME TASK_FILE
leaf task watch NAME TASK_ID
leaf task pull NAME TASK_ID [DEST]
leaf task cancel NAME TASK_ID    # remote cancel (2 args)
```

> `task cancel` is overloaded by argument count: one argument cancels locally on
> the receiver (this is what the master invokes over SSH); two arguments cancel a
> task on a named remote node.

## How submit works

`leaf task submit gpubox examples/echo.task.json` internally does:

```text
1. TASK_ID = task_YYYYmmdd_HHMMSS          (leaf new-task-id)
2. stamp TASK_ID into the task json        (leaf stamp-task)
3. scp task.json -> gpubox:~/.leaf/inbox/TASK_ID.json
4. ssh gpubox "leaf task start TASK_ID"
```

The receiver then moves the task through its state machine and the master can
`watch` and `pull`.

## Task lifecycle

```text
inbox/ -> queued/ -> running/ -> done/
						 \-----> failed/   (non-zero exit or cancellation)
```

A `running/TASK_ID.cancel` flag requests cooperative cancellation. Terminal tasks
always emit a `result.json` under `results/TASK_ID/`.

## Three shared contracts

The system survives internal rewrites as long as these stay stable.

### 1. Task file

```json
{
  "task_id": "task_20260621_142203",
  "kind": "echo",
  "priority": 5,
  "payload": { "message": "hello node" }
}
```

### 2. Task state

```text
inbox -> queued -> running -> done | failed
```

### 3. Log stream (JSONL)

```json
{"time":"...","event":"queued","task_id":"..."}
{"time":"...","event":"started","task_id":"...","runner":"echo"}
{"time":"...","event":"stdout","task_id":"...","text":"hello node"}
{"time":"...","event":"done","task_id":"...","exit_code":0}
```

Watch it remotely with `leaf task watch NAME TASK_ID`, which is just
`ssh NAME "tail -f ~/.leaf/logs/TASK_ID.jsonl"`.

## Runners

| kind | behavior |
| --- | --- |
| `echo` | Sleeps `duration_sec`, then emits `message`. The fake task used to prove the pipe end to end. |
| `shell` | Runs `payload.command`, streaming each line as a `stdout` event. |
| `hardware` | Probes CPU / RAM / GPU (via `nvidia-smi` when present) and stores the report as the result. |
| `llama` | Placeholder. Lands in `failed/` with status `not_implemented` until wired in a later milestone. The llama is a plugin, not the architecture. |

## Transports

* **`local`** -- same machine, a different `$LEAF_HOME`. Used by `tests/nodes.sh`
  so the entire flow is exercised without a network.
* **`ssh`** -- `user@host`. Uses `ssh`/`scp`; honor `LEAF_SSH_OPTS` for a custom
  key or port (e.g. `LEAF_SSH_OPTS="-i ~/.ssh/leaf_node_key"`).

## Quick start (local transport)

```bash
# become a worker
LEAF_HOME=/tmp/worker leaf node init --node-id w1

# from the master, register and run a task
leaf nodes add w1 /tmp/worker --transport local --path /tmp/worker
leaf nodes ping w1
TASK_ID=$(leaf task submit w1 examples/echo.task.json | tail -n1)
leaf task pull w1 "$TASK_ID"
```

For a real node, swap the target for `user@host` and drop `--transport local`.

## Security

* LAN only; SSH keys only; no password login if possible.
* Do not run as root. Keep everything under `~/.leaf`.
* Use a dedicated key:

  ```bash
  ssh-keygen -t ed25519 -f ~/.ssh/leaf_node_key
  export LEAF_SSH_OPTS="-i ~/.ssh/leaf_node_key"
  ```

The adult version: less exciting than "just expose a server," but also less
likely to become a LAN malware donation box.

## Tests

`tests/nodes.sh` runs the full receiver + distributor flow over the local
transport: init, registry add/list/ping, submit, `done/` transition, JSONL
shape, and result pull. It SKIPs cleanly when Python is unavailable.
