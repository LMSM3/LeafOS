# LeafOS-WO-019 — Persistent Reasoning Memory, Live CLI Streams, and Skill Synthesis

Status: proposed, implementation-ready  
Priority: P0 / super-high-value  
Target: `C:\R\LeafOS0.2.2`
Primary subsystem: ProjectLeaf continual agent loop  
Risk class: high; changes affect model context, resume authority, auditability, storage growth, and inference cost  
Depends on: native `leaf-memory`, LMEM v1 journal, memory event/query schemas, provider contract, checkpoint format  
Blocks: reliable multi-chat continuity, observable long-running agents, evidence-aware context packs, useful continual reflection, safe self-improvement

## 0. Mission

Implement a bounded, verifiable memory pipeline that allows a LeafOS run to reason over a large working context, preserve useful reasoning artifacts outside the model context, recover them across processes and chats, and reconstruct a compact context pack without allowing model-authored reflection to become authoritative state.

The work order must prove seven distinct capabilities:

1. A runtime profile can allocate at least 16,384 tokens to deliberate reasoning/output activity without confusing that allocation with the model's total context window.
2. LeafOS can capture an explicit reasoning artifact after a planning step and append it to LMEM as a non-authoritative `reflection` record.
3. LeafOS can retrieve, rank, bound, and assemble prior memory into a deterministic context pack.
4. A checkpoint can bind itself to an exact verified memory-journal head and context-pack digest, then resume without silently changing historical authority.
5. The chat CLI can accept a machine-readable input stream and emit a resumable, continually flushed event stream without corrupting human-readable terminal output.
6. The live terminal can display explicit reasoning summaries and action state while the run continues, without claiming access to private hidden chain-of-thought.
7. LeafOS can propose, draft, validate, sandbox-test, approve, install, version, and roll back a reusable skill without granting the generating model authority over its own safety gates.

This is not a request to expose, scrape, or store a provider's private hidden chain-of-thought. LeafOS shall persist deliberate artifacts that it explicitly requests and can validate: decision summaries, assumptions, alternatives considered, evidence references, uncertainty, action rationale, and unresolved questions.

## 1. Problem statement

The existing continual configuration is too small for the intended development loop:

| Surface | Current value | Defect |
|---|---:|---|
| `config/continual-live.json` `context_size` | 4096 | Cannot hold substantial input, retrieved memory, reasoning artifact, and response |
| `config/continual-live.json` `max_tokens` | 256 | Insufficient for planning or structured reflection |
| `Bash-Version/chat-local.sh` `CTX` / `TOKENS` | 4096 / 256 | Repeats the same ceiling |
| `core/providers/providers.sh` provider max | 12000 | Below the requested reasoning/output allocation |
| `core/providers/_providers_new.sh` provider max | 2048 | Inconsistent with the main provider path |
| `chat-local.sh` reasoning default | off / budget 0 | Explicitly disables the intended lane |

The durable side is architecturally stronger. LMEM v1 already provides append-only framing, checksums, SHA-256 payload sealing, monotonic sequence numbers, and previous-hash linking. Its authority model correctly separates `record`, `evidence`, and `committed_fact`. However, the journal is not yet a complete memory system: indexing, scoring, context packs, promotion gates, checkpoint coupling, redaction, compaction, and retrieval benchmarks remain unfinished. The existing journal test has also not been confirmed passing to completion.

The result is a split system: volatile model context is too small, while durable memory is largely write-only. WO-019 closes that loop.

## 2. Non-negotiable doctrine

### 2.1 Context is capacity, not reasoning

Let

\[
C = I + P + R + O + S
\]

where:

- \(C\) is the model context limit;
- \(I\) is current user/task input;
- \(P\) is the retrieved external-memory context pack;
- \(R\) is any provider-supported reasoning allocation;
- \(O\) is visible model output;
- \(S\) is a safety reserve for templates, tool results, and tokenization error.

Setting \(C=16384\) does not create a 16k reasoning budget. If the operational requirement is \(R+O \ge 16384\), then the configured context must satisfy

\[
C_{configured} \ge I_{p95}+P_{max}+16384+S.
\]

