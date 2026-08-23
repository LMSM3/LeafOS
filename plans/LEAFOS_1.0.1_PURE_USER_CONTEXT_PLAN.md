# LeafOS 1.0.1 Plan — Pure User Context

**Stage:** 2 of 2  
**Status:** Proposed implementation plan  
**Effective date:** 2026-08-19  
**Depends on:** LeafOS 1.0.0 long-loop state, evidence, and epoch contracts  
**Benchmark:** Bench-001 — VSEPR-SIM / VSIM v5.16.0  
**Design authorities:** the supplied *LeafOS 1.0.1 — Pure User Context* brief and the Pure User Context/Context Builder portions of the supplied CCIS ideal-design diagram

## Outcome

LeafOS 1.0.1 will maintain a local, project-native, evidence-backed working
model of the user's projects. It will answer what LeafOS knows, why it believes
it, which project/version the claim belongs to, and when the correct answer is
`UNKNOWN`.

```text
project files + runtime observations + explicit user decisions
                           -> project silo
                           -> authority and supersession
                           -> bounded context packet
                           -> CCIS context builder
```

This is not generic chat memory. It is not a vector-database project. It is not
permission to search every user project for every question.

## Naming and benchmark authority

The canonical project name is **VSEPR-SIM**; **VSIM** is its scripting/runtime
control layer. “VSPER-SIM” is treated as a typo unless a repository artifact
specifically uses it as data.

Bench-001's locked source is:

```text
C:\FlowerOS\V\5.16.0
```

`C:\FlowerOS\V\V6_alpha` and `C:\FlowerOS\V\V6_DFAE_Alpha` are separate v6
corpora. They may be consulted only for an explicit version-comparison case.
The historical `C:\Users\liamm\OneDrive\Documents\VSPER Suite` workspace is
secondary documentation, not master code.

## Stage entry conditions

Implementation starts only after 1.0.0 provides:

- stable task, evidence, decision, and epoch schemas;
- project-root identity and bounded path handling;
- restart-safe append/commit behavior;
- `leafctl context export` for strategic long-loop state;
- provenance requirements for accepted conclusions.

If those contracts change incompatibly, this work is not a patch release.
Keep the 1.0.1 label only while CLI and stored-state changes remain additive
and backward-compatible; otherwise make an explicit re-versioning decision.

## Core authority rule

LeafOS resolves knowledge in this order:

```text
explicit user decision / direct current observation
                    -> current project evidence
                    -> versioned project history
                    -> LeafOS-derived claim or summary
                    -> model pretrained knowledge
                    -> UNKNOWN
```

Recency alone does not outrank authority. A newer generated summary cannot
supersede a source file, test result, or explicit decision. When two sources of
equal authority conflict, LeafOS returns the conflict and requests resolution;
it does not silently pick the more fluent one.

Every durable claim carries:

```text
claim_id, project_id, version_scope, statement, status,
authority, evidence_ids, valid_from, valid_to,
supersedes, created_by, confidence, content_hash
```

Allowed claim statuses are `observed`, `admitted`, `superseded`, `disputed`,
and `unknown`. Model output without project evidence may suggest a search but
cannot create an admitted fact.

## Siloed storage layout

User-wide preferences live separately from project evidence. Project context
is local to the project by default.

```text
~/.leaf/context/user/
├── preferences.md
├── terminology.md
└── decisions.md

<project>/.leaf/context/
├── manifest.json
├── identity.md
├── architecture.md
├── runbook.md
├── gotchas.md
├── decisions/
├── sessions/
├── evidence/
├── bridges.json
└── context.db
```

`manifest.json` binds a stable project ID to canonical root, version/branch,
include paths, excludes, source authority, and index revision. It must not grow
into a provider schema.

Normal retrieval is:

```text
C(query) = C(session) ∪ C(active project) ∪ C(user)
```

No other project is searched unless the request names an explicit import or an
active bridge. Symlinks, junctions, WSL translations, and case differences must
be resolved before enforcing the boundary.

## Filesystem-first index

Use the structure already present in a project:

- paths and filenames;
- symbols, definitions, includes, and call sites;
- Git commits and work orders;
- configuration, tests, logs, and generated evidence;
- maintained summaries with provenance.

