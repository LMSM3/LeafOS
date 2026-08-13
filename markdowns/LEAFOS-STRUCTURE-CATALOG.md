# LeafOS 0.2.1 Structure Catalog

**Scope.** This catalog classifies every directory at the repository root and every direct child directory beneath those roots. It is a structural map, not a recursive file manifest. Deeper paths are named only when they establish authority or explain runtime flow.

**Authority order.** For the current resident system, prefer machine-readable schemas and implementation, then `ProjectLeaf/leafos_taskpack/README.md`, then the current documents listed in `ProjectLeaf/leafos_taskpack/docs/DOCUMENTATION_MAP.md`. The root reusable-tool contract is `ROOT_CONTRACT.md`. Historical reports, imports, and experiment packs are evidence or specialized materials unless their own contract explicitly applies.

## System at a Glance

```text
Operator (PowerShell, Bash, or TUI)
			  |
			  v
PowerShell-Version/leaf.ps1 or Bash-Version/leaf.sh
			  |
			  v
ProjectLeaf/leafos_taskpack/bin/leafctl[.ps1]
			  |
			  +--> project intake and onboarding
			  +--> durable queue / loop inlet / validation
			  +--> resident supervisor and resource governor
			  +--> local llama.cpp provider proposals
			  |
			  v
run evidence: journal + checkpoint + report + telemetry
```

LeafOS is the durable project-automation engine; FlowerOS is the operator-facing usage surface. Local model output is proposal-only. CPU-side policy remains responsible for approval, filesystem boundaries, execution, validation, journaling, and checkpointing.

## Root Directories

| Directory | Classification | Use and authority | Status / handling |
| --- | --- | --- | --- |
| `.agents/` | Local agent support | Contains the `models/` location used for locally managed model material. | Local state; do not treat models as source. |
| `.git/` | Version-control metadata | Git repository internals. | Tool-managed; never catalog recursively or edit manually. |
| `.leaf-tools/` | Download-tool environment | Holds the `hf-download/` helper environment. | Generated/bootstrap support; not the engine. |
| `Bash-Version/` | Reusable Bash surface | POSIX-compatible wrapper commands, installation, local chat, model, and download-doctor helpers. `leaf.sh` delegates to the preserved taskpack CLI. | Active cross-platform entry surface. |
| `continue/` | Empty workspace placeholder | No immediate files or child directories were present. | Unclassified placeholder; no runtime role evidenced. |
| `IMPORTS/` | Imported compatibility/source snapshot | Earlier taskpack-style implementation and its docs, demos, build outputs, tasks, and tests. | Preserved reference/compatibility lane; do not assume it is the current resident engine. |
| `markdowns/` | Root documentation contract | Product map, installation, usage, root contract, and this catalog. | Authoritative for reusable-root layout and user orientation. |
| `New folder/` | Empty workspace placeholder | No immediate files or child directories were present. | Unclassified placeholder; no runtime role evidenced. |
| `PowerShell-Version/` | Reusable PowerShell surface | Windows-focused wrapper commands, installation, local chat, model, and download-doctor helpers. `leaf.ps1` delegates to the preserved taskpack CLI. | Active Windows entry surface; PowerShell 5.1 hands off to `pwsh`. |
| `ProjectLeaf/` | Preserved implementation owner | Owns the canonical taskpack engine and canonical model-acquisition package. | Primary implementation root. |
| `tmp/` | Temporary tooling and downloads | Stores local llama.cpp builds, smoke virtual environment, and PDF staging. | Generated/disposable; not a reusable contract. |
| `training-template/` | Future training-data template | Supplies an auditable SFT/LoRA data shape and training plan. | Template only; it does not directly train GGUF files. |
| `VSEPR-Day98-LeafOS-Run1/` | Bounded scientific experiment pack | Defines a separate, planned VSIM improvement loop with prompts, configs, and promotion gates. | Specialized experiment; not the LeafOS runtime API. |
| `VSEPR-Day98-LeafOS-Z-GR8/` | Empty experiment placeholder | No immediate files or child directories were present. | Reserved/unimplemented at the cataloged level. |

## Direct Subdirectories

### `.agents/`, `.leaf-tools/`, and shell surfaces

