# WO-020 — Thinking-Loop Reasoning Phase Engine

## Identity

- Owner/context: LeafOS WO-019 Persistent Reasoning Memory, tranche A (Thinking loops)
- Current day: Day 1
- Release target: WO-019 phase 2 (post 019-A)
- Branch: local workspace
- Scope boundary: `core/ui/live_stream.py`, `core/ui/chat.py`, new `core/runtime/thinking_loop.py`
- Authority: `LeafOS-WO-019-Persistent-Reasoning-Memory.md`, `docs/WO-019-STATUS.md` (Gate G3 precursor)

## Purpose

`core/ui/live_stream.py` (added under the chat-CLI enrichment pass) already renders a
"thinking -> streaming" phase transition with a smoothed tk/s readout, but it has no
concept of *structured* reasoning phases — it treats all streamed text as one
undifferentiated blob. WO-019's target THOUGHT/ACTION/CODE/MEMORY/SKILL/ERROR view
(gate downstream of G3) requires that a run's output be segmentable into typed phases
before it can ever be captured as a reflection record (WP-3) or projected live (WO-024).

This WO turns `LiveRatePrinter` into a phase-aware `ThinkingLoopEngine`: a small state
machine that classifies streamed chunks into `thinking | acting | coding | error` phases
using explicit markers (llama.cpp `<think>...</think>` style tags, or a configurable
regex/sentinel set), keeps per-phase token counts and tk/s, and exposes a structured
`phase_timeline` at the end of a run — the direct input WO-021 will append to LMEM as a
bounded reflection record, and WO-024 will render live.

## Acceptance criteria

- [x] `core/runtime/thinking_loop.py` defines `ThinkingLoopEngine` with `feed(chunk) ->
	  PhaseEvent | None` and `finalize() -> dict` (schema below).
- [x] Phase classification supports at minimum: `thinking`, `acting`, `coding`, `error`,
	  falling back to `thinking` for unclassified text (never silently drops chunks).
- [x] Per-phase token counts and tk/s are tracked using the existing EMA-smoothing
	  approach from `LiveRatePrinter` (no duplicate smoothing logic — refactor shared
	  math into a small internal helper importable by both modules).
- [x] `core/ui/chat.py`'s `_generate_live()` uses `ThinkingLoopEngine` alongside
	  `LiveRatePrinter` directly, with no change in the visible tk/s behavior already
	  validated (regression: same smoke test must still pass).
- [x] Output schema (reconciled with `schemas/leafos.reasoning-artifact.v1.schema.json`
	  in WO-021):
	  ```json
	  {
		"schema": "leafos.thinking-loop.v1",
		"run_id": "...",
		"phases": [{"phase": "thinking", "tokens": 42, "seconds": 1.9, "text_sha256": "..."}],
		"total_tokens": 128,
		"total_seconds": 4.2
	  }
	  ```
- [x] A dry-run test (offline, simulated stream) proves phase boundaries are detected
	  correctly for at least: pure-thinking response, thinking->acting response,
	  thinking->coding->error response.
- [x] The phase-engine change itself does not alter LMEM, index, or checkpoint semantics.

## Status

[W] WO-020: Thinking-loop reasoning phase engine
[D] Day 1: implementation complete
[I] DONE
[V] PASS: `python -B tests/test_thinking_loop.py`
[P] LOCAL
[N] Delivered to WO-021 and WO-024 consumers

## Out of scope

- Persisting phase timelines to LMEM (WO-021).
- Live CLI rendering of phases (WO-024).
- Real model-side `<think>` tag emission/training (consumes whatever tags the provider
  already emits or none at all — falls back to whole-response-as-thinking).
