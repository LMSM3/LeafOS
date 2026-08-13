# WO-053-B — Native llama.cpp Capability Preflight

## Identity

- Owner/context: LeafOS / native CCIS capability boundary
- Parent: [WO-053 — Real llama.cpp Capability Preflight](WO-053-llamacpp-capability-preflight.md)
- Current day: Day 1 child implementation
- Release target: LeafOS 0.2.2 local-model evaluation
- Branch: shared OneDrive source tree; no Git checkout available
- Scope boundary: read-only binary, GGUF, backend/device, and host inspection; no inference, server start, network, download, installer mutation, or provider reconfiguration

## Mission

Establish a truthful admission boundary between an installed local-model stack and
the live inference work that follows. The probe must prove the identity and
availability of one explicitly named llama.cpp executable, one explicitly named
GGUF artifact, and one requested backend without implying that a model was
loaded or that tokens were generated.

## Acceptance criteria

- [x] `probe.llamacpp.capability.v1` is implemented by a trusted native handler.
- [x] Executable, model, backend, and optional expected version are explicit typed inputs.
- [x] The binary result records resolved path, bytes, SHA-256, version output, parsed version, and commit when reported.
- [x] The model result records resolved path, bytes, GGUF magic/version, and full-file SHA-256.
- [x] Backend/device discovery uses only `--list-devices`; binary identity uses only `--version`.
- [x] Host OS, release, architecture, processor, CPU count, memory, and Python facts are recorded.
- [x] Missing, zero-byte, non-GGUF, unsupported GGUF version, unavailable backend, version mismatch, inaccessible, timeout, and subprocess failures have typed failure codes.
- [x] Execution fails closed unless `LEAFOS_RUN_LLAMACPP_TESTS=1` is present.
- [x] The result is task-digest bound, capability-digest bound, and labeled `preflight_only`.
- [x] The contract fixes inference, server, and network side-effect claims to `false`.
- [x] Focused and adjacent CCIS/root capability tests pass without invoking real inference.

## Status

[W] WO-053-B: native llama.cpp binary/model/backend capability preflight
[D] Day 1: first implementation child under master WO-053
[I] DONE
[V] PASS: 31 CCIS tests; 18 focused runtime/root tests; syntax checks
[P] LOCAL: shared OneDrive source; no commit or live inference claim
[N] Operator may opt in to the first real-host preflight; WO-054 remains gated on a successful digest-bound result

## Native contract

The task claims exactly three read-only resources: CPU inspection, the explicit
model path, and the requested CPU/GPU backend. Its process budget permits only
two metadata subprocesses. The native module never passes the model path to the
executable; the permitted argument set is exactly `--version` and
`--list-devices`.

Successful evidence has schema
`leafos.llamacpp_capability_preflight.v1`, mode `preflight_only`, and includes
both the admitted task digest and a SHA-256 digest over the complete capability
record. A failed prerequisite returns a typed `FAILED` result. A missing opt-in
returns `BLOCKED`, before either metadata subprocess is launched.

## Evidence log

- 2026-08-09: Registered `ccis.probe.llamacpp.capability` as the native handler and retained WO-054/WO-055 tasks as handlerless reservations.
- 2026-08-09: Added the read-only runtime probe and strict result schema.
- 2026-08-09: Added tests proving opt-in refusal, exact subprocess arguments, no model argument, task/result digest binding, GGUF identity, model and binary digests, host facts, resource claims, and explicit prerequisite failures.
- 2026-08-09: `python -m py_compile` passed for the native probe, CCIS dispatcher, and focused test module.
- 2026-08-09: `python -m unittest discover -s .\\ccis\\tests -t .` — 31 tests passed.
- 2026-08-09: focused taskpack run (`test_llamacpp_preflight`, `test_flower_monitor`, `test_runtime_capabilities`) — 18 tests passed.

## Carry-forward

- Run the first real host preflight only after explicit opt-in and retain its
  task digest, capability digest, executable digest, model digest, and raw
  metadata outputs as the admission evidence for WO-054/WO-055.
- A passing preflight proves capability prerequisites only. It does not prove
  model loading, inference quality, token generation, throughput, streaming, or
  provider health.

## Out of scope

- `llama-cli` inference or grammar evaluation.
- `llama-server` startup or HTTP streaming.
- Network access, model discovery, or downloads.
- Changes to the model installer or `PowerShell-Version` surfaces.
- Provider configuration, benchmarking, or semantic quality claims.