The baseline profile shall therefore use a minimum 32,768-token context only where the selected model actually supports it. A 65,536-token profile should be preferred for long continual runs. Unsupported models must fail capability negotiation or fall back to an explicitly named smaller profile; LeafOS must not pretend the requested budget exists.

### 2.2 Reflection is not authority

A `reflection` is always a `record`. It may cite evidence but may not promote itself. Only validation and approval gates can produce or update `evidence` and `committed_fact` objects.

### 2.3 Persist explicit artifacts, not private chain-of-thought

The persisted artifact shall contain concise, inspectable fields. It shall not claim to be a verbatim copy of hidden internal reasoning. Providers that expose a supported reasoning summary may populate the same artifact contract, marked with provenance.

### 2.4 Resume must be reproducible

A resumed run must verify the LMEM chain, locate the checkpoint-bound journal head, reconstruct or verify the referenced context pack, and report any divergence before planning continues.

### 2.5 External memory is untrusted input until verified

Retrieved records can contain obsolete statements, prompt injection, model mistakes, or later-tombstoned content. Retrieval relevance never grants authority.

### 2.6 Observability is not authority

A streamed thought summary, plan delta, or action request describes current agent state. Merely printing it does not approve the action, validate a claim, or commit a fact. Event consumers must use the event's explicit authority and lifecycle fields rather than infer truth from recency or terminal color.

### 2.7 Standard output is a protocol surface

When machine-stream mode is active, standard output shall contain only protocol-valid event frames. Human decoration, progress bars, ANSI control codes, diagnostics, and stack traces belong on standard error or a separate TUI consumer. One stray motivational banner must not turn an overnight run into invalid JSON, a feat shell programs otherwise perform with disturbing reliability.

### 2.8 Self-created skills are proposed capabilities

A model may identify a repeated workflow and author a skill candidate. It may not approve its own permissions, install itself, alter its validator, weaken policy, or mark its own test evidence as trusted. Skill activation is a governed state transition, not file creation with better branding.

## 3. Memory topology

| Tier | Name | Lifetime | Contents | Authority |
|---|---|---|---|---|
| M0 | active context | one inference | prompt, selected memory, tool results, current response | mixed; source-tagged |
| M1 | hot run cache | one process/run | recent verified records, retrieval cache, token counts | cache only |
| M2 | LMEM journal | cross-process/cross-chat | append-only events and payload hashes | record/evidence/fact per event |
| M3 | retrieval index | rebuildable | lexical index, metadata filters, optional embeddings | no independent authority |
| M4 | archive | long-term | compacted journal segments plus manifests | inherits sealed source authority |

M1, M3, and generated context packs are disposable projections. LMEM and its sealed archives remain the source of historical truth. Deleting an index must reduce performance, not destroy memory.

## 4. Required artifacts and contracts

### 4.1 Reasoning artifact

Add `schemas/leafos.reasoning-artifact.v1.schema.json`, or embed the same validated payload under the existing `reflection` event kind.

Required fields:

```json
{
  "schema": "leafos.reasoning-artifact.v1",
  "run_id": "overnight-001",
  "task_id": "coder-refactor",
  "created_at": "RFC3339 timestamp",
  "producer": {
    "provider": "llama.cpp",
    "model": "model-id",
    "mode": "requested_summary"
  },
  "decision_summary": "bounded visible rationale",
  "assumptions": [],
  "alternatives": [],
  "evidence_refs": [],
  "constraint_refs": [],
  "uncertainties": [],
  "unresolved_questions": [],
  "proposed_next_action": null,
  "token_accounting": {
    "context_limit": 65536,
    "input_tokens": 0,
    "memory_tokens": 0,
    "reasoning_budget_requested": 0,
    "output_tokens": 0
  }
}
```

The payload shall be size-bounded, UTF-8, schema-validated, and appended as a `reflection`/`record`. Large auxiliary output may be stored as a content-addressed blob with only its digest, media type, byte length, and safe preview in LMEM.

### 4.2 Context pack

Add `schemas/leafos.context-pack.v1.schema.json` and a native or standard-library builder.

A context pack must include:

