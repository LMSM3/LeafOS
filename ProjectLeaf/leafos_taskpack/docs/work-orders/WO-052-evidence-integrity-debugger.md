# WO-052 — Evidence Integrity Debugger

## Identity

- Owner/context: liamm / CCIS acceptance safety
- Current day: Day 1 (implemented and validated after WO-051)
- Release target: LeafOS 0.2.2 loop debugging
- Branch: `agent/organic-0.9.4-snapshot`
- Scope boundary: CCIS evidence verification, typed diagnostics, and focused tests

## Source

Section 15: `test_acceptance_refuses_a_tampered_evidence_bundle` proves staging is refused when `evaluation.json` no longer matches the bundle digest.

## Architectural authority

- Primary authority: [`../CODEBASE_OVERVIEW.tex`](../CODEBASE_OVERVIEW.tex), especially the operating doctrine that files carry state, the typed inlet owns execution authority, a provider is not the authority, and the CPU validates, gates, writes, and records evidence. Reviewed authority digest: `sha256:2301a5977fbdcb5ecf56c81911ae117a648e7eb8d01189605b1ca953aeeedc1d`.
- Measurement authority: [`../LEAFOS_INFERENCE_THROUGHPUT_WHITE_PAPER.tex`](../LEAFOS_INFERENCE_THROUGHPUT_WHITE_PAPER.tex), especially the requirement to bind measurements to exact model artifacts, runtime, placement, workload, and host conditions. Reviewed authority digest: `sha256:78159b4dd600fe6e144573e5c72ab7d82211b74fa3db7612e785b58b48cd68b3`.
- Derived rule: reports and runs are inspectable evidence, never executable or acceptance authority. The debugger reports damage; it cannot repair, stage, accept, or launch a provider.

## Live-inference intent

Live inference means a real GGUF model computes new tokens from a real prompt while LeafOS records its actual behavior. WO-052 does not load the model; it ensures later live-inference commands, outputs, measurements, model/binary identities, and decisions cannot be altered without detection.

## Acceptance criteria

- [x] `debug.evidence_integrity.v1` accepts only digest-anchored run/bundle references and an inspection budget.
- [x] Result identifies the first bad artifact, expected/actual digest, declaring manifest, and affected decision/event.
- [x] Diagnostic execution is read-only against the run, evidence bundle, Git index, and worktree.
- [x] Clean, artifact-tampered, manifest-tampered, and event-tampered fixtures have distinct typed dispositions.
- [x] Existing section-15 refusal remains unchanged: no index entry is staged after tamper.
- [x] Debug output is safe to queue, rebuild, replay, and compare by digest.
- [x] A fixture demonstrates tamper localization for a representative live-inference evidence record without launching the model.

## Status

[W] WO-052: typed evidence-integrity debugging
[D] Day 1: native read-only inspection, typed localization, allocator execution, and replay verification complete
[I] DONE: `debug.evidence_integrity.v1` is registered and implemented for CCIS runs, CCIS evidence bundles, and benchmark runs
[V] PASS: 31 CCIS tests; two retained MoE runs inspected CLEAN; inspected source trees remained byte-identical
[P] LOCAL: implementation and diagnostic allocation journals are uncommitted; diagnostic execution did not mutate inspected evidence or the test Git index/worktree, and nothing was staged
[N] STOP before WO-053: operator review of WO-052 evidence, then choose whether to begin the llama.cpp capability preflight

## Evidence log

