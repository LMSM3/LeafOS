# LeafOS Version Staging Plane

**Status:** active release-control document

**Reconciled:** 2026-07-16

**Purpose:** one operational view of LeafOS versions, evidence, architecture,
promotion gates, and the next implementation sequence.

This file is the staging plane, not a replacement for detailed work orders or
source documentation. It answers one question first:

> What is real, what is staged, what is planned, and what evidence promotes it?

## Release position

LeafOS has two version identities that must not be confused:

| Identity | Current value | Meaning |
| --- | --- | --- |
| Root package | `0.2.1` | Current two-surface root packaging and handoff state |
| Release target | `0.9.1` | Alpha release-train target; not a capability claim |
| Taskpack | `0.5.0` | Functional CLI/taskpack version |
| Graph contract | `0.3.0` | Version of the graph object and graph-layer smoke test |

The root version is not proof that the 0.6 functional capability is complete.
Functional promotion is controlled by the gates below.

The current checkout is missing the delegated taskpack entrypoints
`ProjectLeaf/leafos_taskpack/bin/leafctl` and
`ProjectLeaf/leafos_taskpack/bin/leafctl.ps1`. The stage table records the
release plan and prior evidence; it does not assert that this incomplete
checkout can currently execute the full CLI.

## Stage summary

| Stage | Capability | Status | Promotion evidence |
| --- | --- | --- | --- |
| 0.2 | Universal CLI task pipeline | PROVEN | `tests/spine.sh` completion gate |
| 0.3 | Brain model and dependency graph | GRAPH GATE PASSED | `tests/graph.sh`: 17 passed, 0 failed |
| 0.4 | Embedded actions, waits, patches | STAGED DEPENDENCY | Patch and repair gates still required |
| 0.5 | Reliable persistent coding loop | DESIGN FINAL | End-to-end resumable reference run required |
| 0.6 | Replicable local project factory | DESIGN FINAL | Template, runtime, hash, and hosting gates required |
| 0.7 | Nodal deployment and relays | PLANNED | Multi-node transfer and recovery evidence |
| 0.8 | Continual hosting and dataset export | PLANNED | Export, redaction, replay, and sustained-run evidence |
| 0.9 | Stable local project builder | PLANNED | Full bounded project-builder acceptance suite |
| 1.0 | LeafOS base system | FUTURE | Stable API, documented release, complete test matrix |

The immediate implementation plane is 0.4 through 0.6. The release spine is
0.5. The local hosting and hardware work in 0.6 is an execution substrate for
the reliable loop, not a separate product direction.

## Evidence ledger

### 0.3 graph layer: real result

The following result was supplied as real execution evidence for the graph
layer:

```text
tests/graph.sh - 0.3.0 graph layer

graph_init                         PASS
graph_add_node                     PASS
graph_node_status                  PASS
graph_next_ready                   PASS
graph_set_status and dependencies  PASS
graph_has_pending                  PASS
brain_generate_graph               PASS
gate_print                         PASS
gate_run empty gate                PASS

17 passed   0 failed
tests/graph.sh PASSED
```

The evidence proves the graph smoke path, including graph creation, dependency
resolution, brain-generated nodes, and completion-gate execution. It does not
by itself prove the 0.4 patch path or the 0.5 persistent repair loop.

The captured run reported this work directory:

```text
/mnt/c/R/LeafOS0.2.1/ProjectLeaf/leafos_taskpack
```

A fresh verification against the current checkout also passed on 2026-07-16:

```text
command: bash ProjectLeaf/leafos_taskpack/tests/graph.sh
workdir: /mnt/c/Users/liamm/OneDrive/Documents/LeafOS/ProjectLeaf/leafos_taskpack
result: 17 passed, 0 failed
status: tests/graph.sh PASSED
```

The current workspace is the Windows checkout at:

```text
C:\Users\liamm\OneDrive\Documents\LeafOS
```

The distinction is recorded because execution evidence must always identify
the source tree and environment from which it was produced.

### Existing evidence families

| Evidence | What it proves |
| --- | --- |
| `tests/spine.sh` | 0.2 task intake, route, dry-run, run, and report pipe |
| `tests/graph.sh` | 0.3 graph CRUD, dependency readiness, brain graph, and gate smoke path |
| Wakeup-node work order | Contained runtime fixture with structured output and degraded optional data behavior |
| Model download throughput work order | Explicit download boundary, acceleration controls, throughput reporting, and verification |
| Node tests | File-backed local/SSH task transport contracts and JSONL result flow |
| Reports and run directories | Historical execution artifacts and operator-facing summaries |

