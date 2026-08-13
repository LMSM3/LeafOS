# Contributing To LeafOS

LeafOS is local-first, CLI-first, evidence-first, and policy-gated.

## Start With The Current Architecture

Read `docs/DOCUMENTATION_MAP.md`, `docs/ARCHITECTURE.md`, and `docs/AGENTIC_CLI.md` before changing the loop. New project workflows should extend the typed inlet and version-2 run contract. Do not create a second queue, scheduler, provider authority, or TUI mutation path.

## Engineering Rules

- Keep changes bounded to the owning subsystem.
- Preserve existing structured schemas and argument-array command execution.
- Provider output remains proposal-only; CPU policy owns execution and validation.
- Every mutation path needs declared paths, approval behavior, validation, and durable evidence.
- Every long-lived process needs explicit ownership, bounded recovery, and clean shutdown.
- Every TUI control must become an authenticated named inlet request.
- Missing hardware counters remain unknown; do not turn absence into zero.
- Resource targets apply only to useful work; never add synthetic load to satisfy a meter.
- Fixture and mock providers are test dependencies only, never production fallback.
- Do not expose or persist private model chain-of-thought.

## Documentation Rules

- Use **stack** for all downloaded and locally available models in the instance.
- Distinguish the resident project stack from the optional SSH node subsystem.
- Distinguish `realbench` and `fullstackbench` gameplay from resident project improvement.
- Mark contract, fixture, synthetic, and real-provider evidence explicitly.
- Preserve historical work orders and reports as dated evidence; update current guides instead of rewriting history.
- Update `docs/DOCUMENTATION_MAP.md` when adding an operator-facing document.

## Verification

Run focused tests while developing, then the complete observatory before a completion claim:

```powershell
.\bin\leafctl.ps1 test visual --plain
.\bin\leafctl.ps1 test visual --match provider --live-stack --plain
```

For native TUI changes:

```bash
bash ./bin/build_tui.sh
python -m unittest tests.test_tui_native
```

For resident scheduling changes:

```powershell
.\bin\leafctl.ps1 resident start --contract-only --iterations 3
.\bin\leafctl.ps1 resident start --profile 4m --provider required
```

Never claim the 8-minute or 64-minute soak passed unless its retained summary is present and successful.
