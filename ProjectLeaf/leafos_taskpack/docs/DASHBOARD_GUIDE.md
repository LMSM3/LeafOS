# LeafOS Dashboard Guide

Version: 0.5.0 | `core/ui/dashboard.py`

The dashboard is the read-only status surface for the optional SSH node and
cluster subsystem. It reads all data from files; no network calls are made
during rendering.

For a version-2 agent run, the canonical active interface is `leafctl tui`.
The TUI reads the normalized inlet snapshot and can send authenticated typed
controls. The dashboard does not display the resident queue, governor, work
orders, provider stream, or checkpoint lifecycle.

---

## Quick start

```sh
leaf dashboard              # single render, auto-sized
leaf dashboard --watch 2    # live refresh every 2 s
leaf dashboard --json       # machine-readable snapshot
```

---

## Launching

```sh
# via leafctl (recommended)
leaf dashboard [FLAGS]

# direct
python3 core/ui/dashboard.py [FLAGS]
```

### Flags

| Flag             | Default       | Effect                                    |
|------------------|---------------|-------------------------------------------|
| `--watch N`      | _(single)_    | refresh every N seconds; Ctrl-C to stop   |
| `--json`         | off           | emit JSON snapshot, exit                  |
| `--no-color`     | auto          | strip ANSI; auto-disabled when piped      |
| `--width N`      | auto (max 180)| override terminal width                   |
| `--home PATH`    | `$LEAF_HOME`  | override workspace directory              |

---

## Boot splash

When launched interactively (real TTY, colour on), a 7-frame ASCII leaf
animates in before the dashboard appears:

```
	 ↑
	/◈\
   / ◈ \
  /_____\
   LeafOS
  v0.5.0
```

Skipped when piped (`--no-color`, or `--json`).

---

## Watch mode spinner

In `--watch` mode a braille spinner (`⠋ ⠙ ⠸ ⠴ ⠦ ⠇`) and a `◉ LIVE` status
bar appear between the box border and the header.  The spinner frame advances
on every refresh.

---

## Layout

```
┌──────────────────────────────────────────────────────────────────────┐
│  LeafOS v0.5.0  NODE: MiniPC  ROLE: worker  STATE: ready  HH:MM:SS  │
├──────────────────────┬───────────────────────────────────────────────┤
│ TASK QUEUE           │ CLUSTER REGISTRY                              │
│   inbox       0      │   name    target          transport  state    │
│   queued      0      │   gpu1    user@192.168.4.45  ssh     ready   │
│   running     0      │                                               │
│   done        5      ├───────────────────────────────────────────────┤
│   failed      1      │ RECENT EVENTS                                 │
├──────────────────────┤   14:52 task_echo  done   exit=0             │
│ HARDWARE             │   14:52 task_echo  stdout hello               │
│   cpu    32 cores    │   14:51 task_echo  queued                    │
│   ram    47.8 GB     ├───────────────────────────────────────────────┤
│   gpus   1           │ ARP TABLE  (LAN hosts)                       │
├──────────────────────┤   192.168.4.1   192.168.4.43   192.168.4.45 │
│ PATHS                │                                               │
│   active  ◉ ACTIVE   │                                               │
│   ip      192.168.4.44                                               │
│   pid     4812                                                       │
│   uptime  00:42:07                                                   │
│   home    ~/.leaf                                                    │
│   lock    ~/.leaf/leaf.lock                                          │
└──────────────────────┴───────────────────────────────────────────────┘
```

---

## Panels

### Header
Single full-width row.  Shows version (read from `VERSION` file), node ID,
role, state, and current timestamp.

### Task Queue (left)
Counts files in each state directory under `LEAF_HOME/`:

| Row       | Directory         |
|-----------|-------------------|
| `inbox`   | `LEAF_HOME/inbox/`   |
| `queued`  | `LEAF_HOME/queued/`  |
| `running` | `LEAF_HOME/running/` |
| `done`    | `LEAF_HOME/done/`    |
| `failed`  | `LEAF_HOME/failed/`  |

### Attention and next action

The dashboard adds two read-only summary rows after the main panels. They use
the local queue state to identify the most important condition and one safe
follow-up command. Priority is failed tasks, running tasks, queued/inbox work,
then an empty queue. JSON output exposes the same data under `attention`.

### Cluster Registry (right)
Reads `LEAF_HOME/nodes.json` — the list of registered remote nodes.
Columns: name, target, transport, state.

### Hardware (left)
Probed once per session and cached.  Sources in order:
1. Latest `result.json` from a `hardware` task (most accurate)
2. Live stdlib probe: `os.cpu_count()`, `GlobalMemoryStatusEx` (Windows) /
   `SC_PHYS_PAGES` (POSIX), `nvidia-smi`

### Recent Events (right)
Last 10 events from `LEAF_HOME/logs/*.jsonl` sorted newest-first.
Event types are colour-coded:

| Type      | Colour  |
|-----------|---------|
| `done`    | green   |
| `failed`  | red     |
| `started` | cyan    |
| `stdout`  | dim     |
| `queued`  | blue    |

### ARP Table (right)
Live read of the local ARP table on every render (one subprocess call < 50 ms).
Only unicast LAN IPs are shown; multicast, broadcast, and loopback are filtered.

### Paths / Host panel (left)
Real runtime values every render:

| Row      | Source                                  |
|----------|-----------------------------------------|
| `active` | always `◉ LEAF_NODE ACTIVE`            |
| `ip`     | `socket.connect("8.8.8.8:80")` trick    |
| `pid`    | `os.getpid()`                           |
| `uptime` | seconds since `node.json` was written   |
| `home`   | `LEAF_HOME`                             |
| `lock`   | `LEAF_HOME/leaf.lock` (written on open) |

---

## Lock file

When the dashboard starts, it writes `LEAF_HOME/leaf.lock`:

```
pid=4812
started=2026-06-22T15:14:00-07:00
```

The file is automatically removed on exit (via `atexit`).  You can check
whether a dashboard session is running from another process:

```sh
cat ~/.leaf/leaf.lock
```

---

## JSON mode

`leaf dashboard --json` emits a single JSON object and exits:

```json
{
  "leafos_object": "dashboard",
  "timestamp": "2026-06-22T15:14:00-07:00",
  "node":     { "node_id": "MiniPC", "role": "worker", ... },
  "queue":    { "inbox": 0, "done": 5, "failed": 1, ... },
  "registry": { "gpu1": { ... } },
  "hardware": { "cpu_count": 32, "ram_gb": 47.8, "gpus": [...] },
  "arp_hosts": ["192.168.4.1", "192.168.4.43", "192.168.4.45"],
  "recent_events": [ ... ]
}
```

Pipe into `jq` for filtering:

```sh
leaf dashboard --json | python3 -m json.tool
leaf dashboard --json | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['queue']['failed'])"
```

---

## Environment override

```sh
LEAF_HOME=/data/leaf1   leaf dashboard
LEAF_DASH_WIDTH=120     leaf dashboard
NO_COLOR=1              leaf dashboard
```

---

## Running without a node

If `LEAF_HOME/node.json` does not exist, the dashboard still renders but shows
`NODE: uninitialized`.  To initialise:

```sh
leaf node init
```