The first implementation uses filesystem metadata, deterministic text reads,
`rg`-style search, SQLite, and SQLite FTS5. No vector store is required for
1.0.1. FTS5 availability is a preflight check; if unavailable, LeafOS either
installs no substitute silently or falls back to filesystem search with an
explicit degraded status.

### Minimal SQLite surface

Keep the database small:

```text
projects
sources
observations
claims
claim_evidence
decisions
supersessions
bridges
documents_fts
```

Original project files remain authoritative. SQLite stores metadata, searchable
text, relationships, and hashes; it does not become the only copy of user
knowledge. The index must be disposable and rebuildable from local files plus
the append-only decision/observation records.

## Command contract

Extend the existing `context export` family without creating a second CLI:

```text
leafctl context search "renderer framebuffer"
leafctl context read <path-or-source-id>
leafctl context history <subject>
leafctl context decisions <subject>
leafctl context explain <claim-id-or-text>
leafctl context import theory:DFAE
leafctl context bridge vsper-v5.16 theory:DFAE
leafctl context export
```

Command semantics:

- `search` returns ranked source excerpts inside the active silo with source ID,
  project/version, path, lines, hash, and authority.
- `read` performs a boundary-checked source read and records what was consulted.
- `history` returns time-ordered observations and supersession events.
- `decisions` returns explicit decisions and their current/superseded state.
- `explain` shows a claim's evidence graph, authority comparison, conflicts,
  confidence, and unanswered gaps.
- `import` adds a named external context only to the current request/packet.
- `bridge` persists an explicit, reviewable cross-project relationship with a
  scope and direction; it never means “search everything.”
- `export` emits a bounded agent-facing packet, preserving the 1.0.0 contract.

The example bridge ID may retain `vsper-v5.16` for compatibility with supplied
text, while the human-facing canonical name remains VSEPR-SIM.

## Observation admission

Observation and memory are different states:

```text
event/file/runtime result
        -> observation
        -> evidence validation
        -> admission decision
        -> discard, session-only, or durable claim
```

The proposed score

```text
M = wU*U + wC*C + wN*N + wR*R + wP*P
```

may order candidates, but it cannot override authority rules. Initial weights
and thresholds remain a measured configuration decision. Hard admission rules
come first:

- Explicit user decisions are durable and attributed to the user.
- A passing runtime/test observation is stored with command, environment,
  timestamp, and artifact hash; it is not generalized beyond what was tested.
- A one-off failure is session history until repeated or explicitly promoted.
- Source-derived facts require stable source location and content hash.
- Model-derived prose is never admitted without supporting project evidence.
- Supersession closes the prior validity interval but never deletes history.

## Bounded context packet

Every agent-facing retrieval produces:

```text
TASK
PROJECT AND VERSION
AUTHORITATIVE FACTS
RELEVANT FILES
RECENT CHANGES
KNOWN GOTCHAS
CONFLICTING EVIDENCE
UNKNOWN / UNCERTAIN
PROVENANCE
```

Each fact points to evidence IDs; each file reference includes a normalized
path, content hash, and line or symbol range where possible. Packets carry a
token/byte budget and stop with an explicit omission summary rather than
silently truncating authority or conflict sections.

The 1.0.0 epoch system may submit observations after every review. The 1.0.1
admission system alone decides which become durable project knowledge.

## Delivery plan

### Phase 0 — Bench-001 corpus and oracle

Deliver:

- Read-only corpus manifest for `C:\FlowerOS\V\5.16.0` with root identity,
  version, branch, relevant source hashes, excludes, and snapshot timestamp.
- Separate manifests for v6 corpora used by version-comparison tests.
- Gold answers and evaluation rubrics stored outside the searchable benchmark
  index so retrieval cannot answer by finding its own test oracle.
- Negative-control corpus from an unrelated project.

Preconditions and known facts:

- `V5_BASELINE_LOCKED.txt` identifies v5.16.0 as immutable.
- `V5_BASELINE_MANIFEST.json` records branch
  `day84t-chemplus-declarative-vsepr`, frozen source, and a build blocked by the
  GCC C++ module dependency scanner.
- The same manifest says the reported binary version is 5.15.0. Bench identity
  must therefore use the source manifest and report the binary mismatch rather
  than inventing a clean v5.16 runtime claim.

