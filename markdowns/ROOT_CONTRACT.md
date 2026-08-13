# LeafOS Reusable-Tool Root Contract

This contract defines the stable entry surface for the reusable LeafOS tool.
It does not replace the roadmap or alter the preserved implementation tree.

## User entrypoints

| Surface | Directory | Canonical command | Intended host |
| --- | --- | --- | --- |
| PowerShell | `PowerShell-Version/` | `./leaf.ps1` | Windows PowerShell 5.1 with automatic `pwsh` handoff, or PowerShell 7+ |
| Bash | `Bash-Version/` | `bash leaf.sh` | Linux, macOS, WSL, MSYS2, or Git Bash |
| README program | repository root | `.\program.ps1` or `bash program.sh` | Interactive README, permanent-asset, and version stewardship |

`LEAFOS-CONTINUAL-BLOOM-PRIMARY-REFERENCE.md` is the primary design and
architecture reference. `markdowns/README.md` is the product map.
`markdowns/USAGE.md` is the day-to-day command reference.
`markdowns/INSTALLATION.md` defines setup and download safety boundaries.
The primary reference guides architecture and release direction; executable
configuration authorities remain controlling for concrete runtime values.

## Source ownership

`ProjectLeaf/` is the preserved implementation tree. It owns:

- `leafos_taskpack/`: task, graph, action, verification, and reporting runtime.
- `leaf_model_installer/`: canonical model acquisition and verification flow.

`ccis/` owns the typed change-control contracts, deterministic allocator, and
evidence gates. `loop/` owns the nested Scientific Change Loop coordinator.
Both are invoked through the root surfaces and consume the taskpack runtime;
neither may create a second journal, allocator, or acceptance authority.

The PowerShell and Bash surfaces delegate into `ProjectLeaf/`; they do not copy
or fork its implementation.

## Configuration authorities

| Concern | Canonical file |
| --- | --- |
| Design doctrine, continual runtime architecture, and release direction | `LEAFOS-CONTINUAL-BLOOM-PRIMARY-REFERENCE.md` |
| Root layout, supported surfaces, and safe defaults | `leafos.root.json` |
| Permanent README identity asset | `assets/brand/immutable/manifest.json` |
| Runtime roles, models, and personas | `ProjectLeaf/leafos_taskpack/config/runtime.json` |
| Provider routing | `ProjectLeaf/leafos_taskpack/config/providers.conf` |
| Model acquisition profiles | `ProjectLeaf/leaf_model_installer/` |
| Typed tasks, allocation, and acceptance gates | `ccis/contracts/allocation/task-type-registry.json` and `ccis/` |
| Scientific Change Loop coordination | `loop/scientific_change_loop.py` |

When configuration overlaps, the more specific authority wins. The root contract
must remain consistent with the runtime contract but must not duplicate model
catalog details.

## Safety and reuse rules

- Planning and status commands are local by default.
- `apply` is the model download boundary and requires explicit confirmation.
- Guarded task and patch paths require their existing explicit approval flags.
- Generated reports, runs, caches, and temporary files are runtime outputs, not
  reusable source contracts.
- README writes verify the content-addressed identity asset before modifying a
  target, and `--check` previews changes without writing.
- Historical successes, including the Catan one-shot stack, remain evidence only.
  They are not runtime dependencies, templates, or acceptance gates.

## Historical evidence

The successful Catan one-shot stack is retained as proof that LeafOS can drive a
bounded, resumable implementation through planning, execution, verification,
and handoff. It does not define the reusable tool's runtime API or directory
layout. Future reusable-tool work should use the root contract and native
LeafOS validation paths as the authoritative interface.

## Baseline checks

Run the command that matches the active surface:

```powershell
./PowerShell-Version/leaf.ps1 status
./PowerShell-Version/leaf.ps1 doctor
```

```bash
bash Bash-Version/leaf.sh status
bash Bash-Version/leaf.sh doctor
```

Validate that declared contract paths exist, all three version authorities
agree, the version is not older than the normalized 0.2.2 baseline, the README
identity asset still matches its immutable manifest, and the three upcoming
llama.cpp task types remain present in the typed registry:

```powershell
pwsh -NoProfile -File .\Validate-RootContract.ps1
.\program.ps1 status
```

For source-level verification, use the taskpack tests documented in
`ProjectLeaf/leafos_taskpack/README.md`.
