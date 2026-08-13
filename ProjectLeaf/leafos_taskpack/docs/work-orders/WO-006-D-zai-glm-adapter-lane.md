# WO-006-D — Z.AI / GLM Advisory Provider Adapter

## Identity

- Owner/context: LeafOS 0.6 provider-layer extension
- Current day: Day 2
- Release target: 0.6 adapter lane
- Branch: local workspace
- Scope boundary: `core/providers/`, `config/providers.conf`, provider contract tests
- Authority: `docs/design/model_assignment.tex` D-006 lane split

## Acceptance criteria

- [x] `zai` and `glm` dispatch through the existing file-backed provider contract.
- [x] Z.AI uses the OpenAI-compatible `/chat/completions` endpoint with API-key indirection.
- [x] Remote GLM is limited to explicit planner/reviewer advisory routing; the default coder lane remains CPU/local (`mock`).
- [x] Request construction supports a bounded 12K output cap and `reasoning_effort=medium` default.
- [x] CPU-side parsing, validation, gates, hashes, reports, and filesystem authority remain unchanged.
- [x] The adapter has deterministic local regression coverage without a live credential or network call.

## Status

[W] WO-006-D: Z.AI / GLM advisory provider adapter
[D] Day 2: implementation and closeout
[I] DONE
[V] PASS: syntax checks plus provider integration suite
[P] LOCAL
[N] Optional live smoke test after `ZAI_API_KEY` is supplied; B plan remains deferred

## Evidence log

- 2026-09-XX: Added `zai|glm` dispatch to `core/providers/providers.sh` without changing the provider contract: response text is atomically written to `LEAF_PROVIDER_TEXT_FILE` and remains subject to existing CPU-side graph/plan validation.
- 2026-09-XX: Added `LEAF_ZAI_KEY_VAR=ZAI_API_KEY`, `LEAF_ZAI_MODEL=glm-5.2`, standard and coding base URL configuration, `medium` reasoning effort, and 12K output-token default. Credentials are not stored in configuration.
- 2026-09-XX: Preserved CPU authority by defaulting `LEAF_CODER_PROVIDER` to `mock`; `zai` status labels GLM as a planner/reviewer advisory lane.
- 2026-09-XX: Added deterministic Z.AI coverage to `tests/providers.sh` with a local `curl` stub. It verifies endpoint, model, 12K cap, reasoning effort, response file persistence, and provider contract success with no live endpoint or key.
- 2026-09-XX: Ran `bash -n core/providers/providers.sh`, `bash -n core/providers/test.sh`, `bash -n tests/providers.sh`, then `bash tests/providers.sh`; all passed with MSYS2 `/ucrt64/bin` available for `python3`. `leaf_provider_status` correctly warns only that `ZAI_API_KEY` is absent.

## Carry-forward

- Run an explicit live planning/reviewer smoke test only after setting `ZAI_API_KEY`; do not route the coder lane to GLM without a separate reviewed contract.
- Treat `LEAF_ZAI_CODING_BASE_URL` as future configuration until a separate coding-output contract and CPU validation path are approved.

## Out of scope

- Storing API credentials.
- Remote authority over graph state, filesystem actions, patches, validation, gates, hashes, or reports.
- Local GLM-4.5 inference; it remains a future vLLM/SGLang OpenAI-compatible runtime target.
- The user’s subsequent B plan.
