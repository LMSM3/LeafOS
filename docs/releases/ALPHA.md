# LeafOS Alpha Coding Tasks

Scope: LeafOS 0.2 through 0.9

## Product Vision

LeafOS is a nodal runtime planted on a device. From a small installation, it
grows into a local hosting node that runs agentic coding workflows, model
workers, and efficient relays for other nodes.

The long-term hardware goal is adaptive utilization: use up to 99% of available
compute when useful work exists and policy allows it, while preserving thermal,
power, storage, network, and user-responsiveness headroom. The node should be
quiet to operate, efficient to relay, and controllable from a CLI.

The 0.6 through 0.9 work below turns that direction into an installable,
observable, and recoverable system.

## 0.5 Exit Capability

By the end of 0.5, LeafOS should support a supervised coding workflow from
task intake through planning, graph execution, scoped patching, verification,
repair, and reporting.

The system should be able to:

- Accept a coding task through `leafctl` and create a structured plan.
- Generate and validate a dependency-aware agent graph.
- Inspect files, run bounded commands, and enforce completion and safety gates.
- Generate, validate, and optionally apply patches within an allowed file scope.
- Wait for bounded conditions, retry manageable failures, and replay failed nodes.
- Create repair nodes from gate or verification failures.
- Record timings, exit codes, changed files, patch results, and final status.
- Produce reproducible failure bundles for debugging.
- Keep local inference efficient and predictable, with llama.cpp optimization
  maintained as a quiet ongoing priority for startup time, memory use, and
  execution consistency.

This remains an alpha release: complex or ambiguous changes and potentially
destructive commands still require human review.

## 0.2 - CLI Task Pipeline

1. [x] Add/clean command registry for `leafctl`.
2. [x] Normalize `agent-task` slug generation.
3. [x] Add overwrite protection for task and plan files.
4. [x] Enforce task template sections: title, scope, steps.
5. [x] Harden mock provider parsing.
6. [x] Add generated-plan metadata header.
7. [x] Validate plans before writing final files.
8. [x] Add `agent-dry-run` output modes: normal/plain/json.
9. [x] Improve guarded `agent-run --yes` confirmation behavior.
10. [x] Add report path printing after successful run.
11. [x] Add spine test fixtures for happy/failure paths.
12. [x] Add doctor checks for required shell tools.
13. [x] Add PowerShell forwarding fallback parity checks.

## 0.3 - Brain Model + Agent Graph

0.3 turns a task into a bounded, inspectable graph. The Brain proposes the
work; LeafOS validates dependencies, persists node state, and stops cleanly
when a gate, failure, or policy limit is reached.

The first orchestration entry point is `leafctl agent-orchestrate`, which
accepts a README, a skeleton, and one wildcard file before producing a
validated skill plan.

14. Finalize `agent.graph.json` schema.
15. Add graph schema validation command.
16. Wire `graph_validate` into `agent-brain`.
17. Wire `graph_validate` into `agent-loop`.
18. Fix graph cycle detection direction if needed.
19. Add missing dependency detection for graph nodes.
20. Add duplicate node ID rejection.
21. Add unknown dependency rejection.
22. Add node status enum validation.
23. Add completion gate required-command validation.
24. Add forbidden-path enforcement in `agent-gate`.
25. Add graph pretty-printer plain mode.
26. Add `agent-node GRAPH NODE_ID` inspector.
27. Add graph summary JSON output.
28. Add smoke task that runs full brain -> graph -> gate.
29. Add repair-node injection tests.
30. Add deadlock test for unsatisfied dependencies.
31. Add graph version migration checks.
32. Add deterministic graph canonicalization and stable node ordering.
33. Define node input, output, and artifact contracts.
34. Record task hash, provider, model, and generation metadata in each graph.
35. Add deterministic `agent-graph --json` output for automation.
36. Add explicit ready, running, blocked, failed, and completed transitions.
37. Add graph iteration, node timeout, and total runtime limits.
38. Add graph resume from persisted node statuses.
39. Add graph import, export, and fixture round-trip tests.
40. Add a human approval pause for high-risk or ambiguous nodes.

## 0.4 - Embedded Actions + Coder Patch Loop