- pack ID, schema version, creation time, task/run IDs;
- LMEM source head sequence and hash;
- query and filter parameters;
- tokenizer/model identifier;
- exact token budget and measured token count;
- ordered record references with sequence, payload hash, authority, event kind, score components, and inclusion reason;
- exclusions caused by tombstones, redaction, age, authority, or token pressure;
- final pack SHA-256.

The pack builder shall never silently truncate a JSON object. It may exclude whole records, include an explicitly generated summary record, or use a validated excerpt carrying the original digest and byte range.

### 4.3 Checkpoint binding

Extend the checkpoint contract with:

```json
{
  "memory": {
    "journal_version": 1,
    "head_sequence": 0,
    "head_hash": "sha256",
    "context_pack_id": "pack-id",
    "context_pack_hash": "sha256",
    "committed_fact_set_hash": "sha256"
  }
}
```

Checkpoint creation must occur only after pending memory appends are flushed and verified. Resume must fail closed on a broken hash chain and enter an explicit `memory_diverged` state when the journal is valid but no longer matches the checkpoint head.

### 4.4 Bidirectional CLI stream envelope

Add `schemas/leafos.stream.event.v1.schema.json` and `schemas/leafos.stream.command.v1.schema.json`. The canonical transport is UTF-8 NDJSON: one complete object per line, flushed immediately after serialization. The first implementation shall work over stdin/stdout and regular pipes; local sockets or named pipes may be added later without changing the envelope.

Every outbound event must include:

```json
{
  "schema": "leafos.stream.event.v1",
  "protocol_version": 1,
  "run_id": "overnight-001",
  "task_id": "coder-refactor",
  "stream_id": "uuid",
  "sequence": 42,
  "event_id": "uuid",
  "timestamp": "RFC3339 timestamp",
  "kind": "action.started",
  "phase": "execute",
  "lane": "action",
  "visibility": "user",
  "authority": "record",
  "parent_event_id": null,
  "memory_ref": null,
  "payload": {},
  "content_sha256": "sha256"
}
```

Required event families:

- `run.started|heartbeat|paused|resumed|completed|failed`;
- `input.received|accepted|rejected`;
- `model.requested|stream_delta|completed|failed`;
- `reasoning.summary|assumption|uncertainty|decision`;
- `action.requested|approval_pending|approved|rejected|started|progress|result|failed`;
- `memory.appended|verified|pack_built|checkpoint_bound`;
- `skill.need_detected|proposed|drafted|validated|tested|approval_pending|installed|activated|rejected|rolled_back`.

The `model.stream_delta` family carries visible model output only. The `reasoning.*` family carries explicitly generated structured summaries. Neither may be labeled or documented as raw hidden chain-of-thought.

Inbound commands must include `user.message`, `action.approve`, `action.reject`, `run.pause`, `run.resume`, `run.cancel`, `checkpoint.request`, and `stream.replay`. Commands require a unique ID, target run, expected run state, and optional reply-to event. Duplicated command IDs must be idempotently acknowledged, not executed twice.

The stream shall provide:

- monotonically increasing sequence numbers per stream;
- immediate line flushing;
- bounded queues and an explicit backpressure policy;
- heartbeat and last-progress timestamps;
- replay from a requested sequence or journal cursor;
- terminal events for every action request;
- payload byte limits and safe truncation metadata;
- secret-field redaction before serialization;
- clean EOF semantics and process exit codes;
- an optional durable spool that can be reconstructed from LMEM events.

Ephemeral token deltas need not enter LMEM. Decisions, action boundaries, approvals, results, reflection summaries, skill lifecycle transitions, and checkpoints must be appended or linked to durable memory.

### 4.5 Human live-view projection

Add a read-only stream consumer that projects protocol events into stable lanes:

| Lane | Shows | Must not imply |
|---|---|---|
| `THOUGHT` | explicit summaries, assumptions, uncertainty, decisions | private chain-of-thought or factual truth |
| `ACTION` | requests, approvals, tool start/progress/result | permission merely because an action was printed |
| `CODE` | visible generated patches, build/test output, file deltas | that generated code has been applied or validated |
| `MEMORY` | append, verify, context-pack, checkpoint events | that all recalled records are authoritative |
| `SKILL` | proposal, validation, sandbox test, approval, activation | automatic trust or unrestricted capability |
| `ERROR` | failures, divergence, corruption, blocked states | successful recovery unless separately emitted |

