# CCIS Inside LeafOS — Compiled Revision

## 0. What Changed Since the First Draft

The first draft treated CCIS as though LeafOS had merely grown a few validators around:

```text
inspect → edit → test → repeat
```

That is no longer the architecture. That loop survives, but only as the innermost mechanical cycle. Describing CCIS as the present-day execution engine undersells the system and accidentally makes two years of architecture look like somebody added SQLite to a Python retry loop.

The corrected relationship:

```text
CCIS
  = ancestral principle

Continual Bloom
  = lifecycle interpretation

LeafOS
  = durable work and reasoning controller

FlowerOS
  = machine execution and user environment

Flower packs
  = selectable cognitive organizations

Scientific Change Loop
  = present operational method

Garden
  = distributed lifecycle, memory, renewal, and pruning model
```

CCIS is no longer the whole loop. It is the old law still operating inside the new civilization: nothing advances merely because a model sounded pleased with itself. A surprisingly necessary constitutional provision.

---

## 1. Lineage

LeafOS did not begin as an operating system, a model pack framework, or a garden of cooperating agents. It began with a smaller and more dangerous idea:

> Code should be able to return to itself.

The first system was CCIS: the Continual Code Improvement System. It inspected an existing project, identified one bounded improvement, attempted the change, tested the result, retained what worked, and repeated. The implementation was primitive because every first implementation is primitive, despite what retrospective README files would have us believe. The central idea survived.

CCIS assumed that generated work was not trustworthy merely because it looked plausible. A change needed evidence. A failed change needed rollback. Work needed to remain bounded. Progress needed to survive beyond a conversation.

To improve code repeatedly, the system needed durable state. To preserve state, checkpoints. To accept or reject changes, validators. To coordinate models and tools, routing. To work safely, authority boundaries. To resume interrupted work, an execution history. Those requirements became LeafOS, and their eventual maturation became the Scientific Change Loop.

CCIS is therefore not an abandoned ancestor and not the modern engine. It is the smallest complete expression of what the modern loop must still guarantee.

---

## 2. The Nested Control System

The current design is a nested scientific control system:

```text
OUTER LOOP: OBJECTIVE
Define the scientific or engineering objective
→ establish units, invariants, tolerances, authority, and stopping conditions
→ inspect available context and resources
→ decide whether the objective remains valid

MIDDLE LOOP: CANDIDATE
Generate competing interpretations or interventions
→ challenge assumptions through the roundtable
→ compare expected scientific value, risk, cost, and reversibility
→ select the smallest defensible candidate
→ escalate, revise, or abandon when evidence is insufficient

INNER LOOP: IMPLEMENTATION
Inspect exact code and scientific context
→ construct a bounded change
→ build and run reproducibly
→ evaluate physics, geometry, numerics, performance, and regressions
→ preserve artifacts and uncertainty
→ accept, reject, repair, or roll back
```

The fuller operating sequence:

```text
Describe task
    ↓
Define scientific constraints and acceptance conditions
    ↓
Negotiate context, RAM, tools, and execution budget
    ↓
Select planning / inspection model or flower pack
    ↓
Inspect code, equations, provenance, and prior evidence
    ↓
Generate multiple candidate approaches
    ↓
Roundtable challenge and candidate selection
    ↓
Select implementation and review roles
    ↓
Implement the bounded candidate
    ↓
Build and run through native tools
    ↓
Evaluate:
    geometry
    physics
    numerical behavior
    performance
    regressions
    uncertainty
    ↓
Independent evidence gate
    ↓
Accept / revise / reject / escalate
    ↓
Persist state, evidence, compost, and one legal next action
```

The original CCIS loop (inspect, propose, change, test, retain or reject, repeat) is recognizable inside the inner loop. Everything above it is what two years of architecture actually bought.

---

## 3. Product Decision

LeafOS will contain an internal subsystem named `LeafOS/ccis/`, but it represents the constitutional core inherited from CCIS, not the entire modern loop.

CCIS answers exactly four narrow questions:

1. Is the proposed transition bounded?
2. Is there sufficient evidence?
3. Is the new state better, or at least defensibly safer?
4. What is the only legal next action?

Everything else — objective definition, context negotiation, candidate generation, roundtable challenge, implementation, native builds, scientific evaluation, lifecycle — belongs to the mature LeafOS architecture. CCIS is the gate every state transition must pass through, regardless of which loop, pack, or plane produced the candidate.

The first release does not need to improve itself indefinitely. It needs to complete one improvement correctly, through the full gate, with complete evidence. Then it needs to do that repeatedly.

---

## 4. Internal Layout

