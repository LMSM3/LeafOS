# LeafOS Task Pack

A small implementation batch for the FlowerOS/LeafOS terminal system.

## Try it

```bash
./bin/leafctl doctor
./bin/leafctl status
./bin/leafctl loaders
./bin/leafctl loader orbit "routing"
./tests/smoke.sh
```

## Build C loader demo

```bash
./bin/build_c_demo.sh
./build/leaf_loader_demo
```


## Agentic CLI layer

LeafOS now includes a small open-source oriented agentic coding layer:

```bash
./bin/leafctl agents
./bin/leafctl agent-task "add config validator"
./bin/leafctl agent-plan tasks/add-config-validator.md default
./bin/leafctl agent-dry-run tasks/add-config-validator.default.plan.sh
./bin/leafctl agent-run tasks/add-config-validator.default.plan.sh --yes
./bin/leafctl agent-report demo
```

The workflow is intentionally boring: write a task file, generate a shell plan, dry-run it, validate it, then execute only with explicit confirmation.
