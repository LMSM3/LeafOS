# LeafOS Live Project Window

The live project window is the shortest route from a directory to the active LeafOS agentic stack. The stack means all downloaded and locally available models in this LeafOS instance.

All instructions, whether detailed or minimal, converge on the same typed
work-order lifecycle. The active window is not a shell prompt and does not
become a second executor.

## Open A Project

```powershell
.\bin\leafctl.ps1 live
```

With no directory, LeafOS opens a six-step project inlet:

1. Choose a new or existing project.
2. For a new project, select its top-level directory and folder name. For an existing project, enter a path or select a recent run.
3. For a new project, choose a template and paste README content through a `.done` line.
4. Paste a file tree, pseudocode, interface, or constraint skeleton through a second `.done` line.
5. Optionally set the first objective, select the current `project-only` sandbox, choose KV-cache work, and decide whether to wait at the mutation gate.
6. Review the normalized request and type `CREATE` or `OPEN`.

Use `.back` to restart the form and `.cancel` to leave without writing. The preview is read-only. A new-project commit creates only `README.md`, `skeleton.md`, and `leafos.project.json`, refuses all conflicts, and preserves pasted line content. An existing-project commit does not add control files to the target.

The optimization selector is intentionally ahead of the provider implementation. `inherit` makes no optimization task. `investigate`, `enable`, or `disable` writes `stack-preferences.json` in the run and queues a priority-1 task behind the initial report. The request remains `applied: false` until the task detects a real project-owned llama.cpp launch surface, implements a reversible setting, validates it, and records throughput and VRAM evidence. A shared provider is never restarted merely because onboarding requested a toggle.

Open a known project directly:

```powershell
.\bin\leafctl.ps1 live C:\R\MyProject
```

The command inspects the directory, reattaches its newest version-2 run when one exists, or creates a bounded work-order run, starts the resident supervisor, and opens the TUI. An objective is optional. Discovery derives the initial objective from root project JSON, README content, source layout, tests, and known project surfaces.

Force a new run or provide a specific first objective:

```powershell
.\bin\leafctl.ps1 live C:\R\MyProject --fresh-run
.\bin\leafctl.ps1 live C:\R\MyProject --objective "Add deterministic replay"
```

The initial mutation gate remains operator-controlled unless `--yes` is supplied. The provider proposes a plan; the CPU allowlist executes and validates it.

## Active Window Syntax

Press `n` outside command mode to run guided onboarding from either the native or Python renderer. When onboarding succeeds, the interface reopens on the selected run; cancelling returns to the previous one.

Press `:` in the TUI and enter one of these lines:

```text
:improve
:improve add resource trading between bots
:again
:make the board easier to inspect during play
:project "C:\R\Another Project"
:new "C:\Games\catan2" catan2
:mode quiet
:targets cpu 80 gpu 90
:budget 64m
:pause
:resume
:drain
:status
:help
```

- `:improve` needs no objective. LeafOS derives one bounded increment from current facts.
- `:again` queues the next iteration after the latest live task.
- Any unrecognized line is treated as a plain-language improvement objective, so command vocabulary is optional.
- `:project` opens or starts any existing directory.
- `:new` creates a project from exactly three seed inputs: `README.md`, `skeleton.md`, and `leafos.project.json`. The template is inferred from a `catan2` directory name or can be stated explicitly.
- Paths containing spaces must be quoted.
- `:mode`, `:targets`, and `:budget` control adaptive resident scheduling without changing project authority.
- `:pause`, `:resume`, and `:drain` route to the existing safe-boundary lifecycle controls.
- `:stop` retains its confirmed `STOP` flow. Task cancellation retains its confirmed `CANCEL` flow.

The Python and native C renderers send the same bounded `live_command` request through the authenticated loopback bridge. The renderer never edits the project, queue, or run files directly.

An accepted objective is acknowledged with a durable task ID. Operator tasks
may be submitted while another task is running and receive priority at the next
safe claim boundary; the active command is not interrupted mid-step.

## Catan2 Benchmark Project

The current LeafOS repository is itself a medium-sized Catan2 demonstration target:

```powershell
.\bin\leafctl.ps1 live C:\R\LeafOS0.2.1\ProjectLeaf\leafos_taskpack --fresh-run
```

Discovery recognizes `core/bench/catan2bench.py` and constrains work to:

- `core/bench`
- `tests/catan2bench.sh`
- `tests/test_board_spatial.py`
- `docs/CATAN2_BENCHMARK.md`

It also declares the spatial unit tests and Catan2 benchmark as CPU validation gates. Repeated `:improve` or `:again` requests ask the stack to choose one coherent increase in RTS complexity from rules, continual production, construction, trading, progression, bot policy, balance, match completion, observability, or interface quality.

The loop is intentionally iterative. Each task records an iteration number, uses the prior live task as its dependency when appropriate, validates the resulting game, and leaves a recommendation for the next increment.

## Blank Catan2 Seed

```powershell
.\bin\leafctl.ps1 live C:\Games\catan2 --new
```

No source layout is required. The three seed files describe intent, suggested boundaries, long-term goals, safety constraints, and a validation command. The normal inspection and plan-v2 path decides what source and tests are needed. There is no separate blank-project engine or Catan-only executor.

## Intake Procedure

1. Walk the project with a 4,000-file bound while ignoring generated, dependency, VCS, environment, and run directories.
2. Classify the state as empty, seed, documents, or codebase.
3. Read only root project intent or a small seed's JSON; nested repository JSON is not mistaken for authority.
4. Infer language, source, tests, allowed paths, validation commands, and optional Catan2 identity.
5. Write the generated intake work order under `runs/agent-loop/live-intake`, not inside the target.
6. Start or reattach the persistent version-2 loop and open the TUI.
7. Normalize every improvement into the existing typed task request, native LMEM control journal, provider proposal, CPU executor, validator, checkpoint, and report path.

Existing projects receive no LeafOS control files during intake. A seed is modified only by the explicit `--new` or `:new` action, and existing seed files are never overwritten.

## Noninteractive Operations

```powershell
.\bin\leafctl.ps1 live C:\R\MyProject --inspect --json
.\bin\leafctl.ps1 live --command ":improve add deterministic replay" --json
.\bin\leafctl.ps1 live --command ":again" --json
.\bin\leafctl.ps1 live --onboard-json .\config\project-onboarding.sample.json --no-tui --json
```

These routes use the same parser and inlet authority as the active window. They are useful for scripts and parser diagnostics, not an alternate execution path.

See `docs/RESIDENT_STACK_USAGE.md` for resource profiles, budgets, provider recovery, resident lifecycle commands, and Catan2 soak profiles.
