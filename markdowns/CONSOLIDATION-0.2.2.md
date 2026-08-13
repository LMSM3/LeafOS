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

## Consolidation status update — 2026-08-11

[W] LeafOS 0.2.2 bounded reconciliation: roadmap and WO-050–WO-060 records
[D] Day 2: restore current planning/evidence records before implementation-file reconciliation
[I] PARTIAL: canonical roadmap corrected; L/M/N/X map added; WO-050-R1/R2 and WO-053-A/B records restored
[V] PASS: root/taskpack VERSION both report 0.2.2; restored records and relative references inspected; no live-provider claim added
[P] LOCAL: canonical dirty worktree only; no staging, commit, push, provider launch, model load, or publication
[N] Reconcile the WO-050-R1/R2 implementation and focused tests as the next bounded group, then reconcile WO-053-B separately

## Consolidation status update — 2026-08-13

[W] LeafOS 0.2.2 bounded reconciliation: WO-050-R1/R2 implementation and shell evidence
[D] Day 2: implementation group 2 closed after canonical-tree verification
[I] DONE: indicator evidence, pack constructor, PowerShell 5/5.1/7 routing, shell triage procedure, quiet-process contract, schema, and focused tests reconciled
[V] PASS: 46 focused tests; Bash/Python syntax; PowerShell 5.1 and 7 parsing; native and MSYS doctor/preview smokes
[P] LOCAL: canonical dirty worktree only; no staging, commit, push, provider launch, model load, or publication
[N] Reconcile WO-053-B preflight implementation and its focused tests as a separate bounded group; do not run the opt-in real-host preflight yet

## Consolidation status update — 2026-08-13 (WO-053-B)

[W] WO-053-B canonical reconciliation: native llama.cpp capability preflight
[D] Day 2: bounded implementation group 3 closed after canonical offline verification
[I] DONE: native probe, strict schema, typed adapter/dispatcher, implemented registry entry, and focused tests reconciled
[V] PASS: source/canonical artifact comparison; Python compilation; schema contract; 31 CCIS tests; 18 focused taskpack tests; real-host probe not executed
[P] COMMITTED: containing bounded reconciliation commit; unrelated dirty worktree changes retained and excluded
[N] Run the opt-in real-host WO-053-B capability preflight and retain task, capability, executable, and model digests; do not open WO-054 unless it passes
