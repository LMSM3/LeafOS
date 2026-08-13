# WO-017 / MOE-001-A — Experimental Qwen Measurement Campaign

## Identity

- Owner/context: liamm / LeafOS measurement-only Qwen sparse-MoE evaluation
- Current day: Day 0 (historical hybrid, corrected strict CPU, and GPU-fit controls captured; placement-resolution fork open)
- Release target: LeafOS 0.2.2 local-hardware orchestration lane
- Branch: `agent/organic-0.9.4-snapshot`
- Parent evidence gate: [WO-017 / MOE-001](WO-017-MOE-001-full-identity-gpu-provider-evidence.md)
- Scope boundary: four sequential, explicitly admitted measurements for one fully hashed Qwen sparse-MoE artifact; no catalog correction, promotion, handler binding, or concurrent execution
- Historical v1 plan: `C:\Users\liamm\OneDrive\Documents\LeafOS\tmp\moe-001-full-identity\plan.json`
- Current v2 plan: `C:\Users\liamm\OneDrive\Documents\LeafOS\tmp\moe-001-bc-strict-identity\plan.json`
- Run evidence roots: `C:\Users\liamm\OneDrive\Documents\LeafOS\tmp\moe-001-experimental-qwen` and `C:\Users\liamm\OneDrive\Documents\LeafOS\tmp\moe-001-b-strict-cpu-run`

## Decision

The operator selected the measurement-only experimental-identity branch on 2026-08-03. `--allow-experimental-identity` may authorize execution of the named Qwen entries, but it does not change the catalog, embedded GGUF metadata, artifact identity, benchmark-admission result, or promotion blockers.

The historical v1 result must retain:

```text
catalog_metadata_parameter_label_mismatch
statistical_promotion_analysis_missing
```

The override is not evidence that either the 14B or 35B label is correct. MOE-001-C later resolved future admission from bounded tensor descriptors; it does not rewrite this historical result.

## Sequential campaign

| Order | Entry | Placement | State | Gate |
|---|---|---|---|---|
| 1A | `bench:a2d2b2160aeaf2329ddf466a` | v1 `cpu-baseline-16t` | CAPTURED | Historical zero-layer hybrid; retains legacy identity and statistical blockers |
| 1B | `bench:fd546ee204c10c2cfbb08b9d` | v2 `cpu-strict-16t` | CAPTURED | Corrected strict CPU control; identity-admissible and statistically blocked |
| 2 | `bench:e42a1268a7046d308d83b25a` | v2 `gpu-fit-1024mib` | CAPTURED | Fit margin and utilization verified; requested sentinel is not a resolved physical layer count |
| 3 | `bench:4878aa3e3e88c300edce41bf` | v2 `moe-cpu-half` | HOLD | Resolve placement-manifest evidence policy before comparing hybrid utilization |
| 4 | `bench:9828cb6c4f6aa90778bca84e` | v2 `moe-cpu-all` | WAITING | Orders 2–3 retain valid evidence and no cleanup leak |

Only one entry may run per tracker advance. A later entry cannot inherit success from an earlier placement, and no result is promotion-eligible until paired statistical analysis is implemented.

## Historical v1 execution contract

```powershell
python -m leaf_moe_bench run `
  C:\Users\liamm\OneDrive\Documents\LeafOS\tmp\moe-001-full-identity\plan.json `
  --out-dir C:\Users\liamm\OneDrive\Documents\LeafOS\tmp\moe-001-experimental-qwen `
  --entry bench:a2d2b2160aeaf2329ddf466a `
  --allow-experimental-identity `
  --timeout-seconds 600 `
  --telemetry-interval-seconds 0.5 `
  --execute
