# WO-061 — Loop Quality Evaluation and Improvement Propositions

## Identity

- Owner/context: liamm / LeafOS loop engineering and release decisions
- Current day: Day 0 (planned after WO-060)
- Release target: LeafOS 0.2.2 evaluation handoff
- Branch: `agent/organic-0.9.4-snapshot`
- Scope boundary: typed measurement aggregation, baselines, ranked propositions, CCIS admission handoff
- Renumbering note: moved intact from WO-057 when the supplied WO-057–WO-060 implementation sequence was admitted

## Objective

Convert the verified outputs of WO-052–WO-056 into reproducible loop-quality baselines and bounded improvement propositions without granting proposals execution authority.

## Live-inference intent

The quality baseline must be grounded in live inference: real local GGUF loads, real prompts, actual CPU/GPU token generation, real streaming behavior, and real containment outcomes. Mock and deterministic-fixture measurements remain useful for regression isolation but must be labeled separately and cannot substitute for live-inference evidence.

## Acceptance criteria

- [ ] `eval.loop_quality.v1` consumes typed results and rejects mixed schema/policy/model digests unless explicitly grouped.
- [ ] Raw measurements remain separate from the versioned scoring policy.
- [ ] Dimensions include evidence integrity, capability truthfulness, structured correctness, TTFT, jitter, completion, timeout containment, cleanup leakage, replay determinism, and run variance.
- [ ] Baseline and candidate runs share a declared comparison key and report confidence/sample limitations.
- [ ] Reports separate `live_inference`, `mock_transport`, `deterministic_fixture`, and `preflight_only` evidence classes and never aggregate them as equivalent samples.
- [ ] `proposal.loop_improvement.v1` cites the measurements, expected benefit, risk, scope, resource budget, validators, rollback, and stopping conditions.
- [ ] Propositions enter the rebuildable heap only after explicit CCIS admission and never self-approve.
- [ ] Priority changes are explicit allocation events, so re-ranking is auditable and replayable.
- [ ] The WO-LOOP1–LOOP6 coherence, command/alias, resource, result, full-path freeze, and real-outcome checks pass for every live-inference measurement path included in synthesis.
- [ ] [WO-017](WO-017-small-scale-moe-hardware-orchestration.md) comparisons group only compatible model, quantization, prompt, context, backend, placement, host, thermal/power, and policy digests; paired samples report confidence and non-regression limitations.
- [ ] A final report identifies immediate fixes, experiments, rejected ideas, and unresolved blockers.

## Status

[W] WO-061: evidence-backed loop-quality scoring and improvement propositions
[D] Day 0: final planned WO in the series
[I] TODO
[V] NONE: awaits comparable real-run evidence
[P] LOCAL: plan only
[N] After WO-060, combine LOOP6 outcomes and MATLABC++ trial evidence, then admit only comparable evidence-backed propositions.

## Out of scope

- Model-generated automatic code mutation or acceptance.
- A single composite score without raw evidence and policy version.
- Cross-model ranking when prompt, grammar, host, binary, or runtime settings differ materially.
- Automatic placement or expert promotion from no-hash, single-sample, CPU-only-provider, or no-inference MoE evidence.
