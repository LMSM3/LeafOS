# LeafOS Node System — Advanced Learning Guide

> Version 0.5.0 · SSH is the pipe · Files are the state · The CLI is the control surface

> **Scope:** this is the advanced guide for the optional SSH node subsystem.
> It does not define the current resident project loop. Start project work with
> `leafctl live PATH`; see `DOCUMENTATION_MAP.md`, `ARCHITECTURE.md`, and
> `RESIDENT_STACK_USAGE.md`. The node subsystem can distribute explicit jobs,
> but it does not share the resident queue, provider lease, or TUI authority.

---

## Part 1 — Architecture deep dive

### 1.1 The one binary, two roles design

`leaf` is a **single executable** that branches purely on which command group you
invoke. The receiver engine (`core/node/leaf_node.py`) runs locally on every
node. The distributor layer (`core/remote/remote.sh`) drives remote nodes by
SSHing into them and invoking the same binary.

```
┌─────────────────────────────────────────────────────────────────────┐
│                         MASTER / distributor                        │
│                                                                     │
│  bin/leafctl  ──source──>  core/remote/remote.sh                    │
│       │                           │                                 │
│       │  nodes.json (registry)    │  ssh / scp / rsync              │
│       └─────────────┐             │                                 │
│                     v             v                                 │
└─────────────────────────────────────────────────────────────────────┘
							   │
						LAN / WAN SSH
							   │
							   v
┌─────────────────────────────────────────────────────────────────────┐
│                         WORKER / receiver                           │
│                                                                     │
│  ssh → bin/leafctl  ──source──>  core/node/node.sh                  │
│                                       │                             │
│                                 python3 leaf_node.py                │
│                                       │                             │
│  ~/.leaf/                             │                             │
│  ├── inbox/   queued/   running/  ────┘                             │
│  ├── done/    failed/                                               │
│  ├── logs/    TASK_ID.jsonl                                         │
│  └── results/ TASK_ID/result.json                                   │
└─────────────────────────────────────────────────────────────────────┘
```

The master **never** contacts an HTTP API. It opens one SSH connection per
operation and reads files the receiver wrote. That is the entire protocol.

---

### 1.2 Source chain

```
bin/leafctl
  source core/brand/brand.sh
  source core/log/log.sh
  source core/remote/remote.sh       <── distributor layer
	source core/node/node.sh         <── receiver wrapper
	  resolves python3
	  exports LEAF_NODE_PY path
```

`leaf_node.py` is loaded fresh per invocation. There is no persistent process. A
node doing no work is a directory tree and an SSH daemon.

---

### 1.3 Workspace resolution order

```
leaf_home()  resolution order:
  1. --home FLAG passed to the command
  2. $LEAF_HOME environment variable
  3. ~/.leaf  (default)
```

This allows a single machine to host multiple isolated node workspaces by setting
`LEAF_HOME` before calling `leaf`.

---

## Part 2 — State machine

### 2.1 Task lifecycle

```
								   ┌──── cancel flag ────┐
								   │                      v
inbox/ ──> queued/ ──> running/ ──>+──> done/        failed/
								   │
								   └──> failed/  (non-zero exit)
```

State transitions are atomic file moves (`shutil.move`). A task can be in
exactly one directory at any time. Crashes that abandon `running/` are detectable
by `task list --state running` after a restart.

### 2.2 Cancellation

Cancellation is **cooperative**: the distributor creates
`running/TASK_ID.cancel` and the runner polls for it. A runner that ignores the
flag finishes normally. This is intentional — we do not `SIGKILL` unknown
processes without warning.

```bash
# master side
leaf task cancel gpu1 task_20260621_142203

# internal (runs over SSH)
touch ~/.leaf/running/task_20260621_142203.cancel
```

The `echo` and `shell` runners poll every 250 ms. When you write your own
runner, call `_cancel_flag(home, task_id)` and check `os.path.exists()` in any
inner loop.

---

## Part 3 — Writing a custom runner

A runner is a Python function with the signature:

```python
def run_myrunner(home: str, task: dict, log: TaskLog) -> tuple[int, str, dict]:
	"""
	home  -- absolute path to ~/.leaf (or $LEAF_HOME)
	task  -- parsed task JSON descriptor
	log   -- TaskLog; call log.event("stdout", text="...") to stream output
	Returns (exit_code: int, status: str, output: dict)
	"""
```

### 3.1 Minimal example: `sleep` runner

```python
import time

def run_sleep(home, task, log):
	secs = float(task.get("payload", {}).get("seconds", 5))
	log.event("stdout", text="sleeping {}s".format(secs))
	time.sleep(secs)
	return 0, "ok", {"slept": secs}
```

Register it in the `RUNNERS` dict in `leaf_node.py`:

```python
RUNNERS = {
	"echo":     run_echo,
	"shell":    run_shell,
	"hardware": run_hardware,
	"llama":    run_llama,
	"sleep":    run_sleep,   # <-- add this line
}
```

