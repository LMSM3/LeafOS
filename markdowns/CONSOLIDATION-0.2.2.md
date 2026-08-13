# LeafOS 0.2.2 consolidation

Date: 2026-08-04

## Source authority

- Canonical LeafOS source: `C:\R\LeafOS0.2.2`
- Canonical FlowerOS consumer: `C:\FlowerOS`
- Branch: `agent/organic-0.9.4-snapshot`
- Baseline commit: `adbc2666524641669d9ceb171d50efc893fb3693`
- Technical authority: `LEAFOS-CONTINUAL-BLOOM-PRIMARY-REFERENCE.formatless.tex`

The OneDrive export and AppData Temp installer copies are not source locations.
Generated installs, caches, and sandboxes must not receive product source edits.
The redundant `C:\R\LeafOS0.9.5` checkout was removed from the active namespace
and recoverably quarantined at
`C:\R\.crooked-shelf\LeafOS0.9.5-duplicate-retired-20260804`.

## Version normalization

The active package version is `0.2.2`. Earlier `0.5` through `0.9.5` labels are
retained in historical evidence and authority gates as development-stage labels;
they are not the active package version.

## Work-order continuity

The active WO-052 and WO-053 identities are:

- WO-052: evidence integrity debugger
- WO-053: real llama.cpp capability preflight

The numbered entries 52 and 53 in `markdowns/alpha.md` are legacy checklist
entries for soft waits, not the active work-order identities.

## Consolidation status

[W] LeafOS 0.2.2 source consolidation; preserve WO-043 through WO-047 and WO-052/053 continuity
[D] Day 1 (anchor 2026-08-02): REBASE to normalized 0.2.2 source and release identity
[I] DONE — source, path, release metadata, and FlowerOS consumer references consolidated
[V] PASS — root contract; 31 CCIS/WO-052 tests; 24 LeafOS integration tests; 8 FlowerOS bridge tests
[P] LOCAL — dirty work preserved on `agent/organic-0.9.4-snapshot`; baseline commit remains pushed
[N] Reconcile and commit the dirty work in bounded groups before implementing WO-053
