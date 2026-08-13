**LEAFOS MIDEND WORK ORDER**

**LeafOS-WO-045\
Durable Event Projection and Live Workspace**

*Disposable UI projections rebuilt from durable LeafOS journals, checkpoints, manifests, and bounded telemetry.*

| **Status** | Proposed implementation baseline |
|----|----|
| **Date** | July 26, 2026 |
| **Target** | LeafOS 0.2.1 -\> 0.3 browser modernization |
| **Authority** | CPU-authoritative native inlet; midend remains non-executing |
| **Imported source** | `IMPORTS2/LeafOS-WO-032-Event-Projection-Live-Workspace.docx` |
| **Depends on** | WO-043 reads plus the WO-044 `run.pause` vertical slice |
| **Unblocks** | WO-046 live integration and degraded projection modes |

# **\[W\] Work Objective**

Design the Branch B projection system that converts durable LeafOS evidence into responsive browser views while preserving journals, manifests, checkpoints, and validated artifacts as the only durable truth.

<table>
<colgroup>
<col style="width: 100%" />
</colgroup>
<thead>
<tr>
<th><p><strong>Primary decision</strong></p>
<p>The browser receives an initial snapshot and bounded incremental notifications. Projection state is disposable. Rebuild from durable evidence must reproduce the same semantic view, apart from explicitly volatile telemetry windows.</p></th>
</tr>
</thead>
<tbody>
</tbody>
</table>

# **\[D\] Source-of-Truth Boundary**

- Journals and checkpoint records define run/task transitions and approval history.

- Project and profile manifests define durable configuration and compatibility facts.

- Validated reports define publishable output; a projection cannot promote an unvalidated artifact.

- Hardware/provider telemetry is sampled, bounded, and labeled volatile; it cannot overwrite durable run facts.

- Projection checkpoints accelerate rebuilds but are caches, not evidence.

- SSE/WebSocket messages are notifications of projected changes, never evidence events themselves.

journal + checkpoint + manifest + validated artifacts + telemetry\
\|\
v\
event normalization\
\|\
v\
projection builder\
\|\
+--------------+----------------+\
v v v\
snapshot store change stream rebuild cursor\
\| \| \|\
+--------------+----------------+\
v\
browser

# **\[I\] Projection Model**

## 3.1 Normalized event envelope

{\
"event_id": "evt_01J...",\
"event_type": "run.phase.changed",\
"schema_version": "1.0",\
"occurred_at": "2026-07-26T20:45:12.125Z",\
"recorded_at": "2026-07-26T20:45:12.131Z",\
"aggregate": {"type": "run", "id": "run_01J...", "version": 18},\
"causation_id": "ctl_01J...",\
"correlation_id": "req_01J...",\
"evidence_ref": "evidence://runs/run_01J/events/18",\
"payload": {"from": "validating", "to": "checkpointed"}\
}

Normalization adapts existing LeafOS records into a projection-safe envelope. It does not rewrite or replace the original evidence record. Each adapter must retain a resolvable evidence reference and deterministic aggregate ordering key.

## 3.2 Event-to-view mapping

| **LeafOS event family** | **Projection(s)** | **UI update** |
|----|----|----|
| project.created / manifest.updated | project summary, profile compatibility | add/update project card; refresh compatibility badge |
| run.created / phase.changed / completed | run timeline, project summary | insert run; append phase; update terminal state |
| task.created / dependency.changed | task board, run detail | add card; update blocked/ready relation |
| approval.requested / granted / denied | task board, action panel | show legal action; record operator disposition |
| artifact.created / validated / rejected | run timeline, report list | show provisional artifact; publish only after validation |
| report.published | report list, project summary | add immutable report reference |
| provider.started / stopped / unhealthy | hardware/provider status | update health state and bounded diagnostics |
| telemetry.sampled | hardware status | append bounded sample; drop outside retention window |
| install.plan.created / step.changed | installation progress | render plan digest, step state, rollback availability |
| checkpoint.committed / resume.classified | run timeline, recovery panel | mark safe resume point and classification |

## 3.3 Projection definitions

| **Projection** | **Key** | **Required fields** | **Rebuild source** |
|----|----|----|----|
| project_summary | project_id | name, manifest version, active run, health, report count | project manifest + run/report indexes |
| run_timeline | run_id | ordered phases, controls, artifacts, validation, checkpoint refs | run journal + evidence index |
| task_board | run_id | task state, dependencies, approvals, retries, owner lane | task graph + approval records |
| hardware_status | host_id | CPU/GPU/RAM/provider state, sample age, confidence | host facts + bounded telemetry |
| install_progress | plan_id | digest, approval, steps, validation, rollback state | install manifest + journal |
| report_catalog | project_id | validated report metadata and artifact refs | report manifests + validation evidence |

