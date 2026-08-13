# WO-LOOP4 — Typed Results, Errors, Progress, and Accessible Output

## Identity

- Owner/context: liamm / LeafOS coherent loop experience
- Current day: Day 0 (plan compiled; implementation not started)
- Release target: LeafOS 0.2.2 coherent loop stage
- Branch: `agent/organic-0.9.4-snapshot`
- Series position: after WO-LOOP3 and before WO-LOOP5
- Scope boundary: typed result envelope, human/JSON renderers, exit codes, errors, progress events, accessibility, and cross-platform output tests

## Objective

Make every command describe the same underlying result to people and programs, with honest progress, actionable errors, stable exit codes, and accessible output across supported shells.

## Relationship to LOOP1

LOOP1 requires one visible vocabulary and no fictional diagram or progress state. LOOP4 turns that principle into a single rendering and error contract consumed by canonical commands and the `plz` alias.

## Live-inference intent

Live inference must expose real phases—allocation, model loading, health readiness, prompt submission, token streaming, validation, cleanup, and gating. A spinner cannot claim generation before tokens arrive, and mock/fallback output must be visibly classified.

## Typed task contract

- `system.result_surface.verify.v1` compares the canonical typed result with human, JSON, redirected, and cross-shell renderings.
- Every result carries command/action, target, state, disposition, resource summary, evidence refs, blockers, legal next action, registry digest, and evidence class.
- Stable exit codes are: `0 success`, `2 invalid_input`, `3 blocked`, `4 rejected`, `5 escalated`, `6 resource_unavailable`, `7 integrity_failure`, and `70 internal_failure`.
- Progress is an ordered typed event stream, not terminal animation state.

## LOOP6 test adoption

Every [LOOP6](WO-LOOP6-real-repository-scientific-outcome-tests.md) C01–C09 and R10–R16 outcome must render from one typed record. Human and JSON modes must agree on `NOT_RUN`, `RUNNING`, `PASS`, `FAIL`, or `BLOCKED`, the evidence class, observed-versus-expected mismatch, repository safety, and the one legal next action.

## Acceptance criteria

- [ ] Human and `--json` output are projections of the same typed result and agree on state, disposition, identifiers, resources, evidence, and next action.
- [ ] Canonical `leafos task` and `plz` render equivalent results and return identical exit codes.
- [ ] Every error states what failed, why, what remains authoritative, what evidence remains valid, whether the project changed, and one legal next action.
- [ ] Default output suppresses stack traces while retaining trace references and detailed evidence logs.
- [ ] `--verbose` adds commands, digests, timings, resource and evidence detail without changing semantics.
- [ ] Progress distinguishes waiting, eligible, leased, model_loading, running, streaming, validating, gated, blocked, and completed.
- [ ] Waiting output names the dependency, authority, claim, lease, model, server, evidence, or checkpoint being awaited.
- [ ] No progress animation continues indefinitely without heartbeat/staleness classification and a cancellation/status path.
- [ ] Color is optional; state remains legible in NO_COLOR, plain terminals, redirected output, PowerShell, CMD-facing launch, Bash, and Linux.
- [ ] Snapshot tests and semantic JSON tests derive from the same fixtures rather than maintaining unrelated expectations.

## Implementation sequence

1. Freeze the typed result, error, progress-event, evidence-class, and exit-code vocabularies.
2. Build one renderer boundary for human, JSON, verbose, and redirected modes.
3. Bind canonical and alias commands to the same renderer and error mapper.
4. Instrument live-inference phases using actual runtime events and token arrival.
5. Add stale-wait, cancellation, integrity, resource, and internal-failure fixtures.
6. Run accessibility and cross-shell output tests without depending on color or Unicode.
7. Publish minimal/realistic help examples generated from tested fixtures.
8. Pass the result surface to LOOP5 for end-to-end verification.

## Owned doctrine clauses

This WO owns clauses 53–62 and 73–75 from the supplied **LeafOS Coherent Experience and Resource Doctrine**. Other LOOP WOs may reference these clauses but may not redefine them.

- **D53.** Errors must identify what failed, why it failed, what remains safe, and what action is permitted next.
- **D54.** Error messages must avoid stack traces by default while preserving detailed logs for inspection.
- **D55.** `--verbose` must add useful evidence, not repeat ordinary output with more punctuation.
- **D56.** `--json` must produce a stable typed result suitable for scripts and later LeafOS components.
- **D57.** Human-readable output and JSON output must represent the same underlying result.
- **D58.** Every command must support predictable exit codes for success, rejection, blockage, invalid input, and internal failure.
- **D59.** Progress output must distinguish waiting, running, validating, blocked, and completed states.
- **D60.** Long-running commands must report what resource or dependency they are waiting for.
- **D61.** A progress indicator must not imply advancement when no state transition has occurred.
- **D62.** The CLI must never hide an indefinite wait behind an animated spinner.
- **D73.** Visual consistency includes indentation, headings, symbols, timestamps, identifiers, table layout, and severity labels.
- **D74.** Color may reinforce meaning, but no state may depend on color alone.
- **D75.** Plain terminals, redirected output, Windows shells, and Linux shells must receive usable results.

## Status

[W] WO-LOOP4: result/error/progress/accessibility contract
[D] Day 0: plan compiled; implementation not started
[I] TODO
[V] DISCOVERY: error, JSON, progress, visual, and live-inference presentation requirements were separated from execution authority
[P] LOCAL: planning document only; unrelated worktree changes remain unstaged
[N] After LOOP3, freeze the result and exit-code schemas before implementing presentation changes

## Evidence log

- 2026-08-03: Allocated doctrine clauses 53–62 and 73–75 to this WO without duplication.
- 2026-08-03: Defined `system.result_surface.verify.v1` as the typed verification task for this scope.

## Carry-forward

- LOOP5 verifies the same result across the complete success, interruption, rejection, and acceptance paths.
- WO-061 consumes typed measurements, not scraped terminal text.
- Future TUI/browser views remain projections of this result contract.

## Out of scope

- A separate state authority inside the renderer, TUI, or JSON serializer.
- Persisting private chain-of-thought.
- Treating animation frames as authoritative progress.
- Changing task disposition based on terminal capabilities.
