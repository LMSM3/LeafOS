# WO-053 — Real llama.cpp Capability Preflight

## Identity

- Owner/context: liamm / local provider truth and CCIS validation
- Current day: Day 0 (planned after WO-052)
- Release target: LeafOS 0.2.2 local-model evaluation
- Branch: `agent/organic-0.9.4-snapshot`
- Scope boundary: opt-in tests, local executable/model inspection, typed evidence; no network download

## Source

Section 16: prove the real `llama-cli`/`llama-server` binary, GGUF model, and selected backend before counting any provider evaluation.

## Live-inference intent

Live inference means the selected local GGUF is actually loaded and generates fresh tokens from a real prompt on CPU/GPU. WO-053 is deliberately the prerequisite check—not live inference—and must never report success as proof that generation occurred. Its typed result authorizes or refuses the later live-inference tasks.

## Acceptance criteria

- [ ] `probe.llamacpp.capability.v1` resolves executable and model paths from explicit configuration.
- [ ] Binary version/commit, model size/GGUF header/digest, backend device list, and host facts are captured.
- [ ] Missing, zero-byte, inaccessible, non-GGUF, CPU-only-when-Vulkan-required, and version-mismatch cases fail explicitly.
- [ ] Heavy tests are skipped unless `LEAFOS_RUN_LLAMACPP_TESTS=1`; after opt-in, missing prerequisites fail rather than skip.
- [ ] The task claims the model path and requested accelerator without launching inference, and labels the result `preflight_only`.
- [ ] The typed capability result is digest-bound and can gate WO-054/WO-055 admission.

## Status

[W] WO-053: real llama.cpp binary/model/backend preflight
[D] Day 0: entry gate prepared after verified WO-052 completion
[I] TODO
[V] PASS: PowerShell/WSL root contracts, 28 runtime integration tests, and 31 CCIS tests; no live inference run claimed
[P] LOCAL: pre-overhaul integration only; native handler remains reserved and uncommitted
[N] Open Day 1 by implementing the opt-in binary/model/backend capability probe

## Entry-gate evidence

- 2026-08-09: Registered CCIS, the Scientific Change Loop, the typed-task registry, this WO, and the series index in the machine-readable root contract.
- 2026-08-09: Root validators now require the three llama.cpp task registrations without treating a reserved task as implemented.
- 2026-08-09: Fixed in-process serialization around the cross-process durable instance lock and proved 40 concurrent capability requests preserve a contiguous 81-event transcript.
- 2026-08-09: Agent-loop unit tests no longer write authority events into the live Monday journal.
- 2026-08-09: Archived three one-off 0.9.5 diagnostic helpers under `ARCHIVE/pre-llamacpp-overhaul-2026-08-09/`; they are not runtime entrypoints.
- 2026-08-09: The PowerShell and WSL root contracts passed; 28 focused runtime/integration tests and all 31 CCIS tests passed.

## MOE parallel handoff

- [WO-017/MOE-001 and MOE-005](WO-017-small-scale-moe-hardware-orchestration.md) consume this preflight result before real provider work. The isolated `llama-bench` probe may seed discovery, but its CPU-only result cannot authorize a GPU placement or prove live inference.

## Out of scope

- Downloading models or changing provider configuration.
- Claiming semantic model quality from a preflight.
