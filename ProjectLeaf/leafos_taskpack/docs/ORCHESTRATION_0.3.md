# LeafOS 0.3 Orchestration

Status: retained compatibility prototype and contract-test surface. It is not
the current top-level project inlet. Use `leafctl live PATH`, a typed task, or
a version-2 work order for new project automation.

LeafOS 0.3 has a narrow orchestration prototype. It accepts exactly three
inputs:

`README  SKELETON  WILDCARD`

The wildcard input may be text, JSON, an image, an archive, or another file
type. LeafOS snapshots all three inputs, records size and SHA-256 metadata,
and gives the planner only the bounded context bundle.

## Run It

Plan without executing:

```bash
leafctl agent-orchestrate README.md skeleton.md input.any --mock
```

Execute the validated allow-listed skills:

```bash
leafctl agent-orchestrate README.md skeleton.md input.any --mock --yes
```

The run directory contains:

```text
context.json              input manifest and hashes
prompt.txt                bounded planner prompt
plan.json                 validated orchestration actions
action.schema.json        JSON schema used by the run
execution.state.json      action state
execution.jsonl           action events
artifacts/                skill outputs
report.md                 final result
```

## Skill Boundary

The model may select only these skills:

| Skill | Behavior |
| --- | --- |
| `context.inspect` | Save the three-input manifest as an artifact |
| `file.read` | Read only the README or skeleton snapshot; binary files become metadata-only |
| `file.hash` | Hash only one of the three input snapshots |
| `check.run` | Run one fixed check: doctor, graph tests, or shell syntax |
| `report.write` | Write the orchestration report |

There is no model-supplied shell command in the protocol. This is the important
execution boundary: model output proposes intent, while LeafOS decides whether
that intent is a known skill with valid references and dependencies.

## llama.cpp Structured Output

For a current llama.cpp server exposing the OpenAI-compatible endpoint, set:

```bash
export LEAF_LLAMACPP_URL=http://127.0.0.1:8080
export LEAF_LLAMACPP_CHAT_URL=http://127.0.0.1:8080/v1/chat/completions
export LEAF_LLAMACPP_MODEL=your-model
leafctl agent-orchestrate README.md skeleton.md input.any --provider llamacpp --yes
```

LeafOS sends `response_format` with a JSON schema and disables reasoning for
this planner call. The returned `message.content` is written as `plan.json`
and validated again before any skill runs.

Native completion endpoints first receive the same schema in the `json_schema`
body field. Older builds can use the `/completion` fallback with the bundled
GBNF grammar:

```text
config/orchestration.action.gbnf
```

The grammar only forces valid JSON. The second validation layer still enforces
the LeafOS protocol, skill enum, input references, dependencies, and DAG
integrity. JSON formatting alone is never treated as permission to execute.

## Failure Behavior

- Invalid JSON means no action runs.
- Unknown skills mean no action runs.
- Unknown input references mean no action runs.
- Dependency cycles and deadlocks stop the run.
- A failed skill stops the run and leaves `execution.jsonl` for inspection.
- Omitting `--yes` produces a plan only.