41. Define embedded action schema for graph nodes.
42. Implement `agent.ask_brain` action stub.
43. Implement `agent.ask_coder` action stub.
44. Implement `fs.inspect` action.
45. Implement `fs.require_file` action.
46. Implement `patch.validate` with real `git apply --check`.
47. Implement `patch.apply` with apply/no-apply modes.
48. Make failed patch validation return nonzero reliably.
49. Add allowed-files scope validation for patches.
50. Extract model output patch from raw response file.
51. Add `LEAFOS_NO_PATCH` handling.
52. Implement `wait.file`.
53. Implement `wait.command_success`.
54. Add soft-wait spinner/status cycle.
55. Add action result JSON artifacts per node.
56. Add tests for action dispatcher failure handling.

## 0.5 - Telemetry + Repair Nodes

57. Add run telemetry JSONL file.
58. Log node start/end timestamps.
59. Log command exit codes and durations.
60. Track changed files per patch.
61. Track changed line ranges per patch.
62. Add node replay command for failed nodes.
63. Add rollback metadata for applied patches.
64. Add repair attempt counter/limit.
65. Feed gate failures into repair-node creation.
66. Add final run summary JSON.
67. Add telemetry export fixture test.
68. Add failure reproduction bundle command.

## 0.6 - Project Templates + Hosting Foundation

69. Add a project template registry for hello-C, hello-shell, and hello-Python.
70. Generate README, test, and documentation gates from each template.
71. Add template validation and version compatibility checks.
72. Define a local runtime adapter interface for llama.cpp and compatible backends.
73. Add llama.cpp startup, memory, throughput, and context-size benchmarks.
74. Add model warm-up and reuse to reduce repeated inference startup cost.
75. Detect CPU, GPU, RAM, storage, thermal, and power capabilities.
76. Add an adaptive resource policy with a configurable high-utilization ceiling.
77. Keep headroom for the operating system, thermal limits, battery state, and CLI responsiveness.
78. Add a persistent node identity and local capability manifest.
79. Add `leafctl node plant`, `leafctl node status`, and `leafctl node stop`.
80. Add a supervised local hosting daemon with clean start, stop, and restart behavior.

## 0.7 - Nodal Deployment + Efficient Relays

81. Define the node manifest and capability advertisement schema.
82. Add bootstrap installation for planting a node on a new device.
83. Add explicit node pairing with encrypted identity exchange.
84. Implement compact relay frames for tasks, graph state, patches, and reports.
85. Add authenticated node-to-node transport with reconnect handling.
86. Add relay routing tables based on reachability and declared capability.
87. Add bounded store-and-forward queues for disconnected nodes.
88. Add backpressure and priority handling for coding work, telemetry, and relays.
89. Add node heartbeats, health checks, and stale-node expiration.
90. Add relay deduplication and idempotency keys.
91. Add distributed agent lanes for brain, coder, reviewer, and repair work.
92. Add cross-node graph scheduling with explicit placement decisions.

## 0.8 - Continual Hosting + Dataset Export

93. Define a stable event schema for tasks, nodes, actions, patches, and relays.
94. Export run traces, graphs, patches, reports, and resource samples as datasets.
95. Add redaction and allowlist controls before telemetry or dataset export.
96. Add replay fixtures for successful runs, repair loops, and relay failures.
97. Version exported datasets with provenance and model/runtime metadata.
98. Add evaluation metrics for patch quality, repair success, latency, and token use.
99. Add a continual job scheduler for hosting, inference, relay, and maintenance work.
100. Add model cache management and warm-worker pools.
101. Add workload priorities so interactive CLI work can preempt background hosting.
102. Add resource, relay, and workload summaries to `leafctl node status`.

## 0.9 - Stable Local Agentic Project Builder

103. Add one bounded command for end-to-end local project generation.
104. Select the best eligible node for each graph task by capability and policy.
105. Add explicit CLI handoff between local and remote nodes.
106. Add durable checkpoints and resume after process, device, or network failure.
107. Add unattended execution mode with limits, approvals, and timeouts.
108. Add policy enforcement for filesystem, shell, network, and model actions.
109. Add automatic diagnostics and repair for unhealthy node services.
110. Add safe upgrade, downgrade, and rollback for node runtime components.
111. Add compatibility tests across supported CPU, GPU, memory, and operating-system profiles.
112. Add sustained high-utilization hosting tests with thermal and responsiveness checks.
113. Add relay efficiency tests for throughput, latency, queue growth, and recovery.
114. Add the 0.9 acceptance run: plant a node, host it, relay a task, complete a coding workflow, recover a failure, and export the audit trail.
