# LeafOS Roadmap

## Design doctrine

Soft surface. Hard backend. Boring and useful beats clever and broken.

```
0.2.0  proves the pipe
0.3.0  introduces the graph
0.4.0  embedded agentic actions + soft waits + coder patches
0.5.0  closes the loop with telemetry + bounded repair
0.6.0  plants the local hosting foundation
0.7.0  connects nodes with efficient relays
0.8.0  supports continual hosting + dataset export
0.9.0  delivers the stable local project builder
```

Every version must satisfy its own completion gate before the next begins.

## Current Operating Baseline

The repository and taskpack versions are `0.2.3`, and implementation has advanced beyond
the original graph-only wording below. The current project path is a resident
version-2 loop with typed work orders, priority/dependency queueing, a
proposal-only llama.cpp Vulkan provider, CPU-authoritative execution and
validation, bounded repair/refill, universal telemetry, and Python/native TUI
controls.

```text
leafctl live PROJECT
  -> intake -> plan -> approve -> execute -> validate -> checkpoint/report
  -> bounded repair or resident next improvement
```

## Current work-order map through WO-060

The letters below are planning overlays, not new work-order identities or new
runtime authorities:

| Lane | Responsibility | Work-order span |
|---|---|---|
| L | Local trust and advanced execution | WO-050 repairs, WO-051–WO-056 |
| M | Coherent loop contracts | WO-LOOP1–WO-LOOP6 |
| N | Native product proof | WO-057–WO-060 |
| X | Cross-cutting UX projection | shell TUI graphics over verified L/M/N state |

```text
reconcile canonical source
  -> L: 050/R1/R2 -> 051 -> 052 -> 053 -> 054 -> 055 -> 056
  -> M: LOOP1 -> LOOP2 -> LOOP3 -> LOOP4 -> LOOP5 -> LOOP6
  -> N: 057 -> 058 -> 059 -> 060

X: evidence-backed shell TUI projection across L, M, and N
```

Current evidence boundary as of 2026-08-11:

- WO-050/R1/R2, WO-051, and WO-052 have local completion evidence.
- WO-053-B has locally verified implementation evidence, but the opt-in
  digest-bound real-host preflight has not run; master WO-053 remains open.
- WO-054–WO-060 and WO-LOOP1–WO-LOOP6 remain planned work.
- Imported repair records do not prove that their implementation files have
  been reconciled into the canonical source tree.

The X lane owns presentation quality—colour, motion, pack glyphs, progress,
errors, accessibility, and legal-next-action display. Its graphics surface is
the shell TUI. X projects typed evidence and state; it does not create a
private scheduler, provider, event stream, or acceptance path.

The 0.2-0.4 sections below preserve release evolution and compatibility
surfaces. They are not the recommended starting workflow. Selected 0.6 ideas,
including project seeds and adaptive resource control, landed early under
WO-037/WO-038. This does not change the `VERSION` file. Current documentation
authority is listed in `docs/DOCUMENTATION_MAP.md`.

---

## Planning Documents

- [Documentation Map](docs/DOCUMENTATION_MAP.md): current authority and historical boundaries.
- [WO-038 Resident Finalization](docs/work-orders/WO-038-resident-stack-finalization.md): implemented resident operating model and outstanding soak gates.
- [WO-038 Completion Report](reports/work-orders/WO-038-COMPLETION-REPORT.md): retained implementation and real-run evidence.
- [0.3 Orchestration](docs/ORCHESTRATION_0.3.md): retained three-input compatibility prototype.
- `ROADMAP.md`: version evolution and future release intent.

Work orders supply task-level authority. This roadmap supplies release-level
direction. Current operator instructions live in the documentation map rather
than an external alpha or skeleton file.

---

## 0.2.0 — Universal CLI Task Pipeline

**Status:** complete ✓

**Spine:**
```
agent-task -> agent-route --provider llamacpp -> agent-dry-run -> agent-run --yes -> agent-report
```

**Completion gate:** `tests/spine.sh` passes end to end.

**Alpha task range:** 1-13

---

## 0.3.0 — Brain Model + Agent Graph

**Status:** implemented as a compatibility surface; superseded by the version-2 project loop

