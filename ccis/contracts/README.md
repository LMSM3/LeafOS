# CCIS contracts

These JSON Schema draft 2020-12 documents are the Day 0 interface authority
for the Scientific Change Loop inside LeafOS.

Contract invariants:

1. A task declares invariants, tolerances, stopping conditions, scope, budget,
   validators, and authority before candidate generation.
2. Candidates remain isolated and report `working_tree_applied: false`.
3. Every evaluation enters `GATED` and records exactly four constitutional
   question IDs, immutable references, and exact source wording. The runtime
   gate rejects mismatched ID/reference/text combinations.
4. Decisions use only `ACCEPTED`, `REVISE`, `REJECTED`, `BLOCKED`, or
   `ESCALATED`. An accepted decision requires explicit staging and still does
   not merge into the working tree.
5. `events.jsonl` is authoritative. Event hashes chain records; any later
   SQLite projection is disposable cache state.
6. Transitions bind before/after state hashes, checkpoints, evidence, and
   hash-verified rollback information.
7. Accepted-transition evidence includes all 18 artifacts named by the
   canonical specification, including the candidate selection record, diff,
   command/log records, validator results, review, decision, and result.

`examples/` is a contract fixture. Executable proof lives in
`ccis/tests/test_milestone1.py` and exercises a real isolated Git repository.
