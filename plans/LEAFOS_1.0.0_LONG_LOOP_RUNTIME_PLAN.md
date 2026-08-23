# LeafOS 1.0.0 Plan — Long-Loop Agent Runtime

**Stage:** 1 of 2  
**Status:** Active — Phases A–D complete; Phase E implementation verified and six-hour soak running  
**Effective date:** 2026-08-19  
**Starts from:** LeafOS Alpha 0.2.4 reduced core  
**Ends at:** LeafOS 1.0.0 🌿  
**Design authorities:** the supplied *LeafOS 1.0 — Long-Loop Agent Runtime* brief and the supplied CCIS/Muse ideal-design diagram; current implementation view: [`docs/leafos-runtime-diagram.html`](../docs/leafos-runtime-diagram.html)

## Outcome

LeafOS 1.0.0 will preserve the trustworthy 0.2.4 model path and add one bounded,
recoverable control plane for long-running agent work:

```text
primary agent
    -> leafctl
    -> one shared objective and task graph
    -> 2–4 bounded local workers + one verifier
    -> evidence, patches, and test results
    -> 30-minute epoch review
    -> compact strategic packet
    -> primary agent decision
```

The primary agent remains responsible for the task. Local model output is
evidence, never project truth. A worker may propose a conclusion or patch; only
the controller's validation path can mark it accepted, and the primary agent
retains final authority.

## Non-negotiable foundation

The long-loop system is an extension of the reduced core, not permission to
rebuild the prototype zoo.

1. Keep `leafctl` as the only public control surface.
2. Keep the real execution path `GGUF -> llama.cpp -> output` intact.
3. Use packs to bind real installed models to roles; do not hard-code model
   brands into orchestration code.
4. Add a feature only after a single-worker vertical slice executes real work.
5. Persist every accepted conclusion with provenance and confidence.
6. Prefer deterministic controller code for normalization, state transitions,
   budgets, and recovery. Models advise; they do not own runtime truth.
7. Foreground interactive inference always outranks background utilization.
8. Keep the swarm small: one supervisor, 2–4 active workers, and one verifier.

## Current evidence baseline

This is the implementation starting point, not a claim that 1.0 behavior exists.

| Claim | Audit status | Evidence and consequence |
|---|---|---|
| Alpha 0.2.4 is the active LeafOS version | VERIFIED CURRENT | `VERSION:1` and `README.md:1`; recheck when the version file changes. |
| The local runtime is ready | TIME-SENSITIVE | On 2026-08-19, `leafctl status` reported llama.cpp/Vulkan on an RTX 4070, 10 usable GGUFs, 1 invalid GGUF, and active pack `viola`. Re-run `doctor` and `models scan` at every gate. |
| A real inference path is active | TIME-SENSITIVE | On 2026-08-20 all 76 tests passed in one invocation with `LEAF_TEST_MODEL` set to Viola's installed fast-lane GGUF. The same host also retained a real interrupted-generation exit and a real failed 16.81 GB model load. Recheck after model, driver, llama.cpp, or runtime changes. |
| Pack routing is real but small | VERIFIED CURRENT | `packs/viola.json` binds real IDs to `fast`, `general`, `reasoning`, `verifier`, and `writer`; the verifier artifact is distinct from the fast worker artifact. |
| Phase A–E task, scheduler, epoch, and recovery commands exist | VERIFIED CURRENT | `core/cli.py` exposes planning, deferred execution, bounded scheduler control, verification, epoch review, immutable recovery checkpoints, fault evidence, and a resumable soak; real execution and negative tests exercise them. |
| Bounded multi-worker scheduling exists | VERIFIED CURRENT | `core/control/scheduler.py` persists one-supervisor state, supports 2–4 OS-process workers plus one verifier, orders dependency-ready work, and exposes observed resource state. Nine Phase C exit tests and a real process gate passed on 2026-08-20. |
| Epoch review exists | VERIFIED CURRENT | Phase D provides `epoch status|configure|review`, immutable manifests, evidence/failure/decision/plan documents, and v2 context packets; at least two live project epochs are sealed. |
| Current state storage is sufficient for the full six-hour loop | TIME-SENSITIVE | Phase E adds boot-scoped leases, owned llama.cpp PIDs, immutable compact checkpoints, append-only prefix verification, and resource/latency telemetry. The live six-hour proof started at 02:29 PDT and remains open until its duration and epoch gates close. |
| Muse, Fable, Qwen-VL, and BGE are active named roles | UNVERIFIED | The ideal diagram names target model candidates. The current active pack proves only its real installed lane bindings. Named roles must stay disabled until scan, pack validation, and real load tests pass. |

