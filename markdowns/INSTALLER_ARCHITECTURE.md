# LeafOS installer architecture

## Executive summary

The existing installation engine was **not replaced**. `ProjectLeaf/leaf_model_installer/leaf_models/install_cli.py` and `orchestrator.py` remain the canonical plan / resolve / apply / verify implementation. The PowerShell front end was refactored so that profiles and packs share one guided public surface without duplicating installer logic.

## Public surfaces

| Surface | Path | Purpose |
|--------|------|---------|
| Primary guided installer | `PowerShell-Version/real-models.ps1` | Guided menu when run without arguments; scripted mode when passed `-Profile`, `-Pack`, `-ResumePlan`, `-Readiness`, etc. |
| Forwarding entry point | `PowerShell-Version/install.ps1` | Cosmetic convenience only. Forwards all arguments to `real-models.ps1`. No installation logic lives here. |
| Legacy catalog | `ProjectLeaf/leaf_model_installer/leaf_models/model_catalog.json` | Slots, repo IDs, quants, patterns, profiles |
| Installer CLI | `ProjectLeaf/leaf_model_installer/leaf_models/install_cli.py` | `plan`, `resolve`, `apply`, `verify`, `status`, `plan-pack`, plus `inspect-resume` and `verify-store` |
| Orchestrator backend | `ProjectLeaf/leaf_model_installer/leaf_models/orchestrator.py` | `create_plan`, `create_pack_plan`, `resolve_plan`, `apply_plan` |
| Read-only resume/store inspection | `ProjectLeaf/leaf_model_installer/leaf_models/state.py` | Discovers resumable transfers and store state without mutating active downloads |
| Pack manifests | `ProjectLeaf/leafos_taskpack/config/packs/*.json` | Pack identity + `install.items` |
| Guarded fallback downloader | `_download_direct_from_resolved.py` | Per-file resumable downloader that consumes a resolved plan (used while live transfers are active) |

## Design rules

1. **Do not replace the existing installation engine.** The backend CLI is authoritative.
2. **No compatibility shim contains installation logic.** `install.ps1` only translates arguments and forwards execution.
3. **Packs and legacy profiles share the same schema.** A pack is an alternative plan source that produces the same plan/resolution/application/verification sequence.
4. **Running without installation arguments opens a guided experience.** A menu lets users choose profile install, pack install, resume, verify, or readiness.
5. **Active downloads stay protected.** Read-only inspection commands will detect a running transfer and skip mutating operations.

## Flow: legacy profile

```text
PowerShell-Version\real-models.ps1 -Profile runtime-default
    -> install_cli.py plan --profile runtime-default
       -> offline plan JSON
    -> install_cli.py resolve <plan>
       -> exact repo revision + expected files
    -> install_cli.py apply <resolved> --yes
       -> downloads / resumes
    -> install_cli.py verify <resolved>
       -> GGUF magic + optional hash check
```

## Flow: pack

```text
PowerShell-Version\real-models.ps1 -Pack ProjectLeaf\leafos_taskpack\config\packs\viola-nocturne.json
    -> install_cli.py plan-pack <pack.json>
       -> offline plan JSON (same schema as legacy plan)
    -> install_cli.py resolve <plan>
       -> same resolved plan JSON
    -> install_cli.py apply <resolved> --yes
       -> same downloader
    -> install_cli.py verify <resolved>
       -> same verifier
```

## Resume / store inspection

```text
PowerShell-Version\real-models.ps1 -ResumePlan ProjectLeaf\leaf_model_installer\viola-resolved.json
    -> state.py inspect-resume
       -> reports running/resumable transfers and active PIDs
       -> offers safe actions (monitor, tail log, resume, verify)
```

## Recommended commands

Guided menu:

```powershell
.\PowerShell-Version\real-models.ps1
```

Legacy profile, plan only:

```powershell
.\PowerShell-Version\real-models.ps1 -Profile runtime-default
```

Legacy profile, download:

```powershell
.\PowerShell-Version\real-models.ps1 -Profile runtime-default -Resolve -Apply -Yes
```

Pack, download:

```powershell
.\PowerShell-Version\real-models.ps1 `
  -Pack ProjectLeaf\leafos_taskpack\config\packs\viola-nocturne.json `
  -Resolve -Apply -Yes
```

Readiness check:

