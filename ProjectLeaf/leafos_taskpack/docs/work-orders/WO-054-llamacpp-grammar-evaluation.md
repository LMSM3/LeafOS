# WO-054 — Grammar-Bound llama.cpp Loop Evaluation

## Identity

- Owner/context: liamm / CCIS live-inference validation
- Current day: Day 0 (planned after WO-053)
- Release target: LeafOS 0.2.2 local-model loop evaluation
- Branch: `agent/organic-0.9.4-snapshot`
- Scope boundary: opt-in `llama-cli` execution in isolated workspaces, GBNF fixtures, typed measurements

## Source

Section 17: run a real local GGUF through `llama-cli` and require a small grammar-bound CCIS verdict.

## Live-inference intent

This WO performs live inference: `llama-cli` loads an actual local GGUF, receives a real prompt, computes fresh tokens on the selected CPU/GPU backend, and returns newly generated grammar-constrained output. Mock output, prerecorded fixtures, configuration-only checks, and policy-generated substitutes cannot satisfy acceptance.

## Acceptance criteria

- [ ] `eval.llamacpp.grammar.v1` requires a successful, matching WO-053 capability result.
- [ ] Command argv is fixed by the native handler: bounded context/tokens, seed, temperature, grammar, and timeout; `shell=False`.
- [ ] An exclusive accelerator claim prevents concurrent model loads unless configuration explicitly permits sharing.
- [ ] Raw stdout/stderr, argv, exit code, duration, model/binary digests, grammar digest, and parsed result are retained.
- [ ] Output must validate against the declared JSON result schema; prose-wrapped or malformed output fails closed.
- [ ] Evidence proves a real process and model load occurred and distinguishes generated tokens from echoed prompt text.
- [ ] Repeated runs separate transport/runtime success from structured correctness and report variance.
- [ ] No model output receives task, filesystem, acceptance, or handler authority.

## Status

[W] WO-054: real grammar-bound llama-cli evaluation
[D] Day 0: queued behind WO-053
[I] TODO
[V] NONE: design only; live inference has not yet been run for this WO
[P] LOCAL: plan only
[N] After WO-053 passes, run the first bounded grammar-constrained live-inference task

## MOE parallel handoff

- [WO-017/MOE-005 and MOE-006](WO-017-small-scale-moe-hardware-orchestration.md) reuse this proven live CLI path for functional expert execution. `llama-bench` throughput evidence remains placement evidence and cannot substitute for grammar-bound functional inference.

## Out of scope

- Free-form benchmark leaderboards or model fine-tuning.
- Applying model-proposed changes to the working tree.
