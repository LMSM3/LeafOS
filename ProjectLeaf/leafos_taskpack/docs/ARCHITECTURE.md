# LeafOS Architecture

LeafOS is a persistent project-automation system with a local model provider, a CPU-authoritative execution inlet, durable run state, and a read-only-plus-typed-control terminal interface.

## System Shape

```text
operator / script / TUI
          |
          v
typed project onboarding + live-project intake
          |
          v
version-2 run directory + priority/dependency queue
          |
          v
resident supervisor <---- foreground and hardware samples
          |
          v
resource governor -----> claim, defer, pace, recover
          |
          +----> llama.cpp Vulkan provider: structured proposals
          |
          +----> CPU inlet: policy, execution, tests, validation
          |
          v
journal + checkpoint + report + bounded next improvement
```

The resident supervisor does not replace the loop inlet. It decides when eligible work may be claimed and whether one bounded follow-up task may be admitted. Queue mutation, process ownership, approval, execution, validation, and journaling remain in the inlet.

## Instruction Contract

An instruction may originate as pasted README/skeleton intent, an existing directory, a full JSON work order, a TUI objective, a one-line typed task, or inferred project intent. Guided onboarding normalizes location, the project-only sandbox, and model optimization preferences into `leafos.project_onboarding_request` and previews it before any write. All routes then normalize to bounded work with:

- one project root and declared allowed paths;
- explicit mutation and approval policy;
- allowlisted commands represented as argument arrays;
- task priority, dependencies, timeout, and attempt budget;
- provider role and resource hints;
- acceptance commands and completion evidence.

The canonical lifecycle is `inspect -> plan -> approve -> execute -> validate -> report`. Checkpoints are written at safe boundaries. A failed plan, execution, or validation may enqueue bounded repair work; repair does not erase the original failure.

## Authority Boundaries

| Component | May do | May not do |
|---|---|---|
| Local model provider | Propose structured plans and bounded content. | Write project files, run commands, approve itself, or become evidence without validation. |
| Resident supervisor | Evaluate resource policy, maintain one supervisor lease, start one worker, and derive bounded follow-up objectives. | Bypass inlet policy or generate unlimited work. |
| Loop inlet/executor | Validate requests, mutate allowed paths, launch tracked commands, journal controls, and checkpoint facts. | Expand authority beyond the accepted work order. |
| Validator | Run declared tests and produce acceptance evidence. | Convert a failure into success or silently skip required commands. |
| TUI renderer | Read normalized snapshots and send authenticated named controls. | Edit queues, policy, project files, or execute arbitrary shell text. |
| Journal/checkpoint | Preserve durable events, hashes, and recovery facts. | Infer facts that were not recorded or validated. |

## Core Boundaries

| Responsibility | Primary location |
|---|---|
| Cross-shell command surface | `bin/leafctl`, `bin/leafctl.ps1` |
| Project onboarding form | `core/ui/tui/project_wizard.py`, `schemas/leafos.project-onboarding.v1.schema.json` |
| Web midend A -> C -> B series | `docs/work-orders/WO-043-resource-oriented-midend-api.md` through `WO-046-layered-integration-native-authority.md` |
| Per-run stack preferences | `stack-preferences.json`, `schemas/leafos.stack-preferences.v1.schema.json` |
| Project intake, seed creation, and objective derivation | `core/python/leaf_live_project.py` |
| Typed inlet, worker, queue, controls | `core/python/leaf_loop_inlet.py` |
| Work-order lifecycle and executor | `core/python/leaf_agent_loop.py`, `core/python/leaf_work_order.py` |
| Resident lifecycle and refill | `core/python/leaf_resident_supervisor.py` |
| Deterministic resource policy | `core/python/leaf_resource_governor.py`, `config/resident-stack-policy.json` |
| Foreground activity and responsiveness | `core/python/leaf_foreground_activity.py` |
| Provider lifecycle and adapters | `core/providers/`, `config/vulkan-provider-stack.json` |
| Medium-MoE policy and runtime status | `config/medium_moe_policy.json`, `config/medium_moe_candidate.template.json`, `core/python/leaf_moe_contract.py`, `core/python/leaf_runtime.py`, `core/runtime/runtime.sh` |
| Universal telemetry | `core/python/leaf_telemetry.py`, `schemas/leafos.universal-run-log.v1.schema.json` |
| Python TUI | `core/ui/tui/` |
| Native TUI | `core/tui/` |
| Durable memory | `core/memory/`, native LMEM journal |
| Schemas | `schemas/` |
| Tests | `tests/` |

