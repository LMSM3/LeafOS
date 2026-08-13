# WO-050 — LeafOS Animation Quality Restoration

## Identity

- Owner/context: LeafOS 0.2.2 presentation layer
- Current day: LeafOS official Day 1 / calendar Day 2
- Release target: 0.2.2
- Branch: `agent/organic-0.9.4-snapshot`
- Scope boundary: `C:\R\LeafOS0.2.2`; FlowerOS and VSPER-SIM excluded

## Acceptance criteria

- [x] Restore the documented shared Bash palette authority.
- [x] Remove literal `${C_*}` output from Bash installer and animation surfaces.
- [x] Correct malformed true-color sequences.
- [x] Separate color capability from Unicode/ASCII glyph selection.
- [x] Preserve the existing `home.render` API used by tests and callers.
- [x] Complete terminal review of menu, home, installer static output, and forced/reduced motion paths.
- [x] Disable motion automatically for redirected output and honor explicit reduced-motion controls before force flags.
- [x] Keep color, Unicode glyphs, and motion as independent capabilities.
- [x] Use bounded `READY` transitions that do not falsely report command success before execution.

## Status

[W] WO-050: LeafOS 0.2.2 animation and presentation repair
[D] Day 1 -> Day 2: regression isolation and focused restoration
[I] DONE: shared palette/motion contract, installer integration, accessibility behavior, and terminal review complete
[V] PASS: historical 42 focused/81 syntax checks plus 25 current focused tests, 5 touched-script syntax checks, menu/home captures, reduced installer, and forced-motion capture
[P] LOCAL: unrelated pre-existing worktree changes remain unstaged
[N] Review WO-050 and WO-051 together; Monday event mismatch remains a separate runtime concern

## Evidence log

- 2026-08-03: scope selected from LeafOS, FlowerOS, and VSPER-SIM based on current activity and the known UX regression.
- 2026-08-03: baseline `test_home_state.py` failed because `home.render` had been removed.
- 2026-08-03: missing documented `core/brand/palette.sh`, 39 literal color-variable `printf` sites, invalid RGB spacing, and ineffective `color("")` probes identified.
- 2026-08-03: Python palette, home, program, and TUI groups passed 42 focused tests after restoring compatibility and robust Windows/MSYS output decoding.
- 2026-08-03: all 81 shell files passed `bash -n`; the shared shell palette passed forced-color/NO_COLOR smoke checks; literal color-variable `printf` sites reduced from 39 to 0.
- 2026-08-03: root `leafos.ps1 menu` returned exit 0 in ASCII mode, exposed option 7 `Open local stack`, and emitted no literal color variables.
- 2026-08-03: a safe reduced installer run returned exit 0 with real ANSI output and completed both animation steps without leaking `${C_*}` text.
- 2026-08-03: repository-wide `test-all.sh` advanced through UI sourcing/status and stopped at a pre-existing Monday durable-stream error: `event sequence mismatch at line 194`; no runtime state was rewritten.
- 2026-08-03: added a shared TTY-aware motion contract with `auto`/`always`/`reduce`, accessibility precedence, independent Unicode control, validated delay override, bounded transitions, and stable redirected output.
- 2026-08-03: Bash installer/model surfaces now use the shared transition and finish at `READY`; real `OK`/`FAILED` remains tied to command exit rather than animation completion.
- 2026-08-03: 25 focused Python tests passed, including five new shell-motion contract tests; five touched Bash files passed syntax checks.
- 2026-08-03: actual PowerShell menu/home captures, reduced redirected installer run, and forced ASCII motion capture returned exit 0 with readable state and no false progress claim.

## Out of scope

- Installation engine or model-download behavior.
- FlowerOS loop engineering.
- VSPER-SIM chemistry/runtime work.
- Publication or staging of the existing dirty worktree.

## Retroactive repair addendum — 2026-08-11

[WO-050-R1](WO-050-R1-pack-glyph-subsystem-evidence-repair.md) corrects the
later beta-era statement that PowerShell pack glyphs were purely cosmetic. The
glyph is now a typed, fail-closed projection of active subsystem evidence and,
when customized, pack-identity binding. This additive repair does not rewrite
WO-050's historical Day 1 completion evidence.
