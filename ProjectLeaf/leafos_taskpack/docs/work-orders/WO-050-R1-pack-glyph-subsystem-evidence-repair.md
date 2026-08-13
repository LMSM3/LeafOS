# WO-050-R1 — Pack Glyph Subsystem-Evidence Repair

## Identity

- Owner/context: LeafOS 0.2.2 PowerShell presentation and subsystem state
- Current day: retroactive Day 1 repair to completed WO-050
- Repair date: 2026-08-11
- Release target: LeafOS 0.2.2
- Branch: local merged OneDrive snapshot
- Parent: [WO-050](WO-050-animation-quality-restoration.md)
- Downstream reference: [WO-053-A](WO-053-A-model-pack-installer-user-path-hardening.md)

## Repair statement

The beta statement that pack glyphs were "cosmetic—never evidence" was too
broad for a feature whose purpose is subsystem indication. This repair makes
the prompt glyph a typed, bounded evidence projection:

- a visible glyph proves that LeafOS found a live owned subsystem process, or
  that the operator explicitly requested a demo-grade projection;
- a visible customized glyph additionally proves that the active projection
  resolved and bound the selected pack's `identity.symbol`;
- an active subsystem without a resolved pack uses canonical `leaf.active`
  (`🍃`);
- no active subsystem produces no LeafOS prompt glyph.

Manifest identity remains passive at rest. The glyph does not replace distinct
model-residency, provider-health, or capability-authorization evidence.

## Acceptance criteria

- [x] Remove the blanket cosmetic-only indicator claim from code and user documentation.
- [x] Require active subsystem evidence before decorating the PowerShell prompt.
- [x] Resolve live activity from an explicit PID, the Vulkan-provider PID, or an active-run lease PID.
- [x] Keep a clearly labeled demo override for presentations without a launched provider.
- [x] Render the selected pack glyph when identity resolves and `🍃` when it does not.
- [x] Emit a versioned evidence object with exact positive and negative claim boundaries.
- [x] Add a JSON Schema for `leafos.subsystem_indicator_evidence.v1`.
- [x] Preserve pack-constructor separation from capability, authority, health, and routing.
- [x] Preserve quiet-process logging and no-window behavior.
- [x] Add regression coverage for live, inactive, fallback, customized, demo, prompt, CLI, and constructor paths.

## Implementation record

- `core/powershell/LeafOS.psm1` now exports `Get-LeafSubsystemActivity` and
  attaches `leafos.subsystem_indicator_evidence` to every indicator result.
- The prompt hook calls `Format-LeafPackIndicator -RequireActive`, so stale or
  absent activity fails closed instead of leaving a decorative status mark.
- `schemas/leafos.subsystem-indicator-evidence.v1.schema.json` freezes the
  evidence fields and bounded claim vocabulary.
- The pack constructor advertises the evidence contract while retaining
  `capability_bearing: false`; pack identity participates in evidence only when
  an owning runtime validates liveness and binds it.
- Human indicator status now prints active state, subsystem, evidence grade,
  evidence source, and claims.

## Verification evidence

- 2026-08-11: PowerShell AST parsing passed for `LeafOS.psm1`.
- 2026-08-11: a live-process smoke check returned glyph `✿`, pack `ficus`,
  evidence grade `process`, and claims `subsystem.process.active` plus
  `pack.identity.bound`.
- 2026-08-11: 23 focused PowerShell-indicator and pack-constructor tests passed.
- 2026-08-11: the evidence schema parsed as JSON and its required contract is
  asserted by the focused suite.
- 2026-08-13: reconciled the implementation, schema, CLI, pack constructor,
  documentation, and focused tests into the canonical source tree; 31 scoped
  tests passed there and the inactive Ficus preview remained truthfully graded
  `none` rather than claiming a loaded subsystem.

## Status

[W] WO-050-R1: pack glyph subsystem-evidence repair
[D] Retroactive Day 1 repair: correct the completed WO-050 beta contract without rewriting its history
[I] DONE: live-process gating, pack binding, leaf fallback, demo grading, typed evidence, docs, and tests are complete
[V] PASS: 31 canonical-tree indicator/constructor tests, dual-host AST parsing, and live Ficus preview
[P] LOCAL: implementation reconciled into canonical `C:\R\LeafOS0.2.2`; no staging, commit, or publication performed
[N] Carry the evidence object into future resident/provider status surfaces without broadening its claims implicitly

## Out of scope

- Treating one active process as proof that every model in a pack is resident.
- Replacing provider-health or capability-authorization contracts.
- Starting or stopping inference providers as part of prompt rendering.
- Opening WO-053-A Day 1 or changing the typed-loop series implementation order.
