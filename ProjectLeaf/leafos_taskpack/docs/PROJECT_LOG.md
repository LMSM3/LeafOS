# LeafOS Project Log

This is a chronological implementation ledger. Early entries describe the
finite 0.2 task-plan and mock-provider test era and are intentionally retained
as history. They are not current operator instructions. See
`DOCUMENTATION_MAP.md` and `reports/work-orders/WO-038-COMPLETION-REPORT.md`
for the resident system baseline.

## Completed Small Tasks: Batch 001

1. Added global `config/brand.conf`.
2. Added global `config/loaders.conf`.
3. Added shared path resolver in `core/system/paths.sh`.
4. Added shell branding helper in `core/brand/brand.sh`.
5. Added shell logging helper in `core/log/log.sh`.
6. Added JSONL event logging.
7. Added universal loader framework in `core/loaders/loaders.sh`.
8. Added three primary loading animations: `dots3`, `bar`, `orbit`.
9. Added three extra loading animations: `pulse`, `blade`, `crawl`.
10. Added main CLI frontend `bin/leafctl`.
11. Added old-name compatibility wrapper `bin/flowerctl`.
12. Added `leafctl doctor` layout validation.
13. Added `leafctl motd` startup message.
14. Added `leafctl session-start`.
15. Added `leafctl session-close`.
16. Added `leafctl new-module NAME` generator.
17. Added shell module template.
18. Added C branding library.
19. Added C loader demo.
20. Added smoke test and C build script.


## Completed Small Tasks: Batch 002 — Agentic CLI Convergence

21. Added `config/agents.conf` for CLI agent profile defaults.
22. Added `core/agent/agent.sh` for task, plan, dry-run, validation, execution, and report helpers.
23. Added agent profile listing with planner, local-coder, reviewer, and shell-guardian roles.
24. Added agent task template in `share/templates/agent_task.md.tpl`.
25. Added executable agent plan template in `share/templates/agent_plan.sh.tpl`.
26. Added `leafctl agents`.
27. Added `leafctl agent-task TITLE`.
28. Added `leafctl agent-plan TASK_FILE [PLAN_NAME]`.
29. Added `leafctl agent-validate PLAN_FILE` and `leafctl agent-dry-run PLAN_FILE`.
30. Added guarded `leafctl agent-run PLAN_FILE --yes` plus local `agent-report` output.

## Open-Source Agentic CLI Direction

The project is now moving toward this spine:

```text
request -> task file -> command plan -> dry-run -> validation -> guarded execution -> report -> PR
```

This keeps agentic coding inspectable. The system should not mutate a project through invisible model impulses like a raccoon loose in `/usr/bin`.

## Completed Small Tasks: Batch 003 — Provider Routing Layer

31. Added `config/providers.conf` — provider mode selector, model hints, key env var names.
32. Added `core/providers/providers.sh` — `leaf_provider_route` dispatcher with mock, openai, anthropic, deepseek, and llamacpp adapters.
33. Mock adapter parses task title/scope/steps and generates a filled, validated agent plan with no API key required.
34. API adapters (openai, anthropic, deepseek, llamacpp) stub cleanly — refuse with a clear error when key is missing, ready for keys to be added.
35. Added `agent_plan_generate` to `core/agent/agent.sh` — routes task to provider, writes filled plan, validates immediately, discards on failure.
36. Added `leafctl provider-status` — shows current mode and key state.
37. Added `leafctl agent-route TASK_FILE [--mock|--provider MODE]` — full end-to-end: route → generate → validate → report path.
38. Added `tests/providers.sh` — mock round-trip, validation, overwrite protection, dry-run, and API stub key-refusal checks.
39. Glyph layer wired into provider routing: `leaf.model`, `leaf.flow`, `leaf.verify`, `leaf.alert` emit at each stage.

## Completed Small Tasks: Batch 004 — 0.2.0 Release Spine

40. Fixed `share/templates/agent_task.md.tpl` — added `## Title`, `## Scope`, `## Steps` sections so the mock provider generates real plan content.
41. Added `--mock` and `--provider MODE` flags to `leafctl agent-route`.
42. Reordered `leafctl` help block to match the 0.2.0 spine order.
43. Created `ROADMAP.md` — authoritative 0.2.0 → 1.0.0 version map with spines, commands, success conditions, and the 0.3.0 graph object spec.
44. Created `tests/spine.sh` — 0.2.0 success condition: 6 named stages, full pipe, no model required.
45. Updated `README.md` with 0.2.0 spine quick-start and roadmap pointer.

## Roadmap

See `ROADMAP.md`.

```
0.2.0  CLI skeleton — agent-task → agent-route --mock → dry-run → run → report
0.3.0  Brain model + agent graph loop + completion gate
0.4.0  Coder model + patch loop
0.5.0  Write telemetry + repair nodes
0.6.0  Project templates
0.7.0  Multi-model lanes
0.8.0  Symbolic training dataset export
0.9.0  Stable local agentic project builder
1.0.0  LeafOS base system
```

## Backlog: 100 Ideas

1. Universal loading animations.
2. Loader themes by environment.
3. Boot-time MOTD rotation.
4. Quiet mode for scripts.
5. No-emoji mode.
6. Session start logging.
7. Session close summary.
8. JSONL event log.
9. TSV command log.
10. Human-readable daily log.
11. Command registry file.
12. Plugin discovery.
13. Shell module template generator.
14. C module template generator.
15. Config validation.
16. Config reset command.
17. Config diff command.
18. Health check command.
19. Dependency doctor.
20. Missing PATH repair hint.
21. Git dirty-state warning.
22. Project snapshot command.
23. Backup config command.
24. Restore config command.
25. Local bin installer.
26. Uninstaller.
27. Version printer.
28. Build metadata file.
29. Theme palette config.
30. ANSI color toggle.
31. Plain-text output mode.
32. JSON output mode.
33. Debug verbosity levels.
34. Error code registry.
35. Standard fatal error format.
36. Standard warning format.
37. Standard success format.
38. `please` command bridge.
39. `flenv` environment bridge.
40. Package install stub.
41. Package analyze stub.
42. Package update stub.
43. Package remove stub.
44. Local script indexer.
45. Script lint runner.
46. Shellcheck integration.
47. C compile smoke test.
48. C header audit.
49. Include path checker.
50. Runtime temp directory manager.
51. Cache directory manager.
52. Lockfile helper.
53. PID file helper.
54. Background service stub.
55. Service status command.
56. Service stop command.
57. Service restart command.
58. Startup script generator.
59. Cron/systemd timer examples.
60. Windows PowerShell bridge.
61. WSL path converter.
62. Windows path converter.
63. Log rotation.
64. Log compression.
65. Log redaction filter.
66. API key presence checker.
67. BYOK profile config.
68. Local model profile config.
69. Hardware routing config.
70. Hardware status mock.
71. GPU/NPU inventory command.
72. RAM/VRAM summary command.
73. Disk usage summary.
74. Network reachability check.
75. Offline mode flag.
76. Command replay file.
77. Command dry-run mode.
78. Batch execution manifest.
79. Export report markdown.
80. Export report JSON.
81. Export report TSV.
82. Manifest checksum.
83. File hash helper.
84. Bundle reference scanner.
85. Bundle manifest writer.
86. Work order generator.
87. Work order status tracker.
88. Day marker tracker.
89. Stable version marker.
90. Changelog generator.
91. Release zip script.
92. Self-test summary.
93. Failure reproduction bundle.
94. Minimal TUI status screen.
95. ASCII splash screen.
96. Runtime color palette.
97. Help page generator.
98. Manpage generator.
99. Documentation index.
100. Contributor notes.
