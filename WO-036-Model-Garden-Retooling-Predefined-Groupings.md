# WO-036 — Model Garden Retooling: Predefined Model Groupings

Status: Draft → Active  
Priority: High  
Target: LeafOS 0.9.6  
Scope: Model garden metadata, provider routing, GPU-load policy  
Depends on: WO-035 (Allow-model filters and slot binding), WO-LeafOS-Medium-MoE-Router  
Produces: A compact, auditable taxonomy of predefined model groupings that feed into allow-model filters and slot resolution.

## 1. Problem

The model garden is about to grow from a handful of curated experts to tens or hundreds of candidate checkpoints, delivered as **packs**: layered JSON bundles of up to ~20 models and over 200 GB. Adding models one-at-a-time would create:

- **Exploded routing decisions** — roles alone cannot distinguish variants.
- **Hidden multi-load conflicts** — two large primaries can be selected and swapped into VRAM inside a single hour, leaving GPU underutilized during load time.
- **No path to specialization** — there is no declarative bucket that says "these models are all feeder-grade coding variants" or "this set is for long-context synthesis."

The solution is to keep models in **predefined groupings** selected by a task profile, then resolve to exactly one checkpoint per slot with the existing allow-model filter machinery. Groupings are themselves selected from a **pack** (e.g. `mwtf`), so the model garden scales from pack inventory down to a single active checkpoint.

## 2. Design philosophy

- **Higher GPU utilization per hour is the goal.** Groupings are chosen so that, within one hour, the scheduler can keep one model loaded and execute multiple assignments on it instead of thrashing VRAM.
- **Predefinition prevents runtime overfit.** A grouping and pack are named, versioned config objects, not user queries.
- **One active model per root per assignment.** The slot + filter machinery from WO-035 remains the single enforcement point.
- **A pack is inventory; a group is selection; a slot is runtime.** A pack may contain 200 GB of artifacts, but only one local model runs at a time by default.
- **Today: metadata and policy only.** No training, no fine-tuning, no expert merging. Those are future WOs.

## 3. Grouping taxonomy

A grouping is a named set of model ids with a declared intent. The taxonomy is layered:

```text
purpose   → what class of work this grouping serves
size      → target compute/VRAM budget
origin    → upstream family (qwen, kimi, deepseek, llama, gemma, mistral, ...)
tier      → quality/cost tier (feeder, primary, judge, mtp, distilled)
quant     → accepted quantization set
placement → runtime location (local, remote, hybrid)
```

### 3.1 Predefined grouping categories

| Category   | Description                                                          | Example name                    |
|------------|----------------------------------------------------------------------|---------------------------------|
| `core`     | Small, general-purpose checkpoints always loaded or cheap to load.   | `core.8b-q4km-local`            |
| `router`   | Fast triage / collar models used before dispatch.                    | `router.7b-q4km-local`          |
| `brain`    | Long-horizon planning / synthesis.                                   | `brain.k2.6-brain.q6k-local`    |
| `coder`    | Code generation / build repair.                                      | `coder.32b-iq2m-local`          |
| `critic`   | Review and contradiction detection.                                  | `critic.14b-q4km-local`         |
| `judge`    | Final release authority with high temperature / reasoning budget.    | `judge.k2-thinking.remote`      |
| `writer`   | Polished prose and documentation.                                    | `writer.32b-q4km-local`         |
| `qa`       | Question-answering and evidence lookup.                              | `qa.7b-q4km-ctx128k-local`      |
| `vision`   | Multimodal / image-capable checkpoints.                              | `vision.7b-vl-local`            |
| `special`  | Reserved for future trained experts (not implemented today).         | `special.memex-v1-local`        |

Groupings are orthogonal to roles: a role can request a grouping, and the grouping resolves to an allowed model list for a slot. A **pack** selects the legal set of groupings for each layer. See `docs/MODEL_PACK_SCHEMA.md` and `config/packs/mwtf-pack.json`.

## 4. Schema extension

Add a new file type: `leafos.model-group/v1`.

