# Flower Pack Constructor

`leafos pack` builds small, installable model-pack manifests without pretending
that downloaded weights are already wired into runtime roles.

## Guided use

From the repository root:

```powershell
.\leafos.ps1 pack create
```

The wizard asks for a name, a catalog preset or custom model selection, a
flower identity, and optional resource limits. It previews the exact
artifact count and estimated storage before writing anything. By default it
writes `ProjectLeaf/leafos_taskpack/config/packs/<pack-id>.json`.

Use `NO_COLOR=1`, `LEAF_GLYPHS=ascii`, or `NO_ANIMATION=1` when needed. Motion is
also automatically disabled for redirected output and CI.

## Scripted use

Start from a catalog preset:

```powershell
.\leafos.ps1 pack create `
  --name "Pocket Meadow" `
  --profile runtime-default `
  --flower clover `
  --colour green `
  --yes
```

Or choose exact artifacts. A numeric slot and a catalog key are equivalent;
append `:QUANT` to override the model's default quantization.

```powershell
.\leafos.ps1 pack create `
  --name "Coder Sprig" `
  --model 1:Q2_K `
  --model qwen35-opus-reasoning:Q4_K_M `
  --max-ram-gib 48 `
  --dry-run
```

Useful inspection commands:

```powershell
.\leafos.ps1 pack catalog
.\leafos.ps1 pack validate .\ProjectLeaf\leafos_taskpack\config\packs\pocket-meadow.json
```

`--json` provides stable machine-readable output. Writing in JSON mode requires
`--yes`; `--force` is required to replace an existing manifest. Experimental
models require `--include-experimental` and remain guarded by the installer.

## Install the result

Construction does not download models. It hands a valid `install.items` list to
the existing plan/resolve/apply pipeline:

```powershell
.\leafos.ps1 models-install plan-pack PACK.json --out leaf-model-plan.json
.\leafos.ps1 models-install resolve leaf-model-plan.json --out leaf-model-plan.resolved.json
.\leafos.ps1 models-install apply leaf-model-plan.resolved.json --yes
```

For an experimental pack, also pass `--include-experimental` to `plan-pack` and
`apply`, then repeat `--confirm-heavy MODEL_KEY` for each confirmation key shown
in the pack preview. No experimental weight is silently promoted into a plan.

The manifest records:

- exact catalog keys and quantizations, deduplicated by artifact;
- estimated bytes and a 15% disk-safety estimate;
- experimental confirmation keys;
- conservative local-model residency and optional RAM/VRAM limits;
- deterministic flower, colour, symbol, and palette metadata.

The constructor records identity but does not claim liveness on its own. When
the PowerShell subsystem indicator binds that identity to a live owned process,
the visible glyph becomes typed evidence of an active subsystem and its pack
identity binding. The constructor still does not generate runtime groups,
personas, capability authorization, provider-health claims, or routing; those
require their own validated runtime integration steps.