Color is optional presentation metadata. Plain-text and `--no-color` output must preserve the same event meaning. A slow or disconnected renderer must not block the agent loop; it reconnects by cursor and replays missed durable events.

### 4.6 Skill candidate package

Add `schemas/leafos.skill-candidate.v1.schema.json`. A candidate package must contain:

- immutable candidate ID and semantic version;
- human-readable name, trigger description, purpose, and non-goals;
- evidence of repeated need, including source task/run references;
- declared inputs, outputs, tools, filesystem/network needs, and approval points;
- concise instructions plus only necessary scripts, references, and assets;
- deterministic tests and expected results;
- provenance for every generated file;
- package manifest with per-file SHA-256 and whole-package digest;
- compatibility range and rollback target;
- lifecycle state and approval record.

The preferred layout is:

```text
skills/
  staging/<candidate-id>/
    SKILL.md
    skill.manifest.json
    agents/openai.yaml          # only when the host supports UI metadata
    scripts/                    # only when deterministic code is necessary
    references/                 # only when detailed source material is necessary
    assets/                     # only when output resources are necessary
  active/<skill-name>/
  quarantine/<candidate-id>/
```

`SKILL.md` shall remain concise and use progressive disclosure. Repeated deterministic operations belong in tested scripts; bulky domain material belongs in directly referenced files, not in the always-loaded instruction body.

## 5. Configuration profile

Introduce named profiles instead of scattering magic numbers:

| Profile | Context | Max visible output | Requested reasoning allocation | Memory-pack cap | Use |
|---|---:|---:|---:|---:|---|
| `interactive` | 32768 | 4096 | provider auto | 6144 | ordinary chat and bounded edits |
| `continual` | 65536 | 8192 | 16384 where supported | 12288 | long local development loop |
| `overnight` | 131072 | 16384 | 32768 where supported | 24576 | slow planner / major refactor |
| `compat-4k` | 4096 | 512 | off | 512 | explicit legacy fallback only |

Values are ceilings, not guaranteed consumption. Startup capability negotiation shall compute a feasible allocation from the actual model metadata and provider features. The resolved values must be logged in the run manifest.

Configuration precedence:

1. command-line override;
2. selected runtime profile;
3. provider-specific supported limit;
4. model metadata;
5. safe compatibility default.

Both shell and PowerShell launch paths must resolve to the same normalized run manifest. `_providers_new.sh` may not carry an independent contradictory default.

## 6. Retrieval and ranking

Phase one shall use deterministic metadata filtering plus SQLite FTS5/BM25 where available. Embeddings are optional and must not block the baseline.

For candidate record \(i\), define:

\[
S_i=w_lL_i+w_rR_i+w_aA_i+w_tT_i+w_cC_i-w_dD_i-w_uU_i
\]

where:

- \(L_i\): normalized lexical relevance;
- \(R_i\): recency decay;
- \(A_i\): authority weight, with committed fact greater than evidence greater than record;
- \(T_i\): task/run relationship;
- \(C_i\): explicit citation or dependency connectivity;
- \(D_i\): duplication penalty;
- \(U_i\): superseded, tombstoned, or unresolved-conflict penalty.

Default weights must be versioned and reported in the pack. Selection under token budget \(B\) is a constrained packing problem:

\[
\max \sum_i S_ix_i \quad \text{subject to}\quad \sum_i t_ix_i \le B,\; x_i\in\{0,1\}.
\]

The initial implementation may use deterministic greedy selection by \(S_i/t_i\), followed by stable ordering by authority, dependency, and journal sequence. Golden tests shall freeze the selected record IDs for fixed fixtures.

## 7. Implementation work packages

### WP-1 — Prove the LMEM foundation

- Run `tests/memory/journal.sh` to completion.
- Capture exit code, duration, binary version, and test log.
- Add corruption cases: bad checksum, broken previous hash, duplicate sequence, truncation, unknown version, invalid UTF-8, oversized payload.
- Confirm recover never mutates the original journal without an explicit output target.

