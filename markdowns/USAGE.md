# LeafOS Usage Guide

This guide is for running the current two-surface LeafOS tree from a terminal.
Use the surface that matches your shell:

| Shell | Start directory | Command style |
|---|---|---|
| PowerShell 7+ | `PowerShell-Version/` | `.\leaf.ps1 status` |
| Bash, WSL, macOS, Linux, Git Bash | `Bash-Version/` | `bash leaf.sh status` |

The version folders are friendly entrypoints. They delegate into
`ProjectLeaf/leafos_taskpack`, where the main implementation lives.

## Root command surface

Run the reusable-tool root command when you want one stable command path from
the repository root:

| Goal | PowerShell | Bash |
|---|---|---|
| Check root contract | `.\leafos.ps1 validate-root` | `bash leafos.sh validate-root` |
| Check runtime status | `.\leafos.ps1 status` | `bash leafos.sh status` |
| Check runtime readiness | `.\leafos.ps1 doctor` | `bash leafos.sh doctor` |

All other arguments are delegated unchanged to the existing matching surface.

## README and version program

The adjacent `program` shell provides a small interactive menu when run without
arguments. It discovers the active LeafOS repository root, so it behaves consistently even
when launched through either shell wrapper.

### Interactive menu

Run `.\program.ps1` in PowerShell or `bash program.sh` in Bash. The menu offers:

1. **Update README** — add or refresh the managed local image reference.
2. **Change version** — preview and synchronize the version authorities.
3. **Verify asset and README** — check the permanent asset and selected link.
4. **Preview README update** — report whether a write would change the target.
5. **List README files** — show practical targets while hiding generated trees.
6. **Split Markdown [developer]** — split on long underscore or dash chains.
7. **Exit** — leave without changing anything.

The menu asks before every write. Direct commands are faster for repeat work:

| Goal | PowerShell | Bash |
|---|---|---|
| Open the menu | `.\program.ps1` | `bash program.sh` |
| Verify the permanent image and root README | `.\program.ps1 status` | `bash program.sh status` |
| Verify another README | `.\program.ps1 status docs\README.md` | `bash program.sh status docs/README.md` |
| Preview a README update | `.\program.ps1 readme path\README.md --check` | `bash program.sh readme path/README.md --check` |
| Apply a README update | `.\program.ps1 readme path\README.md --yes` | `bash program.sh readme path/README.md --yes` |
| Preview a version change | `.\program.ps1 version 0.2.3 --check` | `bash program.sh version 0.2.3 --check` |
| Apply a version change | `.\program.ps1 version 0.2.3 --yes` | `bash program.sh version 0.2.3 --yes` |
| Find README targets | `.\program.ps1 list` | `bash program.sh list` |
| Include archived targets | `.\program.ps1 list --all` | `bash program.sh list --all` |

`readme`, `version`, `verify`, and `list` are concise aliases for
`update-readme`, `change-version`, `status`, and `list-readmes`.

### Import and brand a README

Use `--source` when the new README text lives elsewhere. Preview first, then
repeat with `--yes` to apply it:

```powershell
.\program.ps1 readme README.md `
  --source "C:\Users\me\Downloads\new-readme.md" `
  --check

.\program.ps1 readme README.md `
  --source "C:\Users\me\Downloads\new-readme.md" `
  --yes
```

```bash
bash program.sh readme README.md \
  --source "$HOME/Downloads/new-readme.md" \
  --check

bash program.sh readme README.md \
  --source "$HOME/Downloads/new-readme.md" \
  --yes
```

The source may be outside LeafOS, but the target must remain below the LeafOS
root. For a nested README, `program` computes the correct relative asset path.
The managed block is inserted immediately after the title's badge group and is
replaced in place on later runs, so the operation is idempotent.

### Change the LeafOS version

Versions must use numeric semantic form such as `0.2.3`. A version write keeps
these authorities aligned:

- `VERSION` at the LeafOS root;
- `ProjectLeaf/leafos_taskpack/VERSION`;
- the `version` field in `leafos.root.json`;
- snapshot badges and snapshot wording in each selected README.

Use `--readme` more than once to update additional README files:

```powershell
.\program.ps1 version 0.2.3 `
  --readme README.md `
  --readme ProjectLeaf\leafos_taskpack\README.md `
  --check
