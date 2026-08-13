# WO-000: Getting Started, Skeletoning, and First Boot

Status: active  
Project: Project New Leaf / LeafOS  
Layer: open-source CLI-based agentic coding  
Owner: local operator  
Created: 2026-06-20  

## Purpose

This work order establishes the starting skeleton for Project New Leaf: a small, inspectable CLI framework for agentic coding. The point is not to create a mystical coding oracle. The point is to create boring local machinery that can accept a task, route it to a helper or core model profile, create an auditable plan, dry-run that plan, validate it, execute only with confirmation, and leave logs behind like a civilized tool instead of a raccoon with a GitHub token.

## First Message

```text
hello and welcome to project new leaf
```

This is the first-run greeting. It should stay plain, stable, and script-testable.

## Starting Principle

Project New Leaf is a CLI-first coding assistant shell. It should prefer:

- shell commands over GUI operations
- explicit files over hidden state
- dry-runs over surprise execution
- small helpers for regular tasks
- core clone routing for hard tasks
- logs, reports, and work orders for every meaningful change

## Initial Skeleton

```text
leafos_taskpack/
├── bin/                  # CLI entrypoints and helper launchers
├── config/               # branding, loaders, agents, model profiles
├── core/                 # reusable shell/C modules
│   ├── agent/            # task, plan, dry-run, validation, execution helpers
│   ├── brand/            # console branding helpers
│   ├── loaders/          # universal loading animations
│   ├── log/              # session/event logging
│   ├── model/            # model routing and run cards
│   ├── system/           # shared paths and system helpers
│   └── workorder/        # work order helpers
├── docs/                 # architecture notes and project logs
│   └── work_orders/      # auditable work orders
├── examples/             # example tasks and plans
├── logs/                 # JSONL and text logs
├── reports/              # generated reports and run cards
├── share/                # templates and MOTDs
├── tasks/                # task files and generated plans
└── tests/                # smoke tests
```

## Initial CLI Commands

```bash
./bin/leafctl welcome
./bin/leafctl doctor
./bin/leafctl status
./bin/leafctl models
./bin/leafctl agents
./bin/leafctl wo-list
./bin/leafctl wo-show WO-000
./bin/leafctl wo-start
./tests/smoke.sh
```

## Model Routing Contract

Regular tasks should route to small helper workers:

```text
mode=small-helper
profile=primary-helper
```

Hard tasks should route to the core model in 1:1 clone mode:

```text
mode=clone-1to1
profile=core-qwen-opus-reasoning
```

The actual GGUF names are user-supplied configuration values, not sacred scripture. The CLI should treat them as labels until a real local model runner is wired in.

## Skeletoning Tasks

These are the first important tasks for a clean starting pass:

1. Confirm the root project layout exists.
2. Confirm `leafctl` can run.
3. Confirm the welcome message is stable.
4. Confirm model profiles list correctly.
5. Confirm agent profiles list correctly.
6. Confirm work order directory exists.
7. Confirm WO-000 can be printed from CLI.
8. Confirm logs directory exists.
9. Confirm reports directory exists.
10. Confirm task directory exists.
11. Confirm templates directory exists.
12. Confirm smoke test passes.
13. Create first session log entry.
14. Create first skeleton report.
15. Update project log with this starting milestone.

## Acceptance Criteria

This work order is complete when:

```bash
./bin/leafctl doctor
./bin/leafctl welcome
./bin/leafctl wo-list
./bin/leafctl wo-show WO-000
./bin/leafctl wo-start
./tests/smoke.sh
```

all run without failure.

Expected welcome output:

```text
hello and welcome to project new leaf
```

Expected smoke result:

```text
smoke tests passed
```

## Guardrails

The skeleton must not require remote APIs, cloud credentials, sudo, package installation, or model downloads. Those belong in later work orders. WO-000 is the local starting frame.

Forbidden in this work order:

- automatic destructive file deletion
- `sudo`
- `curl | sh`
- hidden background services
- network-dependent tests
- untracked mutation of user files outside the project root

## Deliverables

- `docs/work-orders/WO-000_GETTING_STARTED.md`
- `core/workorder/workorder.sh`
- `share/templates/work_order.md.tpl`
- `leafctl wo-list`
- `leafctl wo-show WO-000`
- `leafctl wo-start`
- `reports/wo-000-skeleton.txt`
- updated smoke test
- updated project log

## Next Work Orders

- WO-001: CLI Command Registry
- WO-002: Agent Task Lifecycle
- WO-003: Model Runner Adapter Stub
- WO-004: Safe Plan Validator Expansion
- WO-005: Work Order Status Tracker
- WO-006: Git Diff and PR Prep Layer
- WO-007: Local Model Invocation Contract
- WO-008: Hardware Routing Mock
- WO-009: Release Bundle Generator
- WO-010: Contributor Onboarding Pass

## Operator Note

Start small. Make the skeleton boring. Then make the boring skeleton reliable. Then, and only then, allow the agentic coding layer to touch real code without treating your filesystem like a sacrificial altar.
