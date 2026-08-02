# LeafOS CLI Attribute Reference

Version: 0.5.0 | `bin/leafctl`

This document covers every top-level command and its flags.
For install steps see [`INSTALL.md`](INSTALL.md).
For networking details see [`NETWORKING.md`](NETWORKING.md).
For the dashboard see [`DASHBOARD_GUIDE.md`](DASHBOARD_GUIDE.md).

Status: legacy broad CLI reference. The executable `leafctl help` is the
current flag authority. New project-level work should use `live`, `resident`,
`loop`, `tui`, `provider-stack`, and `test visual`; see `AGENTIC_CLI.md` and
`DOCUMENTATION_MAP.md`. The node, LAN, chat, and early agent-plan sections
below remain subsystem references.

---

## Global flags

These flags are read from environment variables before any command runs.

| Variable           | Default    | Effect                                  |
|--------------------|------------|-----------------------------------------|
| `LEAF_HOME`        | `~/.leaf`  | node workspace directory                |
| `QUIET`            | `0`        | suppress brand messages when `1`        |
| `NO_COLOR`         | `0`        | strip ANSI colour when `1`              |
| `NO_EMOJI`         | `0`        | use `›` instead of `✿` when `1`        |
| `FLOWER_EMOJI_RATE`| `2`        | show flower every N brand messages      |
| `LEAF_SSH_OPTS`    | _(empty)_  | extra flags passed to every ssh call    |

---

## System & diagnostics

### `leaf status`
Print system online check, root path, and branding config.

### `leaf versions`
Detect and compare installed component versions against minimum requirements
(Bash, Python, GCC, PowerShell).  Prints a table with pass/warn/missing.

### `leaf doctor`
Deep diagnostics: checks paths, required files, permissions, Python modules,
and node workspace integrity.

### `leaf platform`
Print detected OS, architecture, and shell info.

### `leaf motd`
Print the message-of-the-day from `share/motd/default.motd`.

---

## UI & animation

### `leaf loader [NAME] [LABEL]`
Run a named terminal progress animation.

```sh
leaf loader          # default loader
leaf loader spinner "compiling"
leaf loader dots    "waiting"
```

### `leaf loaders`
List all available loader names.

### `leaf glyph ALIAS [--ascii] [--json]`
Print one glyph by alias. `--ascii` selects the registry fallback and `--json`
emits the versioned `leafos.glyph` object defined by
`schemas/leafos.glyph.v1.schema.json`.

### `leaf glyphs [CATEGORY] [--ascii] [--json]`
List glyphs, optionally filtered by category. JSON mode emits one
`leafos.glyph_registry` envelope containing complete glyph objects. Bash and
PowerShell use the same registry, field names, sorting, and render-mode rules.

The object fields are `alias`, rendered `glyph`, `codepoints`, `category`,
`severity`, `ascii`, `meaning`, and `render_mode`. Unknown aliases and malformed
registry rows fail nonzero instead of producing an incomplete object.

### `leaf spin [LABEL] [CYCLES]`
Run the branded spinner for N cycles.

### `leaf alert SEVERITY MESSAGE`
Print a coloured alert.  SEVERITY is one of: `info`, `warn`, `error`, `ok`.

---

## Node (local worker)

A node is a machine with a Leaf workspace at `LEAF_HOME`.

### `leaf node init [--node-id ID] [--role ROLE]`
Initialise a new node workspace.

| Flag        | Default       | Values                  |
|-------------|---------------|-------------------------|
| `--node-id` | hostname      | any string              |
| `--role`    | `worker`      | `worker`, `coordinator` |

### `leaf node status [--json]`
Print node identity, role, and state.  `--json` for machine-readable output.

### `leaf node hardware [--json]`
Run a hardware probe (CPU count, RAM, GPU via nvidia-smi).

---

## Tasks (local)

Tasks are JSON files placed into the node inbox.

### `leaf task start TASK_ID`
Execute a task that is already in the node inbox directory.

### `leaf task list [--state STATE] [--json]`
List tasks and their states.

| `--state` value | Meaning                    |
|-----------------|----------------------------|
| `inbox`         | waiting to start           |
| `queued`        | accepted, not yet running  |
| `running`       | currently executing        |
| `done`          | completed successfully     |
| `failed`        | completed with error       |

### `leaf task logs TASK_ID [--follow]`
Print task log events.  `--follow` streams new events as they arrive.

### `leaf task result TASK_ID [--json]`
Print the result payload for a completed task.

### `leaf task cancel TASK_ID`
Cancel a running or queued task.

---

## Cluster nodes (distributed)

### `leaf nodes add NAME USER@HOST [--transport TYPE] [--path DIR]`
Register a remote node.

| Flag          | Default | Values          |
|---------------|---------|-----------------|
| `--transport` | `ssh`   | `ssh`, `local`  |
| `--path`      | `~/.leaf`| remote LEAF_HOME|

