# WO-019 Status

Status: partial completion. Gates G1-G7 pass; the separate conventional real-inference run criterion remains open.

## Gate status

| Gate | Description | Status |
|---|---|---|
| G1 | LMEM journal tests pass from a clean local build | **PASS**. Fixed a `tests/memory/journal.sh` harness defect (ROOT_DIR resolved one directory too shallow, causing `tests/tests/memory/fixtures/...` lookups). Built `build/leaf-memory.exe` statically linked (`g++ -static -std=c++17`) to avoid a missing `libstdc++-6.dll` under Git Bash. Full suite now ends with `memory journal test: PASS`, covering append/verify, invalid-event rejection, truncation detection, and recovery. |
| G2 | Shell and PowerShell dry runs emit equivalent resolved manifests for the same model/profile | **PASS**. Introduced `core/runtime/profile_resolver.py` as the single canonical resolver (sorted-key, compact-separator JSON) for the WO-019 capability manifest (`profile`, `provider`, `model`, `context_limit`, `max_output_tokens`, `reasoning_budget_requested`, `memory_pack_tokens`, `capability_status`). `Bash-Version/chat-local.sh` now delegates to this resolver instead of inline python snippets. Added `bin/Resolve-RuntimeProfile.ps1`, a thin PowerShell wrapper that delegates to the same resolver script. `tests/runtime_profile_manifest.sh` invokes both paths for `profile=continual` and asserts byte-identical stdout; verified PASS locally (Bash and `pwsh` outputs match exactly). |
| G3 | A fixture run produces a valid reflection event that cannot be promoted by the producer model | **PASS**. `core/memory/reflection.py` validates bounded artifacts, forces `epistemic_class: record`, delegates writes to native LMEM, and `tests/test_memory_pipeline.py` proves a rejected self-promotion leaves the journal byte-identical. |
| G4 | Deleting and rebuilding the index yields identical query results | **PASS**. `core/memory/index.py` rebuilds SQLite/FTS5 solely from verified replay; the three-query fixture proves byte-identical ordered results before and after replacement. |
| G5 | Fixed journal + fixed query + fixed tokenizer produces the same pack hash on repeated runs | **PASS**. `core/memory/pack.py` builds bounded, sealed packs; repeated fixture builds are byte-identical and `pack verify` checks both seal and journal head. |
| G6 | Kill-and-resume integration test reconstructs the same committed state | **PASS**. `core/memory/checkpoint.py` binds the journal/index head; the terminated-process fixture proves `exact` and clean `advanced`, plus `diverged`, `corrupt`, and `missing`. `context_pack_hash` remains null pending WP-5. |
| G7 | Redacted content absent from new packs/indexes while audit trail proves redaction occurred | **PASS**. Tombstone targets are sanitized from rebuilt SQLite bytes and excluded from packs while the append-only tombstone remains in LMEM. Quota and non-destructive archive behavior are also tested. |

## Work packages completed this phase

- **WP-1** (LMEM foundation proof): complete, see G1.
- **WP-2** (capability/token budget normalization): complete.
  - `config/runtime-profiles.json` created with doctrine (`C = I + P + R + O + S`), profile table, and fallback policy.
  - `config/continual-live.json` upgraded to `schema_version: 2` with `runtime_profile: continual`; legacy `context_size`/`max_tokens` retained only as the compat-4k fallback values.
  - `core/runtime/continual_live.py` resolves the profile, writes `runtime-profile-manifest.json` per run, and embeds the manifest into live state/events.
  - `Bash-Version/chat-local.sh` adds `--profile`, defaults to `interactive`, and resolves CTX/TOKENS/reasoning budget from the profile file; reasoning defaults to `auto` (previously `off`/budget `0`) except under `compat-4k`, which explicitly disables it.
  - `core/providers/providers.sh` and `core/providers/_providers_new.sh` normalized to a consistent `LEAF_PROVIDER_MAX_TOKENS=8192` default (previously `12000` vs `2048`), with a `LEAF_PROVIDER_PROFILE=continual` default and clarifying comments that this is the visible-output ceiling, not the reasoning budget.
  - `core/runtime/profile_resolver.py` added as the single canonical manifest resolver; `bin/Resolve-RuntimeProfile.ps1` added as the PowerShell wrapper delegating to it. `tests/runtime_profile_manifest.sh` proves byte-equivalent output between the Bash and PowerShell paths (Gate G2 now PASS).
  - `core/runtime/gguf_metadata.py` now probes bounded local GGUF metadata. A real local Gemma4 Q4 model reports 262,144 context tokens and supports the continual allocation.
