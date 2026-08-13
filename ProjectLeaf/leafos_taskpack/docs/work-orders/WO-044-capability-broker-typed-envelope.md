**LEAFOS MIDEND WORK ORDER**

**LeafOS-WO-044\
Capability Broker and Typed Action Envelope**

*Declared, state-aware user actions prepared by the midend and granted only by the native LeafOS inlet.*

| **Status** | Proposed implementation baseline |
|----|----|
| **Date** | July 26, 2026 |
| **Target** | LeafOS 0.2.1 -\> 0.3 browser modernization |
| **Authority** | CPU-authoritative native inlet; midend remains non-executing |
| **Imported source** | `IMPORTS2/LeafOS-WO-033-Capability-Broker-Typed-Envelope.docx` |
| **Depends on** | WO-043 resource and typed-command contracts |
| **Unblocks** | Native-admitted `run.pause`, then WO-045 projection generalization |

# **\[W\] Work Objective**

Define Branch C as the mandatory boundary for every mutating browser action. The midend discovers, presents, prepares, previews, and rejects capability requests; the native inlet alone grants and exercises them.

<table>
<colgroup>
<col style="width: 100%" />
</colgroup>
<thead>
<tr>
<th><p><strong>Primary decision</strong></p>
<p>No generic execute endpoint exists. Every action is represented by a named capability, versioned payload schema, explicit target, bounded preconditions, nonce, preview digest, and approval policy.</p></th>
</tr>
</thead>
<tbody>
</tbody>
</table>

# **\[D\] Capability Lifecycle and Authority**

declared -\> discovered -\> legal -\> prepared -\> previewed\
-\> approved -\> submitted -\> native granted/denied\
-\> exercised -\> validated -\> evidenced

| **Stage** | **Owner** | **Meaning** |
|----|----|----|
| Declared | Profile/schema registry | Capability ID, payload schema, policy, and native handler are known |
| Discovered | Midend | Host/profile facts indicate capability might be available |
| Legal | Midend preflight | Current projected state satisfies visible preconditions |
| Prepared | Midend | Payload normalized; target/version/nonce bound |
| Previewed | Native inlet or native planner | Exact intended mutation and plan digest produced |
| Approved | Operator/policy authority | Required approval bound to immutable digest |
| Granted/denied | Native inlet | Authoritative facts and policy evaluated |
| Exercised | Native executor | Typed native operation performed |
| Validated/evidenced | Native validator/state authority | Outcome proven and recorded |

A midend “legal” result is advisory. It controls what the UI displays and can reject obvious invalid requests, but it never guarantees the native inlet will grant the capability.

# **\[I\] Capability Model**

## 3.1 Initial capability catalog

| **Capability ID** | **Target** | **Approval** | **Native result** |
|----|----|----|----|
| project.create | host/workspace | explicit when filesystem mutation begins | ProjectCreateControl |
| project.open | project | session policy | ProjectOpenControl |
| run.start | project + plan | explicit or policy-bound | RunStartControl |
| run.pause | run | session/operator | RunPauseControl |
| run.resume | run + checkpoint | explicit when resume classification requires | RunResumeControl |
| run.cancel | run | explicit | RunCancelControl |
| task.approve | task + plan digest | explicit | TaskApprovalControl |
| task.reject | task | explicit | TaskRejectionControl |
| task.retry | task + prior failure ref | policy or explicit | TaskRetryControl |
| profile.activate | profile + host | explicit | ProfileActivateControl |
| install.plan | profile + host | session/operator | InstallPlanControl |
| install.apply | immutable install plan | explicit digest-bound | InstallApplyControl |
| install.rollback | install transaction/checkpoint | explicit | InstallRollbackControl |
| report.export | validated report | session/operator | ReportExportControl |

## 3.2 Capability declaration

{\
"capability_id": "install.apply",\
"schema_version": "1.0",\
"target_types": \["install_plan"\],\
"payload_schema_ref": "schema://capabilities/install.apply/1.0",\
"preconditions": \[\
"plan.status == 'previewed'",\
"plan.digest == request.preview_digest",\
"host.facts_hash == request.host_facts_hash"\
\],\
"approval_policy": "explicit_digest_bound",\
"native_handler": "leaf.inlet.install.apply.v1",\
"side_effect_class": "host_mutation",\
"evidence_requirements": \["control_receipt", "validation_report", "checkpoint"\]\
}

## 3.3 Action request envelope

{\
"capability_id": "install.apply",\
"schema_version": "1.0",\
"request_id": "req_01J...",\
"session_id": "ses_01J...",\
"subject": {"type": "operator", "id": "local-user"},\
"target": {"type": "install_plan", "id": "iplan_01J...", "version": 7},\
"nonce": "single-use opaque value",\
"issued_at": "2026-07-26T21:00:00Z",\
"expires_at": "2026-07-26T21:05:00Z",\
"host_facts_hash": "sha256:...",\
"precondition_hash": "sha256:...",\
"preview_digest": "sha256:...",\
"approval_ref": "approval://iplan_01J/sha256:...",\
"payload": {"mode": "apply", "restart_policy": "defer"}\
}