```json
{
  "schema": "leafos.model-group/v1",
  "id": "coder.default-local",
  "slot": "coder.primary",
  "enabled": true,
  "policy": {
	"parallel_load": false,
	"preferred_quantization": ["IQ2_M", "Q4_K_M", "Q6_K"],
	"max_vram_gib": 12.0,
	"max_ram_gib": 16.0,
	"allow_remote": false
  },
  "members": [
	{ "id": "qwen25-coder-32b-iq2m-local", "weight": 100 },
	{ "id": "qwen25-coder-14b-q4km-local", "weight": 70 },
	{ "id": "kimi-k27-code-remote", "weight": 50, "remote_only": true }
  ]
}
```

Rules:

- `id` uniquely identifies the grouping.
- `slot` is the logical slot this grouping feeds.
- `policy.parallel_load` is always `false` by default in this WO to maximize GPU util/hour.
- `members` is an ordered list; the router's allow-model filter is populated with `members[*].id`.
- `weight` is used only for deterministic tie-breaking within the allowed set, not as a score override.

## 5. Pack → group → checkpoint flow

At runtime:

```text
Task profile selects pack id
		|
		v
Resolver picks a group per pack layer
		|
		v
Loader resolves grouping file → allow_models list
		|
		v
Router applies role eligibility + allow_model filter (WO-035)
		|
		v
Single checkpoint selected
```

A pack therefore constrains *which* groups are legal to activate, while a group constrains *which* members are legal inside a slot. The router's `AllowModelFilter` remains the single enforcement point.

- The router already enforces `AllowModelFilter.allow_ids` after hard eligibility.
- No changes to `moe_router.cpp` are needed for this WO.
- `leaf-roundtable --group <id>` is implemented; `--pack <id>` is future work.

## 6. Acceptance criteria

- [x] WO-036 document created and recorded in evidence log.
- [x] At least 5 predefined grouping examples created under `config/groups/` (now 7 Blue Banyan Council groups + 5/6 earlier groups).
- [x] Each grouping references only existing experts or explicitly declared missing-artifact placeholders.
- [x] Groupings declare `parallel_load: false` by default.
- [x] `ctest` still passes after adding config files.
- [x] Evidence log captures rationale for taxonomy choices.
- [x] `leaf-roundtable plan --group <id>` loads group and emits session plan.
- [x] Pack schema documented (`docs/MODEL_PACK_SCHEMA.md`) and example packs created (`config/packs/blue-banyan.json`, `mwtf-pack.json`).
- [x] Blue Banyan Council Stack: 16 installed expert profiles across 7 groups, recursive registry loading, and per-member eligibility in dry-run session plans.

## Status

```text
[W] WO-036: Model Garden Retooling — Predefined Groupings
[D] Day closed: 2026-07-28
[I] COMPLETE (metadata + policy slice)
[V] VALIDATED: ctest passes; leaf-roundtable --group emits session plan; group configs reference existing experts or placeholders
[P] LOCAL
[N] Future: pack loader + `--pack` flag; hot-load / unload orchestration; VRAM threshold warnings; group training pipeline
```

## Evidence log

- 2026-07-28: WO-036 created. Predefined grouping taxonomy chosen to maximize GPU util/hour by keeping one model loaded per hour.
- 2026-07-28: Created `config/groups/` with 5 group files: `coder.default-local`, `mapper.default-local`, `brain.judge-remote`, `qa.default-remote`, `core.feeder-local`, and `vision.placeholder`.
- 2026-07-28: All groups declare `parallel_load: false`; vision group is disabled with empty members as a placeholder.
- 2026-07-28: Added GroupRegistry loader and `--group` flag to `leaf-roundtable`; emits `leafos.route.session.v1` plan.
- 2026-07-28: Centralized `json_escape_string`, `provider_kind_to_string`, `placement_to_string` in providers_core.
- 2026-07-28: `ctest` passes.
- 2026-07-28: Documented pack/group/slot hierarchy; created `mwtf-pack.json` placeholder and `MODEL_PACK_SCHEMA.md`.
- 2026-07-29: Replaced Yellow Flower Stack with Blue Banyan Council: 16 installed local members, 7 groups, recursive expert loading, and dry-run plans that show every group member wired to `local_cpu`/`local_gpu` segments.
