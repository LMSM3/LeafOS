# LeafOS Agentic CLI

The current agentic CLI is project-first and resident by default. The shortest interactive instruction is no argument at all:

```powershell
.\bin\leafctl.ps1 live
```

This opens reviewed new/existing project onboarding. A known directory can bypass the form:

```powershell
.\bin\leafctl.ps1 live C:\R\MyProject
```

An objective, command vocabulary, and existing source tree are all optional. LeafOS can begin from an established repository, documentation-only project, empty directory, or an explicit README/skeleton/JSON seed.

## How Instructions Enter

| Input | Example | Normalized result |
|---|---|---|
| Guided new project | `leafctl live`, then choose location and paste README/skeleton | Typed onboarding request, project-only sandbox, three-file seed, and optional optimization task. |
| Guided existing project | `leafctl live`, then select a recent project or path | Read-only intake of the selected directory. |
| Directory only | `leafctl live C:\R\MyProject` | Intake-derived bounded objective. |
| Directory and objective | `leafctl live C:\R\MyProject --objective "Add replay"` | Initial live-project work order. |
| Plain TUI text | `:make failures easier to inspect` | Typed operator task. |
| Minimal TUI command | `:improve` or `:again` | Evidence-derived next iteration. |
| JSON task | `loop task submit active request.json` | Schema-validated typed task. |
| Work order | `agent-loop-start --target ... --work-order ...` | Six-stage dependency lifecycle. |

Every route converges on the same queue, provider contract, executor, validation gate, journal, checkpoint, and report.

For automation, `leafctl live --onboard-json config/project-onboarding.sample.json --no-tui` validates and applies the same request. The published shape is `schemas/leafos.project-onboarding.v1.schema.json`.

## Execution Contract

```text
INTAKE -> PLAN -> APPROVE -> EXECUTE -> VALIDATE -> CHECKPOINT/REPORT
```

1. Intake reads bounded project facts and never mutates an existing project.
2. Planning sends bounded context to the selected stack entry and requires schema-valid output.
3. Approval checks work-order and task mutation policy.
4. Execution allows only declared operations inside declared paths.
5. Validation runs every acceptance command.
6. Checkpoint and report persist evidence before more resident work is derived.

Provider output is proposal-only. A malformed, empty, truncated, or policy-expanding proposal fails closed. Fixture providers are test dependencies only and are never a production fallback.

## Live Commands

```text
:improve [objective]
:again
:<plain objective>
:project PATH
:new PATH generic
:mode auto|quiet|full
:targets cpu N gpu N
:budget Nm
:pause
:resume
:drain
:stop
```

Commands become typed inlet requests; text is never passed directly to a shell. Operator work is durably acknowledged with a task ID and may be submitted while another task is active.

## Noninteractive Use

Inspect a project:

```powershell
.\bin\leafctl.ps1 live C:\R\MyProject --inspect --json
```

Start a work-order run:

```powershell
.\bin\leafctl.ps1 agent-loop-start `
  --target C:\R\MyProject `
  --work-order C:\R\MyProject\WO.json `
  --profile local-coding `
  --yes
```

Submit one task to an existing run:

```powershell
.\bin\leafctl.ps1 loop task submit active .\config\task-control.submit.sample.json
```

Observe without interactive input:

```powershell
.\bin\leafctl.ps1 loop status active --json
.\bin\leafctl.ps1 loop attach active --after 0 --json
.\bin\leafctl.ps1 loop monitor active --noninteractive --jsonl --cursor-file .\monitor.cursor
.\bin\leafctl.ps1 tui --run active --once --page results
```

The loop monitor uses the same run state, worker lease, event journal, and
checkpoint authority as the loop inlet. With a terminal attached it selects
the interactive renderer automatically; redirected output selects JSONL. Use
`--interactive` or `--noninteractive` to make the choice explicit. `--json`
emits one stable snapshot and exits, while `--jsonl` emits one snapshot per
poll until the run reaches a terminal state. A cursor file is optional and is
written outside the run directory so monitoring never rewrites run evidence.

## Earlier Command Surfaces

`agent-task -> agent-route -> agent-dry-run -> agent-run -> agent-report` remains the finite 0.2 pipeline. Graph and three-input commands remain compatibility and research surfaces. They are useful for focused contracts, but new project-level instructions should use `live`, a typed task, or a work-order run.

`oneshot` creates a portable handoff bundle. It does not execute a project loop. The SSH node task commands distribute explicit node jobs and do not share the resident queue contract.

## Evidence And Privacy

The CLI persists accepted instructions, normalized work orders, provider requests and responses, plans, command output, validation, hashes, resource decisions, and reports. It exposes public reasoning summaries and progress events only. Private model chain-of-thought is neither requested as an operator feature nor stored as run evidence.
