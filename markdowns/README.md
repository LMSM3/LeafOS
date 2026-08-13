# LeafOS 0.2.2

> **State outranks conversation.**

LeafOS is a local orchestration and durability layer for serious work with
local language models. It is not another chat wrapper. It is the "work" half of
the FlowerOS family: FlowerOS controls the machine, LeafOS controls the work.

The central doctrine is short and strict:

```text
FlowerOS controls the machine.
LeafOS controls the work.
Native tools prove.
Models interpret.
State outranks conversation.
```

LeafOS turns your intent into bounded, inspectable, resumable state
transitions. It routes tasks across multiple specialist model quantizations
instead of pretending one monolithic model can do everything. It records every
claim, requires native evidence before a claim becomes fact, and never lets the
KV cache, the terminal, or a crashing process become the source of truth.

The current release is **0.2.2**. Earlier high-number labels remain historical
development-stage evidence; `VERSION`, the taskpack `VERSION`, and
`leafos.root.json` are the authoritative active version sources. See
[CONSOLIDATION-0.2.2.md](CONSOLIDATION-0.2.2.md) for source and WO continuity.

## What makes LeafOS different

- **Mixture-of-models, not model-as-god.** Declarative *packs* describe layers
  such as `router`, `brain`, `code`, `critic`, `judge`, `writer`, and `helper`.
  The runtime activates only the models the task needs and degrades gracefully
  when memory is tight.
- **Personas with durable identities.** The MWF system — **Monday — Rescue and
  Analysis**, **Wednesday — Explore and Create**, and **Friday — Research and
  Delivery** — is not cosmetic. Each persona reads a hash-chained transcript,
  records its read head, and is rejected if it tries to commit stale output.
- **Native proof first.** Compilation, tests, JSON schemas, file hashes, and
  structured tool output promote claims to facts. Model confidence is not
  evidence.
- **Plan-first model acquisition.** Model downloads are never accidental. The
  boundary is `apply`, and `apply` requires explicit confirmation.
- **Recovery by design.** If the process, GPU, KV cache, or terminal disappears,
  LeafOS rebuilds state from the persona contract, validated facts, checkpoint,
  and transcript tail.

Read [LEAFOS-CONTINUAL-BLOOM-PRIMARY-REFERENCE.md](../LEAFOS-CONTINUAL-BLOOM-PRIMARY-REFERENCE.md)
for the full architecture and design rationale.

## Layout

This is a *two-surface* root. Pick the folder that matches your terminal, then
run LeafOS through that surface. The friendly wrappers delegate into
`ProjectLeaf/`, where the preserved source tree lives.

```text
LeafOS/
??? PowerShell-Version/     # Windows-friendly entrypoint
??? Bash-Version/           # Linux, macOS, WSL, MSYS2, Git Bash entrypoint
??? ProjectLeaf/            # preserved implementation tree
??? LEAFOS-CONTINUAL-BLOOM-PRIMARY-REFERENCE.md
??? LEAFOS-CONTINUAL-BLOOM-PRIMARY-REFERENCE.formatless.tex
??? markdowns/              # product map, usage, installation, root contract
?   ??? README.md           # this file — the project map
?   ??? USAGE.md            # day-to-day command reference
?   ??? INSTALLATION.md     # setup and safety boundaries
?   ??? ROOT_CONTRACT.md    # reusable-tool surface contract
??? leafos.root.json        # machine-readable root layout and authorities
??? VERSION                 # 0.9.3
```

## First five minutes

Pick one surface and run the readiness checks. None of these commands download
models.

### PowerShell

```powershell
cd C:\path\to\LeafOS\PowerShell-Version
pwsh -File .\install.ps1
..\leafos.ps1 q   # quick command card
..\leafos.ps1 s   # status
..\leafos.ps1 d   # doctor
..\leafos.ps1 r   # runtime selection
```

### Bash

```bash
cd /path/to/LeafOS/Bash-Version
bash install.sh
bash ../leafos.sh q
bash ../leafos.sh s
bash ../leafos.sh d
bash ../leafos.sh r
```

After install, the global shortcut `leafos` is available if you chose to add it
to PATH. From a source checkout, use `..\leafos.ps1` or `bash ../leafos.sh`
instead.

## Documentation compass

