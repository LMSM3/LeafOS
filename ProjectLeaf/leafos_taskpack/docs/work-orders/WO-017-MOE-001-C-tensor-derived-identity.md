# WO-017 / MOE-001-C — Tensor-Derived Parameter Identity

## Identity

- Owner/context: liamm / LeafOS GGUF identity-mathematics correction
- Current day: Day 0 (algorithm and focused full-hash evidence complete)
- Release target: LeafOS 0.2.2 local-hardware orchestration lane
- Branch: `agent/organic-0.9.4-snapshot`
- Parent campaign: [WO-017 / MOE-001-A](WO-017-MOE-001-A-experimental-qwen-benchmark.md)
- Sibling control update: [WO-017 / MOE-001-B](WO-017-MOE-001-B-strict-cpu-control.md)
- Demo source: `C:\Users\liamm\OneDrive\Documents\LeafOS\ProjectLeaf\leaf_moe_benchmark_demo`
- Scope boundary: correct future inventory admission without rewriting the prior signed inventory, plan, run, or catalog

## Problem

Inventory v1 treated parameter-like text in `general.name` as measured identity. The Qwen artifact's filename/catalog says 14B, `general.name` says 35B, and the provider's loaded tensor graph reports 14,137,111,168 logical parameters. Text disagreement alone is not parameter-count mathematics.

## Resolution contract

The bounded GGUF reader now consumes tensor descriptors after metadata while never reading or mapping tensor payloads. Logical parameter count is:

```text
P = sum over tensors t of product over dimensions d in t of d
```

Safety limits cap tensor count at 1,000,000 and dimensions per tensor at four; dimensions must be positive. Total-parameter labels exclude active-parameter labels such as `A3B`.

A declared total label `L` billion matches tensor count `P` when:

```text
abs(P / 1e9 - L) <= max(0.5, 0.05 * L)
```

This explicit rounding tolerance admits the observed 14.137B tensor count under a 14B catalog label. A catalog/filename disagreement with tensor count is the hard `catalog_tensor_parameter_count_mismatch` blocker. A `general.name` disagreement becomes the advisory `metadata_name_parameter_label_disagreement` finding and cannot alone block admission.

## Evidence and compatibility

- The old v1 inventory, plan, run, and `catalog_metadata_parameter_label_mismatch` blocker remain immutable historical evidence.
- Old plans containing the legacy blocker remain override-gated.
- New plans recognize both legacy and tensor-derived hard mismatch codes for measurement-only override behavior.
- The focused Qwen inventory must reproduce the provider's 14,137,111,168 count before the new admission result is accepted.

## Acceptance criteria

- [x] GGUF tensor descriptors yield a bounded logical parameter count without tensor-payload reads.
- [x] Active-parameter labels are excluded from total-count comparison.
- [x] Catalog/tensor mismatch is blocking while name-only disagreement is advisory.
- [x] The comparison tolerance is explicit and covered by passing/mismatch fixtures.
- [x] Legacy hard blockers remain recognized by new plan generation.
- [x] Unit/schema regression tests cover descriptor counting and both identity outcomes.
- [x] Focused full-hash inventory reproduces 14,137,111,168 parameters and retains the 35B name disagreement as advisory.
- [x] The new Qwen entries require no experimental identity override while retaining statistical promotion gating.

## Focused evidence

- Inventory: `inventory:6c70452b63ba83dec1d2713152dd47fe89a5b10222b9721c977515dd86c394cf`
- Inventory SHA-256: `07697f82ac9181ef94697d034c4db21364fa90e62c2f9be4f5c91a8a3870136d`
- Artifact SHA-256: `2b6b9a8aa361acb68ab5faca2f5ab1b8443d2869ebe08ddb714185d5626c1f31`
- Tensor descriptors: 733 tensors, 46,256 descriptor bytes, 14,137,111,168 logical parameters
- Finding: advisory `metadata_name_parameter_label_disagreement`
- Admission: eligible with no benchmark-admission blocker
- Plan: replay-stable `plan:84333e7bb0213c716abde1305ade5ad8899c85aea2039810f0969f389ab79a54`
- Four entries: all provider-ready, none require experimental identity override, all retain `statistical_promotion_analysis_missing`
- Plan SHA-256: `c29bf31c660bdd8e380c933013c3581b91667fe1089daeb91172bb2986b04573`
- Provider SHA-256: `2b6786ab6468931dab284b339e203bd5d6af88124e696a4438b1449271d40fc3`

## Status

[W] WO-017 / MOE-001-C: tensor-derived GGUF parameter identity
[D] Day 0: identity mathematics and real focused evidence complete
[I] DONE
[V] PASS: 733 descriptors reproduce 14.137B; advisory name finding; replay-stable plan; demo 19/19 on Python 3.13/3.14; CCIS 24/24
[P] LOCAL: isolated demo and documentation changes only; prior evidence and catalog unchanged
[N] Handoff complete: v2 GPU-fit captured without identity override; no further action in MOE-001-C

## Evidence log

- 2026-08-03: Reproduced the original flaw: label-set comparison conflated `general.name` text with measured parameter identity.
- 2026-08-03: Implemented bounded tensor-descriptor parsing, total-label comparison, explicit tolerance, advisory name findings, and backward-compatible override recognition.
- 2026-08-03: Added passing 14.137B/14B and blocking 35B/14B fixtures; all 17 demo tests passed.
- 2026-08-03: Focused full-hash inventory read 733 bounded descriptors and reproduced 14,137,111,168 parameters without reading tensor payloads for the count.
- 2026-08-03: Reclassified the 35B `general.name` text as advisory; the 14B catalog label passed the explicit tolerance and all four v2 entries became identity-admissible without override.
- 2026-08-03: Replayed the v2 plan with identical normalized content and passed all 17 demo tests on Python 3.13/3.14 plus all 24 CCIS tests.
- 2026-08-03: Added direct legacy/new hard-blocker override coverage; final regression state is demo 19/19 on Python 3.13/3.14 and CCIS 24/24.

## Out of scope

- Rewriting the catalog or embedded GGUF metadata.
- Removing blockers from already-signed v1 artifacts.
- Inferring active-parameter count from the `A3B` label.
- Promotion, production model admission, commit, merge, or publication.
