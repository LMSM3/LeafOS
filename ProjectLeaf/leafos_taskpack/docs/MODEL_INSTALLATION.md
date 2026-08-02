# LeafOS Model Installation

LeafOS has one model acquisition command surface:

```bash
leafctl models-install catalog
leafctl models-install plan --profile runtime-default
leafctl models-install resolve leaf-model-plan.json
leafctl models-install apply leaf-model-plan.resolved.json --yes
```

## Terminology

Within LeafOS documentation:

- **stack** — the complete set of models downloaded and locally available to this LeafOS instance.
- **pack** — the largest distribution unit: a layering JSON that bundles many checkpoints, often up to ~20 models and over 200 GB. See `docs/MODEL_PACK_SCHEMA.md` and `config/packs/mwtf-pack.json` for an example.
- **group** — a filtered subset of a pack bound to one logical slot, e.g. `coder.default-local`.
- **slot** — a logical runtime role, e.g. `coder.primary` or `judge.primary`.

A stack entry may be a pack, group, artifact, quantization, or role assignment. See `docs/TERMINOLOGY.md` for the shared wording.

For the merged persona/model-swarm runtime, use the runtime boot profile:

```bash
leafctl models-install plan --profile runtime-default --out leaf-runtime-plan.json
```

The implementation is provided by the sibling `leaf_model_installer` package or
an installed `leaf-models` command. LeafOS itself does not keep a second stack
catalog and does not download Hugging Face files directly.

## Selection Versus Inventory

Installing a model or pack adds a stack entry. It does not make that model active,
start a provider, or grant it a runtime role. `config/runtime.json` describes
role selection, while `config/vulkan-provider-stack.json` describes the model
currently served by llama.cpp for the provider lane.

A pack is an inventory convenience. A 200 GB pack can be installed without being
fully resident. Only one local model is active at a time unless a profile
explicitly enables parallel load and VRAM permits.

## Pack installation

Packs are installed at the pack level but resolved into groups and members:

```bash
leafctl models-install plan --pack mwtf --out mwtf-plan.json
leafctl models-install resolve mwtf-plan.json
leafctl models-install apply mwtf-plan.resolved.json --yes
```

After installation, activation still goes through the router:

```bash
leaf-roundtable plan --group coder.default-local --dry-run
```

On the reference RTX 4070 host, the resident coding route selects
`Gemma4-Coder/gemma4-coding-Q3_K_M.gguf`. Real resident trials showed that Q4
and larger assistant routes could leave too little RAM for execution, tests,
telemetry, and foreground work. This is a host-sized active route, not a limit
on which entries may exist in the stack.

GLM-5.2 is deprecated for local activation on this host. The active research
policy in `config/medium_moe_policy.json` prefers MoE candidates with 47-156B
total parameters, but installation alone does not qualify one. Copy
`config/medium_moe_candidate.template.json`, pin its identity and artifact,
record its active topology, and complete the 4/8/64 minute qualification in
`docs/MEDIUM_MOE_MODEL_POLICY.md`. The incumbent provider route remains active
until that evidence is reviewed and approved.

## Safety boundary

- `catalog`, `plan`, `show`, `status`, and `doctor` are local-only.
- `resolve` reads metadata and pins repository revisions.
- `apply` is the only weight-download operation.
- `apply` requires a resolved plan and `--yes`.
- Experimental slot 5 also requires
  `--include-experimental --confirm-heavy gpt-oss-120b`.

The `runtime-default` plan contains the documented main and coding families.
The historical
two-coder download profile is named `legacy-coder-pair` and is not used by the
runtime role policy. Post-install creates only an offline plan. It never starts
model downloads automatically.

## Storage

The local stack defaults to `~/.leaf/models`. Override this with
`LEAF_MODEL_DIR`. Installer state is written below `.leafos-installer` in that
stack root. Pack manifests live under `config/packs/`; group manifests live under
`config/groups/`.

## Blue Banyan Council Stack installation

The current installed LeafOS stack is the **Blue Banyan Council** (`blue-banyan`, pack id `2`). It is derived directly from the `flower-pack-1.2.0` release already present at `C:\flower-pack-1.2.0` and contains 16 expert profiles across 7 groups: router, brain, code, critic, writer, judge, and helpertext.

