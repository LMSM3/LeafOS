**LEAFOS MIDEND WORK ORDER**

**LeafOS-WO-046\
Layered Midend Integration and Native Authority Boundary**

*Integration contract for Branch A routes, Branch C capabilities, Branch B projections, and the native LeafOS inlet.*

| **Status** | Proposed implementation baseline |
|----|----|
| **Date** | July 26, 2026 |
| **Target** | LeafOS 0.2.1 -\> 0.3 browser modernization |
| **Authority** | CPU-authoritative native inlet; midend remains non-executing |
| **Imported source** | `IMPORTS2/LeafOS-WO-034-Layered-Integration-Native-Authority.docx` |
| **Depends on** | WO-043, WO-044, and WO-045 |
| **Unblocks** | Branded web-profile exchange, native inlet packaging, and rollout |

# **\[W\] Work Objective**

Define how the three midend layers operate as one system without duplicating authority, state ownership, validation, or evidence. This work order is the architectural integration gate for WO-043 through WO-045.

<table>
<colgroup>
<col style="width: 100%" />
</colgroup>
<thead>
<tr>
<th><p><strong>Selected composition</strong></p>
<p>A provides conventional pages and resource routes. C governs every mutation. B supplies reconstructed snapshots and live observational updates. The native inlet remains the sole authority for admission, mutation, execution, validation, durable evidence, and checkpoint commitment.</p></th>
</tr>
</thead>
<tbody>
</tbody>
</table>

browser\
\|\
+--\> A: pages + resource reads --------------------+\
\| \|\
+--\> C: capability forms + typed action requests --+--\> native inlet\
\| \| \|\
+\<-- B: snapshots + bounded live updates ----------+ +--\> executor\
+--\> validator\
+--\> evidence/checkpoint\
\|\
+--\> B rebuild

# **\[D\] System Invariants and Ownership**

| **Concern** | **Authoritative owner** | **Midend responsibility** | **Forbidden duplication** |
|----|----|----|----|
| Project/run/task state | LeafOS manifests, journals, checkpoints | serialize/project for browser | independent mutable database as truth |
| Action legality | Native inlet + policy | preflight and hide obvious illegal controls | granting capability from projected state |
| Execution | Native executor | none; submit typed controls only | shell/process/file execution |
| Validation | Native validator | display status and evidence refs | declaring success from HTTP response |
| Evidence | LeafOS evidence store/journal | index and link | creating evidence-shaped UI events |
| Sessions/CSRF/nonces | Midend session service | protect browser interaction | using session state as durable project state |
| Live UI state | Projection builder | cache/rebuild/stream | treating projection as canonical |
| Host/provider telemetry | Native facts + bounded samples | display age/confidence | changing durable run state from telemetry alone |

# **\[I\] Integrated Request and State Flows**

## 3.1 Read flow

1.  Browser requests a conventional Branch A resource route.

2.  Midend resolves the resource ID and requests the latest Branch B projection or builds one from durable evidence.

3.  Response includes projection version, source cursor, evidence references, and currently discoverable Branch C capabilities.

4.  Browser renders the page and may subscribe to bounded live updates.

5.  Refresh reconstructs the same semantic state from durable sources rather than browser memory.

GET /api/v1/runs/run_01J...\
-\> resource resolver\
-\> run_timeline projection @ v1842\
-\> capability discovery for run @ version 18\
\<- 200 {resource, projection, capabilities, evidence_refs}

## 3.2 Mutating flow

6.  Browser selects a discovered capability and submits a Branch C action envelope through a Branch A command route.

7.  Midend validates schema/session/nonce and projected preconditions, then translates the request into a native control object.

8.  Native inlet re-resolves authoritative state, policy, host facts, approval binding, target version, and replay status.

9.  If granted, the native executor performs the bounded operation; the validator determines outcome and commits evidence/checkpoint state.

10. Durable events are normalized by Branch B; the projection changes; the browser receives an observational update.

11. The original HTTP 202 means accepted for native processing, not completed execution.

POST /api/v1/runs/run_01J.../commands/pause\
-\> A route validation\
-\> C envelope validation + ControlObject\
-\> native admission: grant/deny\
-\> executor + validator + evidence\
-\> durable run.phase.changed event\
-\> B projection patch\
-\> browser state update

## 3.3 Preview and approval flow

| **Step** | **Layer** | **Required artifact** |
|----|----|----|
| Prepare request | A + C | normalized draft envelope |
| Generate preview | Native planner/inlet | immutable preview + digest + authoritative facts hash |
| Present preview | A UI | human-readable diff/plan linked to digest |
| Record approval | C request + native approval store | approval bound to capability/target/payload/preview/facts/expiry |
| Apply | Native inlet/executor | control receipt + execution journal |
| Validate and checkpoint | Native validator/state authority | validation report + evidence + checkpoint |
| Project outcome | B | reconstructed install/run/task projection |

## 3.4 Deployment topology

\[Browser\]\
\| HTTPS / loopback auth\
\[Midend process\]\
\|- route/page service (A)\
\|- capability broker/preflight (C)\
\|- projection snapshot/stream service (B)\
\|- disposable cache + session store\
\|\
\| authenticated local IPC; typed schemas only\
\[Native LeafOS inlet\]\
\|- admission/policy\
\|- state authority\
\|- executor adapters\
\|- validators\
\|- evidence/checkpoint writers

Preferred initial deployment is one midend process and one native inlet process on the same host, joined by authenticated local IPC. Process separation is not itself the security model; typed contracts, native revalidation, and authority ownership are.

## 3.5 Cross-layer contract