```powershell
.\PowerShell-Version\real-models.ps1 -Readiness
```

Resume a previously resolved plan:

```powershell
.\PowerShell-Version\real-models.ps1 `
  -ResumePlan ProjectLeaf\leaf_model_installer\viola-resolved.json
```

Monitor a running download:

```powershell
Get-Content viola-download.log -Tail 20 -Wait
```


## Design decisions

### Preserve the Python backend as the single source of truth

`install_cli.py` + `orchestrator.py` already implemented the canonical plan / resolve / apply / verify sequence. Rather than duplicate that logic in PowerShell, we kept the backend unchanged and treated the PowerShell scripts as a presentation and argument-translation layer.

That choice gives us:

- One place for installation semantics (Python).
- One place for Windows-friendly guided UX (PowerShell).
- The ability to swap front ends later without rewriting the engine.

### One public PowerShell surface

`real-models.ps1` is the only public installer surface. `install.ps1` exists only as a short alias. This avoids the user-visible confusion of having multiple installers with overlapping responsibilities and prevents accidental drift between entry points.

### PowerShell 5.1 as the compatibility baseline

All PowerShell code is written for Windows PowerShell 5.1 and avoids constructs that only exist in PowerShell 7. Consequences:

- `Join-Path` accepts only two positional arguments; multi-segment paths use `[IO.Path]::Combine`.
- `ConvertFrom-Json -Depth` does not exist; we rely on default depth.
- `[CmdletBinding()]` on nested helper functions triggered obscure positional-parameter binding errors in this file, so helpers use plain `param()` blocks while the public top-level script still validates its parameters.
- Named parameters on internal helper calls remained unreliable in this file context, so internal calls use positional argument lists.

### Positional helper calls as a pragmatic fallback

PowerShell 5.1 refused to bind named parameters like `-Root` on functions inside the large `real-models.ps1`, even though identical small scripts worked fine. After multiple attempts, we switched internal helper invocations to positional form. This is a presentation-layer workaround; it does not affect the user-facing parameter names, which remain named (`-Profile`, `-Pack`, etc.).

### Single-file front end

We initially split helpers into `PowerShell-Version\installer\*.psm1` modules. PowerShell 5.1 module imports produced a `positional parameter cannot be found` error that we could not diagnose cleanly, so we inlined the helpers into `real-models.ps1`. The result is one file to maintain and one file for users to run.

### Graceful menu errors

Backend commands that fail no longer throw unhandled exceptions and terminate the script. They write a warning and return to the menu. This keeps the interactive experience usable even when a pack plan cannot be generated or a store inspection returns an error.

## Reflections: improving the back end while preserving it

The current backend is intentionally simple: it speaks JSON files and CLI verbs. That simplicity is a strength, but a production front end could ask it for richer, more structured data:

1. **Structured plan metadata**
   - Today the plan JSON already contains `items`, `estimated_bytes`, `destination_root`, and `profile`. We could add `display_name`, `description`, `tags`, and `source` (legacy catalog vs pack) so the front end can render richer summaries without guessing.

2. ** item-level detail endpoint**
   - `show <plan>` returns mostly flat text. A `show --json` variant that emits one record per planned item (slot, quant, repo, target path, size) would let the front end build a scrolling checklist with progress bars.

3. **Progress events during apply**
   - `apply` is currently silent or single-message. Streaming JSONL lines or a named-pipe / file tail of `{ "path": "...", "bytes": N, "total": M }` events would let the PowerShell front end animate a real progress bar instead of just printing `[◔] Apply ...`.

4. **Resume interrogation**
   - `inspect-resume` returns state; it could also return a suggested `--start-at` item or estimated time remaining, so a menu can say *"Resume from item 3/10 (about 4 GiB remaining)"* rather than just listing totals.

5. **Dry-run and conflict checks**
   - A `--dry-run` flag on apply/resolve would let the menu show the user exactly what will be downloaded, overwritten, or skipped before asking for confirmation.

6. **Provider credentials**
   - The front end currently does not surface Hugging Face token prompts. A backend command that checks token/rate-limit status (`doctor` partially does this) would let the guided flow warn early instead of failing mid-download.

Unit of preservation principle: every improvement suggested above can be added as a new CLI verb, a new flag, or a new field in existing JSON payloads. The Python engine remains the authority; the PowerShell layer only translates its answers into menus, summaries, and prompts.
