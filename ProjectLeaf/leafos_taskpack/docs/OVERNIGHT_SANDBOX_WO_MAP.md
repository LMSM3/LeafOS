# Overnight Sandbox Work-Order Map

> Historical GLM-5.2 mapping. Keep it as provenance for the old sandbox; use
> `MEDIUM_MOE_MODEL_POLICY.md` for current model selection and qualification.

This map connects `sandbox/overnight-01` to the existing LeafOS work orders. The overnight run is a bounded local evaluation; mapped work orders provide contracts and evidence requirements, but do not expand the six task scopes.

## Primary mapping

| Sandbox area | Work order | Relationship | Required use |
|---|---|---|---|
| Entire run: explicit files, dry-run, validation, logs, reports | [WO-000 Getting Started](work-orders/WO-000_GETTING_STARTED.md) | Direct foundation | Use its local-first and auditable-work-order rules. Every task must leave logs, a report, and a validation result. |
| Model invocation, output contract, patch acceptance, reviewer boundary | [WO-005-G Model Library](work-orders/WO-005-G-model-library-real-assignments.md) | Direct runtime contract | Treat the model as a bounded execution resource. Require parser/validation gates before accepting generated work. |
| Run records, checkpoint, completion map, export/report pattern | [WO-004-D Wakeup Integration, Tests, and Export](work-orders/WO-004-D-wakeup-integration-tests-export.md) | Supporting integration pattern | Reuse the `action -> test -> completion -> export -> report -> checkpoint` shape for each sandbox assignment. |
| Small isolated action shape and CLI entrypoint discipline | [WO-004-C Wakeup Runtime Node](work-orders/WO-004-C-wakeup-runtime-node.md) | Supporting skeleton pattern | Apply its self-contained node principle to the three coding fixtures and worker commands; do not import its wakeup behavior. |

## Task-by-task mapping

### Coding fixtures

| Sandbox task | Primary WO coverage | Acceptance interpretation |
|---|---|---|
| `coding-cli` | WO-000 + WO-005-G + WO-004-D | Model may propose a small implementation; tests must validate stdin-to-JSON behavior; report must record accepted/rejected changes. |
| `coding-library` | WO-000 + WO-005-G + WO-004-D | Model may implement bounded retry logic; invalid configuration tests are the completion gate. |
| `coding-parser` | WO-000 + WO-005-G + WO-004-D | Model may implement parsing; malformed-input and line-number tests are the completion gate. |

### Game projects

The three game projects already provide their own deterministic simulation, build, test, resume, state, and journal behavior. The overnight worker should preserve those project contracts.

| Sandbox task | Project contract | LeafOS WO coverage | Acceptance interpretation |
|---|---|---|---|
| `game-chess` | `FF/LeafOS/projects/chess/README.md` | WO-000 + WO-005-G + WO-004-D | Reproduce the seeded/non-interactive baseline, then make at most one small validated improvement. Full official chess rules are out of scope. |
| `game-catan` | `FF/LeafOS/projects/catan/README.md` | WO-000 + WO-005-G + WO-004-D | Reproduce the resume/simulation baseline, then make at most one small validated improvement. Full board topology and deferred rules remain out of scope. |
| `game-ticket-to-ride` | `FF/LeafOS/projects/ticket-to-ride/README.md` | WO-000 + WO-005-G + WO-004-D | Reproduce the non-interactive baseline, then make at most one small validated improvement. Official maps and rules remain out of scope. |

## Worker contract derived from the WOs

For each of the six assignments:

1. Read the sandbox work order and project README.
2. Create a baseline log before editing.
3. Produce the first validated checkpoint by minute 30.
4. Accept only bounded changes inside the staged task directory.
5. Run the declared tests/build/simulation checks.
6. Write `RUN_REPORT.json` containing the work-order ID map, commands, changed files, validation result, elapsed time, checkpoint status, and stop reason.
7. Stop at 72 minutes, or earlier when the 30-minute checkpoint is missing.

The model remains a proposer. The filesystem, patch, test, checkpoint, and report gates remain local LeafOS authority, consistent with WO-005-G.

## WOs not activated by this run

| Work order | Reason |
|---|---|
| WO-006-D Z.AI / GLM adapter lane | Not used: this run is defined for local GLM-5.2 inference and does not require a remote provider or API key. |
| Dashboard and interaction WOs | Not used: the run produces file-backed reports and does not require dashboard UI work. |
| Model-download or inventory WOs | Not used by the sandbox: model downloads are disabled and the runtime profile is configured separately. |

## Run-level evidence location

The run should collect evidence under:

```text
sandbox/overnight-01/
├── run-status.json
├── work/<task-id>/RUN_REPORT.json
├── work/<task-id>/logs/
└── work/<task-id>/reports/
```

The final seven-hour productivity result should be compared with the GLM-5.2 overnight metrics contract in [GLM52_OVERNIGHT_RUNBOOK.md](GLM52_OVERNIGHT_RUNBOOK.md), especially validated useful changes rather than token rate alone.