```

Remove `--check` and add `--yes` only after the preview is correct.

### Permanent asset guarantee

The README image is stored under `assets/brand/immutable/` with a
content-addressed filename. Before any README write, `program` verifies its
SHA-256 digest and byte length against `manifest.json`. It refuses the write if
the file is missing or has changed. To replace the visual deliberately, add a
new content-addressed file and update the manifest; never overwrite the current
file in place.

### Automation and exit behavior

Add `--json` to `status`, `readme`, `version`, or `list` for machine-readable
output. Non-interactive writes require `--yes`; without it, `program` refuses
to guess. Exit status `0` means success, `1` means a write was declined, `2`
means validation or input failed, and `127` means a wrapper could not find
Python 3.

## Quick syntax

After a user-space install, use `leafos` from any directory. From the source
root, substitute `.\leafos.ps1` in PowerShell or `bash leafos.sh` in Bash.
The shortcut layer expands fixed command tokens and forwards all remaining
arguments unchanged.

| Shortcut | Expansion | Behavior |
|---|---|---|
| `leafos` | `home` | Read-only FlowerOS Home |
| `leafos q` | `quick` | Concise plain-text command card; add `--json` for tooling |
| `leafos h` | `home` | Home explicitly |
| `leafos s` | `status` | Fast status |
| `leafos d` | `doctor` | Readiness check |
| `leafos r` | `runtime select` | Active runtime selection |
| `leafos p` | `provider-stack check` | Local provider check |
| `leafos t` | `trace latest` | Latest observable run trace |
| `leafos ref` | `reference` | Primary Markdown and formatless TeX paths |
| `leafos b` | `bloom status` | Verify and show the durable Monday instance |
| `leafos m` | `flower-monitor` | Interactive read-only hardware monitor |
| `leafos c` | `chat` | Interactive local chat |
| `leafos go` | `live` | Guided project onboarding |

Use `leafos help` for the complete command surface. The `q`, `h`, `s`, `d`,
`r`, `p`, `t`, `ref`, and `b` routes are read-only.

## First five minutes

PowerShell:

```powershell
cd C:\path\to\LeafOS\PowerShell-Version
pwsh -File .\install.ps1
..\leafos.ps1 q
..\leafos.ps1 s
..\leafos.ps1 d
..\leafos.ps1 r
.\leaf.ps1 web-state --json
.\leaf.ps1 fullstackbench
```

Bash:

```bash
cd /path/to/LeafOS/Bash-Version
bash install.sh
bash ../leafos.sh q
bash ../leafos.sh s
bash ../leafos.sh d
bash ../leafos.sh r
bash leaf.sh web-state --json
bash leaf.sh fullstackbench
```

Use `status` for a quick online check, `doctor` for dependency/layout checks,
`runtime select` to inspect the active main/scheduler/coder/persona selection,
`web-state --json` when you want machine-readable runtime metadata, and
`fullstackbench` for a raw no-download stack benchmark.

## Daily command map

| Goal | PowerShell | Bash |
|---|---|---|
| Show help | `.\leaf.ps1 help` | `bash leaf.sh help` |
| Check readiness | `.\leaf.ps1 doctor` | `bash leaf.sh doctor` |
| Show runtime choice | `.\leaf.ps1 runtime select` | `bash leaf.sh runtime select` |
| Emit runtime JSON | `.\leaf.ps1 runtime select --json` | `bash leaf.sh runtime select --json` |
| Inspect web/runtime state | `.\leaf.ps1 web-state --json` | `bash leaf.sh web-state --json` |
| Initialize durable Monday | `..\leafos.ps1 bloom init` | `bash ../leafos.sh bloom init` |
| Verify durable Monday | `..\leafos.ps1 b --json` | `bash ../leafos.sh b --json` |
| Run raw full-stack benchmark | `.\leaf.ps1 fullstackbench` | `bash leaf.sh fullstackbench` |
| Run local chat wrapper | `.\leaf.ps1 chat-local` | `bash leaf.sh chat-local` |
| Build handoff bundle | `.\oneshot.ps1 --oneshot .. C:\R\LeafOS-OneShot` | `bash oneshot.sh --oneshot .. ./LeafOS-OneShot` |
| Check model artifacts | `.\leaf.ps1 download doctor` | `bash leaf.sh download doctor` |

The bounded Continual Bloom runtime starts with one persona only:
**Monday — Rescue and Analysis**. Its transcript is hash chained, claims remain
unverified until native evidence supports or refutes them, checkpoints require
new validation, and recovery ignores KV cache. See
`ProjectLeaf/leafos_taskpack/docs/CONTINUAL_BLOOM_RUNTIME.md` for the command
and file contracts.

## Model download safety

LeafOS model acquisition is intentionally plan-first:

```text
catalog/status/doctor = local-only
plan                  = offline JSON plan
resolve               = remote metadata and revision pins only
apply                 = model weight download boundary
```

PowerShell model workflow:

```powershell
.\real-models.ps1                 # status + safe offline plan
.\real-models.ps1 -Resolve        # metadata only
.\real-models.ps1 -Resolve -Apply -Yes
```

Bash model workflow:

```bash
bash real-models.sh
bash real-models.sh --resolve
bash real-models.sh --resolve --apply --yes
```

One-command automation keeps the same boundary:

```powershell
.\install-real.ps1       # preview, no model download
.\install-real.ps1 -Yes  # resolve + download/resume + verify
```

```bash
bash install-real.sh        # preview, no model download
bash install-real.sh --yes  # resolve + download/resume + verify
```

The default runtime profile is `runtime-default`. It prepares:

- `gemma4-coder` at `Q4_K_M` for coding work only.
- `gemma4-opus-assistant` at `Q4_K_M` for main assistant and scheduler duties.

Runtime role rule: Gemma/Fable coder is not allowed to be the main or scheduler
model. Main and scheduler duties use Opus or another model from the main-model
pool.

Model storage is chosen in this order:

1. An explicit command argument.
2. `LEAF_MODEL_DIR`.
3. Existing GGUF cache under `ProjectLeaf/leaf_model_installer/models`.
4. The catalog default, `~/.leaf/models`.

## Monitoring long-running work with `leafos vtop`

LeafOS launches background work such as model downloads and chat servers as
ordinary processes. When you want a live view of what those processes are doing,
use the built-in `leafos vtop` helper as a secondary monitor.

Watch every leaf-related process for 10 seconds:

```powershell
leafos vtop --duration-seconds 10
```

Watch continuously until you press `Ctrl+C`:

```powershell
leafos vtop
```

This command is a thin, cross-platform live process table. It is not part of
the core LeafOS runtime; it is a recommended secondary action when you are
waiting on a model download, a chat server, or a long-running agent task and
want more detail than the log tails provide.

## Agent task pipeline

The 0.2 task pipeline works without a live model when you use the mock route.
Run it from `ProjectLeaf/leafos_taskpack` if you want to work directly with the
source CLI:

```bash
cd ../ProjectLeaf/leafos_taskpack
./bin/leafctl agent-task "create a hello world C project"
./bin/leafctl agent-route tasks/create-a-hello-world-c-project.md --mock
./bin/leafctl agent-dry-run tasks/create-a-hello-world-c-project.generated.plan.sh
./bin/leafctl agent-run tasks/create-a-hello-world-c-project.generated.plan.sh --yes
./bin/leafctl agent-report spine-check
```

The safety pattern is always the same:

1. Create or load a task file.
2. Route it into a plan.
3. Dry-run the plan.
4. Validate the plan.
5. Execute only with explicit consent.
6. Write a report.

Run the spine test when you want to prove that full loop:

```bash
cd ProjectLeaf/leafos_taskpack
bash tests/spine.sh
```

## Portable handoff bundle

Use `oneshot` when you want a small starter package for another machine or a
clean handoff folder.

PowerShell:

```powershell
cd C:\path\to\LeafOS\PowerShell-Version
.\oneshot.ps1 --oneshot .. C:\R\LeafOS-OneShot
```

Bash:

```bash
cd /path/to/LeafOS/Bash-Version
bash oneshot.sh --oneshot .. ./LeafOS-OneShot
```

The bundle includes README files, instructions, small sample data, and a zip.
It is separate from full model downloads.

## Useful source-tree commands

The main taskpack CLI has more commands than the friendly surfaces expose in
their short READMEs. From `ProjectLeaf/leafos_taskpack`:

```bash
./bin/leafctl help
./bin/leafctl platform
./bin/leafctl versions
./bin/leafctl loaders
./bin/leafctl runtime models --json
./bin/leafctl provider-status
./bin/leafctl dashboard --json
./bin/leafctl fullstackbench
```

Python helper layer:

```bash
python3 bin/leafpy doctor
python3 bin/leafpy status
python3 bin/leafpy platform
python3 bin/leafpy versions
```

Build C loader samples:

```bash
cd ProjectLeaf/leafos_taskpack
make
./build/leaf_loader_demo_v2 --no-ansi
```

## Troubleshooting

### Windows PowerShell reports a parser error in `leafctl.ps1`

LeafOS uses PowerShell 7 syntax in its delegated command surface. Use an
installed `pwsh` executable, or run the friendly launcher directly from
Windows PowerShell 5.1:

```powershell
.\leaf.ps1 status
```

The launcher automatically hands the command to PowerShell 7. If `pwsh` is not
installed, install PowerShell 7 and retry. Bash and WSL users should use the
Bash surface instead.

### Bash scripts report `$'\r': command not found`

This indicates CRLF line endings were passed to Bash. Convert the affected
script to LF line endings, then retry through the isolated Bash surface:

```bash
bash --noprofile --norc leafos.sh validate-root
```

Do not use an interactive shell for diagnostics when shell profile scripts add
unrelated startup behavior.

### `leaf.ps1` or `leaf.sh` cannot find the source command

Make sure the root still contains `ProjectLeaf/leafos_taskpack/bin/leafctl`.
The top-level version folders are wrappers; they do not duplicate the full
source tree.

### `doctor` says `jq` is missing

Runtime, graph, and structured JSON commands require `jq` on the Bash side.
Install `jq`, then rerun:

```bash
bash leaf.sh doctor
```

### A model command looks like it might download

Only the `apply` phase downloads weights. In the friendly scripts, that means:

- PowerShell: `-Apply -Yes`
- Bash: `--apply --yes`

Everything before that is local planning or metadata inspection.

### Existing model files are not being found

Set `LEAF_MODEL_DIR` to the folder that contains your model directories, or put
GGUF files under `ProjectLeaf/leaf_model_installer/models` so LeafOS can prefer
that local cache.

PowerShell:

```powershell
$env:LEAF_MODEL_DIR = 'D:\LeafModels'
.\leaf.ps1 download doctor
```

Bash:

```bash
export LEAF_MODEL_DIR=/mnt/d/LeafModels
bash leaf.sh download doctor
```

## Where to read next

- `README.md`: root project map and safest starting commands.
- `INSTALLATION.md`: install commands for each terminal surface.
- `ProjectLeaf/leafos_taskpack/docs/USER_GUIDE.md`: deeper taskpack features.
- `ProjectLeaf/leafos_taskpack/docs/MODEL_INSTALLATION.md`: model installer contract.
- `ProjectLeaf/leaf_model_installer/README.md`: canonical model acquisition package.

## Developers only

### Split Markdown at long divider chains

`program split-markdown` treats a standalone chain of 12 or more matching
underscores or hyphens as a section boundary. Spaces between marks are allowed,
so both forms below are boundaries:

```text
____________
- - - - - - - - - - - -
```

Preview a split without creating files:

```powershell
.\program.ps1 split-markdown docs\large-reference.md --check
```

```bash
bash program.sh split-markdown docs/large-reference.md --check
```

Apply it after inspecting the reported part names:

```powershell
.\program.ps1 split docs\large-reference.md --yes
```

```bash
bash program.sh split docs/large-reference.md --yes
```

By default, `large-reference.md` produces a managed sibling directory named
`large-reference.parts/`. Each part receives a numbered filename derived from
its first heading. Use `--output path/to/directory` to select another directory
under the LeafOS root, and add `--json` for machine-readable output.

The original Markdown file is never changed. Divider-looking lines inside
fenced code blocks are preserved rather than treated as boundaries. Empty
sections are omitted. The output directory contains
`.leafos-program-split.json`, which lets later runs update only files created by
this feature and refuse unrelated directories.