Invoke it:

```json
{ "kind": "sleep", "priority": 5, "payload": { "seconds": 10 } }
```

```bash
leaf task submit gpu1 examples/sleep.task.json
leaf task watch  gpu1 <TASK_ID>
```

### 3.2 Streaming stdout in real time

```python
def run_myrunner(home, task, log):
	import subprocess
	proc = subprocess.Popen(
		["long-running-cmd"],
		stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
		universal_newlines=True,
	)
	for line in iter(proc.stdout.readline, ""):
		log.event("stdout", text=line.rstrip("\n"))
		# check cancellation
		if os.path.exists(_cancel_flag(home, task["task_id"])):
			proc.terminate()
			return 130, "cancelled", {}
	proc.stdout.close()
	code = proc.wait()
	return code, "ok" if code == 0 else "error", {"exit_code": code}
```

The master sees each line in real time via `leaf task watch` (`tail -f` over SSH).

---

## Part 4 — The three contracts

These three schemas are the only API surface that must stay stable. Internal
rewrites, new runners, and transport changes are fine as long as these hold.

### 4.1 Task file schema

```json
{
  "task_id":  "task_20260621_142203",   // stamped by distributor
  "kind":     "echo",                   // selects the runner
  "priority": 5,                        // 1 (low) – 10 (high); not enforced yet
  "payload":  { "message": "hello" }   // runner-specific
}
```

`task_id` and `kind` are the only required fields at runtime. `priority` is
reserved for the scheduler milestone. `payload` is entirely runner-defined.

### 4.2 State directory names

```
inbox    queued    running    done    failed
```

Do not rename these. The receiver engine (`_find_task`) iterates `STATE_DIRS` in
order. External tooling that reads `~/.leaf/done/` depends on this layout.

### 4.3 JSONL log event schema

Every event is a JSON object on its own line:

| field | type | always present |
|---|---|---|
| `time` | ISO-8601 string | yes |
| `event` | string | yes |
| `task_id` | string | yes |
| `runner` | string | `started` event only |
| `text` | string | `stdout` / `stderr` events |
| `exit_code` | int | `done` / `failed` events |

Standard event sequence:
```
queued  →  started  →  stdout* / stderr*  →  done | failed | cancelled
```

A `result.json` is always written to `results/TASK_ID/result.json` after a
terminal event, regardless of success or failure.

---

## Part 5 — Transport layer internals

### 5.1 Registry (`nodes.json`)

`leaf nodes add NAME TARGET` writes to `$LEAF_HOME/nodes.json`:

```json
{
  "gpu1": {
	"target":    "user@192.168.1.44",
	"path":      "~/.leaf",
	"transport": "ssh"
  }
}
```

`_node_resolve NAME` in `remote.sh` reads this registry via `registry-get` (the
Python engine so we avoid a `jq` dependency) and exports `_RT`, `_RTGT`,
`_RPATH`.

### 5.2 Local transport

`--transport local` sets `_RPATH` to a local path and bypasses SSH entirely.
Every `_remote_*` function in `remote.sh` switches on `$_RT`:

```bash
case "$_RT" in
	local) _local_engine task-start "$task_id" ;;
	ssh)   _ssh "$_RTGT" "leaf task start $task_id" ;;
esac
```

`_local_engine` is just `LEAF_HOME="$_RPATH" python3 leaf_node.py`. This is why
`tests/nodes.sh` needs no network and no real SSH.

### 5.3 SSH options

```bash
export LEAF_SSH_OPTS="-i ~/.ssh/leaf_node_key -p 2222"
```

`_ssh()` and `_scp()` in `remote.sh` expand `${LEAF_SSH_OPTS:-}` before all
other arguments, so this affects every transport call.

---

## Part 6 — Multi-node patterns

### 6.1 Fan-out: submit to multiple nodes

```bash
for node in gpu1 gpu2 cpu1; do
	TASK_ID=$(leaf task submit "$node" examples/echo.task.json | tail -n1)
	echo "$node $TASK_ID"
done
```

### 6.2 Pull all results into a named collection

```bash
mkdir -p ./run_collection
for node in gpu1 gpu2; do
	leaf task pull "$node" "$TASK_ID" "./run_collection/$node"
done
```

### 6.3 Watching multiple tasks in parallel (tmux panes)

```bash
tmux new-session -d -s leaf
tmux send-keys -t leaf "leaf task watch gpu1 $T1" Enter
tmux split-window -h
tmux send-keys -t leaf "leaf task watch gpu2 $T2" Enter
```

### 6.4 Scheduling by hardware capacity

```bash
# choose the node with no running tasks
pick_idle() {
	leaf nodes list --json | python3 -c "
import json, sys, subprocess, shlex
nodes = json.load(sys.stdin)
for name, cfg in nodes.items():
	r = subprocess.run(['leaf', 'nodes', 'ping', name],
					   capture_output=True, text=True)
	data = json.loads(r.stdout) if r.returncode == 0 else {}
	if data.get('tasks_running', 1) == 0:
		print(name); break
"
}
TARGET=$(pick_idle)
leaf task submit "$TARGET" examples/shell.task.json
```