Evidence precedence is:

```text
captured test or run artifact
  > accepted work-order result
  > implementation documentation
  > roadmap intention
  > conceptual proposal
```

No version is promoted from prose alone.

## System doctrine

LeafOS remains:

- local-first;
- CLI-first;
- file-backed;
- audit-first;
- explicit about planning versus execution;
- conservative about downloads and filesystem mutation;
- usable on Windows, Bash, WSL, and small LAN nodes;
- Python-stdlib-only on the critical node path.

The stable operating model is:

```text
files are the state carrier
CLI is the control surface
JSON and JSONL are the interchange contracts
SSH is the node transport
GPU/NPU models are workers
CPU-side validation is authority
```

## Architecture map

```text
Root surfaces
  PowerShell-Version/       Windows entry surface
  Bash-Version/             Bash entry surface
  ProjectLeaf/              preserved implementation tree

Taskpack
  bin/                      command surface
  core/agent/               task and action orchestration
  core/graph/               graph state and dependency logic
  core/patch/               validate and apply boundary
  core/verify/              completion and verification gates
  core/runtime/             runtime/provider adapters
  core/node/                local node identity and task receiver
  core/remote/              SSH/SCP/local distribution
  core/net/                 node discovery and LAN helpers
  core/ui/ and core/web/    read-only local status surfaces
  config/                   runtime, orchestration, and model policy
  tasks/ and runs/          task inputs and durable execution state
  reports/                  derived human-readable reports

Model installer
  ProjectLeaf/leaf_model_installer/
                            catalog, planning, explicit apply, verification
```

The root wrappers delegate to the preserved taskpack. They should not grow a
second implementation of task, graph, patch, node, or model logic.

## Version planes

### 0.2: universal CLI task pipeline

```text
agent-task
  -> agent-route --mock
  -> agent-dry-run
  -> agent-run --yes
  -> agent-report
```

0.2 is the proven command spine. It establishes guarded execution, plan files,
reports, doctor checks, and the separation between preview and apply.

### 0.3: brain model and agent graph

```text
agent-task
  -> agent-brain
  -> agent.graph.json
  -> agent-loop
  -> agent-gate
  -> agent-report
```

The graph is the continuous record of a task. It must remain inspectable,
dependency-aware, bounded, and resumable.

The 0.3 contract includes:

- graph version and goal;
- nodes with stable IDs and statuses;
- explicit dependencies;
- ready-node resolution;
- completion gates;
- required files and commands;
- forbidden paths;
- graph validation and deterministic ordering as the contract matures.

The supplied `tests/graph.sh` result is the current real gate evidence.

### 0.4: embedded actions, waits, and coder patches

0.4 is the implementation bridge required before the complete 0.5 loop.

Required capabilities:

- embedded action dispatch;
- bounded soft waits;
- coder output as a unified diff or equivalent patch artifact;
- patch scope validation;
- patch preview and explicit apply;
- verification-node execution;
- repair-node creation;
- clean blocked state after limits are reached.

0.4 must preserve the existing graph contracts. It should not introduce an
unbounded autonomous loop.

### 0.5: reliable persistent coding loop

0.5 is the primary product milestone. A complete run is:

```text
intent
  -> durable task
  -> execution graph
  -> parser and policy checks
  -> scoped patch proposal
  -> patch validation and apply
  -> verification gates
  -> failure classification
  -> bounded repair
  -> checkpoint and report
```

#### 0.5 required records

```text
runs/<task-id>/
  task.json
  graph.json
  journal.jsonl
  source-manifest.json
  source-tree.hash
  patches/
  gates/
  commands/
  checkpoint.json
  report.md
  report.json
```

#### 0.5 required behavior

- Every task has objective, constraints, allowed paths, forbidden paths,
  status, and next action.
- Every graph transition is written before dependent side effects.
- Every patch records its base tree and changed-file hashes.
- Every required gate records command, environment policy, result, and
  captured output hashes.
- Failures are classified before repair is requested.
- Repairs stay within the original allowed scope and retry budget.
- A process interruption can resume from the last valid checkpoint.
- Reports are generated from recorded state rather than model narration.