```text
LeafOS/
├── ccis/
│   ├── principles/
│   │   ├── bounded_change.md
│   │   ├── evidence_before_acceptance.md
│   │   ├── rollback_and_recovery.md
│   │   └── continual_improvement.md
│   │
│   ├── contracts/
│   │   ├── candidate.schema.json
│   │   ├── evaluation.schema.json
│   │   ├── decision.schema.json
│   │   └── transition.schema.json
│   │
│   └── kernel/
│       ├── transition_gate.py
│       ├── evidence_gate.py
│       ├── revision_policy.py
│       └── acceptance_policy.py
│
├── loop/
│   ├── objective/
│   ├── candidate/
│   ├── implementation/
│   └── escalation/
│
├── roundtable/
├── context/
├── packs/
├── validators/
├── evidence/
├── lifecycle/
└── runtime/
```

The directory is intentionally boring. Boring directories are easier to execute than philosophical ones. The `ccis/` subtree is small on purpose: a constitution that requires forty modules is a bureaucracy.

Durable state remains under the workspace:

```text
.leafos/
├── state.db
├── events.jsonl
├── tasks/
├── checkpoints/
├── workspaces/
└── evidence/
```

---

## 5. The Task Contract

Every request becomes a task envelope. The envelope separates the request from whatever performs it, which is what later allows distribution.

```json
{
  "task_id": "leaf-20260803-0001",
  "instruction": "Add input validation to the molecule loader.",
  "target": "C:\\Projects\\VSEPR-Sim",
  "mode": "once",
  "objective": {
    "invariants": ["all existing acceptance tests pass"],
    "tolerances": {},
    "stopping_conditions": ["budget exhausted", "objective invalidated"]
  },
  "scope": {
    "allowed_paths": ["src/molecule_loader.*", "tests/*"],
    "denied_paths": [".git/*", "build/*"]
  },
  "budget": {
    "wall_time_seconds": 3600,
    "max_iterations": 4,
    "max_changed_files": 6
  },
  "validators": ["tests", "lint", "diff_policy"],
  "authority": {
    "may_modify": true,
    "may_install": false,
    "may_merge": false
  }
}
```

The middle loop adds a candidate record; the inner loop adds an evaluation record; the CCIS gate adds a decision record; acceptance adds a transition record. Those four artifacts map one-to-one onto the four schemas in `ccis/contracts/`.

---

## 6. Runtime State Machine

Every task moves through explicit states:

```text
CREATED
   ↓
SNAPSHOTTED
   ↓
OBJECTIVE_DEFINED
   ↓
INSPECTING
   ↓
CANDIDATES_GENERATED
   ↓
CANDIDATE_SELECTED        (roundtable record required)
   ↓
MUTATING
   ↓
VALIDATING
   ↓
GATED                     (CCIS gate)
   ├── ACCEPTED
   ├── REVISE
   ├── REJECTED
   ├── BLOCKED
   └── ESCALATED
```

A state transition must produce an event:

```json
{
  "event_id": "evt-0092",
  "task_id": "leaf-20260803-0001",
  "from": "MUTATING",
  "to": "VALIDATING",
  "worker_id": "local-edit-01",
  "timestamp": "2026-08-03T09:14:00-07:00",
  "artifact_hash": "sha256:...",
  "reason": "Candidate patch produced"
}
```

The event log is append-only. Current state may be cached in SQLite, but the event history is the durable record.

State outranks conversation.

---

## 7. Evidence Required for Acceptance

A candidate is not accepted because a model approves its own work. Each accepted transition must include:

```text
task.json
objective.json
candidates.json
roundtable-record.json
plan.json
workspace-manifest.json
before-hash.json
after-hash.json
candidate.diff
commands.jsonl
stdout.log
stderr.log
test-results.json
lint-results.json
evaluation.json          (geometry, physics, numerics, performance, regressions, uncertainty as applicable)
review.json
decision.json
result.json
```

The minimum acceptance rule:

```text
required validators passed
AND prohibited files unchanged
AND task limits respected
AND candidate selection recorded
AND evidence manifest complete
AND resulting project remains reproducible
```

For the first release, the gate stages accepted results and requires an explicit:

```powershell
leafos task accept <task-id>
```

Later, trusted task classes may receive automatic acceptance authority. Trust is earned by evidence history, not asserted by configuration.

---

## 8. Distributed Model

The distributed system does not merely distribute inspector, editor, and test workers. It distributes roles within the nested loop while preserving centralized authority over state transitions.

```text
                         LEAFOS CONTROL PLANE
              objective · policy · state · authority
                               │
             ┌─────────────────┼─────────────────┐
             ▼                 ▼                 ▼
      CONTEXT PLANE      REASONING PLANE      EXECUTION PLANE
      retrieval          planner              builders
      provenance         roundtable           compilers
      RAM negotiation    critics              simulators
      condensation       scientific judges    native validators
             │                 │                 │
             └─────────────────┼─────────────────┘
                               ▼
                        EVIDENCE PLANE
             artifacts · hashes · logs · metrics
                               │
                               ▼
                          CCIS GATE
              accept · revise · reject · escalate
                               │
                               ▼
                       LIFECYCLE PLANE
           persist · checkpoint · compost · regrow
```

