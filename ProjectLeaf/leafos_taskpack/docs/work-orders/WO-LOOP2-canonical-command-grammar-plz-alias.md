# WO-LOOP2 — Canonical Task Command Grammar and `plz` Inner Alias

## Identity

- Owner/context: liamm / LeafOS coherent loop experience
- Current day: Day 0 (plan compiled; implementation not started)
- Release target: LeafOS 0.2.2 coherent loop stage
- Branch: `agent/organic-0.9.4-snapshot`
- Series position: after WO-LOOP1 and before WO-LOOP3
- Scope boundary: root/taskpack dispatchers, task-domain help, alias launchers, command schemas, parity tests, and command documentation

## Objective

Turn the coherent LOOP1 surface into one canonical task grammar and add `plz` as a short, first-class inner alias for `leafos task` without changing authority, defaults, validation, or results.

## Relationship to LOOP1

LOOP1 says the system must look and speak like one program. LOOP2 freezes the task-domain grammar that makes that claim observable and prevents command aliases from becoming alternate runtimes.

## Live-inference intent

Live-inference tasks must be reachable through both `leafos task ...` and `plz ...` with identical task digests, budgets, resource claims, evidence, and safety gates. The alias may shorten invocation; it may not replace actual llama.cpp execution with a fallback or mock.

## Typed task contract

- `system.command_surface.verify.v1` checks the canonical domain/action grammar, dispatcher route, help model, exit behavior, and alias equivalence.
- Inputs bind command-schema digest, dispatcher build identity, platform/shell, canonical argv, alias argv, environment-policy digest, and expected typed result.
- The result reports token translation, canonical route, task digest equality, output/exit parity, mutation classification, and any collision or bypass.
- Alias resolution occurs before task admission. It cannot name a handler, modify authority, add confirmation, or remove confirmation.

## `plz` inner-alias contract

The normative translation is:

```text
plz <action> [target] [options]
    == leafos task <action> [target] [options]
```

Required examples:

```bash
plz plan [project.example]
plz run <task-id>
plz status <task-id>
plz show <task-id>
plz explain <task-id>
plz accept <task-id>
```

- After injecting the canonical `task` domain, remaining arguments are forwarded token-for-token.
- `plz` with no action displays task-domain help and performs no mutation.
- `plz accept` retains the exact explicit confirmation, digest verification, authority checks, and idempotency of `leafos task accept`.
- The canonical task digest is identical regardless of invocation spelling; audit provenance records `invoked_as: plz` separately.
- Human output, `--json`, stderr, and exit codes must match the canonical route.
- Working-directory discovery may not alter alias semantics.
- Bash, PowerShell, CMD-facing installation, and direct Python/runtime routes converge on one dispatcher.
- Installation must detect an existing external `plz` command and refuse to overwrite it silently; `leafos doctor` reports the collision and the exact corrective action.
- Documentation always presents `leafos task` as canonical and `plz` as its documented shorthand.

## LOOP6 test adoption

[WO-LOOP6](WO-LOOP6-real-repository-scientific-outcome-tests.md) supplies the real command outcomes. LOOP2 owns C02 contract validation and R10 canonical/alias acceptance parity. `plz accept` must prove the same task digest, authority, decision, event, result, and exit behavior without causing a second canonical mutation.

## Acceptance criteria

- [ ] One versioned command registry defines task actions, arguments, mutation class, approval rule, result schema, help examples, and exit codes.
- [ ] `plz` resolves internally to the same task dispatcher rather than maintaining a duplicate switch statement.
- [ ] Canonical and alias invocations produce equal task digests and typed results for plan, run, status, show, explain, and accept.
- [ ] Unknown actions, ambiguous targets, unknown task types/versions, and extra shell-shaped arguments fail closed.
- [ ] Read-only actions never mutate task, event, allocation, evidence, Git index, or worktree state.
- [ ] Mutating actions use explicit verbs and retain the canonical confirmation/authority boundary.
- [ ] Task help has one minimal and one realistic `[project.example]` example per major action.
- [ ] Cross-shell quoting, Unicode/ASCII, redirected output, `--json`, and exit-code parity are tested.
- [ ] Alias installation is idempotent and never overwrites a pre-existing unrelated `plz` executable or function.
- [ ] `leafos doctor` can identify the selected dispatcher, alias resolution, registry digest, and collision state.

## Implementation sequence

1. Inventory current task routes; record that only `task accept` is presently wired through both taskpack dispatchers.
2. Define the command registry and stable action/argument/result vocabulary.
3. Route canonical `leafos task` actions through one native dispatcher.
4. Add the thin `plz` entry point that injects only the task domain.
5. Generate canonical and alias help from the same command metadata.
6. Add parity, collision, working-directory, safety, and cross-shell tests.
7. Document install/uninstall behavior and expose it through doctor.
8. Freeze the grammar before LOOP3 adds resource presentation.

