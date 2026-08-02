# WO-023 — Checkpoint Binding and Resume Divergence Detection (WP-6, Gate G6)

## Identity

- Owner/context: LeafOS WO-019 Persistent Reasoning Memory, WP-6 (Memory persistence)
- Current day: Day 1
- Release target: WO-019 phase 2
- Branch: local workspace
- Scope boundary: new `core/memory/checkpoint.py`, `leafctl memory checkpoint bind|verify`
- Authority: WO-019 section 10 Gate G6; depends on WO-022 index (for `committed_fact_set_hash`)

## Purpose

`docs/WO-019-STATUS.md` lists WP-6 (checkpoint coupling) as **not started**. Gate G6
requires a "kill-and-resume integration test [that] reconstructs the same committed
state." Without this, every training/chat run that dies mid-stream has no principled way
to know whether resuming picked up exactly where it left off, advanced past it, diverged,
or is resuming against corrupt/missing state — this is the direct persistence gap behind
the user's "memory persistence" goal.

This WO implements checkpoint binding: a checkpoint record binds `memory.head_sequence`,
`memory.head_hash`, `context_pack_hash` (stubbed to null until WP-5 lands), and
`committed_fact_set_hash` (derived from the WO-022 index) at a point in time. Resume
compares the current journal head against a prior checkpoint and classifies the result as
exactly one of `exact | advanced | diverged | corrupt | missing`.

## Acceptance criteria

- [x] `leafctl memory checkpoint bind` writes a checkpoint record with the four fields
	  above plus a timestamp and run label.
- [x] `leafctl memory checkpoint verify <checkpoint>` classifies current state against
	  the checkpoint as one of the five defined states, matching the exact vocabulary in
	  WO-019 section 10.
- [x] `corrupt` classification is proven by a fixture that mutates a mid-journal byte
	  after checkpointing and confirms `verify` detects it (reuses the corruption-fixture
	  style from the G1 journal tests, not a new detector).
- [x] `missing` classification is proven by pointing `verify` at a checkpoint whose
	  journal file/head no longer exists.
- [x] A kill-and-resume integration test: start a simulated run, bind a checkpoint,
	  forcibly terminate, resume, and assert `verify` reports `exact` when nothing
	  changed and `advanced` when new events were appended cleanly.
- [x] `docs/WO-019-STATUS.md` Gate G6 and the corresponding acceptance-checklist row
	  updated to PASS with evidence.

## Status

[W] WO-023: Checkpoint binding and resume divergence detection
[D] Day 1: implementation complete
[I] DONE
[V] PASS: five-state and terminated-process fixture in `tests/test_memory_pipeline.py`
[P] LOCAL
[N] `context_pack_hash` remains null until the separate WP-5 context-pack WO lands

## Out of scope

- Context-pack building/hashing itself (separate WP-5 WO).
- Redaction/retention interplay with checkpoints (WO-025 / WP-7).
- Automatic resume orchestration in chat/training callers (future integration WO).
