# WO-006 — Dashboard Interaction and Usability

## Identity

- Owner/context: LeafOS0.2.1 reusable-tool branch
- Current day: Day 1
- Release target: reusable-tool dashboard increment
- Branch: local workspace
- Scope boundary: `core/ui/dashboard.py`, dashboard documentation, focused tests

## Acceptance criteria

- [x] The dashboard identifies the highest-priority local condition.
- [x] The dashboard presents one actionable next command.
- [x] JSON output exposes the same interaction summary.
- [x] Dashboard rendering remains read-only and local-state-only.
- [x] Focused tests cover empty, active, and failed queue states.

## Status

[W] WO-006: Dashboard interaction and usability
[D] Day 2: revisit and closeout
[I] DONE
[V] PASS: focused dashboard attention + render-path + layout tests (8/8)
[P] LOCAL
[N] None -- WO closed

## Evidence log

- 2026-07-16: Confirmed `core/ui/dashboard.py` and `docs/DASHBOARD_GUIDE.md` are the canonical interaction surface under DEC-009.
- 2026-07-16: Confirmed imported plans under the operator's Copilot plan directory are reference imports, not runtime source.
- 2026-07-16: Added read-only attention and next-action summary to terminal and JSON dashboard output; `python3 -m unittest tests/test_dashboard_attention.py` passed 3/3.
- 2026-07-17: Revisit -- added `DashboardRenderPathTests` exercising `render_dashboard`/`render_json` directly against temp-dir fixtures for empty/active/failed queue states, with before/after filesystem snapshots asserting no mutation (satisfies read-only criterion). Discovered and fixed a real bug in `core/ui/dashboard.py`: the `C` color palette dict was only populated inside `main()`, so calling `render_dashboard` outside the CLI entry point raised `KeyError: 'green_b'`; `render_dashboard` now lazily initializes `C` via `_init_colors` if unset. `python -m unittest tests/test_dashboard_attention.py` now passes 7/7.
- 2026-07-17: Added width-80 layout regression coverage for long node, role, and registry values. Patched dashboard row/header fitting to clip by visible width without splitting ANSI escape sequences. `python -m unittest tests/test_dashboard_attention.py` now passes 8/8.

## Carry-forward

- Keep WO-006 scoped to read-only dashboard interaction improvements.
- Continue using the WO naming scheme for official planning until replaced.

## Out of scope

- Model routing or local inference changes.
- Network transport, remote node scheduling, or web UI.
- Model downloads and installation behavior.
- Catan one-shot stack integration.