```

The selected command in the signed plan is offline, uses the fully hashed artifact, fixes three repetitions of prompt-256/generation-64, uses 16 CPU threads, and sets zero GPU layers. The runner must revalidate provider and model hashes before process start.

## Captured result

- Run: `run-20260803T232715989184Z-a23d93225361`
- Manifest: `C:\Users\liamm\OneDrive\Documents\LeafOS\tmp\moe-001-experimental-qwen\run-20260803T232715989184Z-a23d93225361\run.json`
- Manifest SHA-256: `3d4d46b59bee8edb50c27837bd210957ab24698a48c423fe0bdb9b10bb5d0709`
- Outcome: success, return code 0, 44.920 provider seconds, two benchmark rows
- Prompt processing: 132.955648 tokens/s, standard deviation 11.496198 tokens/s, coefficient of variation 8.65%
- Token generation: 6.150534 tokens/s, standard deviation 0.597976 tokens/s, coefficient of variation 9.72%
- CPU lane: 14.686 average CPU-core equivalents across the configured 16-thread lane (91.8% lane utilization)
- Process peak RSS: 7.110 GiB
- Tensor-derived provider count: 14,137,111,168 parameters
- Evidence: hashed raw stdout/stderr plus 75 process and 75 device-total GPU telemetry samples embedded in the manifest
- Cleanup: no `llama-bench` process remained after capture
- Promotion: ineligible; both recorded blockers remain

## Architectural review forks

The two review findings are now tracked as supporting updates: [MOE-001-B strict CPU control](WO-017-MOE-001-B-strict-cpu-control.md) and [MOE-001-C tensor-derived identity](WO-017-MOE-001-C-tensor-derived-identity.md).

### 1. CPU-control semantics

The entry set `--n-gpu-layers 0`, but its provider rows also report `devices: auto`, `backends: Vulkan`, and `no_op_offload: 0`. Device-total GPU memory rose from about 5,090 MiB to 6,025 MiB during the run and GPU utilization peaked at 59%. Because telemetry is device-total, it cannot attribute every GPU sample to this process, but the run cannot honestly be described as a strict CPU-only control.

Selected resolution: the historical result remains a **zero-GPU-layer hybrid control**. MOE-001-B added and measured a fail-closed strict control using zero GPU layers, `--device none`, and `--no-op-offload 1`; its in-run GPU memory peak was 11 MiB above the immediately preceding background maximum.

### 2. Parameter-identity mathematics

The current inventory rule compares parameter-like text in the filename/catalog (`14B`) with text in GGUF `general.name` (`35B`). The provider instead counted 14,137,111,168 parameters from the loaded tensor graph. With a reported model size of 8,829,962,752 bytes, that is approximately 4.997 stored bits per parameter, consistent with an MXFP4-class artifact plus packing metadata; interpreting the same payload as 35B parameters would imply only about 2.018 bits per parameter.

Selected resolution: keep the blocker on the already-signed v1 plan and run, while MOE-001-C changes future inventory admission to compare catalog labels with tensor-derived parameter count under an explicit tolerance. `general.name` disagreement is now a separate advisory finding.

The identity inference is strong but is not applied retroactively, and it does not remove the need for a catalog/provenance review.

### 3. Resolved-placement evidence

The v2 GPU-fit row repeats requested `n_gpu_layers: 999` and `fit_target: 1024`; it does not expose a resolved physical layer/tensor placement count. The run still proves the operational fit policy: GPU memory peaked at 10,700 MiB of 12,282 MiB, leaving 1,582 MiB free, while utilization reached 100%.

Recommended branch: before CPU-MoE comparison, add retained verbose/provider placement evidence that records the resolved offload assignment separately from the request and observed memory margin.

Alternative branch: continue using requested policy plus telemetry as the placement identity. That is adequate for an operational margin comparison but cannot support exact layer-residency claims.

## GPU-fit result

- Run: `run-20260804T023345396969Z-84333e7bb021`
- Manifest: `C:\Users\liamm\OneDrive\Documents\LeafOS\tmp\moe-001-gpu-fit-run\run-20260804T023345396969Z-84333e7bb021\run.json`
- Manifest SHA-256: `01b1be956d3a32f7885b9299e2704be2171fca3194e96e9f3ecb28d9667da556`
- Outcome: success, return code 0, 31.842 provider seconds, no experimental identity override
- Prompt processing: 728.863519 tokens/s, standard deviation 57.556275, coefficient of variation 7.90%
- Token generation: 14.818918 tokens/s, standard deviation 0.088191, coefficient of variation 0.60%
- Descriptive comparison with strict CPU: prompt +927.75%, generation +70.03%
- Descriptive comparison with zero-layer hybrid: prompt +448.20%, generation +140.94%
- Process: 0.595 average CPU-core equivalents and 9.719 GiB peak RSS
- GPU: 5,025 MiB background maximum, 10,700 MiB run peak, 5,675 MiB delta, 100% utilization, 44 C, and 78.35 W
- Fit margin: minimum observed free memory 1,582 MiB, exceeding the requested 1,024 MiB margin by 558 MiB
- Cleanup: stdout/stderr hashes match and no `llama-bench` process remained
- Promotion: ineligible only because `statistical_promotion_analysis_missing` remains

All comparisons remain descriptive because each configuration has one run containing three provider repetitions, not the paired multi-run analysis required for promotion.

## Acceptance criteria

- [x] Measurement-only override authority is explicit and limited to the named artifact/entries.
- [x] Runner code preserves entry promotion blockers after an override.
- [x] Entry `bench:a2d2b2160aeaf2329ddf466a` is provider-ready, offline, full-hash bound, and configured for CPU baseline.
- [x] Campaign order is CPU baseline, GPU-fit, half CPU-MoE, then all CPU-MoE, with one entry per advance.
- [x] The first entry executes within 600 seconds and produces a retained immutable run manifest, raw stdout/stderr, telemetry, and hashes.
- [x] The run result retains both identity and statistical-promotion blockers regardless of process success.
- [x] No llama process or owned resource remains after completion or timeout.
- [x] Demo and CCIS regression tests pass after evidence capture.
- [x] MOE-001-B captures a strict CPU control with reviewed background-envelope evidence.
- [x] MOE-001-C reproduces tensor-derived identity and removes the need for an override from the v2 plan without rewriting v1 evidence.
- [x] The v2 GPU-fit entry executes alone, preserves its fit margin, saturates useful GPU work, retains evidence, and cleans up.
- [x] Demo 19/19 on Python 3.13/3.14 and CCIS 24/24 pass after GPU-fit capture.
- [ ] Resolved placement is recorded separately from the `n_gpu_layers: 999` request before exact CPU-MoE residency comparisons.

## Status

[W] WO-017 / MOE-001-A: measurement-only Qwen sparse-MoE benchmark campaign
[D] Day 0: historical hybrid, strict CPU, and GPU-fit controls captured; resolved-placement fork reached
[I] PARTIAL: MOE-001-B/C and GPU-fit DONE; CPU-MoE placements remain
[V] PASS: GPU-fit margin/utilization/evidence/cleanup, demo 19/19 on Python 3.13/3.14, CCIS 24/24; exact resolved placement and promotion statistics missing
[P] LOCAL: isolated demo, retained evidence, and documentation only; no stage, commit, handler binding, promotion, or catalog mutation
[N] DESIGN FORK: add resolved placement evidence before CPU-MoE (recommended) or accept policy-plus-telemetry placement identity

## Evidence log

- 2026-08-03: Operator selected the recommended measurement-only override branch using `[N]`.
- 2026-08-03: Reviewed runner behavior: the override permits execution but copies existing promotion blockers into the result; it cannot make `promotion.eligible` true while either blocker remains.
- 2026-08-03: Selected CPU baseline before GPU/MoE placements so process, identity, output, and evidence behavior are proven independently of GPU headroom.
- 2026-08-03: Revalidated the exact plan entry (`ready: true`, no execution blockers, offline, zero GPU layers) and passed all 13 demo unit tests without starting the provider.
- 2026-08-03: Executed only `bench:a2d2b2160aeaf2329ddf466a`. It succeeded in 44.920 provider seconds and retained an evidence manifest with SHA-256 `3d4d46b59bee8edb50c27837bd210957ab24698a48c423fe0bdb9b10bb5d0709`.
- 2026-08-03: Verified both promotion blockers, raw-stream hashes, telemetry, and process cleanup. Reran all 13 demo and 24 CCIS tests successfully.
- 2026-08-03: Found that zero GPU layers did not disable Vulkan operation offload; held GPU-fit pending baseline-semantics choice.
- 2026-08-03: Found that the name-based 14B/35B mismatch heuristic conflicts with the provider's tensor-derived 14,137,111,168 parameter count; preserved the blocker and opened a future admission-rule correction.
- 2026-08-03: Operator selected the recommended branch. Forked the findings into MOE-001-B strict CPU control and MOE-001-C tensor-derived identity, with one corrected strict benchmark authorized.
- 2026-08-03: MOE-001-C focused inventory reproduced 14,137,111,168 parameters from 733 tensor descriptors and generated a replay-stable, identity-admissible v2 plan.
- 2026-08-03: MOE-001-B strict entry succeeded with `devices: none`, `no_op_offload: 1`, and zero GPU layers; device-total memory stayed within 11 MiB of the background maximum and no process leaked.
- 2026-08-03: Post-capture regressions passed: demo 17/17 on Python 3.13 and 3.14 and CCIS 24/24.
- 2026-08-03: Closed final planner-coverage gaps for missing strict capabilities and both legacy/new override blockers; demo suite increased to 19/19 on Python 3.13/3.14 and CCIS remained 24/24.
- 2026-08-03: Resampled 6,965–6,974 MiB free GPU headroom and executed only v2 GPU-fit entry `bench:e42a1268a7046d308d83b25a`.
- 2026-08-03: GPU-fit succeeded with 1,582 MiB minimum observed free memory, 100% peak GPU utilization, matching evidence hashes, retained statistical blocker, and no leaked process.
- 2026-08-03: Post-capture demo 19/19 passed on Python 3.13/3.14 and CCIS 24/24 passed. Held CPU-MoE because the JSON row records requested `999` rather than a resolved placement count.

## Out of scope

- Correcting or relabeling the model catalog.
- Running more than one entry in this tracker advance.
- GPU or CPU-MoE placement before the CPU baseline evidence passes.
- Treating benchmark success as model-identity resolution or promotion evidence.
- Production scheduler/lease integration, automatic acceptance, commit, merge, or publication.