| What you want | Read |
|---|---|
| Governing architecture, personas, and Continual Bloom runtime | [Continual Bloom Primary Reference](../LEAFOS-CONTINUAL-BLOOM-PRIMARY-REFERENCE.md) |
| First durable Monday release gate and runtime contracts | [Continual Bloom Runtime](../ProjectLeaf/leafos_taskpack/docs/CONTINUAL_BLOOM_RUNTIME.md) |
| Reusable-tool surface, ownership, and configuration authority | [ROOT_CONTRACT.md](ROOT_CONTRACT.md) |
| Install, safety boundaries, and first run | [INSTALLATION.md](INSTALLATION.md) |
| Day-to-day commands and practical workflows | [USAGE.md](USAGE.md) |
| Bash taskpack CLI reference | [ProjectLeaf/leafos_taskpack/README.md](ProjectLeaf/leafos_taskpack/README.md) |
| Model acquisition, catalog, and verification | [ProjectLeaf/leaf_model_installer/README.md](ProjectLeaf/leaf_model_installer/README.md) |
| Structural catalog of the repository | [LEAFOS-STRUCTURE-CATALOG.md](LEAFOS-STRUCTURE-CATALOG.md) |

Rules of thumb:

- `LEAFOS-CONTINUAL-BLOOM-PRIMARY-REFERENCE.md` is the design and architecture
  reference.
- `LEAFOS-CONTINUAL-BLOOM-PRIMARY-REFERENCE.formatless.tex` is its include-ready
  LaTeX fragment.
- `leafos.root.json` is the machine-readable root contract.
- `README.md` (this file) is the map.
- `USAGE.md` is the daily command reference.
- `INSTALLATION.md` is setup and the download safety boundary.
- `ROOT_CONTRACT.md` is the reusable-tool surface contract.

## Core commands

From the repository root, the stable reusable-tool surface is:

```powershell
.\leafos.ps1 validate-root   # verify root contract and layout
.\leafos.ps1 status          # fast runtime status
.\leafos.ps1 doctor          # dependency and readiness check
```

```bash
bash leafos.sh validate-root
bash leafos.sh status
bash leafos.sh doctor
```

All other arguments are delegated unchanged to the matching PowerShell or Bash
surface.

## Model downloads

LeafOS defaults to safe. It will not download model weights unless you
cross the `apply` boundary.

```text
catalog/status/doctor = local-only
plan                  = offline JSON plan
resolve               = remote metadata and revision pins only
apply                 = model weight download boundary
```

PowerShell workflow:

```powershell
.\real-models.ps1                      # status + offline plan
.\real-models.ps1 -Resolve             # metadata only
.\real-models.ps1 -Resolve -Apply -Yes # download/resume after review
```

Bash workflow:

```bash
bash real-models.sh
bash real-models.sh --resolve
bash real-models.sh --resolve --apply --yes
```

One-command automation keeps the same boundary:

```powershell
.\install-real.ps1       # preview, no network/download
.\install-real.ps1 -Yes  # resolve + download/resume + verify
```

```bash
bash install-real.sh
bash install-real.sh --yes
```

`apply` is the only phase that touches the network for weights.

## Run roles and defaults

The default profile is `runtime-default`. It prepares:

- `gemma4-coder` at `Q4_K_M` for coding work only.
- `gemma4-opus-assistant` at `Q4_K_M` for main assistant and scheduler duties.

Role rule:

- Gemma/Fable coder is **coding-only**.
- Main and scheduler duties use Opus or another model from the main-model pool.
- The default scheduler is `gemma4-it-opus`.

Model storage resolution order:

1. Explicit command argument.
2. `LEAF_MODEL_DIR` environment variable.
3. Existing GGUF cache under `ProjectLeaf/leaf_model_installer/models`.
4. Catalog default: `~/.leaf/models`.

`models.ps1` and `models.sh` remain as compatibility aliases.

## Where this is going

The path from `0.9.2` is the Continual Bloom runtime: first prove a single,
durable Monday personality, then add Wednesday and Friday, then expose an
optional two-way chat mode whose only purpose is to project the same durable
state. The chat surface is not the goal; correct, recoverable state is the goal.

If something is unclear, start with [USAGE.md](USAGE.md). If something feels
unsafe, read [INSTALLATION.md](INSTALLATION.md) and the safety rules in
[ROOT_CONTRACT.md](ROOT_CONTRACT.md). If you want the *why* behind every choice,
read the [Continual Bloom Primary Reference](../LEAFOS-CONTINUAL-BLOOM-PRIMARY-REFERENCE.md).

