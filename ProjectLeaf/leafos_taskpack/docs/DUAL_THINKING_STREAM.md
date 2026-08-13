# LeafOS Dual Thinking Stream

Current integration note: the resident version-2 loop may use one active local
provider route while preserving separate planner/coder artifact roles. The
dual-stream document describes explicit role records, not a requirement for
two simultaneously resident model processes. CPU-side validation remains the
authority in either arrangement.

The actions shell is the execution boundary between model proposals and filesystem authority. The dual thinking stream is not an unrestricted shared conversation and does not expose private chain-of-thought. It is two explicit, persisted role lanes joined by validated artifacts:

```text
brain / planner
	│ structured graph, task decomposition, constraints
	▼
validated handoff
	│ task context + graph artifact + coder contract
	▼
coder / implementer
	│ bounded unified diff
	▼
patch gate
	│
	├── accepted validated patch
	└── rejected patch with failure evidence
```

## Role boundaries

### Brain stream

The brain stream owns:

- task decomposition;
- dependency ordering;
- scope and completion criteria;
- runtime and model-role selection; and
- the structured `agent.graph.json` artifact.

It does not write project files or apply patches.

### Coder stream

The coder stream owns:

- implementation proposal;
- unified-diff output;
- bounded file/line scope; and
- patch-gate submission.

It consumes the planner handoff but does not own graph authority, completion authority, or patch application authority.

### System stream

The local system owns:

- filesystem inspection;
- patch validation and application as separate actions;
- tests and verification;
- graph status;
- checkpoints; and
- reports.

A successful coder result means **validated patch available**, not **patch applied**.

## Action entry points

The actions shell exposes:

```bash
agent_run_action agent.ask_brain NODE_ID INPUT_JSON
agent_run_action agent.ask_coder NODE_ID INPUT_JSON
agent_run_action agent.dual_think NODE_ID INPUT_JSON
```

A dual action requires a task file:

```json
{
  "task_file": "tasks/example.md"
}
```

The action performs the following sequence:

1. Generate and validate a planner graph.
2. Persist the graph under `runs/latest/dual-thinking/<node>/brain.graph.json`.
3. Build a coder handoff containing the original task, graph artifact, and diff contract.
4. Generate a coder patch in an isolated node directory.
5. Run the existing patch gate.
6. Copy only the validated patch to `runs/latest/coder.patch`.
7. Persist `dual-thinking.json` with planner/coder statuses and artifact paths.
8. Leave application to the separate `patch.apply` action.

## Evidence artifacts

A successful dual action produces:

```text
runs/latest/
├── actions.jsonl
├── action-results/<node>.json
├── coder.patch
└── dual-thinking/<node>/
	├── brain.graph.json
	├── coder.handoff.md
	├── dual-thinking.json
	└── coder/
		├── patch.diff
		├── validation.log
		└── manifest.json
```

`actions.jsonl` records the role stream (`brain`, `coder`, `dual`, `execution`, or `system`). Action results record status, exit code, timestamps, stream, and generated artifact paths.

## Failure behavior

The dual stream fails closed when:

- the task file is missing;
- the planner cannot produce a valid graph;
- the provider fails;
- the coder returns an empty response; or
- the patch gate rejects the diff.

No failed or unvalidated patch is applied. Repair and retry are represented as new graph actions rather than hidden retries inside the dual action.

## Why this matters for the night loop

The night loop can now wait on explicit artifacts instead of waiting blindly for text:

```text
planner checkpoint
→ coder handoff
→ validated patch
→ tests/verification
→ accepted or rejected report
→ cleanup and next task
```

This makes the dual stream measurable through checkpoint latency, patch acceptance, validation failures, recovery count, and validated useful changes per task.
