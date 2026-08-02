# LeafOS Documentation Map

This map defines which documents describe the current resident system and which preserve optional or historical subsystems. When documents disagree, the machine-readable schema and current implementation win, followed by the current operator and architecture documents below.

## Current Reading Order

1. `../README.md`: product overview, first command, and system boundaries.
2. `work-orders/WO-039-floweros-usage-layer-pivot-finalization.md`: FlowerOS surface and LeafOS engine handoff.
3. `QUICKSTART.md`: open a project and submit the first instruction.
4. `ARCHITECTURE.md`: authority, process, data, provider, and UI boundaries.
5. `AGENTIC_CLI.md`: instruction normalization and execution lifecycle.
6. `LOOP_MONITOR.md`: attached-terminal and detached JSONL observation.
7. `LIVE_PROJECT_TUI.md`: active-window project intake and minimal syntax.
8. `RESIDENT_STACK_USAGE.md`: resource policy, budgets, recovery, and soaks.
9. `LOOP_INLET_USAGE.md`: lifecycle and typed task controls.
10. `CONTINUAL_BLOOM_RUNTIME.md`: the durable Monday transcript and evidence contract.
11. `USB_INTERCEPTOR_USAGE.md`: removable-media transport, spool state, and safety boundary.
12. `TUI_USAGE.md`: pages, keys, snapshots, and transport security.

Recent WO handoff: `work-orders/WO-040-042-CONSOLIDATED-STATUS.md` records the
current deferred/complete/future markings and dated verification snippets for
WO-040 through WO-042.

## Active Midend Work-Order Series

The browser-modernization sequence uses the layered A -> C -> B design. The
native inlet remains authoritative throughout; HTTP acceptance, capability
preflight, projections, and browser state are never execution evidence.

| Order | Work order | Layer and deliverable | Acceptance focus |
|---:|---|---|---|
| 1 | `work-orders/WO-043-resource-oriented-midend-api.md` | A: stable pages, resource APIs, typed command translation | Midend cannot execute or mutate independently. |
| 2 | `work-orders/WO-044-capability-broker-typed-envelope.md` | C: capability catalog, bounded envelopes, native disposition | Forged, stale, replayed, substituted, or shell-shaped actions fail closed. |
| 3 | `work-orders/WO-045-event-projection-live-workspace.md` | B: deterministic snapshots, replay, and bounded live updates | Deleted projections rebuild semantically from durable evidence. |
| 4 | `work-orders/WO-046-layered-integration-native-authority.md` | Integrated A -> C -> B flow, packaging, degraded modes, rollout | Disabling the native inlet makes every mutation impossible. |
| 5 | `work-orders/WO-047-benchmark-brain-coder-observability.md` | Post-install benchmark proves Brain/Coder thinking process and logs named conversations | `conversation.jsonl`, `thinking.json`, and native `agent.dual_think` artifacts are produced for every run. |

The first implementation proof is deliberately narrow: run detail ->
`run.pause` -> native disposition -> durable event -> refreshed read state.
General live projections follow only after that authority path passes.

## Current Domain Guides

| Document | Authority |
|---|---|
| `MODEL_INSTALLATION.md` | Stack acquisition and local model storage. |
| `RUNTIME_PERSONAS_SWARM.md` | Runtime role selection; selection is separate from provider startup. |
| `MEMORY_MODEL.md` | Journal, reflection, promotion, checkpoint, and privacy rules. |
| `CONTINUAL_BLOOM_RUNTIME.md` | Single-persona durable runtime, evidence, cursor, checkpoint, and recovery rules. |
| `MEDIUM_MOE_MODEL_POLICY.md` | Current local model-selection contract, evidence provenance, SSD truth, and qualification workflow. |
| `TEST_OBSERVATORY_USAGE.md` | Visual tests and bounded live-stack demonstration. |
| `CATAN2_BENCHMARK.md` | Gameplay and resident Catan2 benchmark distinction. |
| `ACTION_RESULTS.md` | Per-action result artifacts used by earlier embedded actions. |
| `DUAL_THINKING_STREAM.md` | Explicit role-lane artifacts and public reasoning summaries. |
| `INSTALL.md` | Installation and optional distribution surfaces. |

