# LeafOS Model Pack Schema (`leafos.model-pack/v1`)

A **model pack** is the largest unit of model distribution in LeafOS. A pack bundles many checkpoints — typically up to ~20 models, potentially over 200 GB of quantized artifacts — into a single layering JSON that can be installed, updated, and activated as one.

Packs sit above **groups** and **slots**:

```text
pack      → top-level bundle (e.g. mwtf)
  layer   → functional slice (e.g. coder, brain, judge)
	group → filtered set of models for a slot (e.g. coder.default-local)
	  member → one concrete checkpoint (e.g. qwen25-coder-32b-iq2m-local)
```

## Fields

| Field            | Type            | Required | Description |
|------------------|-----------------|----------|-------------|
| `schema`         | string          | yes      | Must be `leafos.model-pack/v1`. |
| `id`             | string          | yes      | Pack identifier. |
| `name`           | string          | no       | Human-readable name. |
| `description`    | string          | no       | What the pack covers and its rough size. |
| `version`        | string          | no       | Semantic version. |
| `enabled`        | bool            | no       | Whether the pack may be activated. Default false for placeholders. |
| `notes`          | string          | no       | Warnings or migration notes. |
| `policy`         | object          | yes      | Load and resource policy. |
| `layers`         | array           | yes      | Functional layers inside the pack. |
| `groups`         | array of string | yes      | All `leafos.model-group/v1` ids referenced by this pack. |

### `policy` fields

| Field                       | Type    | Description |
|-----------------------------|---------|-------------|
| `parallel_load`             | bool    | If false, only one local model may be resident at a time. |
| `max_concurrent_local_models` | int   | Hard ceiling on simultaneously loaded local checkpoints. |
| `max_pack_vram_gib`         | double  | Design VRAM budget for the pack. |
| `max_pack_ram_gib`          | double  | Design RAM budget for the pack. |
| `allow_remote`              | bool    | Whether remote members may be selected. |
| `require_grouped_activation`| bool    | If true, only whole groups may be activated, not arbitrary models. |

### `layers` entries

| Field           | Type    | Description |
|-----------------|---------|-------------|
| `layer`         | string  | Layer id (router, brain, coder, critic, judge, writer, vision, special). |
| `purpose`       | string  | One-line role of the layer. |
| `default_group` | string  | Group id used when no explicit group is requested. |
| `max_models`    | int     | Maximum members that may be active from this layer at once. |

## Activation flow

1. User or task profile selects a pack id.
2. Loader reads the pack and resolves `layers` to concrete groups.
3. Router applies allow-model filters from the selected group.
4. One checkpoint per active slot is selected.
5. Local models are loaded one-at-a-time unless `parallel_load` is explicitly enabled and VRAM permits.

## GPU utilization rule

Packs default to `parallel_load: false`. This keeps GPU utilization per hour high by avoiding repeated model swaps. A 200 GB pack is an inventory, not a resident set.
