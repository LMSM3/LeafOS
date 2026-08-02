# LeafOS Task Pack

A small implementation batch for the FlowerOS/LeafOS terminal system, now converging into **Project New Leaf**: an open-source, CLI-first agentic coding skeleton.

## First boot

```bash
./bin/leafctl welcome
./bin/leafctl doctor
./bin/leafctl wo-list
./bin/leafctl wo-show WO-000
./bin/leafctl wo-start
./tests/smoke.sh
```

Expected greeting:

```text
hello and welcome to project new leaf
```

## Try it

```bash
./bin/leafctl status
./bin/leafctl loaders
./bin/leafctl loader orbit "routing"
./bin/leafctl motd
```

## Work orders

Project New Leaf now has an initial work-order layer:

```bash
./bin/leafctl wo-list
./bin/leafctl wo-show WO-000
./bin/leafctl wo-new "add command registry"
./bin/leafctl wo-start
```

`WO-000` defines the initial skeleton, acceptance checks, guardrails, and the next work orders. Because apparently writing down scope before coding prevents the traditional ritual of detonating the project and calling it refactoring.

## Build C loader demo

```bash
./bin/build_c_demo.sh
./build/leaf_loader_demo
```

## Agentic CLI layer

LeafOS includes a small open-source oriented agentic coding layer:

```bash
./bin/leafctl agents
./bin/leafctl agent-task "add config validator"
./bin/leafctl agent-plan tasks/add-config-validator.md default
./bin/leafctl agent-dry-run tasks/add-config-validator.default.plan.sh
./bin/leafctl agent-run tasks/add-config-validator.default.plan.sh --yes
./bin/leafctl agent-report demo
```

The workflow is intentionally boring: write a task file, generate a shell plan, dry-run it, validate it, then execute only with explicit confirmation. Revolutionary, if your industry has been drinking glue.

## Project New Leaf model routing

The pack includes model-routing config for helper workers and hard-task clone mode:

```bash
./bin/leafctl models
./bin/leafctl model-route regular
./bin/leafctl model-route hard
./bin/leafctl model-card hard demo-hard-task
```

Regular tasks route to small helper coders. Hard tasks route to the core reasoning profile in `clone-1to1` mode. The model names are configuration labels until a real local runner adapter is wired in.
