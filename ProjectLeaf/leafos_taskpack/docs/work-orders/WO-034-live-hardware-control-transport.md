# WO-034: Live Hardware and Native Control Transport

Machine-readable authority: `WO-034-live-hardware-control-transport.json`

## Objective

Keep hardware utilization visibly current while the LeafOS TUI is open, and replace the native temporary control mailbox with a bounded authenticated local transport.

## Boundary

The sampler is observational: it overlays a presentation snapshot and never appends run events or changes checkpoints. The native C process emits only named requests. Python authenticates and validates each request before forwarding it to `leaf_loop_inlet.py`, which remains the sole state-changing authority.

## Acceptance

- Python and native Hardware pages label live samples and display sample age.
- Fast sampling collects CPU, RAM, GPU, VRAM, temperature, and power without invoking the disk probe.
- Native controls use an ephemeral `127.0.0.1` socket with a 256-bit per-session token.
- Messages over 2 KiB, malformed JSON, invalid tokens, and unlisted actions fail closed.
- The snapshot reports control transport, authentication, and connection health.
- The C build, focused tests, full suite, and live native navigation pass.
