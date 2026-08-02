# WO-018 - Local GGUF Capability Negotiation

## Identity

- Owner/context: LeafOS runtime profile and local stack integration
- Current day: Day 1
- Release target: 0.2.2.1 local runtime reliability
- Scope boundary: bounded GGUF metadata reads and runtime-profile negotiation

## Acceptance Criteria

- [x] Read GGUF v2/v3 metadata without scanning tensor payloads.
- [x] Resolve architecture, model name, and declared context length.
- [x] Mark a profile supported only when its allocation fits the verified model limit.
- [x] Fall back to `compat-4k` when the requested profile exceeds the local model limit.
- [x] Demonstrate at least 16,384 reasoning plus output tokens against a real local stack model.
- [x] Preserve byte-equivalent Bash and PowerShell profile manifests.

## Status

[W] WO-018: Local GGUF capability negotiation
[D] Day 1: implementation complete
[I] DONE
[V] PASS: four focused tests, launcher equivalence, and real Gemma4 metadata probe
[P] LOCAL
[N] Feed verified capability fields into the operator home and future provider start policy

## Evidence

- `core/runtime/gguf_metadata.py` implements bounded GGUF header parsing.
- `core/runtime/profile_resolver.py` now emits verified model capabilities and the capacity equation.
- The local `gemma4-coding-Q4_K_M.gguf` reports a 262,144-token model limit; the 65,536-token continual profile resolves as supported with 16,384 reasoning plus 8,192 output tokens.
- `tests/test_runtime_capabilities.py` covers supported, fallback, malformed, and metadata-read paths.