#### 0.5 completion gate

The reference task must demonstrate:

1. task intake and validated graph creation;
2. allow-listed patch proposal and application;
3. syntax, unit, regression, and policy gates;
4. a forced failure with correct classification;
5. one narrow repair within budget;
6. interruption and resume;
7. a report naming actual files and command results.

### 0.6: replicable local project factory

0.6 combines reliable task execution with project creation and local runtime
hosting.

Required capabilities:

- versioned hello-C, hello-shell, and hello-Python templates;
- template manifest with source, tests, build, gates, repair scope, and
  completion criteria;
- `project new` using the same task/graph/patch/gate/report loop;
- runtime adapter boundary for llama.cpp and future providers;
- hardware and runtime capability detection;
- node identity and supervised local hosting lifecycle;
- adaptive resource policy with responsiveness, thermal, and power headroom;
- content-addressed project snapshots ready for later relay.

Actual multi-node transfer belongs to 0.7. The 0.6 requirement is that a
project can be identified, snapshotted, verified, resumed, and prepared for
replication without a network daemon.

#### 0.6 completion gate

1. Create a versioned project from a template.
2. Record the template, source snapshot, graph, patches, gates, and report.
3. Select a valid local runtime from detected capabilities.
4. Run the project workflow through the CPU control plane.
5. Resume the workflow from disk.
6. Reconstruct the same project identity from the same canonical inputs.
7. Reject a stale patch whose base tree hash no longer matches.

### 0.7 through 1.0

```text
0.7  nodes, pairing, relays, bounded queues, deduplication, reconnects
0.8  continual hosting, redacted dataset export, replay, run metrics
0.9  stable local project builder and full recovery workflow
1.0  stable LeafOS base system and documented API
```

These stages depend on the 0.5 journal/checkpoint contracts and the 0.6
snapshot identity. They should not invent a second state model.

## CPU, parser, GPU/NPU plane

The simple execution model is:

```text
human text or code
  -> CPU intake and parser
  -> typed work object
  -> graph, scope, and policy checks
  -> GPU/NPU model request
  -> model proposal
  -> CPU response parser
  -> validation
  -> accepted artifact or rejection
  -> journal and checkpoint
```

The CPU is the authority and durable writer. The parser is the boundary
between language and execution. The accelerator is a bounded proposal engine.

The model must never directly mutate the graph, filesystem, task state, or
node registry. It returns a proposal. CPU-side schema, scope, policy, and
verification layers decide whether that proposal becomes an accepted artifact.

The internal work envelope is:

```json
{
  "schema": "leafos.work/0.5",
  "work_id": "work-001",
  "run_id": "task-20260716-001",
  "kind": "inspect|plan|patch|verify|repair",
  "input_hash": "sha256:...",
  "allowed_paths": ["examples/WO-004-C/**"],
  "payload": {}
}
```

The existing provider response remains compact and stable:

```json
{
  "response_type": "patch_proposal",
  "content": "...",
  "confidence_score": "0.85"
}
```

LeafOS adds model identity, work hash, latency, parser result, and acceptance
status on the CPU side.

### Model role boundary

| Role | Current policy |
| --- | --- |
| Main and scheduler | Opus-class assistant pool |
| Coder | `gemma4-coder` / Forge; coding-only |
| Deeper planning | Oracle-style reasoning fallback when explicitly allowed |
| Experimental heavyweight | Guarded Titan class; explicit opt-in |
| Reviewer and hardcheck | Confidence- and failure-triggered worker tiers |

Coder workers remain persona-neutral and cannot become the main scheduler.

## Persistence plane

Persistence means a state transition is durable before the next side effect
depends on it:

```text
validate input
  -> append event
  -> flush and sync journal
  -> perform side effect
  -> append result event
  -> atomically update checkpoint
```

Each event carries sequence number, event type, task/run IDs, payload,
timestamp, and the previous event hash. The timestamp is evidence, not
identity. The previous-event hash detects missing or reordered history.

Snapshots use a temporary file followed by atomic replacement. Critical node
code continues to use the Python standard library only.

## Hash and replication plane

Initial hashing uses standard-library SHA-256. A source identity is calculated
from a canonical manifest:

- root-relative paths sorted by UTF-8 byte order;
- explicit file type and operation metadata;
- exact file bytes for byte-level identity;
- generated runs, caches, model weights, and build directories excluded unless
  explicitly included;
