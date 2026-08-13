# WO-017 — Small-Scale MoE Hardware Orchestration

## Identity

- Owner/context: liamm / LeafOS local-model orchestration and full-hardware utilization
- Current day: Day 0 (architecture admitted; handlerless task types reserved; production integration not started)
- Release target: LeafOS 0.2.2 local-hardware orchestration lane
- Branch: `agent/organic-0.9.4-snapshot`
- Tracking position: the previously unused WO-017 slot; implementation runs as a parallel lane across WO-051–WO-061 rather than renumbering that active series
- Depends on: the completed WO-018 GGUF capability reader, WO-051 typed allocation authority, WO-052 evidence integrity, WO-053–WO-056 real-provider lifecycle, and WO-057–WO-059 product/mapping/demonstration gates
- Scope boundary: MoE inventory, placement evidence, typed scheduling extensions, one-GPU lease policy, expert routing, resource governance, evidence/repair integration, read-only UI projection, and overnight proposal generation

## Objective

Integrate the small-scale MoE design into LeafOS without creating a second scheduler, provider authority, evidence store, or acceptance path. The lane should keep one useful GPU expert hot when policy and measured headroom permit, use CPU-side expert and validation work concurrently, escalate from top-1 to top-2 only under explicit predicates and budgets, and preserve interactive control headroom.

“Full hardware utilization” means maximizing useful, bounded work across available CPU, GPU, memory, storage, and provider lanes. It does not mean forcing every utilization counter to 100 percent, oversubscribing VRAM, ignoring thermal or power limits, or starving the operator-facing system.

## Locked architecture

```text
typed work admitted through WO-051
    -> eligibility and hard compatibility gates
    -> top-1 route by default
    -> one GPU-leased hot expert when measured placement fits
    -> CPU expert / validation / evidence lanes in parallel
    -> top-2 only on uncertainty, disagreement, failure, or policy trigger
    -> deterministic validators and WO-052 evidence gates
    -> explicit accept / revise / reject / block / escalate
```

The three operating profiles are:

| Profile | Intent | Required behavior |
|---|---|---|
| `interactive` | Preserve responsive local use | Largest CPU, memory, and GPU headroom; aggressive drain/preemption of background work |
| `balanced` | Default mixed workload | One hot GPU expert, bounded CPU lanes, measured hysteresis, no speculative second load |
| `throughput` | Sustained batch work | Higher concurrency within leases, thermal/power limits, evidence budgets, and explicit stopping conditions |

Only one LeafOS owner may hold an exclusive GPU/model lease at a time unless later measurements prove safe sharing and a separate admitted work order changes the policy. External GPU occupancy is observed state, not a resource LeafOS may evict or silently treat as its own.

## Authority and reuse rules

- `allocation-events.jsonl` and the WO-051 reducer remain allocation truth. MOE work may add registered task types and reducer inputs; it may not create a private queue or authoritative heap.
- WO-018 bounded GGUF metadata is the production capability source. The isolated demo inventory is a testable adapter candidate, not a replacement authority.
- WO-053 preflight decides whether a binary/model/backend combination may enter live execution. A file probe or benchmark plan is not live inference.
- WO-054/WO-055 own proven live CLI/streaming inference paths. `llama-bench` measurements are placement evidence and cannot substitute for those functional inference gates.
- WO-056 owns process-tree cancellation, timeout, cleanup, and lease recovery. The MoE lease manager must use that lifecycle rather than copy the demo runner.
- WO-052 owns evidence integrity. Hard compatibility, identity, safety, and statistical gates cannot be averaged into a passing score.
- WO-057/WO-058 own user-visible states and one-to-one mapping. The MoE TUI is a read-only projection over the same records.
- CCIS and explicit operator acceptance remain authoritative. Routers, experts, overnight analysis, and benchmark reports can propose work but cannot accept or mutate the canonical tree by themselves.

## MOE-001–MOE-010 parallel subtrack

