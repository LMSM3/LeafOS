# LeafOS Model Installer

Version 0.4.0 is the canonical model-acquisition layer for LeafOS.

The architecture is deliberately split into four explicit phases:

```text
catalog -> offline plan -> metadata resolve/pin -> explicit apply -> verify
```

Only `apply` downloads model files. `catalog`, `plan`, `show`, `status`, and
`doctor` are local-only. `resolve` reads repository metadata and pins commit
revisions, but does not transfer model weights.

## Canonical slots

| Slot | Key | Role | Default quant | Default install |
|---:|---|---|---|---|
| 1 | `gemma4-coder` | Primary local coder | `Q4_K_M` | yes |
| 2 | `qwopus35-coder-mtp` | Legacy secondary coder / fast helper | `Q4_K_M` | legacy only |
| 3 | `gemma4-opus-assistant` | General reasoning / assistant / scheduler | `Q4_K_M` | yes |
| 4 | `qwen35-opus-reasoning` | Deeper reasoning / planning | prefers `Q4_K_M`, then `Q5_K_M`; explicit `MXFP4_MOE` fallback | optional heavy |
| 5 | `gpt-oss-120b` | Experimental heavyweight | `MXFP4_NATIVE` | never |

Profiles:

- `default`: slots 1 and 3, Fable coder plus Opus main/scheduler.
- `runtime-default`: slots 1 and 3, the empty-input LeafOS runtime set.
- `extended`: slots 1, 3, and 4, adding deeper non-coder reasoning/planning.
- `legacy-coder-pair`: slots 1 and 2, historical download profile only.
- `experimental`: runtime slots plus optional reasoning, legacy secondary coder, and guarded slot 5.

Slot 4 does not use `*.gguf`. At catalog verification time its repository did
not contain Q4_K_M or Q5_K_M artifacts, so `MXFP4_MOE` is available only when a
plan is created with `--allow-fallback`.

Slot 5 is guarded twice during apply:

```text
--include-experimental --confirm-heavy gpt-oss-120b
```

## Bootstrap tooling

Windows:

```powershell
.\install.ps1
```

Linux, macOS, or WSL:

```bash
./install.sh
```

Bootstrap creates a fresh virtual environment, validates it, and atomically
replaces the previous environment. It does not download a model.

## Safe workflow

```bash
# 1. Inspect the registry.
leaf-models catalog

# 2. Create an offline default plan for Fable coding plus Opus main/scheduler.
leaf-models plan --profile default --out leaf-model-plan.json

# Or create the empty-input runtime plan explicitly.
leaf-models plan --profile runtime-default --out leaf-runtime-plan.json

# 3. Resolve exact remote files and pin repository revisions.
leaf-models resolve leaf-model-plan.json

# 4. Review the resolved plan.
leaf-models show leaf-model-plan.resolved.json

# 5. Start or resume downloads only after review.
leaf-models apply leaf-model-plan.resolved.json --yes

# 6. Verify later without downloading.
leaf-models verify leaf-model-plan.resolved.json
```

The default storage root is `~/.leaf/models`. Set `LEAF_MODEL_DIR` to override
it. Run state and manifests live under
`<model-root>/.leafos-installer/runs/<plan-id>/`.

See [INSTALLATION_ARCHITECTURE.md](INSTALLATION_ARCHITECTURE.md) for contracts,
state transitions, failure behavior, and recovery rules.

<!-- Legacy v0.3 reference follows for migration history only.

It wraps these repositories:

- `tvall43/Qwen3.5-14B-A3B-Claude-4.6-Opus-Reasoning-Distilled-reap-gguf`
- `yuxinlu1/gemma-4-12B-coder-fable5-composer2.5-v1-GGUF`

Important: the Qwen repository name references Claude/Opus as a third-party distillation label. This is not an official Anthropic Claude model. The CLI treats it as an ordinary third-party GGUF repo, because marketing language is not a checksum.

## What changed in 0.3.0

- Added a `preflight` command for system scan, GPU/RAM detection, and target-location reporting.
- Added a 12-second loading animation using the requested frame set: `𒅒 𒈔 𒅒 𒇫 𒄆`.
- Added conservative quant recommendation based on detected RAM and NVIDIA VRAM.
- Added `leaf_preflight_report.json` written inside the exact model target directory.
- Added optional explicit DNS cache flush via `--flush-dns`. No hidden `PowerShell.Exiting` event, because invisible side effects are amateur villainy.
- Added shell fallback preflight helpers:
  - `shell_helpers/system-preflight.ps1`
  - `shell_helpers/system-preflight.sh`
- Kept Version 2 behavior: no fake success after download loops, failed scripts exit nonzero, verified files are listed by exact path.

## Install on Windows PowerShell

```powershell
Set-ExecutionPolicy -Scope Process Bypass -Force
.\install.ps1
```

Then run:

```powershell
.\leaf-models.cmd
```

## Install on Linux/macOS/WSL

```bash
chmod +x install.sh
./install.sh
./leaf-models
```

## First command: preflight

Run this before downloading. It resolves the target folder, checks NVIDIA/RAM, recommends a quant, and writes a report.