## Run Directory Contract

`run.json` identifies the target and run. `work-order.json` records initial authority. `queue.json` and `state.json` record execution state. `events.jsonl` is the reconnectable presentation stream. `control.lmem` is the hash-chained control record. `resident-state.json` stores policy, decisions, budgets, and usage. `checkpoint.json` binds validated repository facts. `universal-run-log.jsonl` stores machine-readable operational telemetry. `artifacts/` contains provider I/O, plans, command output, and hashes. `report.md` summarizes the accepted result or blocker.

Short-lived lease files describe ownership; they are not durable truth after their process exits. Windows PID checks use native process status so stale numeric PIDs cannot retain ownership accidentally.

## Provider And Stack

The stack is the complete local model inventory. Runtime and provider configuration select stack entries for active roles. The current resident coding path uses one warm llama.cpp Vulkan server with one parallel slot to avoid duplicate model residency. Provider failure becomes an explicit degraded state with bounded recovery backoff; production execution never substitutes fixture or mock output.

### Medium-MoE Research Route

The 47--156B Medium-MoE method is a first-class runtime status lane, not a second active provider. `leaf_runtime.py` validates policy and candidate readiness, while the canonical shell selector in `runtime.sh` exposes policy, candidate location and state, and an explicit `active_route: incumbent` / `automatic_promotion: false` boundary; `LEAF_MEDIUM_MOE_CANDIDATE` may point those read-only checks at a private candidate record. The candidate stays observational until the semantic contract, measured 4/8/64-minute evidence portfolio, and operator review all succeed. A `resolved` record means identity and configuration are declared, not that the candidate is qualified or active. The incumbent route in `config/vulkan-provider-stack.json` remains provider authority until a separately approved route change.

## Resource Policy

The governor is a pure decision function over policy, queue facts, hardware, foreground activity, provider health, and prior state. It returns profile, reason, claim gate, targets, CPU slots, and provider delay. Normal throttling occurs at task or provider-request boundaries. Hard pressure can stop new claims immediately.

CPU/GPU percentages are useful-work targets, not completion criteria. Missing counters remain unknown rather than becoming zero. High-frequency display samples do not flood the durable journal.

## Interfaces

The Python and native renderers consume the same normalized snapshot schema. Native controls cross an ephemeral loopback socket authenticated by a per-session token; payloads are bounded and named. Pressing `n` exits either renderer into the shared guided onboarding form; the backend validates and previews the request, creates only the three declared seed files for a new project, records per-run stack preferences, and then reopens the renderer on the new active run. Model optimization choices are typed queue requests and cannot directly mutate or restart the shared provider.

### Layered Web Midend

The traditional browser surface is implemented as A -> C -> B. Layer A owns conventional pages, stable resource URLs, and read aggregation. Layer C is mandatory for every mutation and prepares only declared, versioned, bounded capability envelopes for native admission. Layer B derives disposable snapshots and live notifications from journals, checkpoints, manifests, validated artifacts, and bounded telemetry. A `202 Accepted` response means only that the native inlet accepted a request for processing; completion appears only after durable evidence changes and the projection rebuilds.

The initial proof is `run detail -> run.pause -> native disposition -> durable event -> refreshed read state`. The browser, HTTP server, capability preflight, session store, SSE stream, and projection cache cannot execute commands, edit project files, grant capabilities, declare validation success, or create evidence. If the native inlet is unavailable, all mutation routes fail closed while eligible read surfaces may remain available with explicit freshness and degradation metadata.

The older dashboard, graph runner, one-shot bundles, and SSH node system remain separate optional subsystems. They do not own the resident project loop.

## Privacy And Observability

LeafOS records observable inputs, structured proposals, progress counters, decisions, commands, outputs, tests, hashes, and reports. It does not expose or persist private model chain-of-thought. Any `THOUGHT` or reasoning display is a bounded public phase summary or explicit model output, not hidden internal reasoning.
