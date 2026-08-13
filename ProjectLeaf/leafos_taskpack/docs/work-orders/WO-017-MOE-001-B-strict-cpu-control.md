# WO-017 / MOE-001-B — Strict CPU Control

## Identity

- Owner/context: liamm / LeafOS small-scale MoE benchmark-control correction
- Current day: Day 0 (control contract and corrected evidence complete)
- Release target: LeafOS 0.2.2 local-hardware orchestration lane
- Branch: `agent/organic-0.9.4-snapshot`
- Parent campaign: [WO-017 / MOE-001-A](WO-017-MOE-001-A-experimental-qwen-benchmark.md)
- Sibling identity update: [WO-017 / MOE-001-C](WO-017-MOE-001-C-tensor-derived-identity.md)
- Demo source: `C:\Users\liamm\OneDrive\Documents\LeafOS\ProjectLeaf\leaf_moe_benchmark_demo`
- Scope boundary: correct and remeasure one CPU control; no GPU-fit, CPU-MoE placement, production handler binding, promotion, or catalog mutation

## Problem

The v1 `cpu-baseline-16t` command set `--n-gpu-layers 0` but left `devices: auto` and `no_op_offload: 0`. Its successful evidence is retained as a zero-layer hybrid control, not rewritten as CPU-only evidence.

## Resolution contract

Matrix v2 replaces that placement with `cpu-strict-16t`. A valid strict entry must contain all three provider controls:

```text
--n-gpu-layers 0
--device none
--no-op-offload 1
```

The provider probe records `device` and `no_op_offload` capability separately. Planning blocks the strict placement if either is absent. The runner independently rejects a `cpu-strict-16t` entry if any required value is missing or changed.

`llama-bench --device none --n-gpu-layers 0 --no-op-offload 1 --list-devices` returned zero on the installed provider. Loading Vulkan libraries during probe is not itself evidence of model offload; the measured row and device-total telemetry determine whether the corrected control held.

## Evidence interpretation

- Provider row must report `n_gpu_layers: 0`, `devices: none`, and `no_op_offload: 1`.
- Process telemetry must show useful utilization of the configured 16-thread CPU lane.
- Device telemetry is total-host state, not process attribution. Compare its run peak against a short immediately preceding background envelope; do not attribute unrelated utilization to the benchmark.
- The runner embeds five pre-process device-total samples and their min/max envelope in the same immutable run manifest.
- The old v1 result remains immutable and comparison-incompatible with a strict CPU-only claim.

## Acceptance criteria

- [x] Matrix v2 defines `cpu-strict-16t` with all three isolation controls.
- [x] Provider capability evidence distinguishes device selection and operation-offload control.
- [x] Planning fails closed when either strict-control capability is absent.
- [x] Runtime command validation rejects a weakened strict entry.
- [x] Unit/schema regression tests cover the placement and fail-closed validation.
- [x] Runner evidence embeds a five-sample pre-process GPU background envelope.
- [x] A new full-hash plan contains exactly one reviewed strict Qwen entry with no identity override requirement.
- [x] The corrected entry succeeds within 600 seconds and retains raw streams, telemetry, hashes, and promotion blockers.
- [x] The measured row confirms strict settings, the GPU delta is reviewed against the background envelope, and no owned process remains.

## Corrected evidence

- Plan: `plan:84333e7bb0213c716abde1305ade5ad8899c85aea2039810f0969f389ab79a54`
- Entry: `bench:fd546ee204c10c2cfbb08b9d`
- Run: `run-20260803T235714991957Z-84333e7bb021`
- Manifest: `C:\Users\liamm\OneDrive\Documents\LeafOS\tmp\moe-001-b-strict-cpu-run\run-20260803T235714991957Z-84333e7bb021\run.json`
- Manifest SHA-256: `2789f18d71f5740e0b98ccfc79ca9afcd3d063568f8e12f86079da52638aa58f`
- Outcome: success, return code 0, 47.265 provider seconds, no experimental identity override
- Provider rows: `n_gpu_layers: 0`, `devices: none`, `no_op_offload: 1`
- Prompt processing: 70.918304 tokens/s, standard deviation 0.573571, coefficient of variation 0.81%
- Token generation: 8.715705 tokens/s, standard deviation 0.226580, coefficient of variation 2.60%
- CPU lane: 12.561 average CPU-core equivalents, or 78.51% of the configured 16-thread lane
- Process peak RSS: 13.750 GiB
- GPU background: five samples at 4,792 MiB; in-run peak 4,803 MiB; delta 11 MiB
- GPU utilization: 13% background maximum and 15% in-run maximum, device-total and therefore not process-exclusive
- Cleanup: stdout/stderr hashes match and no `llama-bench` process remained
- Promotion: ineligible only because `statistical_promotion_analysis_missing` remains

Against the historical zero-layer hybrid sample, strict CPU prompt throughput was 46.66% lower, generation throughput was 41.71% higher, and peak RSS was 6.64 GiB higher. These are descriptive single-run differences, not promotion-grade speedup/regression claims.

## Status

[W] WO-017 / MOE-001-B: strict CPU-control correction and remeasurement
[D] Day 0: v2 strict control implemented and measured
[I] DONE
[V] PASS: strict row controls, 11 MiB GPU-memory delta, evidence hashes, cleanup, demo 19/19 on Python 3.13/3.14, and CCIS 24/24
[P] LOCAL: isolated demo, retained evidence, and documentation only; no stage, commit, promotion, or production binding
[N] Handoff complete: GPU-fit captured in MOE-001-A; no further action in MOE-001-B

## Evidence log

- 2026-08-03: Preserved the v1 result as a zero-layer hybrid control after its row reported `devices: auto` and `no_op_offload: 0`.
- 2026-08-03: Confirmed the installed provider parses the three strict controls and exits zero on a no-model `--list-devices` probe.
- 2026-08-03: Implemented matrix, provider-capability, plan, runner-validation, README, schema, and test updates; all 17 demo tests passed.
- 2026-08-03: Generated replay-stable v2 plan `plan:84333e7bb0213c716abde1305ade5ad8899c85aea2039810f0969f389ab79a54`; the strict entry was ready and contained all three controls.
- 2026-08-03: Executed only the strict entry. It succeeded, stayed 11 MiB above the device-total background memory maximum, retained the statistical blocker, and left no owned process.
- 2026-08-03: Passed all 17 demo tests under Python 3.13 and 3.14 and all 24 CCIS tests after capture.
- 2026-08-03: Added direct missing-capability planner coverage; final regression state is demo 19/19 on Python 3.13/3.14 and CCIS 24/24.

## Out of scope

- Reclassifying the v1 evidence as strict CPU-only.
- Running GPU-fit or CPU-MoE placements in this update.
- Treating device-total telemetry as process-exclusive attribution.
- Production scheduling, lease acquisition, acceptance, commit, merge, or publication.