Windows:

```powershell
.\leaf-models.cmd preflight --model gemma4-coder --dest .\models
```

Linux/macOS/WSL:

```bash
./leaf-models preflight --model gemma4-coder --dest ./models
```

With explicit DNS cache flush:

```powershell
.\leaf-models.cmd preflight --model gemma4-coder --dest .\models --flush-dns
```

The preflight report is written here:

```text
<dest>/<model-local-dir>/leaf_preflight_report.json
```

Example for Gemma:

```text
./models/Gemma4-Coder/leaf_preflight_report.json
```

This file does **not** mean the model downloaded. It means the machine scan completed and the target directory is known. Apparently we must now label reality in layers.

## Common commands

List the catalog:

```bash
leaf-models list
```

Inspect matching remote files before downloading:

```bash
leaf-models inspect --model gemma4-coder --quant Q4_K_M
```

Download the Gemma coder 4-bit baseline, then verify its local location:

```bash
leaf-models download --model gemma4-coder --quant Q4_K_M --dest ./models
```

Download and compute SHA256 values after verification:

```bash
leaf-models download --model gemma4-coder --quant Q4_K_M --dest ./models --hash
```

Verify an existing local download later:

```bash
leaf-models verify --model gemma4-coder --quant Q4_K_M --dest ./models
```

Download the Qwen reasoning-distill GGUF files:

```bash
leaf-models download --model qwen-opus-reasoning --dest ./models
```

Print resolved Hugging Face file URLs for PowerShell `Invoke-WebRequest` usage:

```bash
leaf-models urls --model gemma4-coder --quant Q4_K_M
```

## Download-location verification

After a download, the CLI checks:

1. The selected pattern matches at least one remote file.
2. Each expected remote file exists under the exact local target directory.
3. Each file is at least `--min-bytes`, default `1048576` bytes, so an HTML error page cannot quietly cosplay as a GGUF.
4. A manifest exists at:

```text
<dest>/<model-local-dir>/leaf_download_manifest.json
```

For the default Gemma 4-bit path, that means:

```text
./models/Gemma4-Coder/leaf_download_manifest.json
```

A successful download ends with `Status: VERIFIED`. Anything else returns a nonzero exit code. No fake little victory parade at the end of a failure loop.

## Shell fallback helpers

When the Python CLI is unavailable but `huggingface-cli` works, use the shell helpers.

Windows PowerShell preflight:

```powershell
.\shell_helpers\system-preflight.ps1 -Model gemma4-coder -Quant Q4_K_M -Dest .\models
.\shell_helpers\system-preflight.ps1 -Model gemma4-coder -Quant Q4_K_M -Dest .\models -FlushDns
```

Windows PowerShell download / verify:

```powershell
.\shell_helpers\download-model.ps1 -Model gemma4-coder -Quant Q4_K_M -Dest .\models
.\shell_helpers\download-model.ps1 -Model gemma4-coder -Quant Q4_K_M -Dest .\models -VerifyOnly
```

Linux/macOS/WSL preflight:

```bash
./shell_helpers/system-preflight.sh --model gemma4-coder --quant Q4_K_M --dest ./models
./shell_helpers/system-preflight.sh --model gemma4-coder --quant Q4_K_M --dest ./models --flush-dns
```

Linux/macOS/WSL download / verify:

```bash
./shell_helpers/download-model.sh --model gemma4-coder --quant Q4_K_M --dest ./models
./shell_helpers/download-model.sh --model gemma4-coder --quant Q4_K_M --dest ./models --verify-only
```

These helpers are intentionally less fancy than the Python CLI. They exist as boring rescue ropes, not as a second cathedral of scripting mistakes.

## Why not hard-code a direct URL?

This broken pattern does **not** download a GGUF file:

```powershell
Invoke-WebRequest -Uri "https://huggingface.co" -OutFile ".\model.gguf"
```

That saves the Hugging Face homepage as a fake model file. A majestic little brick.

Use the CLI instead:

```powershell
.\leaf-models.cmd urls --model gemma4-coder --quant Q4_K_M
```

Then use one of the resolved `/resolve/main/...gguf` URLs it prints.

## Safety choices

- Only allowlisted repositories are available.
- No arbitrary shell commands are generated or executed.
- Downloads are confirmed before execution unless `--yes` is used.
- Disk space is checked before download for known quant sizes.
- The program downloads model files only. It does not run them.
- Success is only printed after local verification passes.
- DNS flushing is explicit. No hidden exit hooks. Civilization gets one tiny mercy.

## Quantization menu

| Quant | Approx size | Notes |
|---|---:|---|
| Q2_K | 4.83 GB | Smallest, weakest quality. |
| Q3_K_M | 6.09 GB | Compact compromise. |
| Q4_K_M | 7.38 GB | Recommended baseline. |
| Q6_K | 9.79 GB | Better quality, larger. |
| Q8_0 | 12.70 GB | Largest listed option. |

## Gated/private repos

If Hugging Face asks for auth:

```bash
huggingface-cli login
```

Then rerun the download command.
-->
