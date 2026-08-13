# WO-017 / MOE-001 — Full-Identity Inventory and GPU Provider Evidence

## Identity

- Owner/context: liamm / LeafOS MOE-001 production-admission evidence
- Current day: Day 0 (bounded no-inference productionization evidence gate complete)
- Release target: LeafOS 0.2.2 local-hardware orchestration lane
- Branch: `agent/organic-0.9.4-snapshot`
- Parent: [WO-017](WO-017-small-scale-moe-hardware-orchestration.md)
- Scope boundary: full SHA-256 identity for the nine discovered GGUF artifacts, offline GPU-provider probe, deterministic placement-plan generation, and retained no-inference evidence
- Source implementation: isolated `C:\Users\liamm\OneDrive\Documents\LeafOS\ProjectLeaf\leaf_moe_benchmark_demo`
- Evidence root: `C:\Users\liamm\OneDrive\Documents\LeafOS\tmp\moe-001-full-identity`

## Objective

Advance MOE-001 from an isolated no-hash demonstration to reviewable production-admission evidence without installing the demo, binding a native handler, loading a model, or running a benchmark. The result must distinguish durable provider capability from momentary free-VRAM headroom and preserve every identity or promotion blocker.

## Reviewed provider candidate

```text
C:\Users\liamm\AppData\Local\Microsoft\WinGet\Packages\
  ggml.llamacpp_Microsoft.Winget.Source_8wekyb3d8bbwe\llama-bench.exe
```

Read-only discovery on 2026-08-03 reported:

- `llama-bench --list-devices`: `Vulkan0: NVIDIA GeForce RTX 4070 (12226 MiB, 11416 MiB free)`;
- loaded runtime siblings include `ggml-vulkan.dll`, CPU variants, RPC, and llama libraries;
- `nvidia-smi`: RTX 4070, driver 595.79, compute capability 8.9, 12,282 MiB total, and 6,964 MiB free at the later sample;
- `vulkaninfo --summary`: discrete NVIDIA RTX 4070 with Vulkan 1.4.329 device API and driver 595.79.

The free-memory readings are time-separated observations and must not be merged into one value. The provider may be GPU-capable while a placement remains inadmissible because another process consumes headroom.

## Acceptance criteria

- [x] All nine discovered GGUF artifacts receive full SHA-256 content identity without mutation.
- [x] Inventory retains bounded GGUF metadata, artifact role, catalog matches, and identity findings.
- [x] Projector GGUF remains excluded from language-model benchmark entries.
- [x] The provider probe records executable SHA-256, backends, devices, capabilities, return codes, and usability.
- [x] The plan contains deterministic CPU, GPU-fit, and feasible sparse-MoE placement commands with explicit readiness/blockers.
- [x] Catalog/metadata identity disagreement remains a hard promotion blocker.
- [x] Every entry retains statistical-promotion gating until paired analysis exists.
- [x] No model load, inference, benchmark execution, scheduler event, handler binding, or production-state mutation occurs.
- [x] Demo unit tests and production CCIS registry tests still pass after evidence generation.

## Status

[W] WO-017 / MOE-001: full-identity inventory and GPU-provider placement evidence
[D] Day 0: full-identity/provider/plan evidence gate complete; execution fork reached
[I] DONE: bounded no-inference evidence gate; parent MOE-001 remains PARTIAL until measured benchmarks and statistics pass
[V] PASS: 9 full hashes, 7 identity-admissible artifacts, Vulkan provider, deterministic 18-entry plan replay, 13 demo tests on Python 3.13/3.14, and 24 CCIS tests; NOT_RUN: model load or benchmark
[P] LOCAL: no stage, commit, model load, benchmark execution, or handler binding
[N] GPU-fit is captured; resolve placement-manifest evidence policy in [MOE-001-A](WO-017-MOE-001-A-experimental-qwen-benchmark.md) before CPU-MoE

## Evidence log

- 2026-08-03: Confirmed nine artifacts totaling 63,370,891,808 bytes (59.02 GiB): eight language models and one projector.
- 2026-08-03: Reviewed the Winget provider and independently observed Vulkan/RTX 4070 capability plus time-varying free-VRAM state.
- 2026-08-03: Completed the 59.02 GiB SHA-256 pass in 68.5 seconds. All nine artifacts have distinct full content hashes; seven pass the inventory identity gate.
- 2026-08-03: Preserved two refusals: the sparse Qwen model has `catalog_metadata_parameter_label_mismatch`, and the projector has `catalog_untracked_artifact` and remains excluded.
- 2026-08-03: Probed provider SHA-256 `5c1e3321b881eef6be065c0ac60c555d63ad777ad5fcfda88251bf915fe31b47`; backends are CPU, RPC, and Vulkan, with the RTX 4070 visible as `Vulkan0`.
- 2026-08-03: Generated plan `plan:a23d93225361cc8827b4d93622d64aefc17c2b9dbf0d8dac37b743908e1e3933`: 8 CPU, 8 GPU-fit, and 2 sparse-MoE entries. All 18 are provider-ready and all 18 retain `statistical_promotion_analysis_missing`; the four Qwen entries require experimental identity override.
- 2026-08-03: Replayed plan generation with the same plan ID, entry IDs, and normalized content. The two files differ only in generated time.
- 2026-08-03: Evidence digests: `inventory.json` = `139df2b8d825b24793a404e341e6f86c90c6d84df900cab0f51df2a3194ef1b8`; `provider.json` = `85fa0562d9b3195013652981117c3f41127e767ec3c3acd091b6b79b4c8a1cdf`; `plan.json` = `b3b62c322b71029841e48c982084ea88cd9feedfab665149233ceff773144d69`.
- 2026-08-03: Reran 13 demo tests under Python 3.13 and 3.14 and all 24 CCIS tests. No `llama*` process remained after preparation, and no model was loaded.
- 2026-08-03: Operator selected the measurement-only experimental override. Opened [MOE-001-A](WO-017-MOE-001-A-experimental-qwen-benchmark.md) with a sequential CPU → GPU-fit → half CPU-MoE → all CPU-MoE campaign; catalog and promotion blockers remain unchanged.
- 2026-08-03: MOE-001-A order 1 succeeded with retained evidence and blockers. The result exposed GPU operation offload in the nominal zero-layer CPU baseline and a name-based identity heuristic that conflicts with the tensor-derived 14.137B parameter count; GPU-fit is held for design review.
- 2026-08-03: MOE-001-B/C resolved both findings without rewriting v1 evidence. The v2 strict control passed with an 11 MiB device-memory delta, and bounded tensor descriptors made the new plan identity-admissible without override; GPU-fit is now the next single-entry gate.
- 2026-08-03: V2 GPU-fit succeeded with 1,582 MiB observed free margin and 100% peak GPU utilization. The result row retains the requested `n_gpu_layers: 999`, so exact resolved-placement evidence is held as a separate design choice before CPU-MoE.

## Out of scope

- Executing any generated benchmark entry.
- Promoting a model or placement from inventory/provider evidence alone.
- Installing the demonstration into the production scheduler, taskpack, installer, launcher, or model catalog.
- Binding `bench.moe.inventory.v1` or `bench.moe.placement.v1` to a native handler.
