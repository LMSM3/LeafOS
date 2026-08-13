**LEAFOS MIDEND WORK ORDER**

**LeafOS-WO-043\
Resource-Oriented Midend API Gateway**

*Conventional browser routes and typed API commands that translate into existing LeafOS control objects.*

| **Status** | Proposed implementation baseline |
|----|----|
| **Date** | July 26, 2026 |
| **Target** | LeafOS 0.2.1 -\> 0.3 browser modernization |
| **Authority** | CPU-authoritative native inlet; midend remains non-executing |
| **Imported source** | `IMPORTS2/LeafOS-WO-031-Resource-Oriented-Midend-API.docx` |
| **Depends on** | Existing typed inlet, run state, web state, and report contracts |
| **Unblocks** | WO-044 capability enforcement and the first `run.pause` vertical slice |

# **\[W\] Work Objective**

Define the first implementation boundary for the LeafOS midend: a conventional resource-oriented application gateway that supports browser pages, stable URLs, predictable reads, and typed commands without acquiring execution authority.

<table>
<colgroup>
<col style="width: 100%" />
</colgroup>
<thead>
<tr>
<th><p><strong>Primary decision</strong></p>
<p>Branch A is the first build layer. It becomes the compatibility shell around current web state, runs, tasks, reports, profiles, and installation plans. Every mutating request must already be shaped for Branch C capability validation, even before the full capability broker is implemented.</p></th>
</tr>
</thead>
<tbody>
</tbody>
</table>

# **\[D\] Current State and Design Decision**

The current browser interface can expose state, but the modernization requires a stable contract between HTML/CSS/JavaScript and the CPU-authoritative native inlet. A generic backend or shell proxy would create a second authority and is therefore rejected.

- Reads may aggregate and project LeafOS state, but they do not redefine durable truth.

- Commands validate syntax, identity, resource state, and schema version, then translate into native control objects.

- The midend cannot execute shell text, directly edit project files, launch providers, or mark validation as passed.

- All identifiers are opaque, typed, and stable enough for browser history and reconnect behavior.

- Initial transport is HTTP/JSON over loopback or authenticated local network access; transport choice does not change authority.

HTML/CSS/JS frontend\
\|\
v\
resource routes + typed commands\
\|\
v\
control-object translator\
\|\
v\
native LeafOS inlet\
\|\
v\
plan -\> preview -\> apply -\> validate -\> evidence -\> checkpoint

# **\[I\] API Structure and Internal Contract**

## 3.1 Resource namespace

| **Resource** | **Primary reads** | **Permitted typed commands** | **Durable owner** |
|----|----|----|----|
| projects | list, detail, manifest summary | create, open, archive request | LeafOS project manifest |
| runs | list, detail, phase, evidence refs | start, pause, resume, cancel | run state + execution journal |
| tasks | list, detail, dependency/approval state | approve, reject, retry request | task graph + approval record |
| reports | list, metadata, rendered view | open, export request | validated report artifact |
| profiles | list, detail, compatibility facts | activate request, validate request | profile manifest |
| install-plans | list, preview, step state | prepare, approve, apply, rollback request | install manifest + journal |
| sessions | current session, capabilities, CSRF/nonce facts | refresh, close | midend disposable session store |

## 3.2 Initial endpoint surface

| **Method** | **Endpoint** | **Purpose** | **Translation result** |
|----|----|----|----|
| GET | /api/v1/projects | List project summaries | Read model only |
| GET | /api/v1/projects/{project_id} | Project detail and manifest refs | Read model only |
| POST | /api/v1/projects/{project_id}/commands/open | Prepare project-open request | ProjectOpenControl |
| GET | /api/v1/runs/{run_id} | Run state, timeline cursor, evidence refs | Read model only |
| POST | /api/v1/runs/{run_id}/commands/pause | Request bounded pause | RunPauseControl |
| POST | /api/v1/runs/{run_id}/commands/resume | Request validated resume | RunResumeControl |
| POST | /api/v1/tasks/{task_id}/commands/approve | Submit explicit approval | TaskApprovalControl |
| GET | /api/v1/reports/{report_id} | Open validated report metadata/content | Read model only |
| POST | /api/v1/install-plans/{plan_id}/commands/approve | Approve immutable plan digest | InstallApprovalControl |
| POST | /api/v1/install-plans/{plan_id}/commands/apply | Request native plan application | InstallApplyControl |

## 3.3 Typed command envelope