| Path | Classification | Contents / usage |
| --- | --- | --- |
| `.agents/models/` | Model storage | Local model-cache location. Keep separate from runtime source and durable run evidence. |
| `.leaf-tools/hf-download/` | Download helper environment | Python/virtual-environment-style support for model download tooling; bootstrap/generated support. |
| `Bash-Version/config/` | Shell-surface configuration | Bash entry-surface settings, including `leafos.bash.json`. |
| `Bash-Version/docs/` | Shell-surface documentation slot | Empty direct-file surface at catalog time. |
| `Bash-Version/reports/` | Shell-surface evidence | Report hierarchy for Bash-surface runs. Treat as generated operational evidence. |
| `PowerShell-Version/config/` | Shell-surface configuration | PowerShell entry-surface settings, including `leafos.powershell.json`. |
| `PowerShell-Version/docs/` | Shell-surface documentation slot | Empty direct-file surface at catalog time. |
| `PowerShell-Version/reports/` | Shell-surface evidence | Report hierarchy for PowerShell-surface runs. Treat as generated operational evidence. |

### `IMPORTS/`: imported compatibility and earlier taskpack lane

| Path | Classification | Contents / usage |
| --- | --- | --- |
| `IMPORTS/bin/` | Legacy/import command surface | Bash, PowerShell, Python, and helper launchers for the imported pipeline. |
| `IMPORTS/build/` | Build products | Compiled loader demo artifacts. Generated; rebuild rather than editing. |
| `IMPORTS/config/` | Imported configuration | Earlier provider, agent, glyph, brand, and related configuration. |
| `IMPORTS/core/` | Imported implementation modules | Earlier subsystems, including agent, provider, runtime, UI, memory, and validation modules. |
| `IMPORTS/demo/` | Demonstration packaging | PowerShell demonstration bundle material. |
| `IMPORTS/dist/` | Distribution artifacts | Archives and manifests for packaged releases. Generated release output. |
| `IMPORTS/docs/` | Imported architecture and guides | Earlier architecture, installation, usage, orchestration, and historical WO archive. Useful context; current resident docs take precedence. |
| `IMPORTS/reports/` | Imported evidence | Smoke, spine, and work-order reporting; historical/generated evidence. |
| `IMPORTS/runs/` | Imported runtime state | Earlier run directories. Operational evidence, not source authority. |
| `IMPORTS/tasks/` | Imported task examples | Example finite-pipeline task and generated plan files. |
| `IMPORTS/tests/` | Imported tests | Compatibility, smoke, and older pipeline tests. |

### `ProjectLeaf/`: implementation owner

| Path | Classification | Contents / usage |
| --- | --- | --- |
| `ProjectLeaf/.venv/` | Python environment | Local interpreter dependencies for this workspace. Generated; do not use as source. |
| `ProjectLeaf/.vs/` | Visual Studio workspace state | IDE settings and caches. Generated/local. |
| `ProjectLeaf/leaf_model_installer/` | Canonical model-acquisition package | Plan-first model lifecycle: catalog -> offline plan -> resolve/pin -> explicit apply -> verify. `apply` is the download boundary. |
| `ProjectLeaf/leafos_taskpack/` | Canonical LeafOS engine | Current resident taskpack: CLI, project intake, queue, supervisor, provider adapters, CPU policy, TUI, schemas, tests, and evidence. |

The taskpack is deeper than the requested second layer, but its internal boundaries explain most runtime behavior:

| Taskpack boundary | Role |
| --- | --- |
| `bin/` | `leafctl`, `leafctl.ps1`, FlowerOS wrapper, TUI, memory, model, and provider launchers. |
| `config/` and `schemas/` | Machine-readable policy and contract authority. |
| `core/python/` | Live-project intake, loop inlet, work-order lifecycle, resident supervision, resource governor, telemetry, and supporting runtime. |
| `core/providers/` | Local provider lifecycle and adapters, including llama.cpp routing. |
| `core/memory/` | Native-LMEM-backed durable journal integrations and derived retrieval projections. |
| `core/ui/` and `core/tui/` | Python and native TUI renderers consuming normalized snapshots. |
| `docs/` | Current architecture, operational guides, work-order history, and documentation precedence map. |
| `runs/`, `reports/`, `logs/`, `tmp/` | Generated operational evidence or temporary state. |
| `tests/` | Runtime, contract, integration, and visual test coverage. |