**Purpose:**
0.3 turns a task into a bounded, inspectable graph. The Brain proposes the
work; LeafOS validates dependencies, persists node state, and stops cleanly
when a gate, failure, or policy limit is reached.

The graph must be deterministic enough to inspect, resumable after interruption,
and explicit about artifacts, provenance, state transitions, limits, and human
approval points.

**Alpha task range:** 14-40

**Spine:**
```
agent-task → agent-brain → agent.graph.json → agent-loop → agent-gate → agent-report
```

**New object: `agent.graph.json`**
```json
{
  "leafos_graph_version": "0.3.0",
  "goal": "...",
  "nodes": [
    { "id": "brain_inspect",    "type": "inspect", "status": "pending" },
    { "id": "implement",        "type": "write",   "depends_on": ["brain_inspect"], "status": "pending" },
    { "id": "verify",           "type": "verify",  "depends_on": ["implement"],    "status": "pending" },
    { "id": "completion_gate",  "type": "gate",    "depends_on": ["verify"],       "status": "pending" }
  ],
  "completion_gate": {
    "required_files":    ["README.md", "tests/smoke.sh"],
    "required_commands": ["bash -n bin/leafctl"],
    "forbidden_paths":   [".git/", "$HOME/", "/etc/", "/usr/"]
  }
}
```

**New commands:**
```bash
leafctl agent-brain  TASK_FILE [GRAPH_FILE]
leafctl agent-graph  GRAPH_FILE
leafctl agent-loop   GRAPH_FILE [--yes] [--soft-wait] [--apply]
leafctl agent-gate   GRAPH_FILE [WORKDIR]
leafctl agent-node   GRAPH_FILE NODE_ID
leafctl agent-action ACTION NODE_ID [INPUT_JSON]
leafctl agent-wait   TARGET [INTERVAL [MAX_ATTEMPTS]]
leafctl agent-orchestrate README SKELETON WILDCARD [--provider llamacpp] [--yes]
```

**Three-input orchestration prototype:**

The initial execution layer accepts only a README, a skeleton, and one
wildcard file. It snapshots them, asks for a schema-constrained action plan,
validates the plan, and executes only allow-listed skills.

**New modules:**
```
core/graph/graph.sh     jq-based graph CRUD
core/agent/wait.sh      ❑❒❐❏ soft bounded polling loops
core/agent/actions.sh   embedded action dispatcher (12 action types)
core/agent/loop.sh      execution loop: pick → run → update → repair → gate
core/agent/repair.sh    repair node injection
core/model/brain.sh     task -> validated graph through a configured provider
core/model/coder.sh     provider output -> validated patch
core/verify/gate.sh     completion gate
core/patch/validate.sh  patch validation gate
core/patch/apply.sh     confirmed patch application
core/orchestration/     three-input skill and execution boundary
config/orchestration.*  action JSON schema and llama.cpp grammar
```

**Completion gate:** `tests/graph.sh` passes; `agent-gate` passes on a smoke
run; graph fixtures cover invalid dependencies, deadlocks, resume, and
round-trip import/export.

---

## 0.4.0 — Embedded Agentic Actions + Soft Waits + Coder Patches

**Status:** implemented as embedded-action compatibility infrastructure

**Purpose:**
Graph nodes become executable embedded agentic actions.
Soft waits are built in. Coder produces patches per node.
Failures create repair nodes. Completion gate becomes real.

**Alpha task range:** 41-56

**Design thesis:**
Embedded agentic actions are small callable units inside the graph runner.
Soft waiting loops are bounded, visible wait states that poll for completion
without pretending the agent is magic.

The system should never "wait forever." That is how computers become shrines.

**Node format:**
```json
{
  "id": "coder_patch_main",
  "type": "agent_action",
  "actor": "coder",
  "symbol": "⋆",
  "action": "agent.ask_coder",
  "depends_on": ["brain_plan"],
  "input": {
    "task": "Implement the main CLI entrypoint.",
    "allowed_files": ["bin/leaf", "core/agent/runner.sh"],
    "output_format": "unified_diff"
  },
  "wait": {
    "enabled": true,
    "condition": "patch_file_exists",
    "target": "runs/latest/coder.patch",
    "interval_seconds": 1,
    "max_attempts": 60
  },
  "on_success": ["validate_patch"],
  "on_failure": ["repair_or_abort"]
}
```