## CCIS ideal mapped to implementable boundaries

The supplied diagram is the logical target. Its nine stages map to a small
runtime contract rather than nine independent frameworks.

| CCIS stage | LeafOS owner | Required record |
|---|---|---|
| 1. Intake and normalization | deterministic controller | objective, request, environment snapshot |
| 2. Intent and constraints | router lane + controller validation | task class, constraints, output contract |
| 3. Context builder | bounded project reader | input manifest and source hashes |
| 4. Route and plan | supervisor/planner lane | dependency graph, budgets, lane assignments |
| 5. Reasoning loop | reasoning worker | hypotheses, unknowns, proposed next action |
| 6. Skill execution loop | tool worker | command/action, exit state, artifacts, logs |
| 7. Critique and validation | verifier lane + deterministic tests | findings, contradictions, test evidence |
| 8. Judge and final decision | controller and primary agent | accepted/rejected/deferred decision |
| 9. Response and evidence | epoch/context exporter | compact packet with provenance |

The diagram's Muse roles may map to one installed model or several. Vision,
reranking, and long-form writing are optional capabilities, not 1.0 health
requirements. The runtime must degrade to the roles a validated pack can
actually execute.

## Canonical project state

Long-loop state is project-local and recoverable. Global LeafOS `logs/` remains
for runtime diagnostics; project authority lives under the selected project.

```text
<project>/.leaf/
├── state/
│   ├── objective.json
│   ├── taskgraph.json
│   ├── decisions.jsonl
│   └── scheduler.json
├── tasks/
├── epochs/
├── evidence/
├── workers/
└── context/
```

Every mutable JSON document is written atomically. Append-only records carry a
schema version, stable ID, UTC timestamp, producer, content hash, and project
root identity. A startup integrity pass must reject partial or incompatible
state loudly and recover from the last valid epoch snapshot.

### Minimum task record

```text
id, goal, owner, inputs, dependencies, budget, priority,
status, attempt, lease, evidence, confidence, output
```

Allowed status transitions are controller-owned:

```text
planned -> ready -> running -> verifying -> accepted
                              \-> retryable -> ready
                              \-> failed
                              \-> cancelled
```

A worker cannot set `accepted`. Acceptance requires a verifier record or an
explicit primary-agent decision.

### Minimum evidence record

```text
id, task_id, producer, kind, source, command, exit_code,
artifact_path, artifact_hash, observed_at, confidence, claims
```

Evidence paths must resolve inside the selected project or an explicitly
declared read-only source. Secrets, credentials, caches, and ignored runtime
state are excluded by default.

## Agent-facing command contract

Keep the operating vocabulary small:

```text
leafctl status
leafctl swarm plan
leafctl swarm status
leafctl swarm run
leafctl swarm foreground
leafctl swarm stop
leafctl task submit
leafctl task inspect <task-id>
leafctl epoch review
leafctl context export
```

One essential recovery operation may be added as `leafctl swarm stop`; it must
perform a clean, bounded shutdown and preserve resumable state. JSON output is
the stable machine interface. Human output stays compact.

Command responsibilities:

- `swarm plan` creates or revises the single objective and dependency graph,
  validates the active pack, and initializes sealed scheduler state.
- `swarm run` owns the supervisor lease and dispatch loop; `swarm status`
  reports slots, queue, role bindings, resources, and explicit degradation.
- `swarm foreground on|off` is the foreground inference gate; `swarm stop`
  terminates leased children and preserves resumable task state.