Exit tests:

- Indexing never writes into the locked tree.
- Corpus hash changes invalidate the benchmark run.
- A normal v5.16 query cannot retrieve v6 or unrelated-project sources.

### Phase 1 — project identity and silo enforcement

Deliver:

- User and project context roots, minimal manifests, and canonical path IDs.
- Include/exclude policy honoring repository ignore rules plus explicit secret,
  cache, binary, and generated-output exclusions.
- Boundary checks for Windows, WSL, junctions, symlinks, and case folding.
- Explicit ephemeral imports and persistent scoped bridges.

Exit tests:

- Path traversal and link escape fail loudly.
- A VSEPR-SIM v5.16 task returns zero results from LeafOS, FlowerSim, theory,
  v6, or any other silo without an explicit import/bridge.
- Removing a bridge removes cross-project results after index refresh.

### Phase 2 — search, read, and rebuildable index

Deliver:

- Incremental filesystem scanner with path, size, mtime, hash, language, version,
  and authority metadata.
- SQLite FTS index and deterministic filesystem/grep fallback.
- `context search` and `context read` with stable citations.
- Full rebuild command/path exercised by recovery tests, without making a new
  decorative CLI surface.

Exit tests:

- Search results are deterministic for an unchanged corpus.
- Deleted/renamed files cannot survive as current evidence after refresh.
- Rebuilding from local persisted state produces the same normalized source
  identities and claim links.

### Phase 3 — claims, decisions, authority, and explanation

Deliver:

- Observation, claim, evidence, decision, conflict, and supersession records.
- Authority resolver with stable, testable tie rules.
- `context history`, `context decisions`, and `context explain`.
- Explicit `UNKNOWN` response containing the scope and evidence searched.

Exit tests:

- A project source contradiction defeats model prior.
- A newer explicit decision supersedes an older summary without deleting it.
- Equal-authority conflict returns `disputed`, not a guessed winner.
- `explain` reconstructs every accepted claim from local evidence only.

### Phase 4 — admission and maintained summaries

Deliver:

- Session observation queue and deterministic admission policy.
- Candidate scoring as advisory ordering with recorded components and weights.
- Maintained `identity`, `architecture`, `runbook`, and `gotchas` summaries whose
  statements link to claims/evidence.
- Staleness detection when source hashes or authoritative decisions change.

Exit tests:

- A transient crash remains session evidence unless admission policy promotes it.
- A changed authoritative file marks dependent summaries stale.
- Re-admission is idempotent; duplicate observations do not multiply claims.

### Phase 5 — CCIS packet integration

Deliver:

- Budgeted packet builder for the supplied CCIS Context Builder stage.
- Project facts ranked before derived summaries and model background.
- Conflict, uncertainty, and provenance sections protected from compression.
- Epoch-to-observation ingest and context-to-next-epoch export.

Exit tests:

- Packets remain within their declared budget and list omissions.
- All authoritative facts retain resolvable evidence links.
- A fresh 1.0.0 supervisor can consume the packet without reading the complete
  source corpus or prior agent transcript.

### Phase 6 — Bench-001, recovery, and release

Run every benchmark case from a fresh local index and again after restart:

| Case | Question class | Required behavior |
|---|---|---|
| A. Identity | Which parser does v5.16 use and where is its entry point? | Exact source/version citations; no v6 substitution. |
| B. Mechanism | Trace one declared object to rendered/exported output. | Multi-file parser -> construction -> runtime/simulation -> geometry -> renderer -> framebuffer -> output chain with provenance. |
| C. Version separation | Is a behavior v5.16 or v6? | Consult only the two named silos and attribute each claim to the correct version. |
| D. Experienced gotcha | Why does valid-looking input fail? | Retrieve admitted session/history evidence when source inspection alone is insufficient. |
| E. Supersession | What is authoritative after a newer renderer decision? | Return the current decision and show the superseded history. |
| F. Abstention | Does v5.16 support an unsupported feature? | Return `UNKNOWN` plus evidence searched; do not generate architectural fan fiction. |

Use an evaluator that scores citation correctness, version purity, evidence
coverage, abstention, and packet size separately from prose quality.

## LeafOS 1.0.1 release gates

