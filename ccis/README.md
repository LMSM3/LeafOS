# CCIS inside LeafOS

This subtree implements the local Constitutional Core Integration System for
the Scientific Change Loop.

```text
ccis/
  principles/   canonical source, hash manifest, and four operational projections
  contracts/    strict JSON Schema interfaces and examples
  kernel/       gates plus typed-task registry and deterministic allocation reducer
  tests/        contract, real-repository, replay, lease, and tamper proofs
loop/
  scientific_change_loop.py
.leafos/ccis/runs/<task-id>/
  events.jsonl  authoritative state history
.leafos/ccis/allocation/
  allocation-events.jsonl   authoritative scheduling history
  allocation-snapshot.json  disposable deterministic projection
  tasks/                     inspectable typed-task cache
  results/                   typed task results
```

CLI entrypoints:

```powershell
& .\leafos.ps1 ccis init --task .\task-envelope.json
& .\leafos.ps1 ccis status --run <run-directory>
& .\leafos.ps1 ccis validate --run <run-directory> --workspace <isolated-workspace>
& .\leafos.ps1 task accept <task-id>
```

The shorthand resolves `.leafos/ccis/runs/<task-id>` and uses the current OS
user as the operator. Automation may retain the explicit `--run`, `--operator`,
and `--confirm` form. Both routes validate the event chain, accepted state,
candidate hash, complete 18-artifact evidence bundle, exact task identity, and
unchanged Git index before applying the candidate with `git apply --cached`.
They never apply the patch to the working tree and never commit or merge.

Milestone 1 uses the complete canonical state sequence from `CREATED` through
`GATED`, then one outcome. `events.jsonl` is authoritative; `state.json` and
`checkpoint.json` are disposable projections reconstructed during resume.

`ccis validate` executes each declared command as an argument array with
`shell=False`. It refuses the authoritative repository and its descendants,
captures per-validator timing/exit status plus stdout and stderr, and writes
those records under `validation/`. A following `ccis evaluate` uses the
captured `validator-results.json` by default.

WO-051 adds a typed allocation foundation without changing the original
validator entrypoint. `ccis.command_validator/v1` is the first runtime adapter;
reserved loop, llama.cpp, and WO-017 MoE task types have no native handler and
therefore fail closed until their later work orders implement and register one.
The registry never imports a handler name supplied by a model or task payload.
