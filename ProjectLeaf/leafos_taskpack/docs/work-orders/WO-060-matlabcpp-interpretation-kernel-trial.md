# WO-060 — First Broad Scientific Codebase Trial: MATLABC++ Interpretation Kernel

## Identity

- Owner/context: liamm / LeafOS scientific-codebase improvement trial
- Current day: Day 0 (supplied concept compiled; repository not yet bound)
- Release target: post-coherence LeafOS 0.2.2 trial milestone
- Branch: `agent/organic-0.9.4-snapshot`
- Depends on: passing WO-059 demonstration and verified LOOP6 outcomes
- Scope boundary: one explicitly selected MATLABC++ repository, bounded typed tasks, isolated candidates, deterministic compiler/numerical validators, evidence, and explicit acceptance

## Purpose

Use LeafOS to improve a real, imperfect scientific programming project rather than another synthetic fixture. “First” here means the first broad repeated improvement campaign; the bounded VSEPR-Sim acceptance fixture in LOOP6 remains a prior real-repository gate.

## Working project shape

```text
[project.example]/
  kernel/
    lexer/
    parser/
    ast/
    types/
    evaluator/
    cpp_emitter/
  runtime/
  examples/
  tests/
    matlab_compatibility/
    parser/
    emitter/
  docs/
```

The kernel interprets a bounded MATLAB-like language through:

```text
MATLAB-like source
  -> tokenization
  -> syntax tree
  -> shape/type interpretation
  -> intermediate representation
  -> C++ emission or native evaluation
  -> compilation/execution
  -> numerical comparison
```

This layout is provisional until read-only inspection binds the actual repository, build system, tests, invariants, and allowed paths.

## Initial bounded tasks

```bash
leafos loop plan [project.example] \
  --instruction "Add bounded parsing support for matrix literals."

leafos loop plan [project.example] \
  --instruction "Detect incompatible matrix dimensions before evaluation."

leafos loop plan [project.example] \
  --instruction "Translate one indexed assignment form into valid C++."

leafos loop plan [project.example] \
  --instruction "Compare interpreted and emitted results for supplied numerical fixtures."
```

The `plz plan`, `plz status`, `plz explain`, and `plz accept` forms remain canonical task-domain aliases and must preserve identical task/evidence/authority behavior.

## Typed trial architecture

- `trial.scientific_codebase.v1` binds repository/baseline identity, bounded objective, task registry, resource policy, live-inference policy, validators, evidence, and trial-level stopping conditions.
- Parser, type, translation, compilation, numerical-comparison, documentation, and acceptance work remain separate registered child task types.
- All work enters the rebuildable allocation heap; no MATLABC++-specific private orchestrator, queue, or acceptance route is allowed.
- Every candidate is isolated. The canonical repository changes only after CCIS gating and explicit digest-bound acceptance.

## Live-inference and scientific correctness

Candidate generation may use actual local GGUF live inference with declared model/context/token/GPU/time claims and retained output. Model text has no compiler, filesystem, validation, or acceptance authority.

Deterministic validators own:

- grammar/parser fixtures and AST shape;
- type/shape constraints;
- generated C++ compilation and diagnostics;
- runtime safety and bounded execution;
- interpreted-versus-emitted numerical equivalence and tolerances;
- regression, scope, budget, diff, documentation, and evidence checks.

## Why this target is useful

The trial couples language syntax, AST consistency, type/shape inference, numerical behavior, generated C++ validity, compiler output, runtime comparison, documentation, and regression preservation. It is complex enough to expose weak loop contracts while remaining divisible into bounded changes.

## Trial phases

1. Read-only inspect and bind repository facts, baseline, build/test commands, risks, and allowed paths.
2. Choose one narrow task with deterministic acceptance and rollback.
3. Preview complete implementation/validation/evidence/recovery/interface resource budget.
4. Generate diverse candidates, including live inference only through registered capability.
5. Select, mutate in isolation, compile/test/compare, evaluate, and gate.
6. Review evidence and explicitly accept or reject.
7. Replay/rebuild and verify canonical/history consistency.
8. Repeat only within declared trial/stopping budgets.
9. Compare measured outcomes without mixing model/host/policy digests.
10. Hand verified evidence and improvement propositions to WO-061.

## Acceptance criteria

- [ ] An actual MATLABC++ repository is explicitly selected, inspected, clean, and baseline-hashed.
- [ ] At least one bounded task completes the full typed loop without custom orchestration.
- [ ] Live inference, when used, is real, resource-claimed, and separately evidenced from deterministic validation.
- [ ] Existing tests pass and task-specific parser/type/compiler/numerical validators pass.
- [ ] Candidate scope, budget, diff, evidence, and rollback policies pass.
- [ ] Interrupt/replay/resume and reject/restore work without manual state editing.
- [ ] The canonical repository remains unchanged until explicit acceptance.
- [ ] CLI, mapping, events, allocation, evidence, and project state agree.
- [ ] Repeated tasks remain bounded by trial stopping conditions and human authority.
- [ ] A trial report records verified gains, regressions, rejected candidates, resource use, and unresolved contract weaknesses.

## Status

[W] WO-060: first broad MATLABC++ scientific-codebase trial
[D] Day 0: concept compiled; target repository not bound
[I] TODO
[V] NONE: no MATLABC++ inspection, build, test, inference, or transition executed
[P] LOCAL: planning document only; no external repository mutation or publication
[N] After WO-059 passes, locate and inspect the intended MATLABC++ repository before choosing the first bounded task

## Evidence log

- 2026-08-03: Imported supplied MATLABC++ shape, four starter tasks, correctness dimensions, and milestone boundary.
- 2026-08-03: Distinguished this broad trial from the earlier bounded VSEPR-Sim outcome fixture.

## Carry-forward

- WO-061 compares only verified, compatible LOOP6/WO-059/WO-060 outcomes.
- [WO-017/MOE-010](WO-017-small-scale-moe-hardware-orchestration.md) may inspect only a frozen trial snapshot and emit findings, proposed work orders, or patch proposals; it cannot mutate this trial or bypass daytime validation and acceptance.
- Later scientific targets reuse the same task, allocation, mapping, result, evidence, and acceptance contracts.

## Out of scope

- Creating a MATLABC++ repository before its intended source is identified.
- Unbounded language implementation, compiler replacement, or autonomous continual changes.
- Model-generated compiler/test claims without real deterministic execution.
- Automatic acceptance, commit, merge, or publication.