| **Contract item** | **A Route layer** | **C Capability layer** | **B Projection layer** | **Native inlet** |
|----|----|----|----|----|
| Versioning | API version | capability/schema version | projection/handler version | control/event schema support |
| Identity | session + request correlation | subject + nonce + approval | aggregate IDs + evidence refs | authoritative subject/policy mapping |
| State version | returns resource version | binds expected target version | projects aggregate/source cursor | checks and increments authoritative version |
| Success semantics | 200 read / 202 accepted | prepared/submitted only | observed durable outcome | grant + execute + validate + commit |
| Failure semantics | HTTP error taxonomy | denial/preflight reason | gap/resync/stale warning | authoritative denial/failure/evidence |

## 3.6 Failure isolation rules

| **Failure** | **Required system behavior** |
|----|----|
| Midend unavailable | Native LeafOS continues; browser control unavailable; no durable corruption |
| Projection builder failed | UI marks state stale/read-only; commands requiring fresh state hidden; native remains authoritative |
| Stream disconnected | Browser retains labeled stale snapshot and reconnects/resyncs; no inferred transitions |
| Native inlet unavailable | Reads may continue from durable projections; all mutations fail closed |
| Executor failed | Native validation records failure; projection shows evidence-backed failed state |
| Validator failed | Operation is not marked successful; recovery/checkpoint policy decides next state |
| Schema mismatch | Fail negotiation before control submission; do not coerce unknown versions |
| Partial durable write | Recovery replays journal/checkpoint rules; projection waits for authoritative resolution |

## 3.7 Rollout sequence

| **Phase** | **Enabled surface** | **Exit condition** |
|----|----|----|
| R0 Read-only shell | A resource pages backed by direct safe reads | stable URLs and no mutations |
| R1 Typed vertical slice | A route + C run.pause + native stub + audit | authority tests pass |
| R2 Durable run projection | B run_timeline snapshot/replay | digest determinism and refresh parity |
| R3 Live updates | SSE patches with resync | gap/reconnect tests pass |
| R4 High-risk capability | install.plan/preview/approve/apply | digest-bound approval and rollback evidence |
| R5 Profile exchange | trusted capability/profile declarations | signature/trust and compatibility tests pass |
| R6 Multi-host | host-scoped projections/capabilities/inlets | cross-host identity and authority isolation pass |

# **\[V\] Integration Acceptance Gates**

| **Gate** | **Integrated proof** | **Pass condition** |
|----|----|----|
| V1 Authority map | Trace every mutable field and side effect | Exactly one durable/native owner |
| V2 End-to-end pause | UI -\> route -\> capability -\> inlet -\> event -\> projection | 202 is distinct from evidence-backed paused state |
| V3 High-risk install | Preview -\> approval -\> apply -\> validate -\> checkpoint -\> projection | Any digest/facts change forces new preview/approval |
| V4 Fail-closed inlet | Disable native inlet and submit all mutation classes | No mutation path remains |
| V5 Projection loss | Delete disposable projection cache and rebuild | Semantic view returns from durable evidence |
| V6 Stream forgery | Inject fabricated UI patch/message | Cannot create evidence or authorize action |
| V7 Version negotiation | Mix API/capability/projection/native schema versions | Compatible pairs negotiate; incompatible pairs stop safely |
| V8 Recovery | Interrupt execution between admission, mutation, validation, checkpoint | Journal/checkpoint recovery yields classified, evidence-backed state |
| V9 Web-profile restraint | Load profile with unauthorized capabilities/routes | Untrusted declarations ignored/quarantined |

<table>
<colgroup>
<col style="width: 100%" />
</colgroup>
<thead>
<tr>
<th><p><strong>Integration completion rule</strong></p>
<p>The layered midend is accepted only when deleting the midend cache, disconnecting the browser, or replacing the frontend cannot alter durable truth, and disabling the native inlet makes every mutation impossible.</p></th>
</tr>
</thead>
<tbody>
</tbody>
</table>

# **\[P\] Integration Packages**

| **Package** | **Scope** | **Deliverable** |
|----|----|----|
| 034A | Cross-layer schemas, version negotiation, correlation IDs | midend-native contract pack |
| 034B | Read aggregation: resource + projection + capabilities | unified page DTO |
| 034C | Mutating pipeline and native disposition handling | end-to-end control adapter |
| 034D | Preview/approval/apply integration | digest-bound workflow |
| 034E | Live projection stream and command-state reconciliation | browser state coordinator |
| 034F | Failure isolation, read-only modes, stale-state UX | degraded-mode policy |
| 034G | Migration from current web-state and compatibility wrappers | incremental rollout adapters |
| 034H | End-to-end authority, recovery, and red-team suite | integration proof report |

Implementation order: complete the WO-043 vertical slice, bind it to the WO-044 dispatcher, then replace polling/direct reads with the WO-045 run projection. Do not build the full live workspace first. Humans have already invented enough distributed state bugs without volunteering for more.

# **\[N\] Completion Record and Next Action**

| **Marker** | **Record** |
|----|----|
| \[W\] | Defined the layered A -\> C -\> B composition and its native authority boundary. |
| \[D\] | Routes provide familiarity, capabilities govern mutations, projections provide responsive reads, and the native inlet owns truth and side effects. |
| \[I\] | Specified read, mutation, preview/approval, deployment, contract, failure, and rollout flows. |
| \[V\] | Nine gates prove sole authority, end-to-end evidence semantics, fail-closed behavior, rebuildability, version safety, recovery, and profile restraint. |
| \[P\] | Eight packages integrate schemas, DTOs, controls, approvals, streams, degraded modes, migration, and proof. |
| \[N\] | Execute R1: run detail -\> run.pause -\> native disposition -\> projection refresh. |
