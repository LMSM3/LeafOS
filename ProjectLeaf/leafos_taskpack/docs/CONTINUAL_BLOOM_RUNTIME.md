# Continual Bloom Runtime

LeafOS 0.9.3 implements the first Continual Bloom release gate as one durable
persona instance: **Monday — Rescue and Analysis**. The runtime preserves its
identity, transcript, cursor, claims, native evidence, facts, and checkpoints
across process restarts. It does not start a model or grant file, shell, or
network mutation authority.

This bounded Monday instance must remain the only durable personality until its
contract is proven. Wednesday and Friday remain configuration-level persona
descriptions; they are not initialized as sibling durable instances.

## Quick access

From `C:\R\LeafOS0.2.2` in PowerShell:

```powershell
.\leafos.ps1 bloom init
.\leafos.ps1 b
.\leafos.ps1 bloom verify
```

After installation, use the same commands without the path prefix:

```text
leafos bloom init
leafos b
leafos bloom verify
```

`leafos b` is the read-only shortcut for `leafos bloom status`. Use
`leafos q` to display the complete compact command card. Add `--json` to
`init`, `status`, `verify`, or `recover` for machine-readable output.
Before the first initialization, status returns `not_initialized` and the
single next action `instance.initialize`; it does not create the instance.
Once claims exist, status reports supported, refuted, and unverified counts
plus evidence coverage. Coverage is the reference-defined ratio of supported
claims to total claims; it remains unavailable when no claim exists.

The default instance is:

```text
ProjectLeaf/leafos_taskpack/instances/monday-primary
```

Every subcommand also accepts `--instance PATH`, which is useful for an
isolated test or recovery rehearsal.

## Durable layout

| Path | Purpose |
|---|---|
| `persona.json` | Exact identity, duties, model preference, and authority limits. |
| `events.ndjson` | Append-only SHA-256 hash chain and authoritative read head. |
| `state.json` | Rebuildable current-state projection with exactly one next action. |
| `facts.ndjson` | Only supported or refuted claims backed by native evidence. |
| `evidence/` | Immutable validation records containing evidence path, size, and digest. |
| `checkpoints/` | State snapshots allowed only after new validation evidence. |

KV cache is explicitly non-authoritative. Recovery derives state, facts, and
checkpoints from the validated transcript and succeeds when no KV cache exists.

## Claim lifecycle

Append operator input and note the returned `read_head`:

```powershell
.\leafos.ps1 bloom input --text "Inspect the failed build"
```

Monday may record a proposal only against that current read head:

```powershell
.\leafos.ps1 bloom claim --id build-1 --text "The compiler log identifies the failing target" --read-head 1
```

A stale read head is rejected and recorded as a rejection event. A current
claim begins as `unverified`; it is not a fact. A native validator promotes or
refutes it by naming an evidence file:

```powershell
.\leafos.ps1 bloom validate --claim-id build-1 --status supported --evidence .\build.log
.\leafos.ps1 bloom checkpoint --next-action input.append --reason "Await the next operator event"
```

Checkpoint creation fails closed until a new supported or refuted validation
exists. The transcript hash chain, derived facts, state, evidence records, and
checkpoint snapshots are checked together:

```powershell
.\leafos.ps1 bloom verify --json
```

If derived files are missing after an interruption, rebuild them from the
transcript:

```powershell
.\leafos.ps1 bloom recover --json
```

Recovery refuses a broken event chain. It never treats cached model state as
evidence.

## Authority boundary

- Monday can append bounded proposals and request one next capability.
- CPU-side native validation decides whether a claim becomes supported or
  refuted.
- No claim is accepted as fact merely because a model emitted it.
- No checkpoint is valid without validation evidence newer than the previous
  checkpoint.
- Exactly one structured next action is projected at a time.
- Model and coder selections are preferences, not execution authority.

The canonical design reference is
`C:\R\LeafOS0.2.2\LEAFOS-CONTINUAL-BLOOM-PRIMARY-REFERENCE.md`, with its
formatless TeX companion beside it. The machine-readable runtime contract is
`config/continual-bloom-monday.json`.
