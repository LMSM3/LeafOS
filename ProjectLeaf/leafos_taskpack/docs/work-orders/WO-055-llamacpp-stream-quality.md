# WO-055 — llama-server Streaming Loop Quality Observatory

## Identity

- Owner/context: liamm / local streaming UX and loop observability
- Current day: Day 0 (planned after WO-054)
- Release target: LeafOS 0.2.2 local-model loop quality
- Branch: `agent/organic-0.9.4-snapshot`
- Scope boundary: one owned loopback llama-server, actual LeafOS chat adapter, metrics/evidence, cleanup

## Source

Section 18: launch a real `llama-server` on an ephemeral loopback port and exercise the existing OpenAI-compatible streaming adapter.

## Live-inference intent

This WO performs live streaming inference: an owned `llama-server` loads a real local GGUF, a real prompt enters through the LeafOS chat adapter, CPU/GPU computation generates fresh tokens, and those tokens arrive as observable stream chunks. Mock SSE, prerecorded chunks, fallback text, or a health-only response cannot satisfy acceptance.

## Acceptance criteria

- [ ] `eval.llamacpp.stream.v1` allocates one model/backend claim and one ephemeral loopback-port claim.
- [ ] The handler starts only an owned server, records PID/start identity, and waits on bounded health checks.
- [ ] The actual LeafOS streaming adapter receives non-empty chunks without synthetic fallback.
- [ ] Captured chunks reconstruct newly generated model output and are distinguished from prompt echo, mock transport, and fallback output.
- [ ] Evidence includes startup latency, time to first token, chunk count, inter-chunk gaps, completion status, token counts when reported, and raw protocol logs.
- [ ] Client disconnect, malformed event, server early-exit, and health-timeout cases produce distinct results.
- [ ] Normal completion terminates the owned server, releases the port/resource lease, and retains failure logs.
- [ ] At least three runs establish variance rather than presenting a single sample as quality.

## Status

[W] WO-055: real llama-server streaming quality observatory
[D] Day 0: queued behind WO-054
[I] TODO
[V] DISCOVERY: current chat adapter is mock-tested; real endpoint test remains absent
[P] LOCAL: plan only
[N] After WO-054, add owned-server streaming evaluation on an allocated loopback port

## MOE parallel handoff

- [WO-017/MOE-004–MOE-007](WO-017-small-scale-moe-hardware-orchestration.md) reuse this owned streaming lifecycle for hot-expert service evidence. A hot hit, load, drain, or route may be reported only from the canonical provider/lease events and typed measurements.

## Out of scope

- Reusing an unknown service already bound to port 8080.
- Exposing llama-server beyond loopback or changing firewall state.
