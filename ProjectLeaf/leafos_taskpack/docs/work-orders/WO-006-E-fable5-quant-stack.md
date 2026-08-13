# WO-006-E — Fable5 Quantization Benchmark Stack

## Identity

- Owner/context: LeafOS 0.6 local model operations
- Current day: Day 2
- Release target: Fable5 quant stack and orchestration-window foundation
- Branch: local workspace
- Scope boundary: Fable5 artifact verification, ordered benchmark stack, local synthetic benchmark, orchestration-window design
- Authority: `docs/design/model_assignment.tex`, `docs/design/FABLE5_QUANT_ORCHESTRATION_WINDOW.md`

## Acceptance criteria

- [x] Recreated the previous five-quant Fable5 plan: Q2_K, Q3_K_M, Q4_K_M, Q6_K, Q8_0.
- [x] Confirmed all five artifacts are locally present and have valid GGUF headers.
- [x] Recorded current SHA-256 hashes and readiness classification for every artifact.
- [x] Ordered the five entries in a reproducible sequential stack manifest.
- [x] Preserved Q2 as benchmark-only due to the existing malformed-output runtime policy.
- [x] Ran the bounded no-network synthetic orchestration benchmark exactly once per quant.
- [x] Documented a read-only orchestration-window contract and explicit installation/action boundaries.

## Status

[W] WO-006-E: Fable5 quantization benchmark stack
[D] Day 2: restoration and orchestration design closeout
[I] DONE
[V] PASS: artifact headers/hashes, JSON validation, fullstackbench regression
[P] LOCAL
[N] Future work: implement the read-only window, then add a separately scoped real llama.cpp inference benchmark

## Evidence log

- 2026-09-XX: Active catalog enumerates Q2_K, Q3_K_M, Q4_K_M, Q6_K, and Q8_0 for the Fable5 coder. Historical all-quant reports showed the same set.
- 2026-09-XX: Verified active artifact cache: Q2 4.50 GiB, Q3 5.67 GiB, Q4 6.87 GiB, Q6 9.11 GiB, Q8 11.80 GiB; every file starts with `GGUF`. C: had 462.27 GiB free, but no download was needed because every target was valid.
- 2026-09-XX: Wrote offline quant-specific plans, `fable5-all-quants-verify.json`, and `fable5-benchmark-stack.json` under `PowerShell-Version/reports/fable5-all-quants-current/`.
- 2026-09-XX: Corrected `core/bench/fullstackbench.py` to deduplicate by quant rather than tier label; Q8 had previously appeared twice under two role labels. The bounded final benchmark result contains exactly Q2_K, Q3_K_M, Q4_K_M, Q6_K, and Q8_0.
- 2026-09-XX: Validated all generated JSON and ran `bash tests/fullstackbench.sh` successfully. Benchmark results are CPU token-pump orchestration overhead only, not real GGUF inference throughput.

## Carry-forward

- Implement the documented read-only orchestration window against the stack/verify/result JSON contracts.
- Add a distinct real-inference benchmark only after defining llama.cpp process limits, prompt/token workload, timeout, telemetry, and hardware safety gates.

## Out of scope

- Any model download or deletion (all selected artifacts were already valid).
- Changing the Q2 runtime compatibility policy.
- Treating synthetic benchmark numbers as model quality or real decode-speed results.
