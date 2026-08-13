# WO-LOOP6 — Real Repository and Scientific Outcome Test Ledger

## Identity

- Owner/context: liamm / LeafOS loop engineering with VSEPR-Sim fixture integration
- Current day: Day 0 (test catalogue compiled; no LOOP6 tests executed)
- Release target: LeafOS 0.2.2 coherent loop acceptance
- Branch: `agent/organic-0.9.4-snapshot`
- Series position: specification companion after WO-LOOP5 and before the numbered WO-057–WO-060 implementation sequence
- Source: supplied 16-segment minimum/scientific acceptance-test document
- Scope boundary: LOOP test contracts, retained evidence, one explicitly bound real repository, isolated workspaces, and read-only cross-project inspection until a test run is opened

## Objective

Turn the supplied acceptance scenarios into a typed, replayable test ledger that distinguishes planned expectations from real observed outcomes. The ledger must prove LeafOS on a small real repository and must use deterministic scientific validators wherever a model opinion would be insufficient.

## Truth boundary

Every test record has one of four evidence states:

```text
NOT_RUN -> RUNNING -> PASS | FAIL | BLOCKED
```

`PASS` requires retained command/event/artifact evidence and verified digests. A written expected result, discovered test file, mocked response, or manually composed JSON record is never a real outcome.

Each outcome records:

- `test_id` and test-contract digest;
- target repository identity and baseline tree hash;
- evidence class: `repository_transition`, `live_inference`, `deterministic_validator`, or `mock_fixture`;
- exact argv, environment-policy digest, working directory, timing, exit status, stdout/stderr references;
- task, registry, allocator, model, binary, grammar, and validator digests when applicable;
- expected result and separately captured observed result;
- event-stream head and evidence-bundle digest;
- disposition, mismatch explanation, and one legal next action.

## Typed task architecture

The catalogue uses registered types rather than a private test queue:

| Task type | Purpose |
|---|---|
| `test.loop_acceptance.v1` | Repository lifecycle, state, authority, scope, budget, evidence, replay, and rollback tests |
| `test.scientific_outcome.v1` | Diversity, dimensional, geometry, and known-limitation outcomes |
| `test.scientific_invariance.v1` | Permutation, rotation, translation, topology, energy, and aligned-geometry invariance |
| `test.outcome_ledger.verify.v1` | Verify expected/observed separation, evidence classes, digests, and series summary |

All test tasks enter the WO-051 allocation path. Repository mutation, GPU/model use, ports, validators, timeouts, and evidence storage are declared resource claims. Allocation snapshots remain disposable; test/outcome events and evidence remain authoritative.

## Live-inference boundary

Candidate-generation and interpretation-diversity tests use actual live inference: a real local GGUF is loaded by llama.cpp, a real prompt is submitted, and fresh tokens are captured with runtime/resource evidence. Mock or prerecorded candidates may exercise deterministic harness behavior but cannot satisfy live gates.

Scientific correctness is not delegated to the model. Dimensional consistency, VSEPR geometry, topology, pair distances, angular tolerances, symmetry, Kabsch-aligned RMSD, and rollback hashes are computed by deterministic validators. The model may propose; the validators decide whether the proposal satisfies the declared scientific contract.

## Target binding

The supplied target is the VSEPR-Sim molecule loader with the bounded task:

```text
Reject atom records missing an element symbol.
```

Planned allowed paths:

```text
src/molecule_loader.py
tests/test_molecule_loader.py
```

Planned denied paths:

```text
.git/*
build/*
requirements/*
```

Before execution, `[project.example]` must resolve to one inspected, clean real repository and the actual loader/test paths must be verified. The plan does not assume that the supplied illustrative paths already match the current VSEPR-Sim tree.

## Core runtime-integrity lane — segments 1–9

### C01 — Minimum end-to-end acceptance

Traverse `CREATED -> SNAPSHOTTED -> OBJECTIVE_DEFINED -> INSPECTING -> CANDIDATES_GENERATED -> CANDIDATE_SELECTED -> MUTATING -> VALIDATING -> GATED -> ACCEPTED` on the bounded loader defect.

Required evidence:

- canonical repository unchanged before acceptance;
- isolated candidate patch;
- existing and new invalid-input tests passing;
- every transition in the hash-chained event stream;
- complete evidence bundle;
- explicit `leafos task accept <task-id>` or equivalent `plz accept <task-id>` before canonical change.