## Optional Subsystems

These documents remain valid for their named subsystem but do not define the current project-agent architecture:

| Documents | Subsystem |
|---|---|
| `NODES.md`, `NETWORKING.md`, `LAN_ACCESS.md` | SSH/LAN node distribution. |
| `DASHBOARD_GUIDE.md`, `ATTRIBUTES.md` | Legacy node dashboard and broad CLI reference. |
| `NONINTERACTIVE_ONESHOT_USAGE.txt` | Portable handoff bundles. |
| `ORCHESTRATION_0.3.md`, `ACTION_RESULTS.md` | Early graph and three-input action execution. |
| `OVERNIGHT_*`, `GLM52_OVERNIGHT_RUNBOOK.md` | Historical GLM experiment harnesses; not current model policy. |

## Historical Evidence

`docs/history/`, `docs/work-orders/`, `reports/work-orders/`, `PROJECT_LOG.md`, `DECISIONS.md`, and version-specific design documents preserve what was planned, implemented, or measured at a point in time. They may mention mock providers, finite pipelines, old test counts, or interfaces that were correct for that work order. They are not silently rewritten into present tense.

The current WO-038 status is: implementation complete, real 4-minute profile passed, and real 8-minute/64-minute soaks pending. See `../reports/work-orders/WO-038-COMPLETION-REPORT.md`.

## Machine-Readable Authority

| Contract | Location |
|---|---|
| Resource policy | `../schemas/leafos.resource-policy.v1.schema.json` and `../config/resident-stack-policy.json` |
| Typed task control | `../schemas/leafos.task-control-request.v1.schema.json` |
| Project onboarding | `../schemas/leafos.project-onboarding.v1.schema.json` and `../config/project-onboarding.sample.json` |
| Per-run stack preferences | `../schemas/leafos.stack-preferences.v1.schema.json` |
| TUI snapshot | `../schemas/leafos.tui-snapshot.v1.schema.json` |
| Work-order plan | `../schemas/leafos.agent-loop-plan.v2.schema.json` |
| Universal telemetry | `../schemas/leafos.universal-run-log.v1.schema.json` |
| Loop monitor snapshot | `../schemas/leafos.loop-monitor.v1.schema.json` |
| Continual Bloom Monday instance | `../config/continual-bloom-monday.json`, `../schemas/leafos.continual-bloom-event.v1.schema.json`, and `../schemas/leafos.continual-bloom-state.v1.schema.json` |
| USB/LAN transport envelope | `../schemas/leafos.transport-envelope.v1.schema.json` |
| FlowerOS operator surface | `../config/operator-experience.schema.json` and `../config/operator-experience.json` |
| Provider route | `../config/vulkan-provider-stack.json` |
| Medium MoE selection | `../schemas/leafos.medium-moe-policy.v1.schema.json`, `../schemas/leafos.medium-moe-candidate.v1.schema.json`, and `../config/medium_moe_policy.json` |
| Midend resource/capability/projection contracts | Planned by WO-043 through WO-046; schemas are introduced in that series before route implementation. |

## Documentation Quality Rules

- Use exact runnable commands from `leafctl help`.
- State whether evidence is fixture, contract, synthetic, or real-provider.
- Describe models as proposal sources and CPU policy as execution authority.
- Explain pause, drain, stop, and TUI close as different operations.
- Do not promise exact hardware utilization or create work only to raise it.
- Never describe public phase summaries as private chain-of-thought.
- Keep completion status separate from implementation status when a soak remains unrun.

The 2026-07-21 documentation-wide alignment and validation record is
`../reports/DOCUMENTATION-REFRESH-20260721.md`.