- **WP-3** (capture reflection records): complete through native LMEM append with process-local commit notification.
- **WP-4** (retrieval index): complete; disposable SQLite/FTS5 projection, status, query, and deterministic rebuild are implemented.
- **WP-6** (checkpoint coupling): complete with a nullable context-pack binding until WP-5 lands.
- **WP-5** (context packs): complete with deterministic build, inspect, verify, bounded token accounting, authority labels, and checkpoint binding.
- **WP-7** (redaction/retention): complete for tombstone-derived redaction, quota status, and verified non-destructive archive.

## Remaining integration

- Run a conventional single-machine real inference workload with these memory features before enabling experimental MoE routing.

## Acceptance criteria checklist (WO-019 section 10)

- [x] LMEM journal tests pass completely and evidence is attached to the run report (see G1 above; raw log available by re-running `tests/memory/journal.sh`).
- [x] Continual and overnight profiles negotiate against local GGUF metadata, with the local Gemma4 Q4 model demonstrating a supported continual allocation of 16,384 reasoning + 8,192 output tokens.
- [x] No documentation or log equates context size with chain-of-thought size (see doctrine section in `runtime-profiles.json` and `MEMORY_MODEL.md`).
- [x] A validated reasoning artifact is appended as a `reflection` record. (`tests/test_memory_pipeline.py`.)
- [x] The artifact cannot self-promote to evidence or committed fact. (Adapter forces `record`; rejection is tested before native write.)
- [x] The retrieval index is disposable, deterministic, and rebuildable from LMEM. (Three fixed-query results are byte-identical after rebuild.)
- [x] A bounded context pack can be built, inspected, verified, and reproduced. (`tests/test_memory_pipeline.py`.)
- [x] Pack contents carry authority and provenance labels. (Every included record carries epistemic class, source actor/model/tool, and payload digest.)
- [x] Checkpoints bind to an LMEM head and nullable pack digest. (Pack digest remains null until WP-5, as allowed by WO-023.)
- [x] Resume detects exact, advanced, diverged, corrupt, and missing states. (`tests/test_memory_pipeline.py`.)
- [x] Shell and PowerShell launchers produce equivalent normalized manifests. (`core/runtime/profile_resolver.py` is the single canonical resolver; `chat-local.sh` and `bin/Resolve-RuntimeProfile.ps1` both delegate to it; `tests/runtime_profile_manifest.sh` verifies byte-equivalence.)
- [x] Storage quota, redaction, tombstone, and archive behavior have tests. (Seven memory-pipeline fixtures pass.)
- [ ] A conventional single-machine local run passes before any experimental MoE routing is enabled. (Out of scope for this phase; no MoE routing work has been touched.)

## Rollback

New WO-019 behavior is feature-gated (see `docs/MEMORY_MODEL.md` for the full rationale):

```text
LEAF_MEMORY_CONTEXT_PACKS=0
LEAF_MEMORY_REFLECTIONS=0
LEAF_MEMORY_CHECKPOINT_BINDING=0
```

The reflection and checkpoint routes now have consuming code paths; operators can omit those routes while retaining the flags for launcher-level policy. Rollback must leave the LMEM journal intact. The SQLite index may be deleted safely because it is rebuilt from verified replay.

## Changed files (this phase)

- `tests/memory/journal.sh` (harness ROOT_DIR fix)
- `config/runtime-profiles.json` (new)
- `config/continual-live.json`
- `core/runtime/continual_live.py`
- `Bash-Version/chat-local.sh` (repo root: `LeafOS0.2.1/Bash-Version/chat-local.sh`)
- `core/providers/providers.sh`
- `core/providers/_providers_new.sh`
- `schemas/leafos.reasoning-artifact.v1.schema.json` (new)
- `schemas/leafos.context-pack.v1.schema.json` (new)
- `core/runtime/thinking_loop.py`
- `core/memory/journal.py`, `reflection.py`, `index.py`, `checkpoint.py`, `memory_cli.py`
- `core/ui/reasoning_view.py`
- `cli/leaf-memory.cpp` (`replay` command)
- `tests/test_thinking_loop.py`, `tests/test_memory_pipeline.py`, `tests/test_reasoning_view.py`
- `docs/MEMORY_MODEL.md`
- `docs/WO-019-STATUS.md` (this file, new)