- `task submit` adds one bounded unit of work with inputs, dependencies, budget,
  lane, and mutation policy.
- `task inspect` returns status, current lease, attempts, evidence, confidence,
  and blockers.
- `epoch review` freezes an epoch, verifies completed work, identifies duplicate
  or disproven work, and emits the next allocation plan.
- `context export` emits only objective, current state, decisions, active work,
  new evidence, failures, unknowns, and recommended actions.

## Delivery plan

### Phase A closure checkpoint — 2026-08-19

The bounded single-worker slice now exists in `core/control/` and the same
`leafctl` surface. Current evidence:

- Project-local objective/task/evidence state is atomic, locked, integrity
  checked, and rejects partial or corrupt documents.
- `leafctl doctor` re-hashes referenced worker artifacts; context export fails
  loudly if output is missing, altered, or escapes the project boundary.
- Abandoned single-worker leases recover to `ready` or `failed` according to
  their attempt budget.
- The 14-case recovery matrix covers committed objective/task restart, live and
  dead leases, real child-process death, attempt exhaustion, artifact/evidence/
  graph/journal crash boundaries, atomic replace failure, partial/corrupt state,
  and live/dead lock behavior.
- `swarm plan`, `task submit`, `task inspect`, and deterministic `context export`
  are implemented; no decorative `epoch` or multi-worker command was added.
- A real `viola/fast` GGUF completed `task-000003` through llama.cpp/Vulkan on
  2026-08-19. The response `PHASE_A_FINAL_OK` was separated from raw process
  output, hashed, recorded as `evidence-000003`, and left `unverified` in
  `verifying` state.
- The original real-runtime unit gate passes after the capture refactor.
- Long llama.cpp prompt echoes that end in the runtime's truncation marker are
  separated from worker output and covered by a regression test.
- `task-000007` executed a real read-only analysis of `README.md` through the
  `viola/fast` GGUF. `evidence-000007` records the source path and SHA-256 plus
  an immutable matching source snapshot; the model result remains `unverified`
  in `verifying` state.
- All 40 tests pass in one invocation when `LEAF_TEST_MODEL` names the installed
  Viola fast-lane GGUF; no real-runtime test is skipped in that evidence run.

Phase A is closed. Phases B–F were still unimplemented at this checkpoint, so
`VERSION` stayed `0.2.4`.

### Phase A — Beta 0.3: persistent single-worker vertical slice

Deliver:

- Versioned schemas for the Phase A objective, task graph, evidence, and
  append-only control records. Decision, worker-pool, and epoch schemas begin
  only in the phases that execute those transitions.
- Project-root discovery plus explicit `--project` override.
- Atomic state store, journal replay, file lock, and corruption detection.
- `swarm plan`, `task submit`, and `task inspect` for one worker.
- One real task flowing through a validated pack lane and llama.cpp.
- Bounded project-local text inputs with submission hashes and immutable
  evidence snapshots.

Exit tests:

- Restart the controller at every task transition and recover the same graph.
- Reject duplicate IDs, invalid dependencies, path escape, and malformed state.
- Execute a real read-only repository-analysis task and attach source evidence.
- Run the existing real GGUF/runtime/pack gates without regression.

### Phase B — evidence, tools, and verification — complete 2026-08-19

Deliver:

- A minimal allowlisted tool executor for inspect, search, test, and artifact
  capture.
- Read-only workers by default. Mutating work uses an isolated worktree or an
  explicitly task-owned output path.
- Verifier role, confidence vocabulary, contradiction records, and acceptance
  transition.
- Controller-side loop limits for reasoning retries and tool retries.

Exit tests:

- No worker can accept its own result.
- Every accepted claim resolves to source, command, test, or artifact evidence.
- Conflicting worker claims remain visible and block automatic acceptance.
- Failed tools retain stdout/stderr, exit state, attempt number, and next action.

### Phase B closure checkpoint — 2026-08-19

- `leafctl task tool` exposes only `inspect`, literal `search`, dotted Python
  `test`, and bounded `artifact` capture. Paths must remain in the project;
  `.leaf`, Git state, logs, credentials, oversized inputs, arbitrary shell text,
  and unknown tools are rejected.