### C02 — Contract validation

Accept a complete objective/scope/budget/validator/authority envelope. Reject a missing objective before workspace creation. Return `BLOCKED` plus `request_authority` when requested authority exceeds worker capability.

### C03 — State-machine legality

Reject illegal shortcuts including `CREATED -> MUTATING`, `SNAPSHOTTED -> ACCEPTED`, validation without evaluation, acceptance without a decision, and mutation after rejection without a revision. Repeated valid events are idempotent and do not duplicate transitions.

### C04 — Append-only authority and cache disagreement

Tampering with an earlier event blocks resume and leaves the canonical repository unchanged. A cache claiming `ACCEPTED` while events stop at `CANDIDATE_SELECTED` is discarded or repaired from events.

### C05 — Scope-boundary attacks

Reject changes to denied files, traversal paths, outside-repository symlinks, Windows case/separator variants, build artifacts, and allowed-to-denied renames. Retain the isolated candidate as evidence and leave the canonical repository unchanged.

### C06 — Budget enforcement

Enforce iterations, changed-file count, wall time, child-process termination, checkpointing, and partial-log retention. A third mutation after a two-attempt budget is forbidden.

### C07 — Evidence completeness and hash binding

Individually remove each required task/objective/candidate/roundtable/plan/hash/diff/command/test/evaluation/decision artifact. Gating must block with a precise missing-artifact result. Post-hash mutation rejects with an artifact-hash mismatch.

### C08 — Interrupt, restart, and resume

Interrupt candidate generation, mutation, and validation separately. Preserve completed candidates once, invalidate partial workspaces, expire owned validation leases through events, replay projections, and resume from the last valid checkpoint without duplicate event IDs.

### C09 — Reject and rollback

Hash before and after rejection/rollback across modified, created, deleted, renamed, permission, symlink, and interrupted-rollback fixtures. The restored tree hash and untracked set must match the original; staged changes disappear while evidence remains.

## Real testing outcome lane — segments 10–13

These four records are the initial real-outcome ledger. They remain `NOT_RUN` until their retained commands and evidence are verified.

### R10 — Explicit acceptance authority

After validators pass, status must report `GATED`, `ACCEPTABLE`, and `canonical_applied: false`, with acceptance as the legal next action. Unknown and rejected task acceptance fails, repeated accepted-task acceptance is idempotent, and stale-base acceptance blocks pending revalidation.

Outcome evidence must include canonical/alias parity:

```text
leafos task accept <task-id>
plz accept <task-id>
```

Both routes must resolve to the same task, digest, policy, event, result, and exit code. The test performs only one real mutation; the parity route is evaluated through a non-mutating plan/dry-run or idempotent replay.

### R11 — Three-interpretation diversity

Submit the methane prompt through live inference and require three materially distinct candidate interpretations:

1. discrete geometry/pairwise repulsion;
2. constrained energy minimization;
3. coupled PDE or field-assisted interpretation.

Reject heading-only paraphrases. Record governing-equation identifiers, geometry representation, solver class, variables, boundary conditions, and discretization method. Require at least two unique solver families and two unique geometry models.

### R12 — Dimensional consistency

The deterministic validator rejects:

```text
-div(epsilon grad(phi)) = rho + k r
```

when `rho` and `k r` have incompatible dimensions, and accepts the dimensionally consistent Poisson form:

```text
-div(epsilon grad(phi)) = rho
```

The selected candidate may not pass merely because live inference describes the equation confidently.

### R13 — Geometry invariants

For methane, require one central atom, four domain directions, tetrahedral topology, and:

```text
theta_tet = arccos(-1/3) ~= 109.471 degrees
max angular deviation <= 0.5 degrees
centroid deviation <= 1e-8 normalized units
radial-distance spread <= 1e-6
abs(dot(unit(v_i), unit(v_j)) + 1/3) < 1e-6
```

Additional real fixtures cover BeCl2 linear, BF3 trigonal planar, CH4 tetrahedral, NH3 trigonal pyramidal, H2O bent, PCl5 trigonal bipyramidal, SF6 octahedral, and XeF4 square planar geometry.

## Extended scientific outcome lane — segments 14–16