## Owned doctrine clauses

This WO owns clauses 1–16, 34–39, and 63–72 from the supplied **LeafOS Coherent Experience and Resource Doctrine**. Other LOOP WOs may reference these clauses but may not redefine them.

- **D1.** Every action begins with a typed command whose meaning is visible before execution.
- **D2.** Every command must identify its target explicitly, using `[project.example]` as the canonical project placeholder.
- **D3.** The preferred command shape is `leafos <domain> <action> [project.example] [options]`.
- **D4.** Related commands must share vocabulary, argument order, output structure, and failure behavior.
- **D5.** A command must not change meaning merely because it is invoked from a different directory.
- **D6.** Project discovery may provide convenience, but explicit project selection remains available everywhere.
- **D7.** `leafos project inspect [project.example]` must describe the project before LeafOS proposes work.
- **D8.** `leafos task plan [project.example]` must produce a reviewable typed task without executing it.
- **D9.** `leafos task run <task-id>` must execute only the recorded task represented by that identifier.
- **D10.** `leafos task status <task-id>` must report state, resource use, evidence, blockers, and one legal next action.
- **D11.** `leafos task accept <task-id>` must remain distinct from execution, validation, and recommendation.
- **D12.** Destructive or irreversible actions must never hide behind harmless-sounding verbs such as `run`, `sync`, or `update`.
- **D13.** Commands that preview work must use `plan`, `show`, `inspect`, `diff`, or `explain`.
- **D14.** Commands that mutate state must use verbs such as `apply`, `accept`, `create`, `remove`, or `repair`.
- **D15.** The same operation must not have multiple competing command names unless one is a documented alias.
- **D16.** Aliases may shorten commands, but they must never introduce behavior unavailable through the canonical command.
- **D34.** Every CLI action must map to one registered typed task or one read-only projection.
- **D35.** Unknown task types, versions, handlers, or result schemas must fail closed.
- **D36.** Model-generated handler names must never become executable authority.
- **D37.** Native handlers must be registered through an inspectable versioned registry.
- **D38.** The registry digest must be visible in task records, snapshots, diagnostics, and replay reports.
- **D39.** `leafos task explain <task-id>` must show the task type, version, handler, inputs, authority, budget, and provenance.
- **D63.** `leafos doctor [project.example]` must test registry integrity, event integrity, resource visibility, and handler availability.
- **D64.** `leafos project status [project.example]` must summarize tasks, allocations, evidence, checkpoints, and pending acceptance.
- **D65.** Project status must use the same state names found in events and typed results.
- **D66.** Help text must use real examples based on `[project.example]`, not abstract placeholders that explain nothing.
- **D67.** Every major command must include one minimal example and one realistic example.
- **D68.** Documentation examples must be executed in tests or generated from tested fixtures.
- **D69.** New commands must not ship with help text copied from a previous command and “fixed later.”
- **D70.** File and directory names must match the vocabulary used by the CLI.
- **D71.** If the CLI calls something an allocation snapshot, the filesystem must not call it a queue cache.
- **D72.** If the CLI calls something a task result, the schema and documentation must use the same term.

## Status

[W] WO-LOOP2: canonical task CLI + plz parity
[D] Day 0: plan compiled; implementation not started
[I] TODO
[V] DISCOVERY: LOOP1 command vocabulary, current task-accept routes, and the 80-clause doctrine were reconciled
[P] LOCAL: planning document only; unrelated worktree changes remain unstaged
[N] After LOOP1, freeze the task command registry and implement `plz` as a token-preserving dispatcher alias

## Evidence log

- 2026-08-03: Allocated doctrine clauses 1–16, 34–39, and 63–72 to this WO without duplication.
- 2026-08-03: Defined `system.command_surface.verify.v1` as the typed verification task for this scope.
- 2026-08-03: User selected `plz` as the inner shorthand for the canonical `leafos task` surface.

## Carry-forward

- LOOP3 consumes the same command and task registries for resource previews; it may not create resource-only command aliases.
- LOOP4 renders the same typed results for canonical and alias routes.
- LOOP5 must demonstrate both spellings and prove digest/output/exit parity.

## Out of scope

- Replacing `leafos task` with `plz` in schemas, evidence, or canonical documentation.
- Shell text expansion that bypasses the LeafOS dispatcher.
- Implicit acceptance, confirmation suppression, or alias-specific authority.
- Implementing task execution handlers owned by WO-051–WO-056.
