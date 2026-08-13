# LeafOS Complete User Guide
### Version 0.5.0 - Resident Project Stack With Optional Node Tools

> **Current default:** attach the resident local stack to a project with
> `leafctl live PATH`. The stack means all downloaded and locally available
> models in this instance. Models propose; CPU-side policy executes and
> validates.

```powershell
.\bin\leafctl.ps1 live C:\R\MyProject
```

This long guide was originally organized around the SSH node, dashboard, chat,
and LAN subsystems. Those commands remain optional. For the current project
instruction flow, read `QUICKSTART.md`, `ARCHITECTURE.md`, `AGENTIC_CLI.md`,
and `RESIDENT_STACK_USAGE.md` first. The active agent-run interface is `tui`;
the older `dashboard` remains the node/cluster status interface.

> Commands in this repository are shown through `bin/leafctl.ps1` or
> `bin/leafctl`. Historical wrapper paths may exist in a larger checkout but
> are not required for this task pack.

---

## Contents

1. [What is LeafOS?](#1-what-is-leafos)
2. [Install](#2-install)
3. [System check & versions](#3-system-check--versions)
4. [Node setup](#4-node-setup)
5. [Dashboard — the live status window](#5-dashboard)
6. [Chat environment](#6-chat-environment)
7. [Model management — large file loading](#7-model-management)
8. [Theming & appearance](#8-theming--appearance)
9. [Task system](#9-task-system)
10. [Cluster & LAN networking](#10-cluster--lan-networking)
11. [LAN distribution — serve & download](#11-lan-distribution)
12. [Agent & brain](#12-agent--brain)
13. [Full CLI reference](#13-full-cli-reference)
14. [Environment variables](#14-environment-variables)
15. [Troubleshooting](#15-troubleshooting)

---

## 1. What is LeafOS?

LeafOS is a **terminal-native distributed task and chat system**.
Every feature renders inside a single terminal — coloured ANSI, animated
loaders, deterministic chat windows, live dashboards, LAN distribution.

**Core concepts:**

| Term          | Meaning                                                       |
|---------------|---------------------------------------------------------------|
| Node          | any machine with `~/.leaf/` workspace                         |
| Task          | JSON file describing work; moves through state directories    |
| Cluster       | two or more nodes registered and reachable over SSH           |
| Chat window   | themed, scrollable terminal UI for model conversation         |
| Model file    | `.gguf`, `.bin`, or `.safetensors` stored in `~/.leaf/models/`|
| Serve         | one-command LAN HTTP distribution (port 7771)                 |
| Dashboard     | live file-backed status surface; no network calls on render   |

---

## 2. Install

### Fastest — LAN pull from a running node

```sh
# On any machine that already has LeafOS:
leaf serve

# On the new machine (Python 3.8+ is enough — no Leaf needed yet):
python3 -c "
import urllib.request, json, os, sys
mf = json.loads(urllib.request.urlopen('http://SERVE_IP:7771/manifest.json').read())
b  = next(b for b in mf['bundles'] if b['name'].endswith('.tar.gz'))
urllib.request.urlretrieve('http://SERVE_IP:7771/' + b['name'], b['name'])
print('downloaded', b['name'])
"
tar -xzf leafos-0.5.0.tar.gz
bash leafos-0.5.0/bin/install_demo.sh
```

Replace `SERVE_IP` with the IP shown in the `leaf serve` banner.

### From source

```sh
git clone https://github.com/your-org/leafos_taskpack.git
cd leafos_taskpack
bash bin/install_demo.sh           # Linux / macOS / WSL
pwsh -File bin\install_demo.ps1    # Windows
```

### Requirements

| Component  | Minimum | Check               |
|------------|---------|---------------------|
| Bash       | 4.0     | `bash --version`    |
| Python     | 3.8     | `python3 --version` |
| OpenSSH    | any     | `ssh -V`            |
| PowerShell | 7.0     | Windows only        |

```sh
leaf versions    # checks all requirements in one table
```

---

## 3. System check & versions

```sh
leaf status          # quick online check
leaf versions        # component version table
leaf doctor          # deep diagnostics
leaf platform        # OS / arch / shell detection
```

**Version table output:**

```
component        found        required     status
----------------------------------------------------
bash             5.2          4.0          ok
python           3.12         3.8          ok
gcc              15.2         9.0          ok
powershell       7.4          7.0          ok
```

---

## 4. Node setup

Every machine that participates in the system needs a workspace.

```sh
leaf node init                        # auto-detect hostname as node-id
leaf node init --node-id "gpu-box-1"  # explicit name
leaf node init --role coordinator     # marks this node as a task dispatcher
```

Check status:

```sh
leaf node status           # text output
leaf node status --json    # machine-readable
leaf node hardware         # CPU / RAM / GPU probe
```

The workspace is created at `~/.leaf/` (override with `LEAF_HOME=/path`):

```
~/.leaf/
  node.json        identity + role
  nodes.json       registered remote nodes
  inbox/           tasks waiting to start
  queued/          tasks accepted
  running/         currently executing
  done/            completed
  failed/          errored
  logs/            *.jsonl event streams
  results/         task output payloads
  models/          ← model files live here
  chats/           ← chat session history
  leaf.lock        written while dashboard is open
```

---

## 5. Dashboard

The dashboard is the **canonical live status window**.
All panels read from files — no network calls during render.

```sh
leaf dashboard              # single render
leaf dashboard --watch 2    # refresh every 2 s (Ctrl-C to stop)
leaf dashboard --json       # machine-readable snapshot
leaf dashboard --no-color   # plain text (for pipes / logs)
leaf dashboard --width 120  # override column width
```

### Boot splash (interactive terminals only)

A 7-frame ASCII leaf wipes in on first launch:

```
	 ↑
	/◈\
   / ◈ \
  /_____\
   LeafOS
  v0.5.0
```

### Watch mode spinner

```
⠸  ◉ LIVE  refresh 2s
┌──────────────────────────────────────────────────────────────────────┐
│  LeafOS v0.5.0  NODE: MiniPC  ROLE: worker  STATE: ready  15:42:07  │
...
```

The braille spinner (`⠋ ⠙ ⠸ ⠴ ⠦ ⠇`) advances every refresh cycle.

### Dashboard panels

```
┌──────────────────────────────────────────────────────────────────────┐
│  LeafOS v0.5.0  NODE: MiniPC  ROLE: worker  STATE: ready  HH:MM:SS  │
├──────────────────────┬───────────────────────────────────────────────┤
│ TASK QUEUE           │ CLUSTER REGISTRY                              │
│   inbox       0      │   name    target              transport       │
│   queued      0      │   gpu1    user@192.168.4.45   ssh             │
│   running     1      │   local1  /tmp/work           local           │
│   done        5      ├───────────────────────────────────────────────┤
│   failed      0      │ RECENT EVENTS                                 │
├──────────────────────┤   15:41 task_chat   done   exit=0            │
│ HARDWARE             │   15:41 task_chat   stdout  ▶ tokens: 312    │
│   cpu    32 cores    │   15:40 task_chat   started runner=llama     │
│   ram    47.8 GB     ├───────────────────────────────────────────────┤
│   gpus   1           │ ARP TABLE  (LAN hosts)                       │
├──────────────────────┤   192.168.4.1  192.168.4.43  192.168.4.45   │
│ HOST                 │                                               │
│   ◉ LEAF_NODE ACTIVE │                                               │
│   ip     192.168.4.44│                                               │
│   pid    4812        │                                               │
│   uptime 01:12:07    │                                               │
│   lock   ~/.leaf/... │                                               │
└──────────────────────┴───────────────────────────────────────────────┘
```

| Panel          | Data source                        |
|----------------|------------------------------------|
| Task Queue     | file count in each state directory |
| Cluster Reg.   | `~/.leaf/nodes.json`              |
| Recent Events  | `~/.leaf/logs/*.jsonl` (last 10)  |
| Hardware       | stdlib probe, cached per session   |
| ARP Table      | `arp -a` / `/proc/net/arp`         |
| HOST           | live: `os.getpid()`, socket trick, `node.json` mtime |

### JSON snapshot

```sh
leaf dashboard --json | python3 -m json.tool
```

```json
{
  "leafos_object": "dashboard",
  "node":     { "node_id": "MiniPC", "role": "worker" },
  "queue":    { "inbox": 0, "running": 1, "done": 5 },
  "registry": { "gpu1": { "target": "user@192.168.4.45" } },
  "hardware": { "cpu_count": 32, "ram_gb": 47.8, "gpus": [{"name":"RTX 4090"}] },
  "arp_hosts": ["192.168.4.1", "192.168.4.43", "192.168.4.45"]
}
```

---

## 6. Chat environment

The chat system is a **fully themed, deterministic terminal chat window**.
Each session is file-backed; history persists between launches.
No HTTP API required — the model runs locally via the task system.

### Start a chat session

```sh
leaf chat                            # open default model
leaf chat --model llama-3.2-3b       # specific model
leaf chat --session my-project       # named session (resumable)
leaf chat --theme forest             # apply a colour theme
leaf chat --no-color                 # plain text mode
leaf chat --width 100                # column width
```

### Chat window layout

```
┌──────────────────────────────────────────────────────────────────────┐
│  ✿ LeafOS Chat  │  model: llama-3.2-3b  │  session: my-project      │
│  tokens: 1,842  │  ctx: 4096  │  temp: 0.7  │  theme: forest        │
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  [you]  15:41:02                                                     │
│  Explain how the Leaf node system dispatches tasks.                  │
│                                                                      │
│  [leaf]  15:41:04  ████████████████████░░░░  312 tok  0.8s          │
│  The Leaf node system uses SSH as the sole transport layer.          │
│  A task is a JSON file that moves through state directories:        │
│  inbox → queued → running → done (or failed). The distributor      │
│  copies the file to the remote node's inbox via scp, then           │
│  calls `leaf task start TASK_ID` over SSH to execute it.           │
│                                                                      │
│  [you]  15:41:20                                                     │
│  ▌                                              [type, Enter sends] │
├──────────────────────────────────────────────────────────────────────┤
│  /help  /theme  /model  /save  /clear  /exit   session: my-project  │
└──────────────────────────────────────────────────────────────────────┘
```

### Chat commands (typed in the input line)

| Command              | Effect                                           |
|----------------------|--------------------------------------------------|
| `/help`              | show command list                                |
| `/theme NAME`        | switch colour theme live                         |
| `/model NAME`        | swap the active model (triggers model load)      |
| `/save [FILE]`       | export conversation to `~/.leaf/chats/`          |
| `/clear`             | clear screen, keep history                       |
| `/reset`             | clear screen and reset conversation context      |
| `/exit` or `Ctrl-D`  | end session                                      |
| `/tokens`            | show token count, context usage, generation speed|
| `/system PROMPT`     | set or replace the system prompt                 |
| `/temp N`            | set temperature (0.0–2.0)                        |
| `/ctx N`             | set context window size                          |
| `/nodes`             | list cluster nodes (for remote model dispatch)   |
| `/submit NODE`       | send next message to a remote node's model       |

### Session persistence

Every message is appended to `~/.leaf/chats/SESSION_NAME.jsonl` in real time.
Resume any session:

```sh
leaf chat --session my-project       # continues where you left off
leaf chat --session my-project --list   # show message history
leaf chat --export my-project           # export to markdown
```

Export format (`~/.leaf/chats/my-project.md`):

```markdown
# LeafOS Chat Export — my-project
Model: llama-3.2-3b  |  Exported: 2026-06-22 16:00

**you** · 15:41:02
Explain how the Leaf node system dispatches tasks.

**leaf** · 15:41:04
The Leaf node system uses SSH as the sole transport ...
```

### Remote chat (dispatch to cluster node)

```sh
leaf chat --remote gpu1           # run model on registered node 'gpu1'
leaf chat --remote 192.168.4.45  # direct IP
```

Prompts are submitted as tasks, streamed back over SSH tail.
The local chat window shows a live token counter while the remote model runs.

---

## 7. Model management

LeafOS handles the local **stack**: all downloaded and locally available models
within this LeafOS instance. Stack entries can be several gigabytes, so LeafOS
uses
real animated loading, resume-on-interrupt download, and SHA256 verification.

### Where the stack lives

```
~/.leaf/models/
  llama-3.2-3b.Q4_K_M.gguf    3.8 GB
  mistral-7b.Q5_K_M.gguf      4.9 GB
  manifest.json                model registry
```

### List the available stack

```sh
leaf model list                  # local stack
leaf model list --remote gpu1    # remote node stack
```

```
  name                          size      format    status
  llama-3.2-3b.Q4_K_M.gguf     3.8 GB    gguf      ready
  mistral-7b.Q5_K_M.gguf        4.9 GB    gguf      ready
```

### Pull a model from another node (LAN)

```sh
leaf model pull gpu1 llama-3.2-3b.Q4_K_M.gguf
```

**What you see during a large model download:**

```
  LeafOS Stack Pull
  ─────────────────────────────────────────────────────────
  source   gpu1  (192.168.4.45)
  file     llama-3.2-3b.Q4_K_M.gguf
  size     3.8 GB
  dest     ~/.leaf/models/

  downloading ...
  ⠸ [████████████████████░░░░░░░░░░░░░░░░░░░░]  51.4%
	downloaded   1.97 GB / 3.83 GB
	speed        48.2 MB/s
	eta          38 s
	elapsed      41 s

  verifying sha256 ...  ████████████████████████████████  OK

  stack entry ready:  ~/.leaf/models/llama-3.2-3b.Q4_K_M.gguf
```

The braille spinner (`⠋ ⠙ ⠸ ⠴ ⠦ ⠇`) ticks on every 64 KB chunk.
Downloads resume automatically if interrupted — the partial file is kept and
the server is queried for byte-range support.

### Serve your stack to the LAN

```sh
leaf model serve                       # serve all local stack entries
leaf model serve --model mistral-7b    # serve one stack entry only
leaf model serve --port 7772           # custom port (default 7772)
```

Other nodes pull with:

```sh
leaf model pull 192.168.4.44 mistral-7b.Q5_K_M.gguf
```

### Loading animation when a model starts

When `leaf chat` loads a model into memory, a staged animation plays:

```
  ✿ loading llama-3.2-3b.Q4_K_M.gguf

  ⠋ reading model header       ...  done  (0.1 s)
  ⠙ mapping layers to memory   ████████████████████░░░░░░  3.1 GB / 3.8 GB
  ⠸ initialising KV cache      ...  done
  ⠴ warming context window     ...  done

  ✓ model ready  │  ctx: 4096  │  layers: 32  │  load: 1.4 s
```

Each stage is a real read from the model process's stderr — not a fake timer.

### Model info

```sh
leaf model info llama-3.2-3b.Q4_K_M.gguf
```

```
  file      llama-3.2-3b.Q4_K_M.gguf
  size      3.82 GB
  format    GGUF v3
  quant     Q4_K_M
  ctx       4096
  layers    32
  sha256    a3f8e9...
  added     2026-06-20 14:30
```

---

## 8. Theming & appearance

All output — dashboard, chat, loaders, alerts — flows through the brand layer.
Themes can be set globally, per session, or per command.

### Built-in themes

| Theme       | Accent     | Background feel     | Best for          |
|-------------|------------|---------------------|-------------------|
| `default`   | cyan       | neutral             | general use       |
| `forest`    | green      | dark earth          | long sessions     |
| `ocean`     | blue       | deep dark           | coding / agents   |
| `ember`     | yellow/red | warm                | creative writing  |
| `mono`      | white      | greyscale           | logs / CI         |
| `plain`     | _(none)_   | no ANSI             | pipes / files     |

### Apply a theme

```sh
# per-command
leaf chat --theme forest
leaf dashboard --theme ocean

# session-wide (persists until shell exits)
export LEAF_THEME=forest
leaf dashboard

# permanent (write to brand.conf)
echo 'LEAF_THEME=forest' >> ~/.leaf/brand.conf
```

### What changes per theme

- **Chat window** — border characters, prompt colour, response colour,
  token counter accent, spinner colour
- **Dashboard** — header bold, panel label colour, state colour map
  (ready = green, running = cyan, failed = red)
- **Loaders** — spinner frame set and colour
- **Alerts** — OK / warn / error accent colours
- **Banner** — top/bottom border colour

### Custom theme file

Create `~/.leaf/themes/my-theme.conf`:

```sh
# ~/.leaf/themes/my-theme.conf
LEAF_C_ACCENT="\033[38;5;208m"      # orange (256-colour)
LEAF_C_DIM="\033[2m"
LEAF_C_BOLD="\033[1m"
LEAF_C_OK="\033[32m"
LEAF_C_WARN="\033[33m"
LEAF_C_ERR="\033[31m"
LEAF_SPINNER_FRAMES="▏▎▍▌▋▊▉█▉▊▌▍▎▏"
LEAF_CHAT_BORDER="rounded"          # rounded │ square │ heavy
LEAF_CHAT_YOU_PREFIX="▶ you"
LEAF_CHAT_BOT_PREFIX="◉ leaf"
```

Load it:

```sh
export LEAF_THEME=my-theme
leaf chat
```

### Loader animations

Loaders are named animation sequences. Use them in any script:

```sh
leaf loader                    # default
leaf loader dots "loading"     # pulsing dots
leaf loader spinner "thinking" # braille spinner
leaf loader bar "downloading"  # fill bar
leaf loader wave "processing"  # wave sweep
leaf loaders                   # list all
```

**Sample loader in watch mode (bar):**

```
  downloading  [████████████░░░░░░░░░░░░░░░░░░░░░░░░░░░░]  32%
```

**Sample loader (spinner):**

```
  ⠸ thinking ...
```

---

## 9. Task system

Tasks are JSON files that move through state directories.
The task runner executes them and logs every event to `~/.leaf/logs/`.

### Task file format

```json
{
  "kind":     "echo",
  "priority": 5,
  "payload":  { "message": "hello from node" }
}
```

Supported `kind` values:

| kind       | What it runs                                  |
|------------|-----------------------------------------------|
| `echo`     | print a message                               |
| `shell`    | run a shell command string                    |
| `hardware` | probe CPU / RAM / GPU                         |
| `llama`    | run a prompt through a local `.gguf` model    |
| `chat`     | open a chat task (streamed, interactive)      |
| `download` | pull a file from a URL or node                |

### Run a task locally

```sh
# copy task file to inbox, then start
cp examples/echo.task.json ~/.leaf/inbox/task_001.json
leaf task start task_001

# or one-liner
leaf task run examples/echo.task.json
```

### Task state flow

```
inbox → queued → running → done
						 ↘ failed
```

### Monitor tasks

```sh
leaf task list                       # all tasks
leaf task list --state running       # filter by state
leaf task list --json                # JSON output
leaf task logs task_001              # event stream
leaf task logs task_001 --follow     # tail -f style
leaf task result task_001            # output payload
leaf task cancel task_001            # cancel
```

### Submit to a remote node

```sh
leaf task submit gpu1 examples/llama.task.json
leaf task watch  gpu1 task_llama_001
leaf task pull   gpu1 task_llama_001 ./results/
```

---

## 10. Cluster & LAN networking

### Register nodes

```sh
leaf nodes add gpu1   user@192.168.4.45
leaf nodes add local1 /tmp/worker1 --transport local
leaf nodes list
leaf nodes ping gpu1
```

### Discover nodes automatically

```sh
# Read ARP table (passive, instant)
leaf nodes arp

# ICMP sweep (fast, confirms reachability)
leaf nodes ping-sweep 192.168.4.0/22

# SSH scan (authoritative — confirms Leaf is installed)
leaf nodes scan 192.168.4.0/22

# Combined (fastest full scan)
leaf nodes scan 192.168.4.0/22 --arp --ping-first --register
```

Scan output:

```
  192.168.4.45  leaf-4-45    worker   v0.5.0   ready    ✓
  192.168.4.46  gpu-box      worker   v0.5.0   ready    ✓
  192.168.4.47  ─            ─        ─        timeout  ✗
```

### LAN topology display

```sh
leaf nodes topo                   # ASCII topology map
```

```
  MiniPC  (192.168.4.44)  ─── coordinator
	├── gpu1    (192.168.4.45)  worker   ready
	├── gpu2    (192.168.4.46)  worker   ready
	└── local1  (/tmp/w1)       worker   local
```

---

## 11. LAN distribution

Ship LeafOS — code, models, config — to any machine on the LAN without
a web server or file share. Everything is terminal.

### Serve (source node)

```sh
leaf serve                      # build + serve on LAN IP:7771
leaf serve --once               # stop after first successful download
leaf serve --no-rebuild         # skip rebuild if dist/ exists
leaf serve --port 8080          # custom port
```

Live serve banner:

```
┌──────────────────────────────────────────────────────────┐
│ LeafOS v0.5.0  SERVE  ◉ ACTIVE  192.168.4.44             │
│ port  7771   pid  19960   requests  2                     │
├──────────────────────────────────────────────────────────┤
│   leafos-0.5.0.tar.gz                153.2 KB             │
│     sha256: 3ec0f3e30b033e8b58366...                     │
│   leafos-0.5.0.zip                   202.3 KB             │
│     sha256: e89d1f03c1cb255bcb0b...                      │
├──────────────────────────────────────────────────────────┤
│   leaf download 192.168.4.44                             │
│   curl http://192.168.4.44:7771/manifest.json            │
└──────────────────────────────────────────────────────────┘
```

### Download (target node)

```sh
leaf download 192.168.4.44                              # auto tar.gz
leaf download 192.168.4.44 leafos-0.5.0.zip --dest /tmp
leaf dist-info 192.168.4.44                             # show manifest
leaf dist-build                                         # build only
```

Download with live progress bar:

```
  fetching manifest from http://192.168.4.44:7771/manifest.json
  → leafos-0.5.0.tar.gz  (153.2 KB)

  [████████████████████████████████████████] 100.0%  153.2 KB  48.2 MB/s
  done in 0.0s  →  /tmp/leafos-0.5.0.tar.gz
  verifying sha256 ...  OK

  to install:
	tar -xzf /tmp/leafos-0.5.0.tar.gz
	bash /tmp/leafos-0.5.0/bin/install_demo.sh
```

SHA256 is always verified. A mismatch exits non-zero.

### Model distribution

```sh
leaf model serve                            # serve models on port 7772
leaf model pull 192.168.4.44 mistral-7b.Q5_K_M.gguf
```

---

## 12. Agent & brain

The agent system translates task descriptions into execution graphs, then
drives them node-by-node.

```sh
leaf agent-brain task.md            # generate graph from task description
leaf agent-graph graph.json         # visualise the graph
leaf agent-dry-run plan.json        # preview without executing
leaf agent-run plan.json --yes      # execute
leaf agent-loop graph.json --apply  # drive loop
leaf agent-report                   # show last run report
leaf provider-status                # check model provider connections
```

Graph output example:

```
  agent.graph  ──  task: "Refactor loader animation"
  ┌─────────┐     ┌──────────┐     ┌──────────┐
  │ analyse │────▶│  code    │────▶│  verify  │
  │ brain   │     │  coder   │     │  gate    │
  └─────────┘     └──────────┘     └──────────┘
```

---

## 13. Full CLI reference

```
leaf help                              show this table
leaf status                            system online check
leaf versions                          component version table
leaf doctor                            deep diagnostics
leaf platform                          OS / arch / shell info
leaf motd                              message of the day

leaf node init [--node-id ID] [--role ROLE]
leaf node status [--json]
leaf node hardware [--json]

leaf task start TASK_ID
leaf task run   TASK_FILE
leaf task list  [--state S] [--json]
leaf task logs  TASK_ID [--follow]
leaf task result TASK_ID [--json]
leaf task cancel TASK_ID

leaf nodes add  NAME USER@HOST [--transport TYPE] [--path DIR]
leaf nodes list [--json]
leaf nodes ping NAME
leaf nodes scan SUBNET [--ping-first] [--arp] [--register] [--json]
leaf nodes arp
leaf nodes ping-sweep SUBNET [--json]
leaf nodes topo

leaf task submit NAME TASK_FILE
leaf task watch  NAME TASK_ID
leaf task pull   NAME TASK_ID [DEST]
leaf task cancel NAME TASK_ID

leaf chat [--model NAME] [--session NAME] [--theme NAME]
		  [--remote NODE] [--width N] [--no-color]
leaf chat --list                       list sessions
leaf chat --export SESSION             export to markdown

leaf model list   [--remote NODE]
leaf model info   FILE
leaf model pull   NODE FILE [--dest DIR]
leaf model serve  [--port N] [--model NAME]

leaf serve        [--port N] [--host IP] [--once] [--no-rebuild]
leaf download     HOST[:PORT] [FILE] [--dest DIR]
leaf dist-build   [--out DIR]
leaf dist-info    HOST[:PORT]

leaf dashboard    [--watch N] [--json] [--no-color] [--width N]

leaf agent-brain    TASK_FILE [GRAPH_FILE]
leaf agent-graph    GRAPH_FILE
leaf agent-loop     GRAPH_FILE [--yes] [--soft-wait] [--apply]
leaf agent-run      PLAN_FILE --yes
leaf agent-dry-run  PLAN_FILE
leaf agent-plan     TASK_FILE [PLAN_NAME]
leaf agent-validate PLAN_FILE
leaf agent-report   [LABEL]
leaf agent-route    TASK_FILE [--mock|--provider MODE]
leaf provider-status

leaf loader  [NAME] [LABEL]        run a named animation
leaf loaders                       list animations
leaf glyph   ALIAS [--ascii] [--json]
leaf glyphs  [CATEGORY] [--ascii] [--json]
leaf spin    [LABEL] [CYCLES]      branded spinner
leaf alert   SEVERITY MESSAGE      coloured alert

leaf verify-run CMD [ARGS...]
leaf checkpoint LABEL
leaf new-module NAME
leaf session-start
leaf session-close
```

---

## 14. Environment variables

| Variable             | Default         | Effect                                     |
|----------------------|-----------------|--------------------------------------------|
| `LEAF_HOME`          | `~/.leaf`       | workspace root                             |
| `LEAF_THEME`         | `default`       | colour theme name or path to `.conf`       |
| `LEAF_SSH_OPTS`      | _(empty)_       | extra flags appended to every `ssh` call   |
| `QUIET`              | `0`             | suppress all brand messages when `1`       |
| `NO_COLOR`           | `0`             | strip all ANSI escape sequences when `1`   |
| `NO_EMOJI`           | `0`             | replace `✿` with `›` when `1`             |
| `FLOWER_EMOJI_RATE`  | `2`             | show emoji every N brand messages          |
| `LEAF_DASH_WIDTH`    | _(auto)_        | override dashboard column width            |
| `BANNER_ENABLED`     | `1`             | show/hide the startup banner               |
| `LEAF_MODEL_DIR`     | `~/.leaf/models`| model file directory                       |
| `LEAF_CHAT_DIR`      | `~/.leaf/chats` | chat session history directory             |
| `LEAF_LOG_LEVEL`     | `info`          | `debug`, `info`, `warn`, `error`           |

Set permanently:

```sh
echo 'export LEAF_THEME=forest' >> ~/.bashrc
echo 'export LEAF_SSH_OPTS="-i ~/.ssh/leaf_ed25519"' >> ~/.bashrc
```

Or write to `~/.leaf/brand.conf` for LeafOS-specific settings.

---

## 15. Troubleshooting

### `leaf versions` shows WARN or missing

```sh
# Bash too old (macOS default is 3.x)
brew install bash
echo /opt/homebrew/bin/bash | sudo tee -a /etc/shells
chsh -s /opt/homebrew/bin/bash

# Python not found
brew install python3       # macOS
sudo apt install python3   # Debian/Ubuntu
```

### `leaf nodes scan` finds nothing

```sh
# 1. Confirm sshd is running on target
ssh user@192.168.4.45 "cat ~/.leaf/node.json"

# 2. Increase timeout
leaf nodes scan 192.168.4.0/22 --timeout 10

# 3. Try direct ping first
leaf nodes ping-sweep 192.168.4.0/22
```

### Chat shows model not found

```sh
leaf model list              # what's installed
leaf model info FILENAME     # check a specific file

# Pull from another node
leaf model pull gpu1 llama-3.2-3b.Q4_K_M.gguf
```

### Download hangs / SHA256 mismatch

```sh
# 1. Check server is up
leaf dist-info 192.168.4.44

# 2. Check firewall allows port 7771
# 3. Re-download (partial files are automatically removed on mismatch)
leaf download 192.168.4.44
```

### Dashboard ARP panel empty (Windows)

```sh
# Populate ARP table first
ping 192.168.4.1
leaf nodes arp     # should now show the gateway
```

### Slow chat / high latency

```sh
# Check which node is running the model
leaf dashboard --watch 2    # watch the RECENT EVENTS panel

# Submit to a GPU node instead
leaf chat --remote gpu1
```

### `leaf.lock` left behind after crash

```sh
rm ~/.leaf/leaf.lock
```

This is safe — the lock is advisory only.

---

*LeafOS v0.5.0 · terminal-first · LAN-native · chat-ready*
*Docs: docs/ · Source: github.com/your-org/leafos_taskpack*