The envelope is canonicalized and hashed before submission. Approval binds the capability ID, target ID/version, preview digest, payload digest, host facts hash, and expiry. Any change invalidates approval.

## 3.4 Validation layers

| **Layer** | **Executed by** | **Checks** | **Can grant?** |
|----|----|----|----|
| UI form | Browser | field shape, required values, user feedback | No |
| Midend schema | Midend | strict schema, size, enum, target syntax | No |
| Midend projection preflight | Midend | projected state, visible policy, nonce/session | No |
| Native admission | Native inlet | authoritative state/version, host facts, approval, replay, policy | Yes |
| Native execution | Native executor | handler-specific preconditions and side-effect bounds | Exercises granted capability |
| Native validation | Validator/state authority | postconditions, artifacts, evidence, checkpoint | Commits outcome |

## 3.5 Capability discovery response

{\
"resource": {"type": "run", "id": "run_01J...", "version": 18},\
"projection_version": 1842,\
"capabilities": \[\
{\
"id": "run.pause",\
"schema_version": "1.0",\
"status": "available",\
"form_schema_ref": "schema://forms/run.pause/1.0",\
"requires_preview": false,\
"requires_approval": false,\
"expires_at": "2026-07-26T21:05:00Z"\
}\
\]\
}

The UI renders only returned capabilities, but hidden controls are not a security boundary. Native admission must reject unavailable, stale, forged, expired, or replayed capability requests.

## 3.6 Mandatory prohibitions

- No capability accepts arbitrary shell, PowerShell, Python, SQL, filesystem path traversal, or dynamic handler names.

- No capability declaration can be supplied by an untrusted web profile without native signature/trust validation.

- No approval may refer only to a human-readable summary; it must bind the canonical preview digest.

- No midend state may satisfy an authoritative precondition without native re-check.

- No “admin mode” bypass collapses plan, approval, execution, validation, and evidence into one endpoint.

- No capability is considered complete until required evidence and validation records exist.

# **\[V\] Threat Model and Acceptance Gates**

| **Gate** | **Attack/test** | **Required result** |
|----|----|----|
| V1 Forged ID | Submit undeclared capability or dynamic native handler | Denied; no handler resolution |
| V2 Stale target | Use old target version or projection-derived state | Denied with authoritative conflict |
| V3 Approval substitution | Reuse approval for changed payload/target/digest | Denied; binding mismatch recorded |
| V4 Replay | Reuse nonce/request/approval after acceptance | Denied or idempotent same disposition; no second exercise |
| V5 Profile injection | Profile declares shell-like or unsigned capability | Quarantined; not discoverable |
| V6 TOCTOU | Change host facts after preview before apply | Native re-check denies or requires new preview |
| V7 UI bypass | Call endpoint directly for hidden/unavailable action | Native admission denies |
| V8 Evidence completeness | Force executor success without validator/checkpoint | Capability remains incomplete/failed |

<table>
<colgroup>
<col style="width: 100%" />
</colgroup>
<thead>
<tr>
<th><p><strong>Acceptance boundary</strong></p>
<p>WO-044 is complete when every mutating API route resolves to one declared capability and a red-team suite proves that forged, stale, replayed, substituted, or shell-shaped requests cannot reach native execution.</p></th>
</tr>
</thead>
<tbody>
</tbody>
</table>

# **\[P\] Implementation Packages**

| **Package** | **Scope** | **Deliverable** |
|----|----|----|
| 033A | Capability ID taxonomy and declaration schema | capability-registry-v1 |
| 033B | Payload schemas and generated browser forms | versioned form/control schemas |
| 033C | Discovery and projected legality service | resource capability endpoint |
| 033D | Canonicalization, hashing, nonce, expiry, idempotency | action-envelope library |
| 033E | Preview and digest-bound approval model | approval record schema + UI flow |
| 033F | Native admission adapter and denial taxonomy | inlet capability dispatcher |
| 033G | Threat-model and red-team tests | capability security proof report |

# **\[N\] Completion Record and Next Action**

| **Marker** | **Record** |
|----|----|
| \[W\] | Defined the capability-driven mutating boundary and initial action catalog. |
| \[D\] | Branch C prepares and filters requests; only the native inlet grants and exercises capabilities. |
| \[I\] | Specified declarations, action envelopes, discovery, approval binding, validation layers, and prohibitions. |
| \[V\] | Eight adversarial gates cover forgery, staleness, substitution, replay, profile injection, TOCTOU, UI bypass, and evidence gaps. |
| \[P\] | Seven packages implement registry, schemas, discovery, envelope integrity, approval, native admission, and red-team proof. |
| \[N\] | Implement run.pause and install.apply as the first low-risk/high-risk capability pair and verify both through the same dispatcher. |