- Tool output is bounded to 256 KiB, attempt budgets are controller-enforced,
  and every run stores stdout, stderr, exit state, attempt, artifacts, and a
  next action when it fails.
- The `viola` pack now has a real `verifier` lane bound to the installed Q3_K_M
  artifact, distinct from the Q2_K fast worker artifact. The controller rejects
  a verifier lane that resolves to the worker model ID.
- Verifier prose cannot accept a task. `task accept` requires a medium/high
  independent accepting record whose claims cite successful source- or
  tool-backed evidence, no rejecting record, and no unresolved contradiction.
- `task dispute` lets the primary agent persist a semantic contradiction and
  block acceptance when structurally valid verifier output misreads its cited
  evidence.
- Live evidence retained both failure and recovery: `evidence-000008` recorded a
  failed literal search and retry action; `evidence-000010` recorded a Vulkan
  out-of-memory verifier load; `evidence-000011` recorded an incomplete JSON
  verdict without inventing success.
- `task-000008` proved the authority boundary when `evidence-000014` structurally
  accepted a false Phase A claim: the primary agent persisted
  `task-000008-contradiction-001`, and the task remains blocked.
- `task-000009` completed the positive path. The fast worker read `VERSION`, the
  controller captured deterministic inspect evidence, the distinct verifier
  cited both records, and explicit primary review created `decision-000003` and
  moved the task to `accepted` / `verified`.
- All 51 tests pass with the real fast-lane GGUF enabled; the Phase B tests cover
  every allowlisted tool, path escape, failed-output retention, attempt budgets,
  verifier independence, evidence resolution, contradiction blocking, dispute,
  acceptance, parser boundaries, and one-way phase transition.

Phase B is closed. Phases C–F were still unimplemented at this checkpoint, so
`VERSION` stayed `0.2.4`.

### Phase C — bounded swarm and resource scheduler — complete 2026-08-20

Deliver:

- One supervisor, 2–4 worker slots, and one verifier slot.
- Dependency-aware queueing, leases, heartbeats, cancellation, and retry budget.
- Observed CPU, RAM, GPU/VRAM, queue, disk, and thermal signals where the host
  exposes them.
- Scheduling priority: interactive > critical > verifier > speculative >
  compression.
- Pack-role fallback rules. Missing optional roles degrade explicitly.

No sensor value may be invented. If GPU utilization or thermal data is
unavailable, status says `unavailable` and the scheduler uses a conservative
policy. NVIDIA-specific probes may be adapters only when the executable is
actually present; the controller must not depend on them for correctness.

Exit tests:

- Independent tasks run concurrently; dependent tasks do not.
- Foreground inference preempts or throttles background work promptly.
- Killing any one worker expires its lease and requeues or fails the task once.
- Multiple workers cannot write the same task-owned artifact.

### Phase C closure checkpoint — 2026-08-20

- The 0.2.3 audit found a real resident-scheduler attempt in
  `ProjectLeaf/leafos_taskpack`, but it owned one worker and a different run
  state. Phase C reused its proven ideas—deterministic pressure policy and
  foreground observation—without copying that subsystem into the reduced core.
- `core/control/scheduler.py` persists `leafos.scheduler.v1`, enforces one live
  supervisor, supports 2–4 worker process slots plus one verifier slot, and
  orders ready work as interactive, critical, verifier, speculative, then
  compression.
- Worker and verifier processes use opaque task lease tokens and heartbeats.
  Dead or expired leases requeue or fail once according to the attempt budget;
  cancellation and `swarm stop` terminate the leased process and release
  ownership explicitly.
- The task graph lock plus an exclusive task-owner file prevents two workers
  from claiming the same task artifact. Finalization rejects a mismatched lease
  token before writing output.
- Foreground state prevents new background dispatch and promptly terminates
  speculative or compression children. Critical work is not mislabeled as
  background preemption.
- Status observes CPU, RAM, queue depth, disk capacity, and—when `nvidia-smi`
  exists—GPU utilization, VRAM, and GPU thermal state. Disk throughput and KV
  cache remain literal `unavailable` on this host; the NVIDIA adapter is not a
  correctness dependency.