| Subtrack | Deliverable | Integration point | Current state | Completion gate |
|---|---|---|---|---|
| [MOE-001](WO-017-MOE-001-full-identity-gpu-provider-evidence.md) | Inventory and benchmark harness | WO-018, WO-047, WO-053 | PARTIAL | Full model identity plus fixed-prompt CPU, supported GPU backend, and feasible sparse-MoE placement measurements; paired statistical analysis before promotion |
| MOE-002 | Versioned MoE contracts | WO-051, WO-052 | PARTIAL | Work, expert, placement, route, resource, lease, repair, and event fixtures pass schema and failure tests in the production contract tree |
| MOE-003 | Durable scheduler extension | WO-051 | TODO | Compatibility claims, three priority tiers, locality, aging, epochs, lineage, bounds, and deterministic replay pass without a second authority |
| MOE-004 | GPU lease manager | WO-051, WO-056 | TODO | One LeafOS owner; external occupancy, load/hit/drain/failure/sleep/cancel/recovery events are durable and tested |
| MOE-005 | Provider adapters | WO-053–WO-056 | TODO | Explicit load/unload, slots, metrics, timeout, cancellation, health, and real-provider behavior pass |
| MOE-006 | Top-1/top-2 expert router | WO-051, WO-058 | TODO | Eligibility precedes scoring; rationale, escalation predicates, and budgets replay deterministically |
| MOE-007 | Resource governor | WO-051, WO-057 | TODO | Interactive/balanced/throughput headroom, preemption, telemetry provenance, and hysteresis pass |
| MOE-008 | Evidence and repair integration | WO-052, WO-061 | TODO | Hard gates remain non-compensable; repair packets preserve scope/lineage; budget exhaustion stops |
| MOE-009 | Read-only MoE TUI | WO-057, WO-058 | TODO | Seven views, resize/replay/telemetry labels/clean exit, and separate authenticated control path pass |
| MOE-010 | Overnight consolidation lane | WO-059–WO-061 | TODO | Frozen snapshot in; findings/work orders/patch proposals out; live tree unchanged until daytime gates |

PARTIAL is intentional. The isolated MOE-001 slice and its five benchmark-oriented schemas are real, tested artifacts, but they do not satisfy the production contracts, GPU/live-inference runs, full identity, statistical promotion, scheduler, lease, router, or governor gates.

## Reserved typed-task additions

WO-051 reserves these names without binding native handlers until the owning MOE subtrack opens:

```text
bench.moe.inventory.v1
bench.moe.placement.v1
system.moe.contracts.verify.v1
system.moe.scheduler.verify.v1
system.gpu_lease.verify.v1
probe.moe.provider.v1
route.moe.expert.v1
system.resource_governor.verify.v1
debug.moe.evidence_repair.v1
system.moe_surface.verify.v1
analysis.overnight_consolidation.v1
```

Task definitions must use the existing authority, budget, dependency, resource-claim, retry, validator, result, and provenance fields. Model responses cannot select handler names or enlarge authority.

## Demonstration evidence admitted as input

The isolated source workspace is `C:\Users\liamm\OneDrive\Documents\LeafOS`.

- Design source: `docs/design/SMALL_SCALE_MOE_HARDWARE_ORCHESTRATION.tex`
- Demo source: `ProjectLeaf/leaf_moe_benchmark_demo/`
- No-inference evidence: `tmp/moe-001-demo/inventory.json`, `provider.json`, and `plan.json`
- Verification: 13 focused unit tests pass under Python 3.13 and 3.14
- Observed inventory: 9 valid GGUF artifacts, 8 language models admitted to planning, and projector GGUF excluded from language-model benchmarks
- Observed plan: 18 entries; 8 CPU entries ready and 10 GPU/hybrid entries blocked because the probed archived `llama-bench` build exposed no GPU device
- Identity finding: the Qwen reasoner catalog declaration and embedded GGUF metadata disagree; execution remains promotion-blocked unless reviewed under the experimental measurement override
- Evidence limitation: the retained inventory used `hash_mode=none`, no live inference or benchmark execution occurred, and every entry retains `statistical_promotion_analysis_missing`

These facts prove the isolated adapter and fail-closed planning behavior. They do not prove CUDA/Vulkan performance, production provider compatibility, live inference, full SHA-256 model identity, statistical non-regression, or production integration.

## Integration gates

1. Admit WO-017 as the umbrella record without changing the DONE status of WO-018 or WO-051.
2. Register proposed task types through WO-051 with no executable handler until the owning subtrack opens.
3. Move reusable schemas behind production adapters; do not copy the demo writer, process ownership, or private result paths.
4. Rerun MOE-001 with full SHA-256 identity and a reviewed GPU-capable offline `llama-bench` provider before hardware conclusions.
5. Require WO-053–WO-056 gates before provider/router work can claim live inference or safe cancellation.
6. Prove the scheduler, lease, router, and governor with deterministic fixtures before real concurrent model work.
7. Exercise MOE-003–MOE-009 in the WO-059 replayable harness before broad scientific use.
8. Feed only comparison-compatible, statistically qualified outcomes into WO-061 proposals.

## Acceptance criteria