## 3.4 Snapshot plus change-stream protocol

1.  Client requests GET /api/v1/runs/{id}/projection and receives projection_version, source_cursor, generated_at, and state.

2.  Client opens /api/v1/streams/runs/{id}?after={projection_version}.

3.  Server emits bounded projection patches or an invalidation notice, each carrying the next projection_version.

4.  If the client misses retention, schema changes, or detects a version gap, it discards local state and requests a fresh snapshot.

5.  The command channel remains separate. A stream message cannot be echoed back as authorization or evidence.

event: projection.patch\
id: 1842\
data: {\
"projection": "run_timeline",\
"aggregate_id": "run_01J...",\
"from_version": 1841,\
"to_version": 1842,\
"patch": \[{"op":"add","path":"/phases/-","value":{"name":"validated"}}\],\
"source_cursor": "journal:run_01J:18"\
}

## 3.5 Ordering, idempotency, and rebuild rules

- Apply durable events in aggregate-version order; quarantine gaps rather than guessing.

- Deduplicate by event_id and verify payload digest before applying.

- Projection handlers are pure enough to replay: prior state + event -\> next state.

- Persist projection cursor and handler version together; handler changes trigger targeted rebuilds.

- Use tombstones for durable deletion/archive events so stale caches cannot resurrect resources.

- Telemetry uses timestamp ordering and bounded tolerance; late samples may be displayed but cannot alter durable status.

- Every projected claim that affects operator decisions carries an evidence reference or an explicit volatile label.

## 3.6 Retention and backpressure

| **Channel** | **Retention** | **Overflow behavior** |
|----|----|----|
| Durable normalized event index | Same as source evidence or durable pointer | Stop projection and flag source gap |
| Projection snapshots | Latest + previous known-good per aggregate | Rebuild when absent or incompatible |
| SSE patch buffer | Bounded by count and age | Send resync_required; client fetches snapshot |
| Telemetry samples | Short rolling window per host/provider | Drop oldest; report sample age and dropped count |
| Browser local cache | Session-scoped only | Discard on version/schema mismatch |

# **\[V\] Validation and Acceptance Gates**

| **Gate** | **Method** | **Pass condition** |
|----|----|----|
| V1 Replay determinism | Rebuild projection twice from identical evidence | Canonical projection digests match |
| V2 Gap handling | Remove aggregate version N from replay input | Projection halts/flags gap; no fabricated state |
| V3 Duplicate handling | Replay duplicate event IDs and reconnect stream | No duplicate timeline/task/report entries |
| V4 Refresh parity | Compare live UI state with fresh snapshot after activity | Semantic state matches |
| V5 Stream loss | Force buffer expiry and reconnect from old cursor | Client receives resync_required and reconstructs |
| V6 Evidence trace | Open any durable phase/report/approval claim | UI resolves original evidence reference |
| V7 Telemetry isolation | Inject stale/extreme telemetry sample | Durable run/install state unchanged |
| V8 Handler upgrade | Change projection schema/handler version | Targeted rebuild occurs before stream resumes |

# **\[P\] Implementation Packages**

| **Package** | **Scope** | **Deliverable** |
|----|----|----|
| 032A | Inventory journals/manifests/checkpoints and define adapters | event-source registry |
| 032B | Normalized event envelope and schema versions | event schemas + compatibility policy |
| 032C | Pure projection handlers and snapshot model | projection builder library |
| 032D | Snapshot endpoints and evidence links | resource projection API |
| 032E | SSE transport, retention, backpressure, reconnect | live update service |
| 032F | Telemetry adapter and volatile-state labeling | bounded hardware/provider projection |
| 032G | Replay, gap, duplicate, reconnect, and upgrade tests | determinism proof report |

First vertical slice: one run journal -\> run_timeline projection -\> snapshot endpoint -\> SSE phase update -\> browser refresh parity test. The system earns animation only after deterministic replay works, because apparently even progress bars need constitutional law.

# **\[N\] Completion Record and Next Action**

| **Marker** | **Record** |
|----|----|
| \[W\] | Defined a disposable projection layer for durable LeafOS evidence and bounded telemetry. |
| \[D\] | Branch B is observational; normalized events and streams cannot authorize or execute controls. |
| \[I\] | Specified envelopes, projection definitions, UI mappings, snapshot/stream protocol, ordering, retention, and rebuild rules. |
| \[V\] | Eight gates prove replay determinism, gap safety, refresh parity, evidence traceability, and telemetry isolation. |
| \[P\] | Seven packages build from source inventory through live transport and replay proof. |
| \[N\] | Implement 032A-032C against a recorded run journal and produce the first canonical run_timeline digest. |