- no timestamps, hostnames, temporary paths, or process IDs in content identity.

The identities are:

```text
source_tree_hash = canonical source manifest and file contents
task_hash        = canonical task record
graph_hash       = canonical execution graph
patch_hash       = patch bytes and patch manifest
gate_hash        = command, declared environment, and captured result
run_hash         = ordered hashes of accepted run artifacts
```

This is near-deterministic, not perfect reproducibility. Toolchain versions,
operating systems, line endings, model sampling, and external data belong in
a separate execution fingerprint.

The hash plane enables stale-base rejection, resume, deduplication, partial
artifact transfer, source equality checks, replay fixtures, and cache keys.
It does not prove that two executions behaved identically.

## Persistence and node state

The file-backed node state remains:

```text
inbox -> queued -> running -> done
                    \------> failed
```

The stable node contracts remain:

- `node.json` for local identity and capabilities;
- `nodes.json` for the driver registry;
- state directories for queue truth;
- JSONL logs for event streams;
- `result.json` for terminal task results;
- SSH/SCP and local transport for current distribution.

No daemon or HTTP control API is required for the core node path. HTTP remains
appropriate for optional LAN package distribution.

## Promotion rules

A stage may move from STAGED to PROVEN only when all of these exist:

1. Versioned schemas and contracts.
2. A passing automated gate from the target source tree.
3. A durable run or report artifact identifying inputs and environment.
4. Evidence of forbidden-path and scope enforcement.
5. Failure-path evidence, not only the happy path.
6. Resume or recovery evidence where the stage claims resumability.
7. Documentation updated to match observed behavior.

The promotion record should state:

```text
stage:
source_tree_hash:
command:
result:
artifacts:
known_limits:
promoted_by:
date:
```

## Next implementation sequence

1. Preserve the recorded 0.3 graph result and reconcile any remaining graph
   checklist items against the current checkout.
2. Complete 0.4 patch validation, explicit apply, soft waits, and repair-node
   behavior.
3. Implement the 0.5 run directory, JSONL journal, checkpoint, source hash,
   failure classifier, bounded repair, and derived reports.
4. Validate the 0.5 loop with the contained wakeup-node reference workflow.
5. Implement 0.6 templates, runtime adapter, capability detection, node
   lifecycle, resource policy, and content-addressed snapshots.
6. Defer actual relay and multi-node replication to 0.7, using the 0.5/0.6
   hash and journal contracts as the foundation.

## Canonical document map

| Concern | Canonical source |
| --- | --- |
| Release staging | `docs/releases/STAGE.md` |
| Root identity and surfaces | `README.md`, `VERSION`, `leafos.root.json` |
| Alpha task checklist | `docs/releases/ALPHA.md` |
| 0.2 CLI pipeline design | `docs/design/CLI_PIPELINE_0.2.md` |
| Functional version roadmap | `ProjectLeaf/leafos_taskpack/ROADMAP.md` |
| Taskpack architecture | `ProjectLeaf/leafos_taskpack/docs/ARCHITECTURE.md` |
| 0.5/0.6 finalized design | `ProjectLeaf/leafos_taskpack/docs/design/RELIABLE_CODING_LOOP_0.5_0.6.md` |
| Graph execution | `ProjectLeaf/leafos_taskpack/docs/ORCHESTRATION_0.3.md` |
| Node and transport contracts | `ProjectLeaf/leafos_taskpack/docs/NODES.md`, `NETWORKING.md`, `LAN_ACCESS.md` |
| Runtime and model policy | `ProjectLeaf/leafos_taskpack/config/`, `MODEL_INSTALLATION.md`, `ProjectLeaf/leaf_model_installer/` |
| Work-order evidence | `ProjectLeaf/leafos_taskpack/docs/work-orders/`, `docs/WO-*.md` |
| Automated proof | `ProjectLeaf/leafos_taskpack/tests/` |
| Historical execution evidence | `ProjectLeaf/leafos_taskpack/runs/`, `reports/`, and root reports |

When another document describes an intention that conflicts with an accepted
test or run artifact, this staging plane records the discrepancy and the
artifact wins.

## Final identity

LeafOS is a file-backed engineering runtime that converts human intent into
bounded code changes and verification evidence.

```text
No mutation without scope.
No success without evidence.
No repair without classification.
No continuation without durable state.
```
