# WO-022 — Deterministic Retrieval Index (WP-4, Gate G4)

## Identity

- Owner/context: LeafOS WO-019 Persistent Reasoning Memory, WP-4 (Memory persistence)
- Current day: Day 1
- Release target: WO-019 phase 2
- Branch: local workspace
- Scope boundary: new `core/memory/index.py`, `leafctl memory index *` subcommands
- Authority: WO-019 section 10 Gate G4; depends on WO-021 real reflection records

## Purpose

`docs/WO-019-STATUS.md` lists WP-4 (retrieval index) as **not started**: Gate G4 requires
"deleting and rebuilding the index yields identical query results." Today there is no
index at all — LMEM is append-only and has no queryable secondary structure.

This WO adds a disposable, fully-rebuildable SQLite/FTS5 index over the LMEM journal
(events plus, once WO-021 lands, reflection records). "Disposable" is load-bearing: the
index must never be a source of truth — deleting it and rebuilding from the journal must
be a supported, tested, and *undetectable* operation from the query layer's perspective.

## Acceptance criteria

- [x] `leafctl memory index build` creates a SQLite database with an FTS5 virtual table
	  over journal event text/kind/timestamp, driven entirely from journal replay (no
	  other input source).
- [x] `leafctl memory index status` reports last-built head hash/sequence and row count.
- [x] `leafctl memory index rebuild` replaces and rebuilds the index from scratch.
- [x] A fixture test runs `build`, records query results for >=3 representative queries,
	  runs `rebuild`, re-runs the same queries, and asserts byte-identical result sets
	  and ordering (this is the literal Gate G4 acceptance test).
- [x] The index file location is documented and is excluded from any backup/authority
	  path that treats it as durable state (journal remains sole durable authority).
- [x] `docs/WO-019-STATUS.md` Gate G4 updated to PASS with the fixture test referenced as
	  evidence.

## Status

[W] WO-022: Deterministic retrieval index
[D] Day 1: implementation complete
[I] DONE
[V] PASS: deterministic three-query rebuild fixture in `tests/test_memory_pipeline.py`
[P] LOCAL
[N] Journal remains sole durable authority; SQLite file is disposable

## Out of scope

- Context-pack building (separate WP-5 WO).
- Ranking/relevance tuning beyond FTS5 defaults.
- Any query surface beyond `leafctl memory query` used for fixture verification.
