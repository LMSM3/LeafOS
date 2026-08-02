# WO-047 — Benchmark Brain/Coder Observability and Thinking-Process Logging

## Identity

| Field | Value |
|---|---|
| Work order | LeafOS-WO-047 |
| Title | Benchmark Brain/Coder Observability and Thinking-Process Logging |
| Date | 2026-07-27 |
| Target | LeafOS 0.2.1 installation / post-install benchmark |
| Status | Proposed implementation baseline |
| Authority | CPU-authoritative native inlet; `agent.dual_think` remains the Brain/Coder boundary owner |
| Depends on | `docs/work-orders/WO-043-resource-oriented-midend-api.md` through `WO-046-layered-integration-native-authority.md`; `docs/DUAL_THINKING_STREAM.md`; existing `core/agent/actions.sh` `agent.dual_think` action |
| Unblocks | Verifiable post-install evidence that the Brain and Coder lanes execute, produce artifacts, and surface a thinking trace; future HTML benchmark report view |

## Objective

The `leaf_loop_inlet.py benchmark` command must prove the real LeafOS Brain/Coder stack during installation, not merely assert telemetry. Each benchmark iteration shall drive the native `agent.dual_think` action (or a documented equivalent), record the named conversation between operator, Brain, Coder, and System, and persist the **thinking process** artifacts produced by the planner→coder handoff.

## In-scope outcomes

1. A new benchmark mode (`brain-coder`) alongside `llm` and `skeleton`.
2. Per-iteration durable artifacts under `runs/bench/<timestamp>-install/`:
   - `conversation.jsonl` — timestamped, named messages:
	 - `user` — the benchmark instruction.
	 - `brain` — the planner graph artifact summary.
	 - `coder` — the coder handoff/patch proposal summary.
	 - `system` — validation outcome, patch gate result, or failure reason.
   - `thinking.json` — structured handoff status:
	 - `planner.status`, `planner.graph_path`
	 - `coder.status`, `coder.handoff_path`, `coder.patch_path`
	 - `patch_gate.status`, `patch_gate.reason`
	 - `error` if any stage failed
   - Copies or references to `brain.graph.json`, `coder.handoff.md`, and `coder/patch.diff` when available.
3. Human-readable console trace with names, timestamps, and a short phase summary.
4. Final JSON report extended with `conversation` and `thinking_process` fields.
5. Provider-less runs degrade gracefully: the action attempt is still logged, with failure reason captured.

## Out-of-scope

- Generalized live projection streaming (remains WO-045).
- Modifying `agent.dual_think` to do anything beyond its current contract; we wrap and observe it.
- Applying generated patches; the benchmark is observational.
- Calling remote providers or cloud inference.

## Acceptance gates

| # | Gate | Evidence |
|---|---|---|
| 1 | `python core/python/leaf_loop_inlet.py benchmark --help` lists `--mode brain-coder` | Terminal output |
| 2 | `benchmark 10s --provider off --mode brain-coder` completes without raising and writes `conversation.jsonl` | Test + file listing |
| 3 | `conversation.jsonl` contains at least `user`, `brain`, `coder`, and `system` entries with `time` ISO timestamps and `role`/`name` fields | Test |
| 4 | `thinking.json` is produced and contains `planner`, `coder`, and `patch_gate` objects | Test |
| 5 | `benchmark 30s --provider auto --mode brain-coder` successfully invokes `agent.dual_think` and surfaces thinking artifacts when provider is healthy | Manual run |
| 6 | Focused suite `tests.test_install_benchmark` passes | Test output |
| 7 | Full `python -m unittest discover -s tests -p 'test_*.py'` passes without regressions | Test output |

## Invocation contract

```text
python core/python/leaf_loop_inlet.py benchmark <duration> --mode brain-coder \
	[--provider required|auto|off] [--sample-hz N] [--json]
```

Examples:

```text
python core/python/leaf_loop_inlet.py benchmark 60s --mode brain-coder --provider auto
python core/python/leaf_loop_inlet.py benchmark 5m --mode brain-coder --provider required --json
```

## Implementation notes

- The benchmark driver creates one isolated `runs/bench/<timestamp>-install/` directory per invocation.
- Inside that directory, a skeleton `runs/latest` symlink convention or ad-hoc `LEAF_RUN_DIR` is used so `core/agent/actions.sh` can operate without polluting the agent-loop namespace.
- `agent.dual_think` is invoked through `pwsh`/`bash` with the `agent_run_action` helper, or through the documented equivalent that writes to `actions.jsonl`.
- The task file for each iteration is written as `task.md` inside the iteration subdirectory.
- Conversation entries are appended incrementally so a partial run still yields useful evidence.
- If the provider is off, the Brain action is invoked anyway; expected failure is captured in `thinking.json` and `conversation.jsonl` rather than silently skipped.

## File map

| File | Responsibility |
|---|---|
| `core/python/leaf_loop_inlet.py` | `command_benchmark`, `_benchmark_brain_coder_round`, `_parse_benchmark_duration`, conversation/thinking persistence |
| `core/agent/actions.sh` | Existing `action_dual_think`; invoked, not modified, unless portability gaps are found |
| `core/python/leaf_live_project.py` | Reused by `skeleton` mode only |
| `docs/DUAL_THINKING_STREAM.md` | Contract reference for roles and artifacts |
| `docs/DOCUMENTATION_MAP.md` | Updated with WO-047 entry |
| `tests/test_install_benchmark.py` | Tests for role/timestamp schema, artifact presence, bounded runtime, degraded provider behavior |

## Risks

- `agent.dual_think` may require `jq`, `bash`, and a writable `LEAF_RUN_DIR`; Windows paths and PowerShell quoting must be handled carefully.
- A degraded provider can cause rapid failures with no useful artifacts. The driver must still log the attempt and surface the reason.
- The action may be slow per iteration; iterations should be paced by actual completion rather than a fixed sleep, while still respecting telemetry sample rate.

## Carry-forward

After WO-047 merges, the next logical step is to expose the benchmark report and conversation/thinking artifacts in the HTML midend under a “Bench” tab, reusing the A → C → B read routes from WO-043/WO-046.
