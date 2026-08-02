# WO-033: Verify Native LeafOS TUI

Machine-readable authority: `WO-033-native-tui.json`

## Objective

Verify the compiled `ncursesw` renderer, bounded snapshot parser, live bridge, navigation, and fail-closed control boundary against the canonical LeafOS task pack.

## Boundary

The C process renders normalized state and emits named operator requests. Python refreshes snapshots and forwards allowlisted requests. `leaf_loop_inlet.py` remains authoritative for every state-changing operation.

## Acceptance

- Native compilation completes without warnings.
- Malformed snapshots fail closed.
- Native and Python fallback tests pass.
- `q` exits without changing the run or provider.
- Pause, approval, and stop cannot bypass the inlet bridge.
