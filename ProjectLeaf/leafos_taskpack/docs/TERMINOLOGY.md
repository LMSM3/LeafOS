# LeafOS Terminology

These terms are normative for current documentation. Historical work orders may retain earlier wording as dated evidence.

## Stack

**Stack** means every model downloaded and locally available to this LeafOS instance. It may contain multiple families, quantizations, roles, and model artifacts.

- **stack entry**: one local model artifact, selectable profile, group, or pack.
- **runtime stack**: stack entries selected for active runtime roles.
- **provider stack**: the serving layer, such as llama.cpp plus Vulkan, and its active stack entry.
- **remote stack**: models available on another node; they are not part of the local stack until made local.

## Pack And Group

- **pack**: a top-level model bundle described by `leafos.model-pack/v1`. A pack may contain up to ~20 models and exceed 200 GB of artifacts. It is inventory, not necessarily resident.
- **layer**: a functional slice inside a pack, e.g. `coder` or `brain`.
- **group**: a filtered set of models for one slot, described by `leafos.model-group/v1`.
- **slot**: a logical runtime role, e.g. `coder.primary` or `judge.primary`.

Do not use `stack` as a synonym for one active model unless the document explicitly says `single-model stack entry`.

## Project And Run

- **project**: the operator-selected directory being inspected or improved.
- **run**: a persistent version-2 state directory that controls work for one project target.
- **active run**: the run selected by the current active pointer, not necessarily a currently executing process.
- **iteration**: one bounded project improvement that reaches validation and report.
- **resident stack**: the local stack plus supervisor, inlet, executor, validator, telemetry, and UI kept available for continual project work.

## Instruction And Work

- **instruction**: operator intent supplied as a directory, objective, active-window text, JSON task, or work order.
- **intake**: bounded read-only project inspection and objective derivation.
- **work order**: machine-readable authority defining objective, paths, commands, mutation, approval, retries, and timeout.
- **task**: one durable queue item normalized from operator, repair, or resident-generated work.
- **operator task**: work directly requested by the user; highest normal admission class.
- **repair task**: bounded follow-up created from a recorded failure.
- **resident-generated task**: one evidence-derived improvement admitted by the supervisor within budget.
- **productive backlog**: eligible work that can advance the accepted objective; never synthetic utilization work.

## Lifecycle

- **plan**: schema-constrained provider proposal.
- **approval**: policy decision allowing declared mutation; never inferred from model output.
- **execute**: CPU-authoritative application of approved steps.
- **validate**: execution of every declared acceptance command.
- **checkpoint**: durable binding of validated facts, hashes, and recovery position.
- **report**: human-readable summary derived from recorded run evidence.
- **safe boundary**: point between tasks, steps, or provider requests where pause, reprioritization, drain, and ordinary throttling may take effect.

## Process Ownership

- **resident supervisor**: one leased process that evaluates resource policy, maintains availability, and admits bounded follow-up work.
- **worker**: one leased task-claim process using the inlet.
- **provider**: local or configured model service that supplies proposals.
- **executor**: allowlisted CPU-side authority that applies approved operations.
- **validator**: CPU-side authority that produces acceptance evidence.
- **lease**: short-lived process-ownership record; it is not durable completion evidence.

## Resource Policy

- **target**: desired utilization during matching productive work, not a requirement to create load.
- **profile**: named governor behavior such as `auto-idle`, `auto-interactive`, `quiet`, `full`, or `pressure`.
- **claim gate**: decision permitting or deferring the next task claim.
- **headroom**: reported unused CPU or GPU capacity; it is observational, not authority.
- **pressure**: memory, thermal, responsiveness, provider, pause, drain, or stop condition that closes or reduces dispatch.
- **budget**: renewable bound on unattended minutes, generated iterations, failures, and changed files.

## Interfaces And Evidence

- **inlet**: the typed, policy-enforcing command and task boundary.
- **active window**: interactive TUI attached to a project run.
- **snapshot**: normalized read-only TUI state plus bounded event delta.
- **event cursor**: sequence position used to reconnect without replay ambiguity.
- **journal**: append-only native record of durable events or controls.
- **telemetry**: measured CPU, GPU, memory, provider, throughput, process, and task state.
- **public reasoning summary**: explicit bounded plan, decision, progress, or result intended for inspection.
- **private chain-of-thought**: hidden model internals that LeafOS does not display or persist.

## Benchmarks

- **`realbench`**: conversation and raw-inference benchmark that measures provider throughput and correctness against local CPU baselines.
- **`fullstackbench`**: end-to-end stack benchmark covering routing, provider lifecycle, and universal telemetry.
- **contract profile**: scheduler/control test without a real-provider claim.
- **real profile**: wall-clock run requiring the configured provider and measured hardware evidence.