- Pack roles report native, fallback, or unavailable bindings. The current
  `viola` pack resolved every Phase C role to a real installed GGUF, including a
  verifier model distinct from the fast worker model.
- All 60 tests passed with the installed Viola fast GGUF enabled and no skips.
  The Phase C cases cover two simultaneous independent leases, dependency
  blocking, priority, foreground preemption, a real killed child process,
  cancellation, ownership contention, integrity, slot bounds, and unavailable
  sensors.
- An isolated live gate ran `task submit --defer` through a scheduler-spawned
  worker process and dedicated verifier process. `evidence-000001` contains the
  real llama.cpp output `PHASE_C_SCHEDULER_OK`; `evidence-000002` is the distinct
  verifier record. No automatic acceptance occurred.
- The maintained HTML/SVG diagram was updated from aspirational named models to
  the verified Viola topology and passed responsive light/dark checks at 736 px
  and 360 px.

Phase C is closed. Phase D is now also closed; Phases E–F remain unimplemented,
so `VERSION` stays `0.2.4`.

`[N]` Open Phase D's epoch review and token-amplification packet.

### Phase D — epoch review and token amplification

Deliver:

- A configurable epoch clock with a 30-minute default and a manual review path.
- Immutable epoch manifest, evidence index, failures, decisions, and next plan.
- Deduplication and contradiction detection before summary generation.
- `context export` in stable text and JSON forms.
- Token/byte accounting for raw inputs and strategic packets.

Each packet contains:

```text
OBJECTIVE
CURRENT STATE
LAST DECISIONS
ACTIVE TASKS
NEW EVIDENCE
UNRESOLVED FAILURES
UNKNOWN / CONFLICTING
NEXT RECOMMENDED ACTIONS
PROVENANCE
```

Exit tests:

- A packet is at most 20% of the epoch's raw text size, unless the evidence set
  itself is smaller, while retaining links for every accepted decision.
- Repeated content appears once and preserves all contributing evidence IDs.
- A fresh supervising process reconstructs the objective and next action using
  only persisted state and exported context.

#### Phase D checkpoint — 2026-08-20

- `leafctl epoch status|configure|review` is the single epoch surface. The
  interval defaults to 30 minutes, early automatic reviews fail explicitly,
  and `--manual` records the override in the manifest.
- Every `epoch-NNNNNN` directory contains sealed immutable `manifest`,
  `evidence-index`, `failures`, `decisions`, `next-plan`, `context.json`, and
  stable `context.txt` records. Manifest hashes detect later tampering.
- Normalized text is deduplicated before packet generation while its source,
  task, occurrence count, and every contributing evidence ID remain linked.
  Persisted task contradictions and opposing verifier verdicts are indexed
  before the context summary is assembled.
- The packet has all required sections plus canonical byte/token accounting.
  A minimum evidence envelope defines the explicit evidence-floor exception;
  otherwise the allowed size is 20% of raw epoch input.
- Eight Phase D tests cover the clock, manual review, immutability/tampering,
  CLI shape, deduplication, contradiction ordering, the 20% gate, the evidence
  floor, and fresh-supervisor reconstruction. The full 68-test contract suite
  passed, and the installed 5.32 GB Q2_K GGUF separately passed the unskipped
  real llama.cpp inference gate.
- The live LeafOS project sealed `epoch-000001` over 17 earlier real-model and
  tool/verifier evidence records. Its evidence envelope is larger than 20% and
  is therefore reported—rather than hidden—as an evidence-floor packet.
- The README-and-seed [Verdant Quant Lab](../examples/stock-analysis-lab/README.md)
  exercised Phase D as a new project. Its epoch indexed 22 real local-model,
  tool, failure, and verifier records; retained two primary-agent disputes and
  two runtime failures; linked accepted `decision-000003`; and compressed
  120,399 raw bytes to 19,728 packet bytes (16.39%).