{\
"command_type": "run.pause",\
"schema_version": "1.0",\
"request_id": "req_01J...",\
"session_id": "ses_01J...",\
"resource": {"type": "run", "id": "run_01J..."},\
"expected_state": "executing",\
"nonce": "single-use opaque value",\
"payload": {"reason": "operator request"},\
"client_facts": {"ui_version": "0.3.0"}\
}

The translator must emit an internal control object with the same semantic fields plus server-observed identity, authoritative resource version, normalized payload, request digest, and capability placeholder. It must never emit a command string.

## 3.4 Response and error model

| **HTTP** | **Code** | **Meaning** | **Client behavior** |
|----|----|----|----|
| 200 | READ_OK | Read completed | Render returned representation |
| 202 | CONTROL_ACCEPTED | Native inlet accepted control for processing | Follow returned run/task reference |
| 400 | SCHEMA_INVALID | Payload or version invalid | Correct form; do not retry blindly |
| 401/403 | AUTH_REQUIRED / CAPABILITY_DENIED | Identity missing or action illegal | Refresh session or hide control |
| 409 | STATE_CONFLICT | Expected state/version no longer matches | Reload resource projection |
| 422 | CONTROL_REJECTED | Semantically invalid request | Show bounded native reason |
| 503 | INLET_UNAVAILABLE | Native authority unavailable | Keep UI read-only; retry with backoff |

## 3.5 Security and data handling invariants

- Reject unknown fields on mutating requests unless a schema explicitly permits extensions.

- Use same-site session cookies or equivalent local credentials, CSRF protection, single-use nonces, and bounded request sizes.

- Canonicalize resource IDs and payloads before hashing; do not accept filesystem paths where resource IDs are expected.

- Return evidence references, not unrestricted filesystem paths.

- Record request receipt and native disposition separately so an accepted HTTP request cannot be mistaken for completed execution.

- The browser never receives secrets, raw provider credentials, or unrestricted host facts.

# **\[V\] Validation and Acceptance Gates**

| **Gate** | **Test** | **Pass condition** |
|----|----|----|
| V1 Contract | Schema tests for every endpoint and control object | Unknown/malformed fields fail deterministically |
| V2 Authority | Attempt shell text, file path mutation, or direct provider launch through API | All attempts rejected before native inlet |
| V3 Concurrency | Issue command with stale resource version | 409 state conflict; no control exercised |
| V4 Replay | Repeat same request_id/nonce | No duplicate control; idempotent disposition returned |
| V5 Outage | Stop native inlet while UI remains online | Reads remain available where safe; mutations return 503/read-only mode |
| V6 Evidence | Trace accepted request through control receipt and resulting event | Request digest and native evidence reference correlate |
| V7 Browser | Navigate list/detail/report pages and refresh | Stable URLs reconstruct the same durable state |

<table>
<colgroup>
<col style="width: 100%" />
</colgroup>
<thead>
<tr>
<th><p><strong>Acceptance boundary</strong></p>
<p>WO-043 is complete when the browser can read resources and submit at least one typed command per mutating resource class, while a hostile test suite proves the midend cannot execute or mutate anything by itself.</p></th>
</tr>
</thead>
<tbody>
</tbody>
</table>

# **\[P\] Implementation Packages**

| **Package** | **Scope** | **Deliverable** |
|----|----|----|
| 031A | Route map and versioned namespace | api-v1-route-manifest.yaml |
| 031B | Read DTOs and resource serializers | project/run/task/report/profile/install schemas |
| 031C | Typed command envelopes and translator | control-object adapter library |
| 031D | Session, nonce, CSRF, and request limits | authenticated request middleware |
| 031E | Error taxonomy and correlation IDs | stable client/native disposition model |
| 031F | Contract, authority, and outage tests | automated acceptance suite + report |

Recommended implementation order: 031A -\> 031B -\> 031C -\> 031D -\> 031E -\> 031F. Build one vertical slice first: project list -\> run detail -\> run.pause control -\> native disposition -\> refreshed state.

# **\[N\] Completion Record and Next Action**

| **Marker** | **Record** |
|----|----|
| \[W\] | Defined the resource-oriented API boundary and versioned route model. |
| \[D\] | Branch A is the first implementation layer; it remains a translator and read gateway. |
| \[I\] | Specified resource namespaces, typed commands, control envelopes, errors, and security invariants. |
| \[V\] | Seven gates prove schema correctness, idempotency, outage behavior, browser reconstruction, and absence of midend execution. |
| \[P\] | Six packages provide a narrow vertical slice before surface expansion. |
| \[N\] | Implement 031A-031C and bind the first run.pause request to a native inlet stub that records but does not execute. |