### Temporary, template, and experiment areas

| Path | Classification | Contents / usage |
| --- | --- | --- |
| `tmp/chat-smoke-llama-cpp/` | Provider smoke environment | Temporary local environment used to smoke-test llama.cpp chat behavior. |
| `tmp/llama-cpp-ubuntu-x64-b9828/` | Downloaded Linux llama.cpp package | Tool archive and extraction area. Disposable tooling. |
| `tmp/llama-cpp-win-cpu-b9828/` | Downloaded Windows CPU llama.cpp package | Executables and DLLs for a local tool build. Disposable tooling. |
| `tmp/pdfs/` | PDF staging | Temporary PDF workspace. |
| `training-template/config/` | Training template configuration | `training-plan.json` for future auditable data preparation. |
| `training-template/data/` | Example training data | `leafos-sft.example.jsonl` demonstrates accepted/rejected evidence-oriented records. |
| `VSEPR-Day98-LeafOS-Run1/config/` | Experiment configuration | Run parameters and source controls for bounded Day-98 / 98-Z experiments. |
| `VSEPR-Day98-LeafOS-Run1/examples/` | Experiment examples | VSIM contract examples; contains deeper `day98/` inputs. |
| `VSEPR-Day98-LeafOS-Run1/prompts/` | Experiment role prompts | Planner, explorer, coder, verifier, curator, and benchmark-judge instructions. |
| `VSEPR-Day98-LeafOS-Run1/VSEPR-Day98-LeafOS-Run1/` | Duplicated/nested experiment copy | Nested copy of the experiment material. Treat as an experiment artifact until a specific launcher establishes it as authoritative. |

## Usage Map

### Normal operator path

1. Start from the matching shell surface: `PowerShell-Version/leaf.ps1` on Windows or `Bash-Version/leaf.sh` on Bash-capable hosts.
2. The wrapper delegates to `ProjectLeaf/leafos_taskpack/bin/leafctl.ps1` or `bin/leafctl`.
3. Use `live` to inspect/onboard a project and establish a durable run.
4. The loop normalizes instructions to bounded work: `INTAKE -> PLAN -> APPROVE -> EXECUTE -> VALIDATE -> CHECKPOINT/REPORT`.
5. The local model provider emits structured proposals only; the inlet validates authority, paths, commands, budgets, and acceptance commands.
6. The resident supervisor and resource governor decide when eligible work may be claimed. They do not bypass the inlet.
7. Durable run evidence consists of queue/state, `events.jsonl`, `control.lmem`, checkpoints, telemetry, artifacts, and reports.

### Reading path for understanding the current engine

1. `ROOT_CONTRACT.md` — reusable-root ownership, shell surfaces, and safety boundaries.
2. `ProjectLeaf/leafos_taskpack/README.md` — product behavior and first live-project commands.
3. `ProjectLeaf/leafos_taskpack/docs/DOCUMENTATION_MAP.md` — document precedence and current reading order.
4. `ProjectLeaf/leafos_taskpack/docs/ARCHITECTURE.md` — authority boundaries and implementation locations.
5. `ProjectLeaf/leafos_taskpack/docs/AGENTIC_CLI.md` — instruction normalization and resident lifecycle.
6. `ProjectLeaf/leafos_taskpack/docs/MEMORY_MODEL.md` — record/evidence/committed-fact hierarchy.
7. `ProjectLeaf/leaf_model_installer/README.md` — model storage and explicit acquisition boundary.

## Boundary Rules Worth Retaining

- Do not promote model proposals to facts; only validation and checkpoint flows establish authoritative state.
- Do not treat virtual environments, `.vs`, downloaded models, tool binaries, `tmp`, `build`, `dist`, `runs`, or reports as canonical source.
- Do not use `IMPORTS/` or old/optional subsystem documentation to redefine the current resident project loop.
- Keep `apply` as the explicit model-download boundary.
- Keep the trusted project mutation boundary inside the accepted work order and CPU-side inlet.
- Treat the VSEPR pack as an isolated experiment: it must not mutate its trusted baseline without explicit promotion/apply authorization.