Gate G1: all journal tests pass from a clean local build. No context or retrieval work proceeds on an unverified journal.

### WP-2 — Normalize capability and token budgets

- Replace duplicated constants in `continual-live.json`, `chat-local.sh`, `providers.sh`, and `_providers_new.sh` with named profile resolution.
- Add provider/model capability discovery.
- Distinguish `context_limit`, `max_output_tokens`, `reasoning_budget_requested`, and `memory_pack_tokens` in all contracts and logs.
- Default continual reasoning to `auto`, never blindly `on` when unsupported.
- Reject impossible allocations with the computed budget equation in the error.

Gate G2: shell and PowerShell dry runs emit equivalent resolved manifests for the same model/profile.

### WP-3 — Capture reflection records

- Prompt for a bounded structured reasoning artifact after plan generation or at a configurable milestone.
- Validate the artifact before append.
- Append as `reflection` with authority `record`.
- Preserve provider response IDs and visible token accounting when available.
- If generation or validation fails, append an error event; do not invent a reflection.

Gate G3: a fixture run produces a valid reflection event that cannot be promoted by the producer model.

### WP-4 — Build the retrieval index

- Implement rebuildable SQLite metadata and FTS index.
- Index LMEM sequence, event kind, authority, task/run IDs, timestamps, tags, payload digest, and permitted text fields.
- Make indexing incremental and idempotent.
- Detect stale index head versus journal head.
- Provide `leafctl memory index build|update|status|rebuild`.

Gate G4: deleting and rebuilding the index yields identical query results and does not change LMEM.

### WP-5 — Assemble context packs

- Implement query, filtering, scoring, deduplication, token measurement, selection, and serialization.
- Add `leafctl memory pack build|inspect|verify`.
- Source-label every injected section and place records below system/developer policy in prompt authority.
- Exclude tombstoned/redacted content by default.
- Record why each item was included or excluded.

Gate G5: fixed journal + fixed query + fixed tokenizer produces the same pack hash on repeated runs.

### WP-6 — Couple memory to checkpoints and resume

- Flush and verify LMEM before checkpoint sealing.
- Bind checkpoint to journal head, fact-set hash, and context-pack hash.
- On resume, verify journal, validate the checkpoint head is an ancestor of current head, then rebuild or verify the pack.
- Define explicit recovery modes: `exact`, `advanced`, `diverged`, `corrupt`, `missing`.
- Never continue automatically from `diverged` or `corrupt`.

Gate G6: kill-and-resume integration test reconstructs the same committed state and reports any later non-authoritative records separately.

### WP-7 — Redaction, compaction, and retention

- Add tombstone/redaction events without rewriting historical LMEM.
- Keep secrets and raw environment dumps out of reflection payloads.
- Implement sealed archive segments with manifests and chain continuity.
- Set per-run and per-project storage quotas plus warnings.
- Summaries must retain citations to source sequences and hashes.

Gate G7: redacted content is absent from new context packs and indexes while the audit trail still proves that a redaction occurred.

### WP-8 — Implement the bidirectional CLI stream

- Add versioned NDJSON event and command schemas.
- Add `leaf chat --stream=ndjson` with protocol-only stdout and diagnostics on stderr.
- Flush each frame immediately and preserve one-frame-per-line atomicity.
- Implement bounded queues, heartbeat, cancellation, idempotent commands, replay cursors, EOF, and exit-code behavior.
- Persist lifecycle-significant events or their LMEM references.
- Add a `leaf stream verify` consumer that rejects malformed, duplicated, out-of-order, oversized, or hash-invalid frames.

Gate G8: a scripted producer/consumer run survives pause, approval, action progress, renderer disconnect, replay, and clean completion without losing a durable lifecycle event.

### WP-9 — Add continual thought/action rendering

- Implement a read-only TUI/plain-text consumer for `THOUGHT`, `ACTION`, `CODE`, `MEMORY`, `SKILL`, and `ERROR` lanes.
- Emit reasoning summaries at state transitions and configured time/token intervals, not uncontrolled token-by-token monologue.
- Clearly label all summaries as model-authored records.
- Correlate action requests, approvals, execution, and results using event and parent IDs.
- Support `--quiet`, `--plain`, `--no-color`, `--lane`, and `--since` without altering runtime semantics.
- Ensure rendering can be disabled with zero effect on checkpoints, action gates, or memory.

