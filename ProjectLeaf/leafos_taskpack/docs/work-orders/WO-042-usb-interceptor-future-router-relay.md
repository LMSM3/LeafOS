# WO-042 - USB 3.0 Interceptor And Future Router Relay

Status: active; USB phase implemented, LAN phase future
Machine-readable authority: `WO-042-usb-interceptor-future-router-relay.json`

## Identity

[W] WO-042: Consolidated two-way transport from USB 3.0 interceptor to future home router
[D] Post-WO-041 late-stage usage: remote observation and typed live-stack updates need one transport contract
[I] ACTIVE (USB phase implemented; LAN phase remains future)
[V] PASS (fixture and contract evidence; physical USB not attached in this run)
[P] LOCAL
[N] Validate against the assigned USB mount, then design the disabled-by-default LAN adapter

## Interpretation

“UBS 3.0” is recorded as USB 3.0. The interim device is an interceptor and
file-backed relay, not a transparent packet router. A USB storage device can
carry durable messages between trusted devices; it cannot itself route LAN
packets unless it is part of a separate network adapter or router appliance.

The future router phase promotes the same message contract onto a private LAN
transport. It must not create a second LeafOS scheduler, queue, journal,
checkpoint, or execution authority.

## Objective

Create one two-way transport contract for updating and observing the LeafOS
live stack from another trusted home device. Phase one uses an explicitly
assigned USB 3.0 medium as a removable interceptor/spool. Phase two can use a
real router or LAN access point as the network path while preserving the same
validated message envelopes, cursors, acknowledgements, and audit records.

## Consolidated System Boundary

```text
device UI or shell
        |
        v
USB interceptor/spool  --->  future authenticated LAN/router relay
        |
        v
typed transport envelope
        |
        v
LeafOS loop inlet  --->  resident queue/executor/validator/checkpoint/report
        |
        v
events + monitor snapshots + reports
```

The interceptor terminates and validates messages. It does not forward raw
shell text, mutate `queue.json` directly, restart providers, or bypass
approval and work-order policy.

## Phase One - USB 3.0 Interceptor (implemented)

- Assign one explicit USB root and record its stable identity or operator-selected path.
- Use separate `inbox`, `outbox`, `processing`, `complete`, `rejected`, and `quarantine` directories.
- Use atomic temporary-file-to-ready-file publication so partially copied messages are ignored.
- Define a versioned JSON envelope with direction, message ID, sequence, sender, target run, payload type, payload hash, created time, and expiry.
- Accept only typed requests such as monitor snapshot, task submission, pause, resume, drain, stop, approval, and report retrieval.
- Validate schema, path policy, approval policy, replay/deduplication, hash, and target run before the local inlet sees a request.
- Emit acknowledgements and rejection reasons back to the USB outbox without exposing secrets or private model reasoning.
- Make interruption and safe removal resumable; duplicate or out-of-order messages must not create duplicate tasks.

Implementation is in `core/python/leaf_usb_interceptor.py` and is exposed through
`leafctl transport usb ...` in both Bash and PowerShell. It uses atomic JSON
publication, a persisted interceptor cursor, operator-selected device identity,
replay detection, typed payload checks, and the existing `leaf_loop_inlet`
mutation/observation functions.

## Phase Two - Future Router / LAN Relay

- Keep the LeafOS host on a reserved private-LAN address.
- Bind the relay to the trusted LAN interface only; do not expose it through WAN port forwarding or UPnP.
- Use authenticated and encrypted transport, preferably SSH or mutually authenticated HTTPS.
- Keep device identity separate from router identity; the router supplies connectivity, not authorization.
- Preserve the same envelope, schema, sequence, acknowledgement, and audit semantics as the USB phase.
- Expose read-only monitoring broadly only within the trusted policy; keep mutation commands approval-gated and narrowly named.

## Acceptance Criteria

- [x] PASS: The USB phase moves valid monitor and task requests from `inbox` to the existing loop inlet exactly once.
- [x] PASS: Monitor snapshots, structured report results, acknowledgements, and rejection reasons return through `outbox`.
- [x] PASS: Partial copies, invalid hashes, malformed envelopes, expired messages, replayed IDs, stale sequences, and invalid typed actions are rejected without queue mutation; malformed or hash-invalid files are quarantined.
- [x] PASS: Restart recovery moves `processing` files back to `inbox`; accepted task replay is deduplicated by request ID/message ID.
- [x] PASS: The existing `loop monitor`, TUI, queue, journal, checkpoint, report, and resident supervisor remain the only current authorities.
- [x] PASS: The current implementation calls only the existing inlet APIs; no second queue, journal, checkpoint, or executor is created.
- [ ] FUTURE: A transport-independent contract test will prove USB and future LAN adapters produce equivalent inlet inputs and audit evidence.
- [ ] FUTURE: A LAN/router prototype is disabled by default and has no WAN exposure, arbitrary shell route, or direct provider-control route.
- [x] PASS: The live stack remains resumable and historical run evidence is never rewritten by transport delivery.

## Real Dated Run Snippets

Recorded from fresh local fixture and regression runs on 2026-07-24 in
`C:\R\LeafOS0.2.2\ProjectLeaf\leafos_taskpack`:

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
```

These are real local fixture/contract runs. They do not constitute physical
USB hardware acceptance or LAN/router validation.

## Safety And Privacy Boundary

- Do not use transparent packet interception or traffic decryption as the phase-one design.
- Do not enable USB autorun or execute files from the removable medium.
- Treat the USB device as untrusted input until its envelope, hash, schema, and policy checks pass.
- Do not store credentials, private keys, model weights, or private chain-of-thought on the transport medium.
- Do not allow a browser or USB message to execute arbitrary PowerShell, Bash, Python, or provider commands.

## Related Work

- WO-041: `loop monitor` provides the canonical observation projection.
- WO-040: version hopping remains deferred and is not a prerequisite for this relay.
- `docs/LAN_ACCESS.md`: existing SSH-based optional LAN subsystem and its boundary against resident project control.
- `docs/NETWORKING.md`: authenticated loopback control bridge and network restrictions.

## Out Of Scope

- Replacing the home router firmware.
- Treating a USB storage device as an Ethernet router without a separate network adapter or appliance.
- WAN access, cloud relay, port forwarding, UPnP, or public exposure.
- A second scheduler, queue, journal, checkpoint, TUI, or report authority.
- Model downloads, model-weight movement, or runtime promotion.

## Carry-Forward

Phase one is implemented against fixtures. Next, inventory the physical USB
device and choose its stable mount/path contract, then perform a supervised
real-device acceptance pass. Only after that should a disabled-by-default,
private-LAN adapter be designed.
