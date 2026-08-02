# LeafOS Agentic CLI Direction

LeafOS is converging toward an open-source CLI-based agentic coding system.

The point is not to hide work behind a glowing assistant button. The point is to make agent work boring, inspectable, replayable, and safe enough that a human can understand what happened without sacrificing a goat to a SaaS dashboard.

## Core model

```text
user request
  -> task file
  -> command plan
  -> dry-run
  -> validation
  -> guarded execution
  -> report
  -> git diff / PR
```

## Rules

1. Every agent task must become a text file.
2. Every executable action must appear in a shell plan.
3. Every shell plan must support dry-run.
4. Destructive commands are rejected by default.
5. Reports are local files, not vibes.
6. The CLI should work offline when possible.
7. BYOK/API support can be added later, but the local workflow comes first.

## New commands

```bash
./bin/leafctl agents
./bin/leafctl agent-task "add config validator"
./bin/leafctl agent-plan tasks/add-config-validator.md default
./bin/leafctl agent-dry-run tasks/add-config-validator.default.plan.sh
./bin/leafctl agent-run tasks/add-config-validator.default.plan.sh --yes
./bin/leafctl agent-report demo
```

## Intended open-source shape

LeafOS should eventually expose:

- provider adapters for OpenAI, Anthropic, DeepSeek, local llama.cpp, and mock/offline modes
- a task planner
- a command-plan validator
- a patch applier
- a reviewer agent
- a shell guardian
- a PR generator
- a replay bundle generator

The boring shell layer comes first. Otherwise the project becomes another shiny agent framework that can summarize your repo while quietly knowing nothing about how to fix it.
