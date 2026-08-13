# WO-053-A — Model Pack and Installer User-Path Hardening

## Identity

- Owner/context: liamm / LeafOS model-pack and local-model installation experience
- Current day: Day 0 (proposal prepared for operator review; implementation not opened)
- Release target: LeafOS 0.2.2 installer reliability gate before WO-053
- Branch: local merged OneDrive snapshot; WO-053 upstream reference is `agent/organic-0.9.4-snapshot`
- Scope boundary: model installer, PowerShell presentation wrapper, pack discovery, model-root resolution, store verification, documentation, and focused regression tests
- Entry position: immediate alphabetic addendum between verified WO-052 and implementation of WO-053

## Objective

Make the documented model-pack path behave like a trustworthy user product before
WO-053 consumes its executable and GGUF locations. A user must receive the same
catalog, plan, model root, safety gates, validation result, and exit disposition
from the guided PowerShell surface and the canonical Python backend.

This work order hardens acquisition and discovery. It does not download models,
run inference, or claim that a discovered model is executable by llama.cpp.

## Immediate alphabetical implementation order

| Order | Package | Work | Exit evidence |
|---:|---|---|---|
| A | Argument and exit integrity | Replace string-built `ProcessStartInfo.Arguments` handling with token-preserving argument transport; propagate backend failures through the wrapper and retain structured error text. | Paths with spaces pass unchanged; every forced backend failure produces the same nonzero wrapper exit. |
| B | Backend and catalog parity | Detect source/installed CLI and catalog drift; rebuild or refuse with an exact repair command; make readiness compare versions, slot count, command surface, and catalog digest. | A stale five-slot environment cannot report ready against the ten-slot source catalog. |
| C | Catalog-qualified pack discovery | List only supported `leafos.model-pack.v1` documents containing non-empty `install.items`; classify identity-only packs and companion manifests separately instead of offering them as install targets. | Every selectable install pack can produce an offline plan; unsupported JSON receives a clear classification. |
| D | Deterministic model-root discovery | Reconcile explicit `--dest`, `LEAF_MODEL_DIR`, installer-local weights, and `~/.leaf/models` into one reported precedence contract shared by doctor, plan, pack, status, runtime, and WO-053 handoff. | All surfaces name the same canonical absolute model root and explain why it was selected. |
| E | Experimental-pack safety | Keep base Viola and dormant experimental lanes distinct at plan/apply time; require confirmation for every selected experimental catalog key; correct role/item counts and size presentation. | The documented base command cannot silently include experimental weights; multi-key experimental plans require complete acknowledgement. |
| F | Full store verification | Separate inventory from verification; validate GGUF magic, minimum size, catalog membership, expected paths/sizes when pinned, duplicate/unknown artifacts, and overall failure disposition. | Corrupt, zero-byte, missing, size-mismatched, and unknown fixtures cannot yield verification success. |
| G | Guides and regression gates | Update root and installer documentation; add wrapper, clean-install parity, pack-contract, storage-resolution, experimental-guard, and store-verification tests. | Documented PowerShell and direct CLI workflows pass from a clean temporary environment without network transfer. |

## Acceptance criteria

- [ ] The documented profile and Viola pack planning commands succeed with repository paths containing spaces.
- [ ] A failed plan, resolve, apply, or verify operation yields a nonzero exit from every wrapper and preserves the backend reason.
- [ ] Readiness fails closed when the installed CLI/catalog differs from the source CLI/catalog and prints one deterministic repair action.
- [ ] The guided menu never presents a JSON document that the selected planning command cannot consume.
- [ ] `LEAF_MODEL_DIR`, explicit destination, installer-local discovery, plan output, runtime status, and WO-053 model input resolve through one documented precedence rule.
- [ ] Base Viola planning excludes dormant experimental catalog entries; experimental planning requires explicit inclusion and confirmation of every experimental key.
- [ ] Store inventory and store verification are separate operations with truthful operation names, result fields, and exit codes.
- [ ] Verification rejects invalid GGUF magic, undersized weights, missing pinned artifacts, size mismatches, and unclassified artifacts unless an explicit policy permits them.
- [ ] Source catalog expansion to ten slots is reflected in tests, installed tooling, help text, and readiness evidence.
- [ ] Documentation states whether weights are bundled in the current distribution and identifies their canonical absolute storage root without contradiction.
- [ ] Focused tests cover all A–G packages without network access or model transfer.
- [ ] WO-053 receives an explicit, verified model-path handoff but remains responsible for binary, model, backend, and host capability evidence.

