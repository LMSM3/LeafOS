# Reliable Persistent Coding Loop: 0.5 and 0.6

**Status:** finalized design

**Scope:** LeafOS 0.5 and 0.6

## Decision

LeafOS should follow two connected ideas:

1. **Reliable Persistent Loop:** make every coding task resumable, scoped,
   verifiable, repairable, and explainable.
2. **CPU Control Plane and Accelerator Workers:** keep authority, state, and
   writing on the CPU side while GPU/NPU models perform bounded proposals.

The first idea is the product spine. The second is the execution architecture
that becomes visible in 0.6. This keeps the system useful before it becomes
distributed or hardware-heavy.

The governing rules are:

```text
No mutation without scope.
No success without evidence.
No repair without classification.
No continuation without durable state.
No accelerator authority over the filesystem.
```

## Possibility A: Reliable Persistent Loop

This is the primary release path. A task becomes a durable engineering run:

```text
intent
  -> task record
  -> execution graph
  -> parser and policy checks
  -> scoped patch proposal
  -> patch validation and apply
  -> verification gates
  -> failure classification
  -> bounded repair
  -> checkpoint and report
```

### 0.5: Reliable Persistent Loop

0.5 closes the existing graph and patch work into one supervised workflow.

It must provide:

- A persistent task record containing the objective, constraints, allowed
  paths, forbidden paths, current status, and next action.
- A graph whose node state is written before and after every action.
- A JSONL event journal for task intake, node transitions, patches, commands,
  gates, repairs, checkpoints, and completion.
- A patch manifest containing file operations, base hashes, resulting hashes,
  and scope validation.
- Verification gates with explicit commands, expected results, required or
  optional status, stdout/stderr evidence, and exit codes.
- Failure classification before any repair request.
- A bounded repair policy: same scope, no unapproved dependencies, limited
  attempts, and a clean blocked state when the budget is exhausted.
- Resume from the last valid checkpoint without repeating completed nodes.
- Markdown and JSON reports generated from recorded state.

The reference workflow should remain small and contained, such as the
wakeup-node example. It should prove the orchestration system itself rather
than introduce a large second debugging problem.

### 0.5 run layout

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

The journal is the chronological record. The checkpoint is the compact resume
record. Reports are derived views and are never the source of truth.

### 0.5 completion gate

0.5 is complete when a reference task can:

1. Start from a human task file.
2. Produce a validated graph.
3. Propose and apply only an allow-listed patch.
4. Run syntax, unit, regression, and policy gates.
5. Classify a forced failure and perform one narrow repair.
6. Resume after process interruption.
7. Produce a report that names the actual changed files and command results.

## Possibility B: CPU Control Plane and Accelerator Workers

This is the physical execution model behind the loop.

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

The useful simplification is:

```text
The CPU is the authority and durable writer.
The parser is the boundary between language and execution.
The GPU/NPU is a bounded proposal engine.
```

The CPU does not need to perform all language reasoning. It does need to own
the state machine, permissions, filesystem writes, hashes, command execution,
and final acceptance decision.

The accelerator receives structured work, not an open-ended shell session.
Its output is untrusted until the CPU parser and policy layer accept it.

### Work envelope

The internal dispatch object should be a schema-versioned JSON envelope:

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

The existing provider response contract remains stable:

```json
{
  "response_type": "patch_proposal",
  "content": "...",
  "confidence_score": "0.85"
}
```

LeafOS wraps that response with CPU-side evidence such as model identity,
work hash, latency, parser result, and acceptance status. The model response
does not directly become a filesystem mutation.

### 0.6: Replicable Local Project Factory

0.6 combines the reliable loop with a local project and runtime foundation.

It should provide:

- Versioned project templates for hello-C, hello-shell, and hello-Python.
- A template manifest containing source files, build commands, tests, gates,
  allowed repair scope, and completion criteria.
- `project new` followed by the same task, patch, gate, repair, and report loop.
- A runtime adapter boundary for llama.cpp and future providers.
- Hardware and runtime capability detection.
- Node identity and a supervised local hosting lifecycle.
- Resource policy with responsiveness, thermal, and power headroom.
- A content-addressed project snapshot format ready for later replication.

The actual multi-node relay remains a 0.7 concern. In 0.6, LeafOS should make
replication possible to verify without requiring a network service.

### 0.6 completion gate

0.6 is complete when LeafOS can:

1. Create a versioned project from a template.
2. Record the template, source snapshot, graph, patches, gates, and report.
3. Select a valid local runtime based on detected capabilities.
4. Run the project workflow through the CPU control plane.
5. Resume the workflow from disk.
6. Reconstruct the same project identity from the same canonical inputs.
7. Refuse a stale patch whose base tree hash no longer matches.

## Persistence model

Persistence means that a state transition is recorded before the next side
effect depends on it.

For each transition:

```text
validate input
  -> append event
  -> flush and sync journal
  -> perform side effect
  -> append result event
  -> atomically update checkpoint
```

Snapshots use write-to-temporary-file followed by an atomic replace. The
implementation should use the Python standard library on the critical path,
matching the existing node doctrine.

An event contains a sequence number, event type, run and task identifiers,
payload, timestamp, and the hash of the previous event. The timestamp is
evidence, not identity. The previous-event hash detects missing or reordered
history without pretending that wall-clock time is deterministic.

## Near-deterministic identity and replication

The first implementation should use SHA-256 from the standard library. A
source tree identity is calculated from a canonical manifest:

- root-relative paths sorted by UTF-8 byte order;
- explicit file type and operation metadata;
- file bytes preserved exactly for the byte-level identity;
- generated runs, caches, model weights, and build directories excluded by
  the manifest unless explicitly included;
- no timestamps, hostnames, temporary paths, or process identifiers in the
  content identity.

The important identities are:

```text
source_tree_hash = canonical source manifest and file contents
task_hash        = canonical task record
graph_hash       = canonical execution graph
patch_hash       = patch bytes and patch manifest
gate_hash        = command, declared environment, and captured result
run_hash         = ordered hashes of accepted run artifacts
```

This is near-deterministic, not a claim of perfect reproducibility. Toolchain
versions, operating systems, line endings, model sampling, and external data
can still change behavior. Those belong in a separate execution fingerprint.

The hash layer supports:

- stale-base detection before patch application;
- resume after interruption;
- deduplication of repeated snapshots;
- transfer of only missing artifacts in a future relay;
- audit of whether two machines began from the same source;
- replay fixtures and cache keys.

It does not by itself prove that two executions behaved identically.

## Final release shape

```text
0.5  Reliable Persistent Coding Loop
     task records, graph state, scoped patches, gates, repair, journal,
     checkpoints, hashes, and evidence-based reports

0.6  Replicable Local Project Factory
     templates, project identity, runtime adapter, hardware-aware local
     hosting, and replication-ready snapshots

0.7  Nodal Deployment and Relays
     actual multi-node transfer, routing, deduplication, reconnect, and
     distributed worker lanes
```

This gives LeafOS a clear identity: a file-backed engineering runtime in which
human intent is converted into bounded changes, and every claim of success is
backed by durable evidence.
