# WO-024 — Live Reasoning/Action CLI Projection (THOUGHT/ACTION/CODE/MEMORY/SKILL/ERROR)

## Identity

- Owner/context: LeafOS WO-019 Persistent Reasoning Memory, live-view extension (goal C)
- Current day: Day 1
- Release target: WO-019 phase 2
- Branch: local workspace
- Scope boundary: `core/ui/live_stream.py`, `core/ui/chat.py`, new `core/ui/reasoning_view.py`
- Authority: user-clarified goal C; depends on WO-020 (phase engine) and WO-021 (reflection append)

## Purpose

The chat CLI already streams tokens live via `LiveRatePrinter` with a smoothed tk/s
readout (validated in the earlier chat-enrichment pass), but it renders undifferentiated
text — there is no visual distinction between the model thinking, taking an action,
emitting code, touching memory, invoking a skill, or hitting an error. The user's goal C
is explicit: a live CLI view that projects **THOUGHT / ACTION / CODE / MEMORY / SKILL /
ERROR** as first-class, visually distinct streams, sourced directly from WO-019 state
(reflection records, checkpoint events, LMEM appends) rather than being a cosmetic-only
change.

This WO builds `ReasoningView`, a renderer that consumes `PhaseEvent`s from WO-020's
`ThinkingLoopEngine` in real time plus asynchronous LMEM-append notifications (from
WO-021) and checkpoint/skill events, and renders each on its own labeled, colorized
line/region without breaking the existing tk/s display contract.

## Acceptance criteria

- [x] `core/ui/reasoning_view.py` defines `ReasoningView` with `on_phase(event)`,
	  `on_memory_event(event)`, and `on_skill_event(event)` hooks, each rendering with a
	  distinct label/prefix: `THOUGHT`, `ACTION`, `CODE`, `MEMORY`, `SKILL`, `ERROR`.
- [x] Reuses `LiveRatePrinter`'s smoothing/refresh primitives (no duplicate refresh-timer
	  logic); tk/s readout remains visible and unchanged from the already-validated
	  baseline.
- [x] `core/ui/chat.py` wires `ReasoningView` into `_generate_live()` behind a
	  `--reasoning-view` flag (default on for interactive TTY, off for non-TTY/pipe
	  output, matching existing simulated-stream fallback conventions).
- [x] A `MEMORY` line can be emitted immediately from WO-021's process-local commit callback
	  record during the same run (event-driven, not polled).
- [x] A dry-run smoke test (simulated stream, no live model/server) exercises all six
	  label types at least once and captures output for visual/diff review.
- [x] No change to underlying LMEM/journal/checkpoint semantics — this WO is
	  presentation-only, consuming events produced by WO-020/WO-021/WO-023.

## Status

[W] WO-024: Live reasoning/action CLI projection
[D] Day 1: implementation complete
[I] DONE
[V] PASS: `python -B tests/test_reasoning_view.py`
[P] LOCAL
[N] Skill hook is ready; invocation subsystem remains outside this WO

## Out of scope

- A skill-invocation subsystem itself (stub `on_skill_event` with a synthetic event in
  the smoke test until one exists).
- Non-CLI (web/GUI) projection surfaces.
- Historical replay of past runs' reasoning views (live-only for this WO).