### `leaf nodes list [--json]`
List all registered remote nodes.

### `leaf nodes ping NAME`
SSH-probe a registered node; prints reachability and Leaf version.

### `leaf nodes scan SUBNET [OPTIONS]`
Scan a subnet for nodes running Leaf.

| Flag            | Default | Effect                             |
|-----------------|---------|------------------------------------|
| `--user U`      | current | SSH user for probes                |
| `--timeout N`   | `5`     | seconds per SSH attempt            |
| `--concurrency N`| `16`   | parallel probe threads             |
| `--ping-first`  | off     | ICMP pre-filter before SSH         |
| `--arp`         | off     | ARP pre-filter before SSH          |
| `--register`    | off     | auto-add discovered nodes          |
| `--dry-run`     | off     | print what would be registered     |
| `--json`        | off     | machine-readable output            |

```sh
leaf nodes scan 192.168.4.0/22
leaf nodes scan 192.168.4.1-20 --ping-first --register
```

### `leaf nodes arp`
Print all unicast hosts currently in the local ARP table.

### `leaf nodes ping-sweep SUBNET [--json]`
ICMP-only sweep (no SSH); faster but only confirms reachability.

---

## Remote tasks (distributed)

### `leaf task submit NAME TASK_FILE`
Copy `TASK_FILE` to the named registered node's inbox and queue it.

### `leaf task watch NAME TASK_ID`
Tail the remote task log in real time.

### `leaf task pull NAME TASK_ID [DEST]`
Download the result of a completed remote task.

### `leaf task cancel NAME TASK_ID`
Cancel a task on a remote node.

---

## LAN distribution

### `leaf serve [OPTIONS]`
Build release bundles (`dist/`) and start an HTTP server so other machines on
the LAN can pull them.

| Flag           | Default        | Effect                                    |
|----------------|----------------|-------------------------------------------|
| `--port N`     | `7771`         | TCP listen port                           |
| `--host IP`    | local LAN IP   | bind address                              |
| `--once`       | off            | stop after first successful download      |
| `--no-rebuild` | off            | skip rebuild if `dist/` already populated |

```sh
leaf serve
leaf serve --port 8080 --once
```

### `leaf download HOST[:PORT] [FILE] [OPTIONS]`
Pull a bundle from a running `leaf serve` node.

| Argument/Flag   | Default       | Effect                                   |
|-----------------|---------------|------------------------------------------|
| `HOST[:PORT]`   | required      | IP or hostname; port default `7771`      |
| `FILE`          | `.tar.gz`     | specific filename to download            |
| `--dest DIR`    | current dir   | where to save the file                   |

SHA256 checksum is always verified after download.

```sh
leaf download 192.168.4.44
leaf download 192.168.4.44 leafos-0.5.0.zip --dest /tmp
```

### `leaf dist-build [--out DIR]`
Build bundles without starting a server.  Output to `dist/` by default.

### `leaf dist-info HOST[:PORT]`
Fetch and print the JSON manifest from a running serve node.

```sh
leaf dist-info 192.168.4.44
# → {version, built_at, host_ip, bundles:[{name,size,sha256},...]}
```

---

## Agent & graph (advanced)

### `leaf agent-brain TASK_FILE [GRAPH_FILE]`
Run the brain model against a task to produce an execution graph.

### `leaf agent-graph GRAPH_FILE`
Print a graph file in human-readable form.

### `leaf agent-loop GRAPH_FILE [--yes] [--soft-wait] [--apply]`
Drive an agent loop against a graph.

### `leaf agent-run PLAN_FILE --yes`
Execute a plan file non-interactively.

### `leaf agent-dry-run PLAN_FILE`
Show what `agent-run` would do without executing anything.

### `leaf agent-plan TASK_FILE [PLAN_NAME]`
Generate a plan from a task description.

### `leaf agent-validate PLAN_FILE`
Validate a plan file for correctness.

### `leaf agent-report [LABEL]`
Print the agent execution report.

### `leaf agent-route TASK_FILE [PLAN_NAME] [--mock|--provider MODE]`
Route a task through the provider selection logic.

### `leaf provider-status`
Show the status of all configured AI/model providers.

---

## Verification & checkpoints

### `leaf verify-run CMD [ARGS...]`
Run a command; emit `leaf.verify` token only if it exits 0.

### `leaf checkpoint LABEL`
Assert that a `leaf.verify` token exists (set by `verify-run`) before
recording a checkpoint.  Used in CI/CD pipelines.

---

## Module & session management

### `leaf new-module NAME`
Scaffold a new module directory.

### `leaf session-start`
Open a new named session.

### `leaf session-close`
Close the current session and write a summary.

---

## Dashboard

```sh
leaf dashboard
leaf dashboard --watch 3
leaf dashboard --json
leaf dashboard --no-color
leaf dashboard --width 120
```

See [`DASHBOARD_GUIDE.md`](DASHBOARD_GUIDE.md) for full documentation.
