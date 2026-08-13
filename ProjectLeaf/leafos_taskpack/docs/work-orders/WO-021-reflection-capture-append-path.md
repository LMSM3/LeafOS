# WO-021 — Reflection Capture: Bounded Thinking-Loop Append Path

## Identity

- Owner/context: LeafOS WO-019 Persistent Reasoning Memory, WP-3 completion (Gate G3)
- Current day: Day 1
- Release target: WO-019 phase 2
- Branch: local workspace
- Scope boundary: `leafctl` memory subcommands, `core/memory/`, `schemas/leafos.reasoning-artifact.v1.schema.json`
- Authority: WO-019 section 10 acceptance criteria (Gate G3); depends on WO-020 `phase_timeline` output

## Purpose

`docs/WO-019-STATUS.md` marks Gate G3 as **schema only**: the bounded reasoning-artifact
contract exists at `schemas/leafos.reasoning-artifact.v1.schema.json`, but there is no
`leafctl memory append` path that validates a reflection payload against it, and no proof
that the artifact "cannot be promoted by the producer model" (i.e. self-promotion to
evidence/committed-fact is structurally blocked, not just documented as doctrine).

This WO closes WP-3 for real: it takes the `phase_timeline` produced by WO-020's
`ThinkingLoopEngine`, wraps it as a `reflection` LMEM event, validates it against the v1
schema, and appends it through the existing G1-proven journal path
(`tests/memory/journal.sh` foundation) — with an explicit authority check that rejects
any payload carrying `authority: evidence` or `authority: committed_fact` when the writer
identity is the producer model itself.

## Acceptance criteria

- [x] `leafctl memory append --kind reflection` accepts a JSON payload, validates it
	  against `schemas/leafos.reasoning-artifact.v1.schema.json`, and rejects invalid
	  payloads with a non-zero exit and a structured error (no partial journal writes).
- [x] The append path enforces reflection `epistemic_class=record` server-side regardless of what the
	  caller requests; any attempt by the producer-model identity to set
	  `authority=evidence|committed_fact` is rejected before journal write.
- [x] A fixture test proves: (a) a valid reflection appends and is readable back via
	  journal replay; (b) an attempted self-promotion is rejected and the journal is
	  byte-identical to before the attempt (extends the existing corruption/recovery test
	  style from WP-1).
- [x] Journal append reuses the existing `build/leaf-memory.exe` binary/append path from
	  G1 — no second, parallel append implementation.
- [x] `docs/WO-019-STATUS.md` Gate G3 and the two related acceptance-checklist rows are
	  updated to PASS with evidence log entries once the fixture test passes.
- [x] WO-020's `phase_timeline` schema and this WO's reflection payload schema are
	  reconciled (either the artifact schema embeds `phase_timeline` directly, or the
	  mapping between them is documented in-line).

## Status

[W] WO-021: Reflection capture bounded append path
[D] Day 1: implementation complete
[I] DONE
[V] PASS: `python -B tests/test_memory_pipeline.py`
[P] LOCAL
[N] Native append and immediate commit callback available to index/live-view consumers

## Out of scope

- Retrieval indexing of reflection records (WO-022 / WP-4).
- Context-pack building from reflections (WP-5, separate WO).
- Live rendering of reflection capture events (WO-024).
