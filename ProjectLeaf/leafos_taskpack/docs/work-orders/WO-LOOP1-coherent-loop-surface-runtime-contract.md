# WO-LOOP1 — Coherent Loop Surface and One-to-One Runtime Contract

## Identity

* Owner/context: liamm / LeafOS loop, CCIS, and product architecture
* Current day: Day 0, memory document compiled; implementation not started
* Release target: LeafOS 0.2.2 loop-quality foundation
* Branch: `agent/organic-0.9.4-snapshot`
* Series position: companion specification after WO-056 and before numbered WO-057 implementation
* Imported source: Codex attachment `8d868eb2-7669-4f31-b5ab-48f045027aa8/pasted-text.txt`
* Project placeholder: `[project.example]`
* Scope boundary:

  * `loop/`
  * `ccis/contracts/`
  * `ccis/kernel/`
  * `cli/`
  * `evidence/`
  * `docs/diagrams/`
  * `.leafos/tasks/`
  * `.leafos/events.jsonl`
  * `.leafos/evidence/`

## Intent

Create one coherent LeafOS loop experience before attempting broad autonomous improvement.

The loop must:

* look like one program,
* speak one vocabulary,
* expose one clear CLI,
* map every visual node to real runtime behavior,
* preserve one authoritative task history,
* produce one complete evidence path,
* and always expose one legal next action.

The objective is not merely to draw a convincing loop.

The objective is to ensure that the loop shown in documentation is the loop executed by LeafOS.

## Architectural Position

The operating structure remains:

```text
Objective loop
    ↓
Candidate loop
    ↓
Implementation loop
    ↓
Scientific evaluation
    ↓
CCIS transition gate
    ↓
Accept / revise / reject / block / escalate
    ↓
Persist one legal next action
```

CCIS is the constitutional transition gate.

CCIS is not the planner, scheduler, editor, compiler, simulator, or complete loop.

The broader LeafOS loop generates and evaluates work.

CCIS determines whether that work may become authoritative state.

## Live-Inference Position

Live inference means loading an actual local GGUF model with `llama-cli` or `llama-server`, submitting a real prompt, performing CPU/GPU computation at that moment, receiving newly generated tokens, and recording the real output, timing, errors, and resource behavior.

Mocked responses, prerecorded output, file-existence checks, configuration validation, and deterministic policy fallbacks are not live inference.

WO-LOOP1 makes live inference visible and coherent across the CLI, typed-task registry, runtime states, allocation claims, events, diagrams, and evidence. It does not privately implement a second llama.cpp lifecycle; WO-054 through WO-056 own execution, streaming, and containment.

## Product Principle

A user should be able to understand the complete loop through the main CLI without knowing internal directories, schema names, queue structures, handler classes, or implementation history.

The system must feel continuous from:

```text
project inspection
    ↓
task planning
    ↓
resource allocation
    ↓
candidate selection
    ↓
implementation
    ↓
validation
    ↓
evidence review
    ↓
explicit acceptance
```

No stage may feel like a separate utility attached after the fact.

## Canonical CLI Surface

The preferred command structure is:

```bash
leafos <domain> <action> <target> [options]
```

Project-oriented commands use:

```bash
leafos project inspect [project.example]
leafos project status [project.example]
leafos project doctor [project.example]
```

Loop-oriented commands use:

```bash
leafos loop plan [project.example]
leafos loop run <task-id>
leafos loop status <task-id>
leafos loop inspect <task-id>
leafos loop resume <task-id>
leafos loop reject <task-id>
```

Task authority commands use:

```bash
leafos task show <task-id>
leafos task explain <task-id>
leafos task accept <task-id>
```

Allocation commands use:

```bash
leafos allocation show [project.example]
leafos allocation replay [project.example]
leafos allocation verify [project.example]
```

Evidence commands use:

```bash
leafos evidence show <task-id>
leafos evidence verify <task-id>
leafos evidence export <task-id>
```

Read-only commands must not mutate state.

Mutation commands must use explicit verbs.

Execution must remain separate from acceptance.

## Vocabulary Contract

The following terms must remain consistent across CLI output, JSON, schemas, diagrams, logs, documentation, and filesystem layout:

* project
* objective
* task
* candidate
* selection
* plan
* allocation
* claim
* lease
* workspace
* validation
* evaluation
* evidence
* decision
* transition
* checkpoint
* acceptance
* rejection
* escalation
* legal next action

