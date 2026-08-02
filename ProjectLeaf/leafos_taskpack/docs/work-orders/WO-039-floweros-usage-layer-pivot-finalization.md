# WO-039 - FlowerOS Usage-Layer Pivot Finalization

[I] DONE

## Decision

FlowerOS is the operator-facing experience. LeafOS remains the execution, policy, journal, provider-routing, validation, checkpoint, and evidence engine. Durable object names remain `leafos.*`; the pivot does not fork or rename the engine.

Within this system, stack means all downloaded and locally available models in this instance. A provider route selects a stack entry for a role without changing that definition.

## Implemented

- Restored `bin/flower.ps1` as a real PowerShell entrypoint and retained `bin/flowerctl` for Bash-compatible hosts.
- Added `config/operator-experience.json` and its schema as the operator-surface and economics authority.
- Added reusable local-token economics with an explicit output-token comparison rate.
- Extended inference matrix reports with measured benchmark tokens, gross cloud-equivalent value, and decode-only hourly projections.
- Added `realbench summary` for saved matrix reports.
- Extended new universal telemetry events with scoped economics while preserving reads of historical events without that field.
- Added the local-token dollar column to the operator telemetry view.
- Projected operator identity, latest benchmark status, and local-token value through Home and the TUI Hardware page.

## Truth Boundary

The initial comparison rate is an operator assumption of USD 10 per million generated output tokens. It can be changed in the operator config or overridden for a report. It is not a provider quote unless marked as such.

Gross cloud-equivalent value is not net savings. Local electricity, cooling, storage, and hardware depreciation remain null until measured; cloud input and cache charges and model-quality differences are also excluded. Decode-rate projections are labeled as arithmetic, not sustained agentic output.

## Usage Entry

```powershell
.\bin\flower.ps1 home
.\bin\flower.ps1 live C:\R\MyProject
.\bin\flower.ps1 tui --run active
.\bin\flower.ps1 chat
```

The equivalent Bash entry is `./bin/flowerctl`.

## Handoff

The next development phase should prioritize ordinary use: onboarding a real project, issuing lightweight objectives, observing progress, correcting tasks, and evaluating whether the resident stack is useful over repeated daily sessions. Infrastructure changes should now be driven by friction observed in that usage rather than speculative subsystem expansion.