Install via the flower-pack CLI (Windows PowerShell):

```powershell
cd C:\flower-pack-1.2.0\flower-pack-1.2.0
$env:FLOWER_MODEL_ROOT = 'C:\R\LeafOS0.2.1\models'
pwsh -NoProfile -ExecutionPolicy Bypass -File .\flower-pack.ps1 install 1 --yes
```

Then verify:

```powershell
pwsh -NoProfile -ExecutionPolicy Bypass -File .\flower-pack.ps1 verify 1
```

After the download finishes, the artifacts are placed under
`C:\R\LeafOS0.2.1\models\packs\pack-1\<entry_id>\`.

### Windows bootstrap

If you are starting from a host without `flower-pack` installed, run the bootstrap
PowerShell script. The release host and version are configurable through
environment variables.

```powershell
# Optional overrides
$env:LEAF_RELEASE_HOST      = 'https://releases.leafos.local'
$env:LEAF_FLOWER_PACK_VER   = '1.2.0'

pwsh -NoProfile -ExecutionPolicy Bypass -File C:\path\to\flower-pack-install.ps1
```

The script downloads the release archive, verifies its SHA-256 hash, extracts it
to `C:\flower-pack-<version>`, flattens the nested archive directory if present,
unblocks files, and runs `repair-install.ps1`. A copy is kept at
`ProjectLeaf/install/windows/flower-pack-install.ps1`.

### Installation phases

| Phase | Purpose | Command |
|-------|---------|---------|
| Inspect | Show pack entries and total size | `pwsh -NoProfile -ExecutionPolicy Bypass -File .\flower-pack.ps1 show 1` |
| Download | Acquire artifacts into model root with resume support | `pwsh -NoProfile ... -File .\flower-pack.ps1 install 1 --yes` |
| Verify | Check size and, if available, SHA-256 of each artifact | `pwsh -NoProfile ... -File .\flower-pack.ps1 verify 1` |
| Status | Show which pack entries are present/missing | `pwsh -NoProfile ... -File .\flower-pack.ps1 status 1` |
| Dry run | Validate every group wiring without loading models | `leaf-roundtable plan --group blue.brain --dry-run` etc. |
| Launch test | Start each local model serially and record metrics | `leaf-model test blue-banyan --serial` |

### What a Blue dry run looks like

Because `flower-pack-1.2.0` Blue is already installed, the experts are
registered and enabled. A dry run checks every group member, maps it to the
correct CPU/GPU segment, and records memory usage:

```bash
leaf-roundtable plan --group blue.brain --dry-run
```

```text
members_requested: 2
members_eligible: 2
simultaneous_memory_gib: 24.0
finish_reason: all_members_ready
models:
  blue-brain-primary  local_gpu  eligible=true  reason=ok
  blue-brain-feeder   local_cpu  eligible=true  reason=ok
```

### Partial installs

```bash
flower-pack install 1 --only router
flower-pack install 1 --only brain,code
flower-pack install 1 --only judge
flower-pack install 1 --only helpertext
```

### Status and repair

```bash
flower-pack show 1
flower-pack status 1
flower-pack verify 1
flower-pack repair 1
flower-pack path 1 brain-primary
```

### Completion criteria

The Blue Banyan Council Stack is ready when:

1. Pack manifest `blue-banyan` exists and is recorded.
2. All 16 expert profiles are registered.
3. Every local profile resolves to an exact file under the flower-pack model root.
4. Every Hugging Face source uses a pinned revision.
5. Every installed artifact has a verification record.
6. Incomplete files are excluded from publication.
7. Local groups pass route-plan validation.
8. Every local model passes an individual launch test.
9. Memory estimates, context ceilings, and fallback chains are recorded.
10. Blue experts are enabled and point at `C:\flower-pack-1.2.0\flower-pack-1.2.0\models`.

Expected final status:

```text
Blue Banyan Council Stack
Status: ready
Expert profiles: 16
Local profiles: 16
Remote profiles: 0
Groups: 7
Missing artifacts: 0
Unverified artifacts: 0
Broken registrations: 0
Launch tests passed: 16/16
```

## Resume

Run `apply` again with the same resolved plan. Partial Hugging Face cache files
are retained and reused. LeafOS does not delete partial stack data implicitly.
