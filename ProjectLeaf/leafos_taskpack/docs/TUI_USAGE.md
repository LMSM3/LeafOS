# FlowerOS Terminal Interface

The TUI is the FlowerOS observation and control surface for an active run. LeafOS remains the authoritative engine; the interface reads structured run artifacts and sends supported actions through `leaf_loop_inlet.py`.

## Start

```powershell
.\bin\flower.ps1 live
.\bin\flower.ps1 live C:\R\MyProject
.\bin\flower.ps1 tui
.\bin\flower.ps1 tui --run active
.\bin\flower.ps1 tui --run RUN_ID
```

Build the native renderer:

```bash
bash ./bin/build_tui.sh
make tui
```

Require native mode explicitly:

```powershell
.\bin\leaf-tui.ps1 --run active
.\bin\leafctl.ps1 tui --native --run active
```

An interactive `leafctl tui` automatically prefers `build/leaf-tui` when it exists. Use `--python-renderer` to force the ANSI Python fallback.

When input or output is not an interactive terminal, `leafctl tui` renders one plain frame and exits. This makes the same route useful in logs and smoke tests.

## Pages

1. Overview: active work, blocker, condensed hardware, latest validation, and next action.
2. Tasks: dependency lineage, role, worker, model, attempts, and correction depth.
3. Hardware: provider, stack, GPU, VRAM, token rates, gross local-token cloud equivalent, latest benchmark, CPU, RAM, resident targets, headroom, and scheduling reason.
4. Queue: dependency-ordered work, generated/repair classes, budgets, and selected-task details.
5. Brain: structured provider progress, proposals, actions, and results.
6. Ledger: durable append-only run events and evidence references.
7. Results: validation evidence, changed-file hashes, artifacts, failures, and gate state.

The header, page tabs, and fact-based milestone rail remain visible on every standard-size page. Terminals below 80 columns or 24 rows use a compact view.

## Keys

```text
n                 guided new/existing project onboarding
Tab / Shift+Tab   next or previous page
1-7               open a page directly
j / k             move the current view selection
Space             freeze or resume visual refresh only
l                 return to live refresh
?                 toggle key help
p                 pause or resume dispatch through the inlet
a                 approve a pending work-order gate
r                 retry the selected failed task within its attempt budget
x                 begin confirmed cancellation of the selected task
[ / ]             raise or lower selected-task priority
A                 approve the selected typed task
:stop             begin confirmed stop flow
q                 close the TUI without stopping LeafOS
```

The `n` route is shared by both renderers. It closes the renderer cleanly, runs a six-step terminal form, and reopens the window on the resulting run. New-project location is entered as a top-level directory plus folder name. README and skeleton input is multiline and paste-friendly; `.done`, `.back`, and `.cancel` are local wizard controls. The form also records the project-only sandbox and can queue KV-cache optimization work. The active command window accepts `:improve`, `:again`, `:project PATH`, `:new PATH generic`, `:mode auto|quiet|full`, `:targets cpu 80 gpu 90`, `:budget 64m`, `:pause`, `:resume`, `:drain`, and `:<plain objective>`.

Task controls emit authenticated typed requests containing the selected task ID. Cancellation requires typing `CANCEL`. The TUI does not edit queue files or terminate processes directly.

## Noninteractive And Integration Modes

```powershell
.\bin\leafctl.ps1 tui --run active --once --page results
.\bin\leafctl.ps1 tui --run active --json
python core\ui\tui\inlet_pipe.py --run active --after 120 --json
```

The snapshot follows `schemas/leafos.tui-snapshot.v1.schema.json` and contains a reconnectable event cursor, bounded event delta, normalized tasks, milestones, resident state, resource targets, budgets, hardware, Brain records, ledger records, and results. Provider reasoning progress may be shown as counts. Private chain-of-thought is not persisted or presented as durable evidence.

## Renderer Boundary

The native implementation is split across `core/tui/leaf_tui.c`, `leaf_tui_state.c`, `leaf_tui_pages.c`, `leaf_tui_input.c`, and `leaf_tui_json.c`. It uses `ncursesw`, fixed-size state buffers, and the normalized snapshot contract. Malformed or oversized snapshots fail closed.

Python refreshes the snapshot through atomic replacement. Native control requests use an ephemeral TCP listener bound only to `127.0.0.1` and a 256-bit per-session token. Messages are bounded to 2 KiB. The bridge accepts named run controls plus typed retry, cancel, approval, and priority requests containing validated task IDs; invalid tokens, fields, oversized messages, malformed JSON, and arbitrary commands are discarded.

The Overview page shows the tracked child PID and task ID while a command is active. Control requests are recorded in the append-only event stream and hash-chained native `control.lmem` journal before queue mutation.

The Hardware page uses an independent low-latency sampler. It updates CPU, RAM, GPU, VRAM, temperature, and power without waiting for a durable run event or invoking the slower disk probe. The page labels the data `live`, shows sample age, and retains recorded provider throughput because sampling is observational and does not alter the run ledger.

The Python renderer remains the plain-output and dependency fallback. Neither renderer schedules tasks or edits queue files directly. The onboarding form submits `schemas/leafos.project-onboarding.v1.schema.json` to `leaf_live_project.py`; only that backend creates seed files, starts a run, writes `stack-preferences.json`, or admits the typed optimization task.