- The stock workload intentionally exposed trust/recovery failures: one Windows
  command-line overflow, one Vulkan out-of-memory model load, hallucinated
  worker/verifier claims that the controller disputed, and invalid verifier
  JSON. A later independent pair succeeded only after source inspection and
  integration-test evidence were attached. No failure was rewritten as success.

Phase D is closed. `[N]` now opens Phase E's recovery and six-hour soak.

### Phase E — recovery and six-hour soak

Deliver:

- Supervisor restart, worker crash, terminal closure, model unload, and WSL
  restart recovery.
- Clean cancellation and shutdown with no orphaned worker/model process.
- Checkpoint compaction that preserves append-only audit history.
- Resource and latency telemetry for the release gates.

Exit tests:

- Six-hour mixed workload with at least two epoch boundaries.
- Inject a worker kill, controller restart, failed model load, tool failure, and
  interrupted generation.
- No accepted task is lost, accepted twice, or detached from its evidence.
- Interactive work remains responsive while useful background work is queued.

#### Phase E active checkpoint — 2026-08-20

- `core/control/recovery.py` owns one sealed `leafos.recovery-state.v1` record,
  immutable checkpoint directories, append-only stream-prefix verification, a
  fault ledger that rejects unproved pass claims, and resumable resource/latency
  telemetry. The CLI keeps these actions under `leafctl swarm` as `soak`,
  `recover`, `checkpoint`, and `fault`.
- Worker and verifier leases now include a boot-scoped host-session identity.
  A PID from an earlier Windows/WSL boot is never treated as live merely because
  the numeric PID was reused.
- Each llama.cpp child PID is bound to its task lease. Worker death, verifier
  death, cancellation, foreground preemption, and clean shutdown terminate the
  owned model process tree before releasing task ownership.
- Checkpoints seal objective, task graph, scheduler, epoch state, accepted-task
  decision/evidence links, and the exact journal/decision prefixes. Later
  append-only records do not invalidate an earlier checkpoint; tampering does.
- Eight Phase E tests cover boot restart, orphan cleanup, clean process-tree
  shutdown, checkpoint tamper detection, acceptance preservation, pause/resume,
  telemetry, the CLI surface, and rejection of self-reported fault success.
  The complete 76-test suite passed with the real Q2_K GGUF gate unskipped.
- Five required live faults now have persisted proof: controller restart
  (`resume-count:1`), worker kill (sealed lease-recovery journal record), failed
  16.81 GB reasoning-model load (`evidence-000019`), bounded tool failure
  (`evidence-000020`), and interrupted Q2_K generation (`runtime-event:172`,
  exit 130). No owned worker or llama.cpp PID remained after the stop checks.
- The six-hour run started at 02:29 PDT and is active through 08:29 PDT. It has
  already resumed across controller death, retained all five fault proofs, and
  crossed its first automatic epoch boundary. Phase E remains open until the
  duration completes, at least two epoch boundaries verify, and final recovery,
  foreground, and acceptance-invariant checks pass.

The implementation slice is verified, but the clock-dependent release evidence
is still `TIME-SENSITIVE`; do not mark Phase E complete or advance `VERSION` yet.

### Phase F — RC 0.9 interface freeze and 1.0 release

Deliver:

- Freeze CLI JSON, task/evidence/epoch schemas, and pack-role conventions.
- Publish the short upstream-agent operating contract.
- Migration test from clean 0.2.4 state and clean-install test.
- Remove experimental commands, unused adapters, fake fixtures, and duplicate
  execution paths.

No feature enters RC unless it is exercised by a real task, real model lane,
and an automated recovery or negative test.

## LeafOS 1.0.0 release gates