**Embedded action types (0.4.0):**

| action                | symbol | purpose |
|-----------------------|--------|---------|
| `agent.ask_brain`     | ⋆      | re-plan or repair via brain model |
| `agent.ask_coder`     | ⋆      | generate bounded unified diff |
| `fs.inspect`          | 𓂃     | read files, list layout |
| `fs.require_file`     | 𓂃     | assert file exists |
| `patch.validate`      | 𓂃     | git apply --check |
| `patch.apply`         | 𓂃     | git apply |
| `shell.run`           | 𓂃     | run bounded shell command |
| `wait.file`           | ❑❒❐❏  | poll for file |
| `wait.command_success`| ❑❒❐❏  | poll for command exit 0 |
| `verify.run`          | ⚝     | run test/check command |
| `report.append`       | ⎙     | append to report.md |
| `repair.create_node`  | ⚠︎     | inject repair node |

**Soft wait loop (spec):**
```
❑ waiting for coder.patch
❒ waiting for coder.patch
❐ waiting for coder.patch
❏ waiting for coder.patch
⚝ ready: coder.patch
```

**Spine:**
```
agent.graph.json → embedded agent actions → soft waits → coder patches
→ verify/repair loop → completion gate → report
```

---

## 0.5.0 — Telemetry + Repair Nodes

**Status:** current repository version; resident implementation complete, extended soaks pending

**Exit capability:** LeafOS can run a supervised coding workflow from task
intake through planning, graph execution, scoped patching, verification,
bounded repair, and reporting.

Track changed line ranges. Feed failures back to repair nodes. Write telemetry
per run, support rollback metadata and node replay, and produce reproducible
failure bundles.

Local inference should remain efficient and predictable. llama.cpp optimization
is a quiet ongoing priority for startup time, memory use, and execution
consistency, without becoming a separate user-facing workflow.

**Alpha task range:** 57-68

---

## 0.6.0 — Project Templates + Hosting Foundation

Scaffold hello-C, hello-shell, and hello-Python projects from versioned
templates with README, test, and documentation gates. Establish the local
runtime adapter boundary, benchmark llama.cpp startup and throughput, detect
device capabilities, and add adaptive resource policies for high utilization
with thermal, power, and responsiveness headroom. Introduce node identity and
the supervised local hosting lifecycle.

**Alpha task range:** 69-80

---

## 0.7.0 — Nodal Deployment + Efficient Relays 𓆝

```
𓆝 secondary model reviewing patch
𓆝 lint model checking shell safety
```

Plant nodes on devices, pair them securely, advertise capabilities, route work
across reachable nodes, and relay compact task, graph, patch, and report
messages. Add bounded queues, backpressure, deduplication, reconnect handling,
and distributed brain/coder/reviewer/repair lanes.

**Alpha task range:** 81-92

---

## 0.8.0 — Continual Hosting + Dataset Export

Export run logs, task files, graphs, patches, reports, relay events, and
resource samples as versioned, redacted datasets. Add replay fixtures and
metrics for patch quality, repair success, latency, and token use. Schedule
hosting, inference, relay, and maintenance work with model cache and priority
controls.

**Alpha task range:** 93-102

---

## 0.9.0 — Stable Local Agentic Project Builder

Provide a bounded end-to-end project builder from the CLI. Select eligible
nodes by capability and policy, support handoff and resume, enforce action
limits, diagnose unhealthy services, and roll back runtime upgrades. Validate
the system with sustained high-utilization hosting, relay efficiency, thermal,
responsiveness, and failure-recovery tests.

**Alpha task range:** 103-114

---

## 1.0.0 — LeafOS Base System

LeafOS local agentic coding CLI environment and automatic hardware layer
completed. Stable API. Documented. Tested. Boring in the right way.

---

## Symbol legend

```
𔓘  root / identity / system origin
🍃  active runtime
❦   node selected / work order
⋆   model action generated
𓂃  shell/write action performed
❑❒❐❏  soft wait loop active
⚠︎  warning/error (yellow/red)
⚝   verified (checks passed)
⎙   report / export
ꕤ   checkpoint (after verification)
𓆝  multi-agent lane (0.7.0+)
```
