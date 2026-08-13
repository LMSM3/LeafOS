# WO-053 — Real llama.cpp Capability Preflight

## Identity

- Owner/context: liamm / local provider truth and CCIS validation
- Current day: Day 1 (implemented and reconciled)
- Release target: LeafOS 0.2.3 local-model evaluation
- Branch: `agent/leafos-0.2.3-snapshot`
- Scope boundary: opt-in tests, local executable/model inspection, typed evidence; no network download

## Source

Section 16: prove the real `llama-cli`/`llama-server` binary, GGUF model, and selected backend before counting any provider evaluation.

## Live-inference intent

Live inference means the selected local GGUF is actually loaded and generates fresh tokens from a real prompt on CPU/GPU. WO-053 is deliberately the prerequisite check—not live inference—and must never report success as proof that generation occurred. Its typed result authorizes or refuses the later live-inference tasks.

## Acceptance criteria

- [x] `probe.llamacpp.capability.v1` resolves executable and model paths from explicit configuration.
- [x] Binary version/commit, model size/GGUF header/digest, backend device list, and host facts are captured.
- [x] Missing, zero-byte, inaccessible, non-GGUF, CPU-only-when-Vulkan-required, and version-mismatch cases fail explicitly.
- [x] Heavy tests are skipped unless `LEAFOS_RUN_LLAMACPP_TESTS=1`; after opt-in, missing prerequisites fail rather than skip.
- [x] The task claims the model path and requested accelerator without launching inference, and labels the result `preflight_only`.
- [x] The typed capability result is digest-bound and can gate WO-054/WO-055 admission.

## Status

[W] WO-053: real llama.cpp binary/model/backend preflight
[D] Day 1: implementation reconciliation and offline release proof
[I] COMPLETE: read-only probe, typed CCIS handler, schema, digest binding, and opt-in guard are present in 0.2.3
[V] PASS: 4/4 focused preflight tests, 77/77 combined release tests, 31/31 CCIS tests, and both root contracts; real-host probe not run
[P] READY: reconciled on `agent/leafos-0.2.3-snapshot` for the bounded 0.2.3 snapshot commit
[N] With explicit operator approval, configure the real binary/model/backend and run the opt-in host preflight; keep WO-054 closed until that evidence passes

## Entry-gate evidence

- 2026-08-09: Registered CCIS, the Scientific Change Loop, the typed-task registry, this WO, and the series index in the machine-readable root contract.
- 2026-08-09: Root validators now require the three llama.cpp task registrations without treating a reserved task as implemented.
- 2026-08-09: Fixed in-process serialization around the cross-process durable instance lock and proved 40 concurrent capability requests preserve a contiguous 81-event transcript.
- 2026-08-09: Agent-loop unit tests no longer write authority events into the live Monday journal.
- 2026-08-09: Archived three one-off 0.9.5 diagnostic helpers under `ARCHIVE/pre-llamacpp-overhaul-2026-08-09/`; they are not runtime entrypoints.
- 2026-08-09: The PowerShell and WSL root contracts passed; 28 focused runtime/integration tests and all 31 CCIS tests passed.
- 2026-08-13: Reconciled the implemented preflight module, CCIS native handler, schema, and focused tests into the isolated 0.2.3 release tree.
- 2026-08-13: Confirmed the opt-in gate refuses execution without touching the configured executable and that opt-in missing/invalid prerequisites fail explicitly.
- 2026-08-13: Passed 4/4 preflight tests inside a 77-test focused release suite, 31/31 CCIS tests, and both 0.2.3 root contracts. No real executable, model, backend, or live inference probe was run.

## MOE parallel handoff

- [WO-017/MOE-001 and MOE-005](WO-017-small-scale-moe-hardware-orchestration.md) consume this preflight result before real provider work. The isolated `llama-bench` probe may seed discovery, but its CPU-only result cannot authorize a GPU placement or prove live inference.

## Out of scope

- Downloading models or changing provider configuration.
- Claiming semantic model quality from a preflight.