| Gate | Pass condition |
|---|---|
| Reduced-core regression | Real model discovery, pack validation, llama.cpp inference, interruption, and clean shutdown all pass with no skipped real-runtime test. |
| Long loop | A six-hour run crosses at least two epoch boundaries with valid state hashes and no cumulative corruption. |
| Utilization | While useful work is queued, the scheduler keeps available compute productively occupied without violating configured memory/thermal limits. |
| Foreground | Interactive work takes priority; measured latency regression stays within the declared host policy and background work yields predictably. |
| Recovery | Killing any worker does not stop the swarm; leases recover without duplicate acceptance. Controller and WSL restart resume from persisted state. |
| Context | A fresh supervisor reconstructs objective, decisions, active tasks, failures, and next action from local persisted state. |
| Verification | No accepted conclusion lacks provenance, confidence, and an independent verifier or explicit primary-agent decision. |
| Epoch | Every review emits valid summary/evidence/failure/plan artifacts and a strategic packet no larger than 20% of its raw text input. |
| Small swarm | Default concurrency never exceeds 4 active workers plus one verifier, and every slot performs graph-owned work. |
| Status | `leafctl status` remains brief and reports supervisor, epoch, queue, workers, active pack/model, resource policy, and degraded reason. |

## Explicit non-goals for 1.0.0

- Unbounded autonomous agents or self-created worker personalities.
- Cloud orchestration or provider abstraction without a working backend.
- Automatic model downloads.
- A GUI or installer framework.
- A vector database.
- Treating summaries, model prose, or worker consensus as authority.
- Requiring the diagram's named model brands for release health.
- Allowing workers to commit, publish, or cross project boundaries by default.

## Assumption ledger

| ID | Assumption | Status | Current evidence | Impact / action |
|---|---|---|---|---|
| L10-A1 | The 0.2.4 runtime is a safe base | TIME-SENSITIVE | `leafctl status` is ready and the 76-test suite passed with the real GGUF test unskipped on 2026-08-20. | Re-run the real runtime matrix at every phase exit. |
| L10-A2 | Multi-agent work was previously deferred until after 1.0 | EXPIRED | The newer user-supplied 1.0 brief explicitly defines bounded CCIS long-loop control as the 1.0 target. | Adopt the new target while retaining every reduced-core gate as a prerequisite. |
| L10-A3 | Named diagram models are installed | UNVERIFIED | No supplied scan/pack evidence binds Muse, Qwen-VL, or BGE; `viola` is the only currently validated pack. | Treat names as desired candidates, never defaults. |
| L10-A4 | Thirty minutes is the correct epoch for every workload | UNVERIFIED | Phase D ships and tests 30 minutes as a configurable default; the live gates used explicit manual reviews, not a duration study. | Measure alternate intervals during the Phase E soak before changing the default. |
| L10-A5 | More workers improve throughput | UNVERIFIED | Phase C proves two independent task leases can be live concurrently, not that this host gains useful throughput under concurrent GGUF loads. | Keep two as the default; raise concurrency only with measured throughput and foreground safety. |
| L10-A6 | Host sensors expose every scheduling signal | CONTRADICTED | Phase C observed CPU, RAM, NVIDIA GPU/VRAM, queue, disk capacity, and GPU thermal state; disk throughput and KV-cache use were unavailable. | Preserve literal `unavailable` values and conservative pressure policy. |
| L10-A7 | Worker output can safely mutate the shared checkout | CONTRADICTED | Phase C prevents duplicate task-artifact ownership, but shared-checkout mutation is still read-only by default and has no merge authority. | Isolate any later mutating work; do not broaden worker authority. |
| L10-A8 | The 0.2.3 resident scheduler already satisfies Phase C | CONTRADICTED | The historical subsystem schedules one worker in a different run-state model; it has no dependency-aware 2–4 process pool or task-owned artifact contract. | Preserve it as historical evidence only; the reduced Phase C scheduler is canonical. |
| L10-A9 | Phase E is complete because its automated tests pass | CONTRADICTED | Recovery code, eight focused tests, the 76-test real-GGUF suite, and five live fault proofs pass, but the six-hour run has not reached its deadline. | Keep Phase E active and `VERSION` at `0.2.4`; recheck after the soak completes. |

## Definition of done

LeafOS 1.0.0 is complete only when all gates pass on real installed models, a
fresh supervising process can resume a six-hour run from local state, and the
primary agent receives a compact evidence-backed packet instead of a transcript.
The release is not complete because menus appear, workers produce prose, or a
mock task graph can be serialized.
