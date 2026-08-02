# WO-025 — Enriched-Run Training Evidence and Checkpoint Bridge

## Identity

- Owner/context: Training subsystems (enriched runs), bridging board-game-lab into WO-019 memory
- Current day: Day 1
- Release target: WO-019 phase 2 / board-game-lab integration
- Branch: local workspace
- Scope boundary: `board_game_lab/trainer.py`, `board_game_lab/contracts.py`, `board_game_lab/hardware.py`
- Authority: user statement "'training' is basically just enriched runs atm"; depends on
  WO-021 (reflection append) and WO-023 (checkpoint binding)

## Purpose

`board_game_lab/trainer.py` already runs an evolutionary mutation/elitism loop with
`RunEvidence`/`TrainingCheckpoint` contracts and live games/s output, but its checkpoints
and evidence records are private to `board_game_lab` — they are not durable LMEM events
and cannot be resumed, verified, or queried through the WO-019 memory pipeline. Since
"training" here means enriched runs rather than weight updates, the highest-leverage
improvement is making every generation's evidence a first-class, queryable, resumable
memory event instead of a local-only JSON file.

This WO bridges `board_game_lab.trainer` to WO-019: each generation's `RunEvidence` is
appended as an LMEM event (reusing WO-021's validated append path with a new
`training-evidence` kind, not a new schema-less writer), and each `TrainingCheckpoint` is
bound through WO-023's `leafctl memory checkpoint bind` so a killed training run can be
resumed with the same `exact|advanced|diverged|corrupt|missing` vocabulary used
elsewhere in WO-019.

## Acceptance criteria

- [ ] `schemas/leafos.training-evidence.v1.schema.json` added, describing generation
	  index, mutation params, score, `RunEvidence.gpu_samples`, and elapsed time.
- [ ] `trainer.py`'s `run_generation()` appends a `training-evidence` LMEM event per
	  generation via the WO-021 append path (in-process call or subprocess to `leafctl`,
	  matching whichever integration style WO-021 exposes).
- [ ] `trainer.py`'s checkpoint writing is replaced/augmented with a call to
	  `leafctl memory checkpoint bind` at each generation boundary; the existing local
	  `TrainingCheckpoint` JSON file is retained as a convenience artifact, not the
	  source of truth.
- [ ] A dry-run test (existing dry-run mode, no real game binaries) runs 2-3 generations,
	  confirms LMEM events were appended and a checkpoint bound, then simulates a kill
	  and resume, asserting `leafctl memory checkpoint verify` reports `exact` or
	  `advanced` as appropriate.
- [ ] Live training output (already validated games/s printer) is unchanged in visible
	  behavior — this WO adds durability, not new console output (CLI projection is
	  WO-024's job if later extended to training).
- [ ] `board_game_lab/__init__.py` exports remain stable (`adapters`, `select`, `train`)
	  unless a new durability-check helper is intentionally added and documented.

## Status

[W] WO-025: Enriched-run training evidence and checkpoint bridge
[D] Day 1: not started
[I] TODO
[V] PENDING
[P] LOCAL
[N] Depends on WO-021 (append path) and WO-023 (checkpoint bind/verify); should not start
	until at least one of those has a working CLI entry point to call into

## Out of scope

- Real model weight training/gradient updates (explicitly out of scope per user framing
  of "training" as enriched runs).
- Retrieval/query of training evidence beyond what WO-022's index already provides.
- Live reasoning-view rendering for training runs (future extension of WO-024).
