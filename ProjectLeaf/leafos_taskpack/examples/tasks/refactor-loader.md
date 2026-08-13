# Example Agent Task: Refactor Loader System

## Goal

Move all loading animations behind one stable function call and add a validation command that lists every available loader.

## Constraints

- Keep compatibility with `leafctl loader NAME LABEL`.
- Do not add dependencies.
- Add or update smoke tests.

## Acceptance

```bash
./bin/leafctl loaders
./bin/leafctl loader pulse testing
./tests/smoke.sh
```