- [x] A non-colliding canonical WO slot and parallel execution position are documented.
- [x] The locked hybrid architecture, authority boundaries, and resource profiles are recorded.
- [x] MOE-001–MOE-010 map to existing WO-051–WO-061 owners without introducing a second scheduler or acceptance path.
- [x] Isolated demo evidence and its limitations are recorded without claiming live inference or promotion.
- [x] Proposed MoE task types are registered as handlerless reservations in the production registry.
- [ ] Production adapters consume WO-018/WO-051/WO-052/WO-053–WO-056 contracts.
- [ ] Full-identity CPU/GPU/MoE benchmark evidence and statistical promotion analysis pass.
- [ ] Scheduler, GPU lease, router, governor, evidence/repair, UI, and overnight lanes pass their owning gates.
- [ ] WO-059 proves replay, interruption, cleanup, rejection, and explicit acceptance with the MoE lane active.

## Status

[W] WO-017 / MOE-001–MOE-010: small-scale MoE hardware orchestration integration
[D] Day 0: MOE-001 GPU-fit captured; resolved-placement evidence fork open before CPU-MoE
[I] PARTIAL: MOE-001-B/C and GPU-fit DONE; [MOE-001-A](WO-017-MOE-001-A-experimental-qwen-benchmark.md) ACTIVE; CPU-MoE, handlers, and later runtime integrations remain
[V] PASS: GPU-fit 1,582 MiB free margin, 100% utilization, cleanup, demo 19/19 on Python 3.13/3.14, and CCIS 24/24; resolved placement NOT_RECORDED
[P] LOCAL: active dirty worktree plus retained benchmark evidence; no stage, commit, handler binding, scheduler event, promotion, or canonical acceptance
[N] DESIGN FORK: capture resolved provider placement (recommended) or accept policy-plus-telemetry evidence before CPU-MoE

## Evidence log

- 2026-08-03: Confirmed WO-017 was unused while WO-050–WO-061 and WO-LOOP1–WO-LOOP6 were already allocated.
- 2026-08-03: Chose a gap-plus-parallel structure: WO-017 owns the architecture and MOE subtrack; existing WOs retain their identities and runtime authority.
- 2026-08-03: Reconciled the finalized design and isolated benchmark demonstration with the live-inference, allocation, evidence, mapping, replay, and synthesis series.
- 2026-08-03: Admitted WO-017 and extended the registry from 21 to 32 entries. All eleven MoE additions are `reserved` with `native_handler: null`; the registry digest changed from `sha256:41a4feafa18c64f0d2ffac0eda27ebb524b5fade27ffd0da11885fcb1f1ea832` to `sha256:6621580e74add5f3006e86e5a10385951a105552b59bef3404fb91beb399223e`.
- 2026-08-03: Confirmed no persisted typed tasks existed under the prior digest, then passed 9 focused allocation tests and all 24 CCIS tests.
- 2026-08-03: Opened the bounded [MOE-001 productionization evidence gate](WO-017-MOE-001-full-identity-gpu-provider-evidence.md); reviewed the Winget Vulkan provider and recorded the 59.02 GiB full-identity scope without loading a model.
- 2026-08-03: Completed that no-inference gate: nine full hashes, seven identity-admissible artifacts, an 18-entry replay-stable CPU/GPU/MoE plan, and passing demo/CCIS regressions. Sparse-MoE execution now waits on the preserved Qwen identity decision.
- 2026-08-03: Operator chose measurement-only override. The mismatch remains recorded and non-promotable; the first CPU baseline entry is the sole open execution action.
- 2026-08-03: Captured the first entry successfully. It used 91.8% of its configured 16-thread CPU lane, but Vulkan operation offload remained active; provider tensor count also supports 14.137B parameters rather than the name-based 35B label. GPU-fit is held pending the recorded design choice.
- 2026-08-03: Completed supporting updates [MOE-001-B](WO-017-MOE-001-B-strict-cpu-control.md) and [MOE-001-C](WO-017-MOE-001-C-tensor-derived-identity.md). Strict CPU isolation held within an 11 MiB device-memory delta; 733 bounded descriptors reproduced 14,137,111,168 parameters; v2 GPU-fit is now the next gate.
- 2026-08-03: Captured v2 GPU-fit successfully: prompt 728.864 tokens/s, generation 14.819 tokens/s, 100% peak GPU utilization, and 1,582 MiB minimum observed free memory. Exact resolved residency remains separate from the requested `999` sentinel.

## Out of scope

- Installing the demo into the production taskpack, scheduler, installer, launcher, or model catalog under this documentation-only change.
- Treating maximum utilization, VRAM saturation, or concurrent model loads as goals independent of useful throughput and safety.
- Killing or preempting unowned GPU processes.
- Promoting a placement from no-hash, single-sample, CPU-only-provider, or no-inference evidence.
- Automatic repair, acceptance, commit, merge, or publication by a router, expert, overnight lane, or benchmark result.