| Gate | Pass condition |
|---|---|
| Silo | Bench-001 retrieves no unrelated/v6 context without an explicit scoped bridge. |
| Authority | Direct user/project evidence outranks LeafOS summaries and model prior in every conflict fixture. |
| Trace | Bench-001 reconstructs the selected real v5.16 input-to-output path with file- and line/symbol-level provenance. |
| Version | Every benchmark claim is scoped to v5.16, v6, or `UNKNOWN`; the known 5.16 source/5.15 binary mismatch is surfaced. |
| Update | New authoritative decisions supersede stale claims and summaries while retaining audit history. |
| Abstention | Unsupported queries return `UNKNOWN`, search scope, and missing evidence. |
| Compression | The packet is at most 20% of the consulted raw text size while retaining all evidence required by the oracle. |
| Recovery | Delete the disposable SQLite index, restart LeafOS, rebuild locally, and reproduce normalized claims and benchmark results. |
| Privacy/boundary | Secret exclusions, path traversal, symlink/junction escape, and accidental cross-project retrieval tests all pass. |
| 1.0 compatibility | Existing model, pack, run, swarm, task, epoch, status, and context-export contracts remain valid. |

## Explicit non-goals for 1.0.1

- Global semantic search across all user data.
- Automatic cross-project bridges.
- A vector database or embedding pipeline.
- Treating an LLM summary as the source of truth.
- Autonomous rewriting of project files or historical decisions.
- Cloud synchronization or multi-user knowledge sharing.
- Experience/adaptation policy; that belongs to the proposed 1.0.2 stage.
- Modifying the locked VSEPR-SIM v5.16.0 benchmark tree.

## Assumption ledger

| ID | Assumption | Status | Current evidence | Impact / action |
|---|---|---|---|---|
| L101-A1 | The benchmark project is named VSPER-SIM | CONTRADICTED | Current project doctrine and `C:\FlowerOS\V` use VSEPR-SIM; VSIM is the scripting layer. | Use canonical naming while retaining legacy IDs only where compatibility requires it. |
| L101-A2 | The locked v5.16 corpus exists locally | VERIFIED CURRENT | `C:\FlowerOS\V\5.16.0\V5_BASELINE_LOCKED.txt` and 2,609 non-ignored files observed on 2026-08-19; representative renderer sources are materially present. | Hash the selected benchmark corpus before every scored run. |
| L101-A3 | The v5.16 binary reports version 5.16.0 | CONTRADICTED | `V5_BASELINE_MANIFEST.json` records `binary_reported_version: 5.15.0`. | Make the mismatch a version-awareness fixture; do not silently normalize it. |
| L101-A4 | The v5.16 baseline currently builds | CONTRADICTED | The frozen manifest records build status `blocked` on the GCC C++ module dependency scanner. | Retrieval/index work may proceed read-only; runtime benchmark claims require separate current build evidence. |
| L101-A5 | SQLite FTS5 is available in every supported Python environment | UNVERIFIED | No LeafOS preflight currently checks it. | Add a doctor check and explicit filesystem-search fallback. |
| L101-A6 | A numeric admission score establishes truth | CONTRADICTED | Usefulness and novelty do not establish authority. | Use scores only to order candidates; hard evidence rules decide admission. |
| L101-A7 | The 1.0 epoch system already emits admissible observations | VERIFIED CURRENT | Phase D emits sealed evidence indexes, decisions, failures, next plans, and v2 context packets; the stock workload created a real 22-record epoch on 2026-08-20. | Stage 1 must still define which epoch observations are admissible as durable user context; schema validity alone does not establish authority. |
| L101-A8 | Newer evidence always wins | CONTRADICTED | A newer low-authority summary cannot supersede current source or explicit decisions. | Resolve by authority first, then validity/recency within the same authority. |
| L101-A9 | A 1.0.1 patch label is automatically appropriate | UNVERIFIED | This stage adds a substantial subsystem. | Retain 1.0.1 only if changes are additive and backward-compatible. |

## Definition of done

LeafOS 1.0.1 is complete only when Bench-001 passes from a fresh index, passes
again after restart/rebuild, refuses unrelated project evidence by default,
explains every accepted claim, preserves superseded history, and says `UNKNOWN`
when the project cannot support an answer. A searchable database by itself is
not the feature; correct authority under bounded context is the feature.
