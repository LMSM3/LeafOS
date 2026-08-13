# WO-040 To WO-042 Consolidated Status

This document consolidates the recent release-control, loop-monitor, and
transport work orders. The individual WO files and their JSON records remain
the detailed authorities; this page is the current handoff view.

## Status

[W] WO-040 to WO-042: release navigation, hands-off monitoring, and USB-to-LAN transport boundary
[D] 2026-07-24: monitor complete; USB transport phase complete; version hopping deferred
[I] PARTIAL: WO-041 DONE; WO-042 USB phase DONE; WO-040 DEFERRED; WO-042 LAN phase FUTURE
[V] PASS: fresh dated local tests and read-only monitor check recorded below
[P] LOCAL: no commit or remote handoff recorded
[N] Perform supervised acceptance on the assigned USB mount before designing the private-LAN adapter

## Consolidation Map

| Work order | Scope | Marking | Current truth |
|---|---|---|---|
| WO-040 | Version hopping | DEFERRED | No implementation or test run claimed after the 2026-07-22 operator deferment. |
| WO-041 | Interactive/non-interactive loop monitor | DONE | One read-only Python monitor authority, Bash/PowerShell parity, cursor support, heartbeat/stale reporting. |
| WO-042 USB phase | File-backed USB 3.0 interceptor | DONE | Typed envelope, spool state machine, acknowledgements, rejection, replay protection, and restart recovery. |
| WO-042 LAN phase | Future router/private-LAN relay | FUTURE | No LAN listener, WAN exposure, router firmware change, or second authority exists. |

## Completion Marking Key

- `[x] PASS` means the scoped criterion has fresh or recorded verification.
- `[ ] FUTURE` means intentionally not complete and carried forward.
- `DEFERRED` means the operator paused the WO; it is not a failed implementation.
- `DONE` applies only to the completed WO-041 monitor and WO-042 USB phase, not to the full future LAN relay.

## Dependency And Authority Boundary

```text
WO-040 version hopping (deferred)
              |
              v
WO-041 loop monitor (canonical read-only observation)
              |
              v
WO-042 USB interceptor (typed transport projection)
              |
              v
existing loop inlet -> queue / journal / checkpoint / executor / report
              |
              v
future authenticated private-LAN adapter (disabled, not implemented)
```

WO-042 reuses the WO-041 monitor projection and the existing typed loop inlet.
Neither work order creates a second scheduler, queue, journal, checkpoint,
provider controller, or report authority.

## Real Dated Run Snippets

All snippets below are from fresh local runs on 2026-07-24 in
`C:\R\LeafOS0.2.2\ProjectLeaf\leafos_taskpack`. `python -B` was used for the
test commands so the evidence describes execution rather than bytecode cache
generation.

```text
> python -B tests/test_transport_envelope.py
Ran 5 tests in 0.020s
OK

> python -B tests/test_usb_interceptor.py
Ran 8 tests in 0.534s
OK

> python -B tests/test_loop_inlet.py
Ran 14 tests in 3.677s
OK

> python -B tests/test_leafctl_dispatch.py
Ran 8 tests in 40.374s
OK

> python -B tests/test_work_order_loop.py
Ran 10 tests in 12.859s
OK

> PYTHONPATH=. python -B tests/test_live_project.py
Ran 19 tests in 5.794s
OK

> python -B tests/test_model_profiles.py
Ran 4 tests in 0.015s
OK
```

Shell parity and live read-only observation were also exercised on 2026-07-24:

```text
> bash ./bin/leafctl loop monitor --help
usage: leaf_loop_inlet.py monitor [-h] [--after AFTER] [--interval INTERVAL]

> pwsh -NoProfile -File .\bin\leafctl.ps1 loop monitor --help
usage: leaf_loop_inlet.py monitor [-h] [--after AFTER] [--interval INTERVAL]

> bash ./bin/leafctl loop monitor active --json --once
state: blocked; event_cursor: 39; heartbeat.reason: no_worker_lease
exit code: 2
```

The blocked snapshot is evidence about the pre-existing active run and is the
documented monitor result, not a failed test. No physical USB device was
attached for these runs.

## Carry-Forward

1. Inventory and mount the assigned USB device using a stable operator-selected identity.
2. Repeat the USB acceptance suite against the real mounted spool without autorun or credentials.
3. Design a disabled-by-default authenticated private-LAN adapter with no WAN, UPnP, arbitrary-shell, or second-authority path.
4. Reactivate WO-040 only when version hopping is explicitly requested again.

## Source Records

- `WO-040-version-hopping.md` and `.json`
- `WO-041-loop-monitor.md` and `.json`
- `WO-042-usb-interceptor-future-router-relay.md` and `.json`
- `reports/work-orders/WO-041-COMPLETION-REPORT.md`
- `reports/work-orders/WO-042-USB-PHASE1-REPORT.md`
