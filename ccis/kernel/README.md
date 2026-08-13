# CCIS kernel boundary

Implemented Milestone 1 modules:

- `transition_gate.py` — enforces legal state transitions and `GATED` admission.
- `evidence_gate.py` — requires complete, hash-valid evidence bundles.
- `revision_policy.py` — bounds candidates and revisions using the task budget.
- `acceptance_policy.py` — permits explicit index staging only and never
  changes working-tree content automatically.
- `storage.py` — owns hash-chained append-only events, atomic projections,
  checkpoint recovery, repository hashes, and cross-platform run locking.
- `task_registry.py` — validates strict typed tasks/results, binds canonical
  task and registry digests, and resolves only inspectable native handlers.
- `allocation_events.py` — owns the independent hash-chained allocation
  journal; malformed or tampered authoritative events halt replay.
- `allocation_reducer.py` — pure state transition logic for tasks,
  dependencies, logical time, leases, and resource claims.
- `allocation_heap.py` — rebuilds deterministic ready/delayed heaps and a
  disposable, digest-bound snapshot from the journal.
- `allocation_lease.py` — serializes admission, queueing, claims, execution
  outcomes, explicit clock observations, and lease expiry events.

The kernel remains principle-text agnostic: it consumes exactly four configured
question references but cannot supply their constitutional meaning.

Allocation authority is deliberately asymmetric:

```text
allocation-events.jsonl  authoritative, append-only, hash-chained
allocation-snapshot.json disposable projection; rebuilt on corruption
tasks/*.json              inspectable task cache; never journal authority
results/*.json            typed execution results and evidence references
```

Eligibility, aging, and expiry change only through recorded events. Reading a
snapshot never advances the logical clock. The current bridge keeps the
original CCIS validator callable while `run_ccis_validator_task()` can route
that same validator through typed admission and exclusive workspace claims.