A concept may not have one name in the CLI, another in the event log, and a third in the source tree.

Aliases may shorten commands but may not invent alternate semantics.

## One-to-One Diagram Rule

Every canonical loop diagram must obey:

```text
one diagram node
    = one runtime state or one bounded operation

one diagram arrow
    = one validated transition

one transition
    = one append-only event

one event
    = one recorded reason and evidence reference

one stopped state
    = one legal next action
```

A diagram node without runtime implementation is fictional.

A runtime state absent from the diagram is hidden behavior.

Neither is acceptable for the canonical loop.

## Canonical Mapping Record

Every loop node must define:

```text
node identifier
display name
runtime state
task type and version
native handler
input schema
result schema
required authority
resource claims
entry event
exit event
required evidence
failure outcomes
legal next actions
CLI presentation
```

This mapping should be machine-readable.

Documentation diagrams should be generated from, or verified against, this mapping whenever practical.

## Core Runtime States

The first complete loop should expose:

```text
CREATED
SNAPSHOTTED
OBJECTIVE_DEFINED
INSPECTING
CANDIDATES_GENERATED
CANDIDATE_SELECTED
PLANNED
ALLOCATED
MUTATING
VALIDATING
EVALUATED
GATED
ACCEPTED
REVISE
REJECTED
BLOCKED
ESCALATED
```

Additional internal events may exist, but they must not create hidden state semantics.

## Typed Task Requirement

Every actionable loop step must be a registered typed task.

A typed task must bind:

* task type,
* task version,
* objective,
* project target,
* authority,
* budget,
* validators,
* dependencies,
* resource claims,
* input artifacts,
* provenance,
* expected result schema.

Unknown task types must fail closed.

Unknown task versions must fail closed.

Model-generated handler names must never grant execution authority.

Native handlers must be registered explicitly.

## Task Digest

Every task must have a canonical digest covering:

* task type and version,
* objective,
* target,
* authority,
* budget,
* validators,
* dependencies,
* resource claims,
* input hashes,
* provenance,
* registry digest.

Semantically identical task records must produce identical digests.

A changed authority or budget must change the digest.

## Allocation Position

The allocation heap is a derived projection.

It is not authoritative state.

Authoritative allocation history remains in append-only events.

The scheduler may maintain:

* ready heap,
* delayed heap,
* dependency projection,
* resource projection,
* lease projection,
* task-state projection.

All projections must be rebuildable from events.

Deleting and rebuilding the allocation cache must preserve ordering and eligibility.

## Logical Time

Eligibility, delayed activation, lease expiry, and priority aging must depend on recorded logical-clock events.

Ambient wall-clock time must not silently mutate authoritative task state.

The operating system clock may inform a proposed event.

Only the recorded event changes LeafOS state.

## Resource Doctrine

Every task plan must reserve sufficient resources for:

* inspection,
* candidate generation,
* implementation,
* validation,
* scientific evaluation,
* documentation,
* evidence packaging,
* rollback,
* integration,
* interface polish.

A plan that funds code generation but not validation is incomplete.

A plan that funds validation but not recovery is incomplete.

A plan that funds functionality but not integration must be marked prototype-only.

Tracked resource classes should include:

* wall time,
* CPU threads,
* GPU memory,
* GPU utilization,
* system RAM,
* disk workspace,
* model context,
* token budget,
* model calls,
* compiler time,
* simulator time,
* human review time.

Requested, reserved, consumed, and remaining resources must remain distinct.

## Experience Budget

Every major implementation plan should reserve explicit time for:

* command naming,
* help text,
* output formatting,
* status presentation,
* error messages,
* JSON compatibility,
* cross-platform shell behavior,
* documentation examples,
* integration testing.

Product coherence is part of completion.

It is not optional polish added after architecture work.

## Human and Machine Output

Human-readable output and `--json` output must represent the same typed result.

The human view should emphasize:

* current state,
* completed stages,
* active work,
* resource use,
* blockers,
* evidence,
* one legal next action.

The JSON view should expose the complete typed record.

Stable exit codes must distinguish:

* success,
* invalid input,
* blocked,
* rejected,
* escalated,
* resource unavailable,
* integrity failure,
* internal failure.

## Progress Display

