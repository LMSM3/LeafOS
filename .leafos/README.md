# LeafOS local CCIS state layout

Runtime state uses the following local layout:

```text
.leafos/ccis/runs/<task-id>/
  task-envelope.json
  task.json
  objective.json
  events.jsonl                 # authoritative, append-only
  checkpoint.json
  state.json                   # rebuildable projection
  cache.sqlite                 # rebuildable cache only
  candidates/
  validation/
    run.json                  # isolated workspace and before/after hashes
    commands.jsonl            # argv, timing, status, shell=false
    stdout.log
    stderr.log
    validator-results.json
  evidence/<transition-id>/
    task.json
    objective.json
    candidates.json
    roundtable-record.json
    plan.json
    workspace-manifest.json
    before-hash.json
    after-hash.json
    candidate.diff
    commands.jsonl
    stdout.log
    stderr.log
    test-results.json
    lint-results.json
    evaluation.json
    review.json
    decision.json
    result.json
    evidence-bundle.json
```

The bundle manifest hashes all 18 required artifacts. Runtime creation,
locking, event-only resume, index-only staging, tamper refusal, and
hash-verified rejected-candidate rollback are executable Milestone 1 behavior.
Day 1 validator execution runs only in a disjoint workspace, records a
hash-bound `ccis.validation.completed` event, and copies the captured command
stream and logs into the final bundle.
