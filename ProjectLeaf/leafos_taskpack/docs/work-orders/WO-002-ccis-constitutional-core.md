# WO-002 — CCIS constitutional core inside LeafOS (Scientific Change Loop integration)

## Identity

- Owner/context: liamm / LeafOS core architecture
- Current day: Day 1 close-ready (execution-backed validator evidence complete; Day 2 not opened)
- Release target: Milestone 1, local nested loop passing the CCIS gate on one real repository
- Branch: `agent/organic-0.9.4-snapshot` (`C:\R\LeafOS0.2.2`)
- Scope boundary: `ccis/*`, `loop/*`, `.leafos/*` state and evidence layout; two CLI dispatch entries

## Acceptance criteria

- [x] `ccis/` subtree created: `principles/`, contracts, and kernel modules (`transition_gate`, `evidence_gate`, `revision_policy`, `acceptance_policy`).
- [x] Task envelope schema includes objective (invariants, tolerances, stopping conditions), scope, budget, validators, authority.
- [x] State machine implemented with `GATED` state and outcomes `ACCEPTED` / `REVISE` / `REJECTED` / `BLOCKED` / `ESCALATED`.
- [x] Append-only `events.jsonl` authoritative; metadata reserves SQLite for cache only.
- [x] Complete 18-artifact evidence bundle produced and hash-verified on an accepted transition in a retained real Git repository.
- [x] Explicit `leafos task accept` stages through `git apply --cached`; no automatic merge or working-tree application.
- [x] Interrupt / restart / resume from checkpoint demonstrated by deleting projections and rebuilding from events.
- [x] Reject + rollback restores original tracked worktree state, hash-verified.
- [x] Canonical `CCIS-Inside-LeafOS_v2.md` imported with source/projection hashes; all four `principles://` references resolve to exact authoritative wording.

## Day 1 acceptance criteria

- [x] `leafos ccis validate` executes declared command validators without a shell and only inside an isolated workspace.
- [x] The authoritative repository and its subdirectories are refused as validator workspaces.
- [x] Per-validator command, duration, exit status, stdout, and stderr are persisted under the run.
- [x] `ccis evaluate` can consume the runner-produced result record without a hand-authored validator JSON file.
- [x] The final 18-artifact bundle contains the captured command stream and real validator logs/results.
- [x] Required failures and timeouts fail closed and produce `REVISE` or `BLOCKED` recommendations.

## Status

[W] WO-002: CCIS constitutional core + Scientific Change Loop gate integration
[D] Day 1 close-ready: execution-backed validator evidence complete; Day 2 not opened
[I] DONE: isolated runner, CLI integration, authoritative event binding, and real-log evidence implemented
[V] PASS: 15 CCIS tests + retained three-command Day 1 replay; final state STAGED at event 12
[P] LOCAL: LeafOS index untouched; two isolated demo indexes staged; no commit/merge; unrelated changes preserved
[N] Next architecture selected: open WO-051 for typed tasks and a rebuildable event-derived allocation heap; Day 2 remains unopened until implementation begins

## Evidence log

- 2026-08-03: supplied revised WO accepted as the active LeafOS scope; Day 0 retained.
- 2026-08-03: canonical source appeared in Downloads and was imported under `ccis/principles/`; original and normalized-projection SHA-256 values are locked in `manifest.json`.
- 2026-08-03: seven strict draft 2020-12 schemas and seven coherent examples added; dependency-free contract validation passed.
- 2026-08-03: hash-chained append-only events, atomic projections/checkpoints, legal transition gate, evidence gate, revision budgets, and explicit acceptance policy implemented.
- 2026-08-03: real temporary Git repository accepted-path proof traversed every canonical state, resumed from deleted projections, produced the complete 18-artifact bundle, refused bad confirmation, and staged only through literal `leafos task accept <task-id>`.
- 2026-08-03: rejected-path proof reached `ROLLED_BACK` with matching target/restored hashes and no candidate file in the working tree.
- 2026-08-03: tampered event payload and tampered evidence artifact both failed closed before staging.
- 2026-08-03: 12 CCIS tests passed; 16 JSON documents parsed, Python compiled, Bash and PowerShell parsed, and the PowerShell CLI help route resolved successfully.
- 2026-08-03: retained Bloom Ledger demo started from a three-file baseline Git commit (`8b3e90f`) containing only README/starter materials; the isolated candidate added 11 files and 443 lines.
- 2026-08-03: six financial-model/CLI tests and compilation passed; immutable `starter/` inputs had no staged diff.
- 2026-08-03: demo exposed and fixed leading-dotfile scope normalization; a focused regression test raises the CCIS suite to 13 tests.
- 2026-08-03: exact `leafos task accept demo_bloom_ledger_m1` advanced the retained run to `STAGED` at event 11; baseline working-content hash remained unchanged and no commit or merge occurred.
- 2026-08-03: 18-artifact evidence bundle hash `sha256:f86c0a64fa6647afbcf0da6bbff0d6c9bfb5dca0bf16b6e61623aa67efb79fa3`; final event hash `sha256:62b6ac7905725bed0751583e25a03bb9c0321973b69ba7ea000e250000bcbcf7`.
- 2026-08-03: combined watcher displayed retained CCIS state and all 12 deterministic financial-garden months, then exited normally.
- 2026-08-03: Day 1 opened after operator continuation; objective is execution-backed, isolated validator evidence rather than hand-authored result claims.
- 2026-08-03: added `ccis validate --run <run> --workspace <isolated>`; commands execute as argv with `shell=False`, bounded timeouts, and no authoritative-repository overlap.
- 2026-08-03: runner persists per-command timing/status, stdout, stderr, validator results, workspace hashes, and a hash-bound `ccis.validation.completed` event.
- 2026-08-03: `ccis evaluate` now defaults to runner-produced results; evidence creation rejects result drift from either the gated evaluation or authoritative validation event.
- 2026-08-03: 15 CCIS tests passed, including repository/descendant refusal, real output capture, nonzero exit to `REVISE`, timeout to `BLOCKED`, and post-validation tamper refusal.
- 2026-08-03: fresh retained task `demo_bloom_ledger_day1` ran unit tests, compilation, and finite watch directly through CCIS; all three command records report `PASSED` and `shell=false`.
- 2026-08-03: Day 1 bundle contains 18 hash-verified artifacts; bundle hash `sha256:48f3b9c611d45819215c672e05e0b57f30e07a5bfc03feef299e26242fae237b`, final event hash `sha256:7646e39e8919c42ff2ad0f5c1f4fe543307ee6767c2dc25d4024e988df9d92a6`.
- 2026-08-03: operator selected typed task architecture plus a rebuildable allocation heap as the immediate next plan; the expanded WO-051–WO-061 line now orders evidence debugging, real llama.cpp evaluation, containment, coherent implementation, scientific trial, and improvement propositions.

## Carry-forward

- Milestone 1 has now repeated with canonical principles and without manual state repair; worker separation/filesystem queue is eligible for a future Day 2 scope decision.
- Flower pack capability semantics remain deferred to Milestone 4 (see WO-001 for pack install path status).

## Out of scope

- Multiple coordinators / consensus.
- Message broker transport (Phase 4).
- Automatic acceptance authority for trusted task classes.
- Commit, merge, or working-tree application by the CCIS kernel.