Distributable: workers, roundtable roles, context assembly near the models that need it, simulations on specialized nodes, content-addressed and replicated evidence.

Authoritative, and therefore centralized:

* the task state
* the declared objective
* acceptance conditions
* authority boundaries
* candidate selection record
* evidence manifest
* final state transition
* exactly one legal next action

There is initially one authoritative control plane. Multiple coordinators introduce consensus, leader election, split-brain behavior, and several other delightful ways to destroy a weekend.

### 8.1 Worker Nodes

A worker registers its capabilities:

```json
{
  "worker_id": "gpu-node-02",
  "capabilities": {
    "models": ["coder", "reasoner"],
    "tools": ["git", "pytest", "cmake"],
    "platform": "linux",
    "gpu_vram_gb": 12,
    "ram_gb": 48
  }
}
```

Workers are disposable. If one disappears, the coordinator waits for the lease to expire and reassigns the job. Workers return evidence; they do not decide global truth.

### 8.2 Artifact Store

Large data does not travel through the job queue. Workers exchange references to content-addressed artifacts (`sha256:...`). First implementation:

```text
.leafos/objects/ab/cdef...
```

Later, a shared network directory or S3-compatible store. The contract does not change.

### 8.3 Transport

Replaceable by design:

```text
Phase 1: local in-process queue
Phase 2: filesystem queue
Phase 3: SSH or HTTP workers
Phase 4: message broker
```

A filesystem queue (`pending/ leased/ completed/ failed/`, atomic moves, lease records) is sufficient to prove distribution. Crude systems that work are more valuable than sophisticated systems presented exclusively through diagrams.

---

## 9. Safety Rules

Enforced from the beginning, not retrofitted:

* **Idempotency.** Every job has a stable identifier. Repeating a job must not produce conflicting state transitions.
* **Leases.** Claimed jobs expire. Dead workers do not hold tasks hostage.
* **Immutable inputs.** Workers receive snapshots and hashes. They never touch the authoritative repository.
* **Single merge authority.** Only the control plane, through the CCIS gate, applies an accepted patch to the canonical project.
* **Hashed results.** A worker result that does not match its manifest is rejected.
* **Append-only events.** Workers propose; the coordinator records.
* **Capability boundaries.** A test worker does not need install authority. A review worker does not need write access. Ordinary engineering discipline, which naturally makes it appear radical in agent software.

---

## 10. Implementation Sequence

**Milestone 1: Local loop through the gate.** One repository, one worker process, one model lane, one validator set, explicit acceptance, complete evidence bundle. The nested loop may be degenerate (one objective, one candidate) but every state and artifact must be real. Do not begin distribution until this works repeatedly.

**Milestone 2: Worker separation.** Inspection, editing, validation, and roundtable roles in separate processes, same contracts, filesystem queue. Killing and restarting a worker must not destroy the task.

**Milestone 3: Second machine.** One remote worker over SSH or a small authenticated HTTP service. Artifact references in, results and released lease out. The gate stays local.

**Milestone 4: Resource-aware scheduling.** Model availability, CPU and GPU limits, tool availability, worker trust levels, priority, estimated cost, timeouts. This is where flower packs become meaningful as capability and cognitive-organization bundles rather than decorative personalities.

**Milestone 5: Continual operation.**

```powershell
leafos please `
  "Improve the VSEPR simulation while preserving all acceptance tests." `
  "C:\Projects\VSEPR-Sim" `
  viola `
  --budget 8h
```

The eight-hour mode is not one uninterrupted model conversation. It is a sequence of bounded tasks, each passing the gate, each leaving the project in a recoverable state. This is Continual Bloom operating under CCIS law.

---

## 11. Definition of Shipped

The system is shipped when the dev team can demonstrate the following without editing state files by hand:

1. Submit a bounded improvement request.
2. Interrupt the process during execution.
3. Restart LeafOS.
4. Resume from the last valid checkpoint.
5. Inspect the complete evidence bundle, including the candidate selection record.
6. Reject the candidate and restore the original state.
7. Run the same request on a remote worker.
8. Obtain the same task record, gate behavior, and one legal next action.

That demonstration matters more than version numbers, model counts, naming systems, dashboards, or speculative architecture.

---

## 12. Closing Direction

CCIS should not be rebuilt as it originally existed, and it should not be mistaken for the modern loop. Its purpose should be rebuilt clearly, as law:

```text
One request.
One bounded task.
One isolated change.
One evidence bundle.
One acceptance decision.
One recoverable state.
```

The nested loops, the roundtable, the planes, the packs, and the Garden are how LeafOS generates and evaluates work. CCIS is why any of that work is allowed to become real.

LeafOS does not need to prove that it can imagine an entire operating architecture. It needs to prove that it can improve one real project, safely, repeatedly, and with evidence. Once it can do that locally, the same contracts carry the work across processes, machines, model packs, and eventually the entire Garden.

The project began with continual improvement. The next release should finally ship it.

