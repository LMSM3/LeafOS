# Scientific Change Loop integration boundary

`scientific_change_loop.py` is the nested-loop coordinator that consumes CCIS
contracts. It treats `.leafos/ccis/**/events.jsonl` as authoritative, rebuilds
disposable state/checkpoints from events, and stops at `ACCEPTED` until an
explicit `leafos task accept` command stages a candidate.