---

## Part 7 — Security hardening

### 7.1 Dedicated key per cluster

```bash
# generate
ssh-keygen -t ed25519 -C "leaf-cluster" -f ~/.ssh/leaf_node_key

# install on each worker
ssh-copy-id -i ~/.ssh/leaf_node_key.pub user@192.168.1.44

# use it
export LEAF_SSH_OPTS="-i ~/.ssh/leaf_node_key"
```

### 7.2 Restrict the SSH key to leaf commands only

In `~/.ssh/authorized_keys` on the worker:

```
command="leaf task start ${SSH_ORIGINAL_COMMAND#* }",no-port-forwarding,\
no-X11-forwarding,no-agent-forwarding,no-pty \
ssh-ed25519 AAAA... leaf-cluster
```

This allows the master to call `leaf task start TASK_ID` only. Every other
command is rejected.

### 7.3 Firewall

```bash
# allow SSH from LAN subnet only (ufw example)
ufw allow from 192.168.1.0/24 to any port 22
ufw deny 22
```

No other port needs to be open. There is no HTTP listener, no agent socket, no
exposed API. The only open port is SSH.

### 7.4 Non-root dedicated user

```bash
useradd -m -s /bin/bash leafrunner
su - leafrunner -c "leaf node init --node-id worker1"
```

Give this user write access only to `~leafrunner/.leaf` and the `leaf` binary.
Nothing else.

---

## Part 8 — Debugging and observability

### 8.1 Read the JSONL log directly

```bash
# all events for a task
cat ~/.leaf/logs/task_20260621_142203.jsonl | python3 -m json.tool

# just stdout lines
grep '"event":"stdout"' ~/.leaf/logs/task_20260621_142203.jsonl \
	| python3 -c "import sys,json; [print(json.loads(l)['text']) for l in sys.stdin]"
```

### 8.2 Orphaned running tasks

A crash during execution leaves the task in `running/`. Detect and re-queue:

```bash
leaf task list --state running --json
# decide: re-start, cancel, or move to failed manually
leaf task cancel TASK_ID
```

### 8.3 Inspect result.json

```bash
leaf task result TASK_ID --json
# or directly
cat ~/.leaf/results/TASK_ID/result.json
```

### 8.4 `LEAF_HOME` override for isolation

```bash
# run an entirely isolated node for debugging without touching ~/.leaf
LEAF_HOME=/tmp/debug_node leaf node init --node-id debug
LEAF_HOME=/tmp/debug_node leaf task start TASK_ID
```

### 8.5 SSH connectivity check

```bash
# what leaf nodes ping does internally
ssh $LEAF_SSH_OPTS user@192.168.1.44 "leaf node status --json"

# raw reachability without leaf
ssh -v -o ConnectTimeout=5 user@192.168.1.44 "echo ok"
```

---

## Part 9 — Extension roadmap

| Milestone | Planned change |
|---|---|
| 0.6.0 | `llama.cpp` runner wired; `leaf task submit` selects nodes by GPU presence |
| 0.7.0 | Priority queue: `running` at most N tasks, `queued` drain in priority order |
| 0.8.0 | `rsync` replace `scp` for large payload / partial-transfer resume |
| 0.9.0 | Restricted SSH command wrapper (`leafrunner`) + authorized\_keys templates |
| 1.0.0 | Optional read-only web viewer (`leaf node serve`) — no write API, log streaming only |

The three contracts in Part 4 are frozen from this milestone forward. All
extension work must remain backward-compatible with them.

---

## Reference — full command surface

### Receiver

```text
leaf node init [--node-id ID] [--role ROLE] [--json]
leaf node status [--json]
leaf node hardware [--json]
leaf task start   TASK_ID
leaf task list    [--state STATE] [--json]
leaf task logs    TASK_ID [--follow]
leaf task result  TASK_ID [--json]
leaf task cancel  TASK_ID
```

### Distributor

```text
leaf nodes add   NAME USER@HOST [--transport ssh|local] [--path DIR]
leaf nodes list  [--json]
leaf nodes ping  NAME
leaf task submit NAME TASK_FILE
leaf task watch  NAME TASK_ID
leaf task pull   NAME TASK_ID [DEST]
leaf task cancel NAME TASK_ID
```

### Key files

```text
core/node/leaf_node.py   receiver engine (stdlib only)
core/node/node.sh        brand-aware receiver wrapper
core/remote/remote.sh    distributor + transport layer
bin/leafctl              CLI dispatch
examples/*.task.json     example task descriptors
tests/nodes.sh           end-to-end local-transport test suite
docs/NODES.md            architecture reference
docs/QUICKSTART.md       this system's quick start
```