- 2026-08-03: Baseline 24-test CCIS suite passed before WO-052 changes.
- 2026-08-03: Promoted `debug.evidence_integrity.v1` from a handlerless reservation to native handler `ccis.debug.evidence_integrity`; the 32-entry registry now has digest `sha256:eed17436fcd491092a5c33f12d0009b5c840ce5f70fb533226ccf48bae6de9ec`.
- 2026-08-03: No persisted `.leafos/ccis/allocation` root or admitted task was present in the repository, so the registry-digest change requires no local task drain or migration. A deployment with queued tasks must still drain or migrate them before replacing its trusted registry.
- 2026-08-03: Added a strict diagnostic schema with `CLEAN`, `ARTIFACT_TAMPERED`, `MANIFEST_TAMPERED`, `EVENT_TAMPERED`, `INVALID_REFERENCE`, and `BUDGET_EXCEEDED` dispositions. Tamper outcomes produce `REVISE`; invalid or exhausted inspections produce `BLOCKED`.
- 2026-08-03: Enforced one canonical target reference, no inputs, dependencies, resource claims, subprocess validators, repair authority, or canonical-write authority. Only wall-time and evidence-byte budgets are admitted.
- 2026-08-03: Added bounded cached reads, containment checks, canonical `run.json`/`evidence-bundle.json` names, source/allocation-root non-overlap, and before/after metadata checks. Architectural review closed an initial file-size race in byte-budget accounting before completion.
- 2026-08-03: Mathematical review made an external SHA-256 anchor mandatory for every task. A self-hashed manifest or hash chain without a separately trusted head detects accidental/non-coherent edits but cannot prove integrity after a complete coherent rewrite; deriving the expected hash from the inspected file was therefore removed.
- 2026-08-03: Seven focused tests prove strict admission, non-overlap, clean replay, byte-identical allocation rebuild, Git index/worktree non-mutation, the four required dispositions, budget refusal, and representative MoE benchmark localization without starting a model.
- 2026-08-03: Retained strict-CPU run `run-20260803T235714991957Z-84333e7bb021` matched manifest anchor `sha256:2789f18d71f5740e0b98ccfc79ca9afcd3d063568f8e12f86079da52638aa58f` and inspected `CLEAN` across 3 files / 82,883 bytes with diagnostic digest `sha256:b1877cdaa15880d4a927fe9cdf5c7d8c0222e9f268a015fa0be96d64f80ebbb6`. Source-tree digest stayed `sha256:43c7b085ee51a7c19015cc12c87d19fe0329773d128830a19dd174fb6c9abc23`.
- 2026-08-03: Retained GPU-fit run `run-20260804T023345396969Z-84333e7bb021` matched manifest anchor `sha256:01b1be956d3a32f7885b9299e2704be2171fca3194e96e9f3ecb28d9667da556` and inspected `CLEAN` across 3 files / 63,207 bytes with diagnostic digest `sha256:7fb082466c76e61236a657c81e38ab96ab685410fe84aea5a99f3d1d3f4d0fa8`. Source-tree digest stayed `sha256:8595314634714481c46a54e1d4b625b584c5e2500d2af270ba0e481feaa01a6b`.

## MOE parallel handoff

- [WO-017/MOE-008](WO-017-small-scale-moe-hardware-orchestration.md) must use this evidence-integrity path for inventory, placement, routing, repair, and benchmark evidence. Identity, compatibility, safety, and statistical gates remain hard failures and cannot be averaged away by a router score.
- [WO-017-B strict CPU control](WO-017-MOE-001-B-strict-cpu-control.md) and [WO-017-C tensor-derived identity](WO-017-MOE-001-C-tensor-derived-identity.md) are the supporting MoE records exercised by the retained strict-CPU and GPU-fit manifests above. They remain parallel evidence inputs, not alternate allocator or acceptance authorities.

## Architectural fork intentionally deferred

- WO-052 inspects a quiescent run/bundle snapshot against a trusted digest. For an actively appended event stream, a changed head can mean either legitimate progress or tamper; one file digest cannot distinguish them.
- Before active-run inspection is admitted, choose between (a) sealed-run-only inspection (recommended for the current small-scale design) or (b) a versioned head contract carrying source sequence plus terminal event hash. This choice is not required for completed benchmark/bundle evidence and is deferred rather than silently embedded in WO-052.

## Out of scope

- Re-signing, repairing, or silently replacing damaged evidence.
- Staging or accepting a candidate.