Progress output must distinguish:

* waiting,
* eligible,
* leased,
* running,
* validating,
* gated,
* blocked,
* completed.

A spinner must not imply progress when no state transition has occurred.

Waiting output must identify the resource, dependency, lease, evidence, or authority being awaited.

## Error Contract

Every error should state:

1. What failed.
2. Why it failed.
3. What state remains authoritative.
4. What artifacts remain valid.
5. Whether the project is unchanged.
6. The one permitted next action.

Detailed traces belong in evidence logs.

Default CLI output should remain readable.

## Evidence Contract

Every completed loop must connect its visible stages to evidence.

Minimum evidence includes:

```text
task.json
objective.json
candidates.json
selection.json
plan.json
allocation-events.jsonl
workspace-manifest.json
before-hash.json
after-hash.json
candidate.diff
commands.jsonl
test-results.json
evaluation.json
review.json
decision.json
transition.json
result.json
```

The CLI must make these artifacts discoverable without requiring filesystem archaeology.

## Explicit Acceptance

A passing candidate must not silently modify the authoritative project.

After gating, LeafOS should report:

```text
decision: acceptable
canonical project changed: no
legal next action:
    leafos task accept <task-id>
```

Acceptance must verify that:

* the base project is not stale,
* evidence hashes still match,
* authority permits acceptance,
* the task has not already been rejected,
* the transition remains reproducible.

Repeated acceptance of an already accepted task must be idempotent.

## Replay and Recovery

LeafOS must be able to:

* delete derived allocation state,
* rebuild it from events,
* reconstruct task state,
* reconstruct dependency state,
* reconstruct resource claims,
* reconstruct leases,
* reproduce ready and delayed ordering,
* verify snapshot integrity,
* discard corrupt caches,
* halt on corrupt authoritative events.

State reconstruction must require no manual editing.

## Visual Coherence

The canonical terminal presentation should share:

* indentation,
* state labels,
* identifiers,
* timestamps,
* severity labels,
* table layout,
* progress language,
* evidence references,
* next-action formatting.

Color may reinforce meaning.

Meaning must never depend on color.

Plain terminals and redirected output must remain usable.

## Demonstration Path

The first complete demonstration should use:

```bash
leafos project inspect [project.example]

leafos loop plan [project.example] \
    --instruction "Correct the bounded defect while preserving existing behavior."

leafos loop run <task-id>

leafos loop status <task-id>

leafos allocation verify [project.example]

leafos evidence verify <task-id>

leafos task accept <task-id>

leafos project status [project.example]
```

The demonstration must show:

* task creation,
* deterministic allocation,
* candidate selection,
* isolated modification,
* validation,
* evidence production,
* CCIS gating,
* explicit acceptance,
* final project state.

## Failure Demonstration

The same system must also demonstrate:

* interruption during execution,
* restart,
* replay,
* resume from checkpoint,
* candidate rejection,
* hash-verified rollback,
* unchanged authoritative project,
* retained evidence,
* one legal next action.

## Acceptance Criteria

* [ ] Canonical CLI vocabulary is defined and used consistently.
* [ ] Main loop commands operate through typed tasks or read-only projections.
* [ ] Every canonical diagram node maps to runtime behavior.
* [ ] Every canonical diagram transition maps to an event.
* [ ] Every stopped state exposes one legal next action.
* [ ] Human and JSON output use the same typed results.
* [ ] Allocation state rebuilds deterministically from append-only events.
* [ ] Resource and time budgets include validation, evidence, recovery, integration, and interface work.
* [ ] Project, loop, task, allocation, and evidence commands feel like one program.
* [ ] One fixture project completes the entire loop.
* [ ] One interrupted run resumes without manual state repair.
* [ ] One rejected run restores the original project hash.
* [ ] One accepted run changes the canonical project only after explicit acceptance.
* [ ] CLI state, diagram state, event state, and evidence state agree.
* [ ] Live-inference tasks, model/backend claims, streaming phases, containment outcomes, and evidence have one-to-one CLI, diagram, event, and runtime mappings.

## Status

```text
[W] WO-LOOP1: coherent loop surface + one-to-one runtime contract
[D] Day 0: memory document compiled
[I] TODO
[V] DISCOVERY: coherent surface and one-to-one mapping specified
[P] LOCAL: imported plan; implementation not started
[N] Bind the canonical CLI vocabulary to the typed-task registry and diagram mapping, then hand the frozen task grammar to WO-LOOP2
```

