# Leaf-WO-009 Memory Foundation

Current integration: version-2 resident runs use native LMEM for durable
control records, `events.jsonl` for reconnectable presentation, and
`checkpoint.json` for validated recovery facts. Memory records do not replace
the queue, work order, resource policy, or acceptance gate.

## Authority hierarchy

LeafOS memory distinguishes three classes:

1. **Record** — an observation, request, plan, reflection, or tool attempt. Records never authorize mutation.
2. **Evidence** — a checkable tool or validator result with source identity and artifact references. Evidence may support a declared policy but does not silently become checkpoint state.
3. **Committed fact** — state accepted through checkpoint commit. Only this class is authoritative for resume position, task state, and `next_action`.

A model-generated plan or reflection is always a record. It cannot promote itself into evidence or a committed fact.

## Foundation delivered

The current native `leaf-memory` executable provides the durable prerequisite for later work packages:

- versioned event and query schema files under `schemas/`;
- compact canonical JSON normalization for the accepted event envelope;
- SHA-256 payload sealing, with the hash computed after replacing the envelope hash field with 64 zero characters;
- framed `LMEM` v1 journal entries containing magic, version, sequence, payload length, checksum, and canonical payload;
- strict monotonic sequence and per-run previous-payload-hash validation;
- `append`, `verify`, `recover`, and verified `replay` commands that emit machine-readable JSON;
- truncated-final-record recovery that preserves the verified journal prefix.

The native executable is the authority. `bin/leaf-memory.sh` and `bin/leaf-memory.ps1` only locate and invoke it. Set `LEAF_MEMORY_BIN` to override the executable location.

## Commands

```text
leafctl memory append --journal PATH --event EVENT.json
leafctl memory verify --journal PATH
leafctl memory recover --journal PATH
leafctl memory append --kind reflection --journal PATH --payload ARTIFACT.json
leafctl memory index build --journal PATH
leafctl memory index query --journal PATH --text QUERY
leafctl memory checkpoint bind --journal PATH --checkpoint PATH --label RUN
leafctl memory checkpoint verify --checkpoint PATH
leafctl memory pack build --journal PATH --out PACK.json --query TEXT --token-budget N --run-id RUN --task-id TASK --model-id MODEL
leafctl memory pack inspect PACK.json
leafctl memory pack verify PACK.json
leafctl memory stats --journal PATH --max-bytes N
leafctl memory archive create --journal PATH --out ARCHIVE.lmem
leafctl memory archive verify ARCHIVE.lmem
```

`append` rejects an event that is not the next sequence in the journal, does not continue the prior payload hash, exceeds the payload limit, or fails envelope validation. `verify` reports a truncated final record as non-success so callers must choose recovery explicitly. `recover` removes only that incomplete tail.

## Event lifecycle

1. Normalize and validate the incoming versioned event envelope.
2. Seal its payload hash.
3. Verify the journal prefix and the new event's sequence and previous-hash link.
4. Flush the framed record to the append journal.
5. Later work packages derive indexes, hot caches, retrieval manifests, and context packs from this journal. None may replace it.

## Deferred Leaf-WO-009 phases

This foundation intentionally does not yet implement SQLite/FTS indexing, bounded hot memory, scoring, embedding vectors, promotion gates, sensitivity redaction, archive compaction, or retrieval-quality benchmarks. Those features must consume this journal and preserve the record/evidence/committed-fact authority boundary. See WO-019 below for the reflection and context-pack schemas that have since been added on top of this foundation.

## Validation status

`tests/memory/journal.sh` was fixed (a ROOT_DIR path defect caused incorrect fixture resolution) and run to completion against a statically linked `build/leaf-memory.exe`. It covers valid append, verification, rejection of the invalid fixture, truncated-tail detection, and recovery, and now ends with `memory journal test: PASS`. This satisfies WO-019 Gate G1.

## WO-019: bounded, verifiable memory pipeline (in progress)

WO-019 extends this foundation with runtime capacity doctrine, explicit reasoning artifacts, and deterministic context packs, without changing the authority hierarchy above.

### Context is capacity, not reasoning

A runtime profile's `context_size` is not a reasoning budget. Configured context must satisfy `C >= I_p95 + P_max + (reasoning + output) + S`. See `config/runtime-profiles.json` for the `interactive`, `continual`, `overnight`, and `compat-4k` profiles, their `context_size`, `max_output_tokens`, `reasoning_budget_requested`, and `memory_pack_tokens` ceilings, and the documented resolution precedence (CLI override > runtime profile > provider limit > model metadata > compat-4k default). `core/runtime/continual_live.py` (`resolve_profile`) and `Bash-Version/chat-local.sh` (`--profile`) both resolve against this same file and must not silently invent a budget the model does not support.

### Reasoning artifacts (non-authoritative reflection)

`schemas/leafos.reasoning-artifact.v1.schema.json` defines a bounded, inspectable payload (decision summary, assumptions, alternatives, evidence/constraint references, uncertainties, unresolved questions, proposed next action, token accounting) that is embedded as the `content.data` of a `leafos.memory.event.v1` event with `kind: reflection` and `epistemic_class: record`. It is never a claim of verbatim hidden chain-of-thought, and it cannot self-promote to `evidence` or `committed_fact`; only validation/approval gates can do that.

`core/memory/reflection.py` validates this artifact and delegates every write to the native LMEM append command. An optional `phase_timeline` carries the bounded output of `ThinkingLoopEngine`; explicit model markers are observable, but LeafOS does not claim access to private hidden chain-of-thought.

### Disposable retrieval index

`core/memory/index.py` rebuilds an SQLite/FTS5 projection exclusively from native verified replay. Its default location is `JOURNAL.index.sqlite3`. This file is disposable cache state: exclude it from durable backups and authority decisions, and use `leafctl memory index rebuild` to replace it. The LMEM journal remains the sole durable source.

### Checkpoint binding

`core/memory/checkpoint.py` binds a run label to the LMEM head sequence/hash, the committed-fact-set hash from the index, and a nullable context-pack hash. Resume verification returns exactly one of `exact`, `advanced`, `diverged`, `corrupt`, or `missing`.

### Context packs

`schemas/leafos.context-pack.v1.schema.json` defines a deterministic, reproducible projection of LMEM records bounded to a token budget: source journal head, query/filters, tokenizer identity, token budget vs. measured tokens, ordered record references with score components and inclusion reason, typed exclusions (tombstoned/redacted/age/authority/token_budget/duplicate), and a final `pack_sha256`. A context pack never grants independent authority to the records it references.

`core/memory/pack.py` implements this contract. Fixed inputs use the verified journal timestamp and canonical hashing, so repeated builds are byte-identical. Tombstoned records are excluded before excerpts are assembled.

### Retention and archive

`core/memory/retention.py` reports quota state and creates verified, non-destructive LMEM archives with a hash manifest. Archiving never deletes the source journal. Redaction remains an append-only tombstone plus sanitized derived projections; historical LMEM bytes stay auditable.

### Rollback / feature gates

The context-pack work package remains deferred. Existing deployment feature gates are retained for operators that have not enabled the new reflection and checkpoint routes:

```text
LEAF_MEMORY_CONTEXT_PACKS=0
LEAF_MEMORY_REFLECTIONS=0
LEAF_MEMORY_CHECKPOINT_BINDING=0
```

Setting any flag to `0` disables the corresponding new reads/writes, restores the previous runtime profile behavior, and leaves existing LMEM entries intact. Rollback must never delete the journal; schema-versioned records written during a trial remain valid but are ignored by older readers.
