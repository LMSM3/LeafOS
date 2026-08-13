# LeafOS combined runtime: personas + model swarm

Scope: this document defines the role-selection envelope. It does not start a
provider and is not the resident scheduler. The stack inventory, runtime role
selection, and active provider route are three separate facts.

LeafOS now treats runtime choice as four independent choices under one envelope:

- main model: the planner, synthesizer, judge, and checkpoint authority
- scheduler model: the task queue, follow-up, and checkpoint scheduler
- coder model: the persona-neutral patch worker family
- persona: the voice, code policy, care mode, and output contract applied to the main model only

The default empty-input selection is:

```text
main model   gemma4-it-opus
scheduler    gemma4-it-opus
coder model  gemma4-coder
persona      monday
mode         loop
```

## Role rule

Fable/Gemma4-Coder is coding-only. It may generate patches, shell edits,
reviews, and verification signals, but it does not own main assistant or
scheduler authority.

Opus, or another model from the main-model pool such as the deeper reasoning
planner, owns main and scheduler duties.

The canonical manifest is `config/runtime.json`. The shell entrypoint is `core/runtime/runtime.sh`.

## Current Resident Route

The reference resident host currently serves the Gemma4-Coder Q3 stack entry
through llama.cpp Vulkan with one parallel slot. The version-2 loop uses that
provider for bounded structured proposals and keeps scheduling, path policy,
approval, execution, validation, checkpointing, and repair under CPU
authority. A future multi-model resident route may materialize the main,
scheduler, and coder roles independently without changing that boundary.

Do not infer that `runtime select` has loaded a model. It resolves policy only.
Use `provider-stack status` to inspect the active server and
`resident status active --json` to inspect the running scheduler.

## Output envelope

Every user-facing runtime event uses exactly this JSON shape:

```json
{
  "response_type": "plan",
  "content": "human-readable content",
  "confidence_score": "0.85"
}
```

No extra keys belong on the transport. Renderers may pretty-print `content`, but the wire object stays stable.

## Persona rule

Personas apply to the main model only. Coder workers stay persona-neutral and emit raw patches, critiques, and verification signals.

Friday declares `code_policy=avoid_unless_stuck`, so the coder swarm is suppressed until an explicit stuck signal asks for code.

Care mode is shared runtime behavior, not per-persona politeness. Medical, mental health, and grief contexts suppress snark and tail lines for every persona.

## Worker escalation

Confidence chooses the normal worker tier:

| Confidence | Workers |
| --- | --- |
| `>= 0.80` | scout, sketch, builder |
| `0.50 - 0.79` | scout, sketch, builder, reviewer |
| `< 0.50` | scout, sketch, builder, reviewer, hardcheck |

LeafOS also forces higher tiers when tests fail, workers disagree, the diff is large, installer/runtime/security files are touched, or the user marks the task hard.

## CLI

```bash
bin/leafctl runtime validate
bin/leafctl runtime select
bin/leafctl runtime select --persona friday --json
bin/leafctl runtime personas
bin/leafctl runtime models
bin/leafctl runtime workers 0.42 tests_failed
bin/leafctl runtime event plan 0.86 "Plan text here"
```

`runtime select` is offline and does not start or download models.