Gate G9: the same recorded event fixture produces semantically equivalent color, no-color, filtered, and replayed views; no view claims to expose private chain-of-thought.

### WP-10 — Implement governed self-skill creation

- Detect skill opportunities only from explicit user request or repeated measured workflow friction; never from a single whim emitted during generation.
- Create a `skill.need_detected` record containing examples, frequency, expected benefit, and why ordinary code/config is insufficient.
- Generate candidates only in `skills/staging` with no activation rights.
- Validate name, trigger specificity, package shape, size, references, declared permissions, and manifest hashes.
- Run scripts and representative skill tasks in a restricted sandbox with network off unless explicitly required and approved.
- Compare candidate behavior against baseline tasks; record success, regressions, cost, and failure modes.
- Require an approval event bound to the exact candidate digest before installation.
- Install by immutable version, activate separately, retain the previous version, and provide one-command rollback.
- Quarantine candidates that fail validation, request undeclared capabilities, modify their own evidence, or attempt to alter policy/validators.

The skill lifecycle is strictly:

```text
need_detected -> proposed -> drafted -> static_validated -> sandbox_tested
              -> approval_pending -> installed -> activated
```

Any stage may transition to `rejected` or `quarantined`. Only an activated version may trigger during ordinary routing.

Gate G10: a repeated fixture workflow produces a candidate that passes static validation and sandbox tests, remains inert before approval, activates only for its declared triggers, and rolls back to the previous version without journal loss.

## 8. Commands to exist at completion

```text
leafctl memory append
leafctl memory verify
leafctl memory recover
leafctl memory index build|update|status|rebuild
leafctl memory query
leafctl memory pack build|inspect|verify
leafctl memory checkpoint bind|verify
leafctl memory stats
leaf chat --stream=ndjson
leaf stream verify|replay|view
leafctl skill detect|propose|draft|validate|test
leafctl skill approve|install|activate|rollback|quarantine
```

Shell and PowerShell wrappers may locate and invoke native executables, but must not reimplement journal or hashing semantics.

## 9. Validation matrix

| Test | Expected result |
|---|---|
| 20k visible reasoning-artifact request on supported model | resolved context equation remains within model limit |
| Same request on 4k model | explicit capability failure or named fallback; no silent truncation |
| Reflection contains unsupported factual claim | stored only as record; not returned as committed fact |
| Journal byte corruption | verify fails at exact sequence |
| Process killed between append and checkpoint | resume chooses last sealed checkpoint and reports unbound tail |
| Index deleted | rebuilt results match golden record ordering |
| Journal advances after checkpoint | state reported as `advanced`, not exact |
| Checkpoint references non-ancestor head | state reported as `diverged`; planning blocked |
| Tombstoned memory matches query strongly | excluded from pack |
| Prompt injection stored in old reflection | returned as quoted untrusted memory, never as instruction |
| Context pack exceeds token budget | whole-record deterministic exclusion; valid serialization preserved |
| Repeated pack build | identical pack hash for fixed inputs |
| NDJSON stdout with human renderer enabled | stdout remains protocol-valid; rendering appears only on stderr/separate consumer |
| Renderer disconnects during a tool action | agent continues; consumer replays from last acknowledged sequence |
| Duplicate approval command | action executes at most once |
| Backpressure limit reached | configured coalescing/spooling occurs; terminal lifecycle events are never dropped |
| Reasoning summary emitted | labeled as model-authored record, not hidden chain-of-thought or evidence |
| Skill candidate requests undeclared network access | sandbox test fails and candidate enters quarantine |
| Model approves its own skill candidate | approval rejected as invalid authority |
| Skill files change after approval | digest mismatch blocks installation |
| Activated skill regresses golden task | rollback restores prior version and emits durable lifecycle events |

## 10. Acceptance criteria

WO-019 is complete only when all of the following are true:

