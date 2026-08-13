# USB 3.0 Interceptor Usage

WO-042 phase one provides a durable, file-backed transport for a trusted
operator device. The USB medium is an inbox/outbox spool; it is not a packet
router and it never becomes a second LeafOS queue or executor.

## Initialize a device root

Choose a stable mount path and an operator-selected identity. Do not use an
autorun file or place credentials on the device.

```powershell
.\bin\leafctl.ps1 transport usb init E:\LeafOS-Transport --identity usb-interceptor-01 --json
```

```bash
./bin/leafctl transport usb init /media/leafos-transport --identity usb-interceptor-01 --json
```

The root contains `inbox`, `processing`, `complete`, `rejected`,
`quarantine`, `outbox`, and `state`. Only complete `.json` files in `inbox`
are eligible for delivery; `.tmp` files are ignored.

## Publish a typed request

Payloads are JSON objects. The interceptor constructs the envelope and hashes
the canonical payload before atomically publishing it.

```bash
./bin/leafctl transport usb publish /media/leafos-transport \
  --payload monitor.json \
  --type monitor.snapshot \
  --target-run active \
  --sender home-device-01 \
  --json
```

Supported inbound types are `monitor.snapshot`, `report.get`, `task.submit`,
`task.approve`, `run.pause`, `run.resume`, `run.drain`, and `run.stop`.
Mutation requests remain subject to the existing typed inlet, work-order,
approval, path, and validation policy.

## Pump and inspect

Run one delivery pass or keep the interceptor attached to the USB root:

```bash
./bin/leafctl transport usb pump /media/leafos-transport --once --json
./bin/leafctl transport usb pump /media/leafos-transport --interval 1 --json
./bin/leafctl transport usb status /media/leafos-transport --json
```

PowerShell uses the same subcommands:

```powershell
.\bin\leafctl.ps1 transport usb pump E:\LeafOS-Transport --once --json
```

Accepted and duplicate deliveries are acknowledged in `outbox`. Invalid,
expired, hash-mismatched, replayed, or out-of-order messages are rejected;
malformed files are moved to `quarantine`. Removing the device between pump
passes is resumable because publication is atomic and `processing` is
recovered on the next pump.

## Boundary

The transport accepts typed JSON only. It does not execute arbitrary shell,
start providers, move model weights, expose WAN services, configure UPnP, or
store credentials/private keys. A future private-LAN/router adapter must use
the same envelope and inlet boundary and remain disabled by default.