## Verification plan

1. Run PowerShell wrapper tests with temporary roots containing spaces and injected backend failures.
2. Install the package into a fresh temporary virtual environment and compare CLI commands, catalog version, slot count, profiles, and catalog digest with source.
3. Validate every JSON file in the pack directory as installable, identity-only, companion manifest, or invalid; require complete classification.
4. Exercise destination precedence with explicit destination, environment override, detected installer cache, and home default fixtures.
5. Plan base and experimental Viola variants offline; assert deduplication, item count, estimate, and heavyweight confirmation behavior.
6. Verify valid, corrupt, zero-byte, missing, mismatched, duplicate, and unknown artifact fixtures without hashing production weights.
7. Re-run installer unit tests and model-profile tests, then execute the documented safe plan commands end to end without resolve/apply.

## Status

[W] WO-053-A: model pack and installer user-path hardening
[D] Day 0: review evidence converted into an immediate alphabetic proposal before WO-053
[I] TODO
[V] DISCOVERY: wrapper, source/backend parity, pack contracts, local status, store inventory, and focused tests inspected
[P] LOCAL: proposal document only; no installer, catalog, pack, configuration, or series-index edits
[N] Operator reviews A–G scope and acceptance criteria; edit the proposal if requested, then explicitly authorize Day 1

## Evidence log

- 2026-08-09: The documented PowerShell Viola plan reported backend exit 2 while the outer script returned exit 0.
- 2026-08-09: Direct source planning accepted `viola-nocturne.json`, deduplicating 16 role entries to 10 catalog-key/quant items with an estimated 176,520,000,000-byte transfer.
- 2026-08-09: Six other JSON files exposed by the guided pack selector lacked `install.items` and were rejected by `plan-pack`.
- 2026-08-09: The installed virtual environment reported five catalog slots and lacked newer commands while source reported ten slots; readiness still passed.
- 2026-08-09: Direct `runtime-default` local status validated the existing Gemma coder and Opus assistant weights.
- 2026-08-09: Store inspection enumerated nine GGUF artifacts but returned success without artifact-level verification when no resolved-plan state was present.
- 2026-08-09: Installer unit tests passed 14 of 15; the failing assertion still required exactly slots 1–5. Model-profile tests passed 4 of 4. No pack-planning regression tests were found.

## Dependencies and handoff

- Depends on verified WO-052 evidence integrity only for truthful result/evidence handling; it does not modify WO-052 history.
- Receives the bounded pack-identity/subsystem evidence contract from [WO-050-R1](WO-050-R1-pack-glyph-subsystem-evidence-repair.md); this repair does not open WO-053-A Day 1 or prove model residency.
- Gates WO-053 Day 1 model-path consumption, but does not replace WO-053 binary/model/backend capability checks.
- Supplies reliable model identity and location inputs to WO-053; WO-054 through WO-056 remain the owners of live inference, streaming, and containment.
- The typed-loop series index should be updated only after this proposal is approved.

## Out of scope

- Resolving remote Hugging Face metadata or downloading, deleting, moving, requantizing, or hashing production weights.
- Starting `llama-cli`, `llama-server`, or any other inference provider.
- Changing runtime role policy, provider assignments, model quality rankings, or GPU placement.
- Claiming that installer verification proves llama.cpp compatibility or semantic model quality.
- Renumbering WO-053 through WO-061 or rewriting completed WO-051/WO-052 evidence.
- Editing source, packs, configuration, tests, documentation, or the series index before operator approval.

## Retroactive repair note — 2026-08-11

The operator explicitly authorized WO-050-R1 as a cross-stack repair. Its
source, schema, documentation, test, and index edits are confined to subsystem
indicator evidence and do not constitute approval of WO-053-A packages A–G.