### R14 — Symmetry and permutation

Permuting equivalent atom order preserves molecular topology, energy, selected interpretation class, and geometry up to rotation/reflection/permutation. Compare aligned geometry using Kabsch RMSD with `RMSD <= 1e-8`, not raw coordinate equality.

### R15 — Rotation and translation invariance

Translate and arbitrarily rotate a geometry. Internal angles, pairwise distances, energy, scientific evaluation, and gate decision remain unchanged within declared tolerance.

### R16 — Known scientific limitation

For transition-metal, delocalized multi-center, or strong Jahn-Teller cases where basic VSEPR is insufficient, require `ESCALATED`, recorded uncertainty, a precise insufficiency reason, and the legal next action to request an electronic-structure or ligand-field model. Confident unsupported success fails the test.

## Recommended first eight-test pack

| ID | Test | Primary lane |
|---|---|---|
| T01 | `valid_task_full_acceptance` | C01 |
| T02 | `forbidden_path_rejected` | C05 |
| T03 | `missing_evidence_blocks_gate` | C07 |
| T04 | `interrupt_resume_from_validation` | C08 |
| T05 | `reject_rollback_hash_exact` | C09 |
| T06 | `explicit_accept_required` | R10 |
| T07 | `methane_tetrahedral_geometry` | R13 |
| T08 | `ambiguous_model_escalates` | R16 |

This pack is the first execution target because it covers a bounded task, isolated change, complete evidence, explicit authority, scientific correctness, refusal behavior, and repository recovery.

## Acceptance criteria

- [ ] All 16 segment contracts exist as registered typed test records with expected results and `NOT_RUN` initial state.
- [ ] A real repository inspection resolves the VSEPR-Sim target and validates allowed/denied paths before execution.
- [ ] T01–T08 run through the shared allocator and retain authoritative event/evidence records.
- [ ] R11 uses live local llama.cpp inference; R12–R15 use deterministic scientific validators.
- [ ] Each result preserves expected and observed fields separately and refuses a result without evidence digests.
- [ ] Canonical `leafos task` and `plz` acceptance semantics pass R10 parity without a second mutation.
- [ ] Core failures leave the canonical repository unchanged or hash-restored as declared.
- [ ] Cache deletion/replay reconstructs test task state, allocation, resource claims, and outcome status.
- [ ] The LOOP6 summary reports PASS/FAIL/BLOCKED/NOT_RUN counts and never presents partial execution as suite success.
- [ ] WO-061 consumes only comparable verified outcomes and excludes mocks from live-inference aggregates.

## Status

[W] WO-LOOP6: real repository + scientific outcome test ledger
[D] Day 0: 16-segment catalogue compiled; no LOOP6 test executed
[I] TODO
[V] DISCOVERY: expected outcomes and evidence requirements defined; observed outcomes remain empty
[P] LOCAL: planning document only; no VSEPR-Sim mutation, model load, staging, or publication
[N] After LOOP5, inspect and bind the real fixture repository, then admit T01 without advancing any result beyond NOT_RUN

## Evidence log

- 2026-08-03: Imported all 16 supplied segments and the recommended T01–T08 first pack.
- 2026-08-03: Segments 1–9 classified as runtime-integrity gates, 10–13 as the initial real-outcome lane, and 14–16 as extended scientific outcomes.
- 2026-08-03: Corrected the methane tetrahedral expression into a stable plain-text formula suitable for deterministic tests.
- 2026-08-03: No test execution is claimed by this planning record.

## Carry-forward

- LOOP1 owns one-to-one state/CLI/event/evidence vocabulary.
- LOOP2 owns canonical task commands and `plz` parity.
- LOOP3 owns budgets, allocation, leases, and replay.
- LOOP4 owns typed results, errors, progress, and accessibility.
- LOOP5 owns the coherent full-path demonstration and contract freeze.
- LOOP6 owns real acceptance outcome recording; WO-061 owns subsequent comparison and improvement propositions.

## Out of scope

- Mutating an unresolved or dirty external repository.
- Treating expected results as executed outcomes.
- Letting live inference replace dimensional, geometry, invariance, scope, hash, or authority validation.
- Adding VSEPR-Sim-specific orchestration outside registered LeafOS task types.
- Automatic acceptance, merge, publication, or scientific-model escalation.