- LMEM journal tests pass completely and evidence is attached to the run report.
- Continual and overnight profiles resolve to model-supported budgets with at least one demonstrated configuration allocating 16,384 or more tokens to reasoning plus visible output.
- No documentation or log equates context size with chain-of-thought size.
- A validated reasoning artifact is appended as a `reflection` record.
- The artifact cannot self-promote to evidence or committed fact.
- The retrieval index is disposable, deterministic, and rebuildable from LMEM.
- A bounded context pack can be built, inspected, verified, and reproduced.
- Pack contents carry authority and provenance labels.
- Checkpoints bind to an LMEM head and pack digest.
- Resume detects exact, advanced, diverged, corrupt, and missing states.
- Shell and PowerShell launchers produce equivalent normalized manifests.
- Storage quota, redaction, tombstone, and archive behavior have tests.
- A conventional single-machine local run passes before any experimental MoE routing is enabled.
- The chat CLI accepts versioned inbound commands and emits protocol-valid, continually flushed outbound events.
- Human rendering is fully separable from machine stdout and cannot block the run.
- Reasoning telemetry consists only of explicit summaries and never claims hidden chain-of-thought access.
- Every requested action has a correlated terminal result and every approval command is idempotent.
- Stream replay reconstructs all durable lifecycle events after consumer disconnection.
- Skill candidates remain inert in staging until static validation, sandbox testing, and digest-bound approval succeed.
- Self-authored skills cannot modify policy, validators, approval rules, or their own evidence.
- Skill activation, versioning, quarantine, and rollback are proven by integration tests.

## 11. Evidence required for closure

- clean-build command and exit status;
- full journal test log;
- profile resolution manifests for shell and PowerShell;
- sample reflection LMEM event with private or sensitive fields removed;
- index status before and after rebuild;
- deterministic context-pack fixture and SHA-256;
- checkpoint JSON showing memory binding;
- kill/restart resume transcript;
- corruption and divergence test results;
- storage-growth measurement for at least 1,000 events;
- an NDJSON protocol fixture covering input, reasoning summary, action approval, result, memory append, and completion;
- disconnect/replay and backpressure test transcripts;
- machine stdout validation with TUI enabled;
- one complete skill-candidate package, manifest, sandbox report, approval record, activation result, and rollback result;
- final changed-file list and rollback instructions.

## 12. Rollback

All new behavior shall be feature-gated initially:

```text
LEAF_MEMORY_CONTEXT_PACKS=0
LEAF_MEMORY_REFLECTIONS=0
LEAF_MEMORY_CHECKPOINT_BINDING=0
LEAF_STREAM_PROTOCOL=0
LEAF_STREAM_LIVE_VIEW=0
LEAF_SKILL_SYNTHESIS=0
LEAF_SKILL_AUTO_ACTIVATE=0
```

Rollback disables new reads and writes, restores the previous runtime profile, and leaves LMEM entries intact. Stream consumers may be removed without changing run state. Skill rollback deactivates the failed version and restores the last approved immutable version; it never deletes lifecycle evidence. Schema-versioned records written during the trial remain valid but ignored by older readers. Never roll back by deleting the journal.

## 13. Explicitly deferred

- vector embeddings and ANN infrastructure;
- learned retrieval weights;
- cross-project memory sharing;
- automatic fact promotion without human or validator evidence;
- raw provider-private chain-of-thought capture;
- distributed/MoE memory routing;
- lossy archive rewriting.
- automatic skill installation or activation without approval;
- skills that rewrite LeafOS policy, validators, approval logic, or memory authority rules;
- unrestricted network or filesystem access for generated skill scripts.

These may become later work orders after the conventional local loop is measured and trusted.

## 14. Completion statement

This work order converts LeafOS memory from a durable append-only audit trail into a controlled cognitive substrate: large enough to support serious planning, observable while it operates, strict enough to prevent reflection from becoming truth, capable of improving its reusable procedures, and reproducible enough to survive process death, chat boundaries, renderer loss, skill rollback, and model replacement.

The terminal completion state is:

```text
LMEM verified
reflection captured as record
index synchronized
context pack sealed
checkpoint bound
resume reproduced
CLI stream verified and replayable
thought/action view live
skill candidate sandboxed and digest-approved
skill activation reversible
authority preserved
```
