# LeafOS

LeafOS is an experimental local orchestration and durability stack. FlowerOS
is the operator-facing machine surface; LeafOS manages bounded work, model
routing, native authority, evidence, checkpoints, recovery, and terminal or
web projections.

This repository intentionally begins as an **organic, partially working 0.9.4
snapshot**. It contains useful architecture and working subsystems alongside
known regressions and unfinished integrations. It is a development record, not
a polished release.

## Current shape

- PowerShell and Bash entry surfaces
- local model planning and installation infrastructure
- FlowerOS terminal presentation and hardware monitoring
- durable Monday — Rescue and Analysis runtime
- append-only evidence, capability, checkpoint, and recovery contracts
- project intake, task loops, TUI, web projections, benchmarks, and tests

The governing design is
[Continual Bloom Primary Reference](LEAFOS-CONTINUAL-BLOOM-PRIMARY-REFERENCE.md).
The current root contract is [documented here](markdowns/ROOT_CONTRACT.md).

## Start here

From Windows PowerShell:

```powershell
cd C:\R\LeafOS0.2.1
.\leafos.ps1 q
.\leafos.ps1 status
.\leafos.ps1 doctor
.\leafos.ps1 b
```

From Bash or WSL:

```bash
bash leafos.sh q
bash leafos.sh status
bash leafos.sh doctor
```

Model downloads are never included in this repository. Installer commands are
plan-first and should not cross the download boundary without explicit
confirmation.

## Honest snapshot status

The root contract validates on PowerShell and Bash, and the original bounded
Continual Bloom tests pass. The broader 0.9.4 integration is not green: the
latest complete local run passed 214 of 273 tests, with 10 failures and 49
errors.

Known problems include:

- the PowerShell installer currently bypasses the richer historical animation
  layer;
- authority-bridge tests are not isolated from the default Monday journal;
- a duplicate in-memory append can produce a transcript sequence gap;
- root and taskpack version files disagree;
- model-profile, shortcut, Catan2, USB, and Bash environment contracts have
  drifted from their tests.

These issues are being published rather than hidden because the project is at
the point where visible history and disciplined stabilization are more useful
than another private rewrite.

## Public-source boundary

The repository includes source, tests, schemas, configuration, and
documentation. It excludes model weights, download caches, virtual
environments, compiled binaries, live runtime state, logs, generated reports,
and local scratch work.

Some contained components carry their own MIT licenses. A repository-wide
license has not yet been selected; files outside those licensed components
remain under normal copyright rules.