## Implementation Sequence

### Stage 1 — Vocabulary and command contract

Define canonical domains, verbs, arguments, states, output fields, and exit codes.

### Stage 2 — Typed mapping record

Define the machine-readable mapping from diagram nodes to task types, handlers, schemas, events, evidence, and CLI presentation.

### Stage 3 — Read-only loop display

Implement project, loop, allocation, and evidence inspection without mutation.

### Stage 4 — Fixture execution

Run one bounded fixture task through the real typed-task and allocation path.

### Stage 5 — Replay and interruption

Delete caches, replay events, interrupt execution, and resume from the last valid checkpoint.

### Stage 6 — Gate and acceptance

Produce a complete evidence bundle, gate the result, and require explicit acceptance.

### Stage 7 — Visual integration pass

Normalize help, status, errors, JSON, diagrams, examples, naming, and filesystem vocabulary.

### Stage 8 — Freeze the loop contract

Treat the demonstrated CLI, states, task mappings, and evidence path as the baseline for subsequent codebase trials.

## Evidence Log

* 2026-08-03: Imported the supplied WO-LOOP1 memory document into the LeafOS work-order shelf.
* 2026-08-03: Positioned as the coherent-surface specification after WO-056 and before the numbered implementation sequence.
* 2026-08-03: Added explicit live-inference mapping requirements consistent with the expanded WO-051–WO-061 series.

## Carry-Forward

* WO-051 supplies typed tasks, registry binding, deterministic reduction, heaps, leases, resource claims, and replay.
* [WO-LOOP2](WO-LOOP2-canonical-command-grammar-plz-alias.md) freezes canonical task commands and the `plz` inner alias.
* [WO-LOOP3](WO-LOOP3-resource-allocation-experience.md) operationalizes resource budgets and allocation presentation.
* [WO-LOOP4](WO-LOOP4-result-error-progress-accessibility.md) unifies typed results, errors, progress, and accessible rendering.
* [WO-LOOP5](WO-LOOP5-full-path-live-inference-contract-freeze.md) specifies the complete real path implemented and demonstrated by WO-057–WO-059.
* [WO-LOOP6](WO-LOOP6-real-repository-scientific-outcome-tests.md) records the 16 real repository/scientific acceptance outcomes without confusing expectations with executed evidence.
* [WO-057](WO-057-unified-loop-cli-visual-state-contract.md) implements the unified CLI and visual read model.
* [WO-058](WO-058-one-to-one-diagram-state-event-command-mapping.md) enforces diagram/state/event/command parity.
* [WO-059](WO-059-executable-loop-demonstrator-replayable-harness.md) executes the controlled replayable fixture.
* [WO-060](WO-060-matlabcpp-interpretation-kernel-trial.md) opens the first broad scientific-language trial.
* [WO-061](WO-061-loop-quality-improvement-propositions.md) synthesizes verified outcomes into bounded propositions.
* Later loop work orders may extend the canonical mapping but may not create private states or hidden task records.
* The first scientific codebase trial must use this same CLI and evidence path.
* MATLABC++ should not receive custom orchestration merely because it is scientifically interesting.
* New model packs must enter through registered task capabilities rather than alternate command surfaces.
* Executor concurrency remains one until replay, ordering, lease, rollback, and acceptance invariants pass.

## Out of Scope

* Distributed workers.
* Multiple authoritative coordinators.
* Implementing a second live llama.cpp lifecycle; mapping the real WO-054–WO-056 lifecycle into the coherent surface remains in scope.
* Automatic merge or acceptance.
* Automatic repair of corrupt authoritative events.
* Fully autonomous continual operation.
* Rich graphical UI.
* Scientific codebase improvement before the loop demonstration passes.

## Definition of Complete

WO-LOOP1 is complete when a user can watch the canonical diagram, run the canonical CLI, inspect the canonical event history, and verify the canonical evidence bundle while seeing the same loop represented four ways without contradiction.

```text
The diagram shows it.
The CLI names it.
The event log records it.
The evidence proves it.
```

Only then should LeafOS begin improving real scientific codebases.

Otherwise it merely possesses several individually impressive subsystems that communicate primarily through shared branding, a condition also known as enterprise software.
