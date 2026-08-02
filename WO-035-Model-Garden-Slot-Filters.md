# WO-035 — Model Garden Slot Binding and Per-Assignment Allow-Model Filters

Status: Draft → Active  
Priority: High  
Target: LeafOS 0.9.5  
Scope: Provider routing, model-stack configuration, reasoning graph integration  
Depends on: WO-LeafOS-Medium-MoE-Router (Iteration A–B implemented)  
Produces: deterministic slot→checkpoint binding, one active model per root, filter-enforced substitution control

## 1. Problem

The active model library is now ~249.9 GB and contains many checkpoints per root (feeders, primaries, fallbacks, MTP variants, and HelperText tiers). Models are delivered in **packs**: layered bundles of up to ~20 checkpoints and over 200 GB. The MoE router can already score experts by role, capability, memory, and placement, but it has no way to restrict a particular assignment to a **single approved checkpoint**. Without that, the router may:

- silently substitute a feeder when a primary was intended;
- load two large primaries at once and exhaust VRAM;
- ignore the user's explicit quantization preference;
- fail to bind a pack artifact to a logical slot.

The solution is: **one model per slot per assignment**, enforced by **allow-model filters** carried in the `LaneRequest` and applied after hard eligibility but before scoring. Packs declare which groups are legal for each layer; groups declare which members are legal for each slot; filters guarantee that exactly one member is selected.

## 2. Doctrine

- A **slot** is a logical function, not a file.
- A **checkpoint** is a concrete quantized artifact.
- An **assignment** maps one slot to one allowed checkpoint for one task.
- A filter is a whitelist checked deterministically by native code; absence of an allowed match fails closed.
- Model identity (`expert.id`, `model_ref`, `quantization`) must match exactly; glob/regex is reserved for `include` patterns in download wrappers only.

## 3. Slot taxonomy

```text
router.scout        → fast triage / collar
router.primary      → main router
router.fallback     → emergency router
brain.feeder        → cheap decomposition
brain.primary       → main brain / planner
coder.feeder        → quick patch drafting
coder.primary       → serious implementation
critic.feeder       → shallow review
critic.primary      → deep audit
writer.feeder       → rough summary
writer.primary      → polished writing
judge.fallback      → reserve heavy judge
judge.primary       → bedrock judge / release authority
```

HelperText slots are a separate sub-library and are not wired into the main model tree unless explicitly requested by a task profile.

## 4. Allow-model filter contract

An `AllowModelFilter` is attached to a `LaneRequest`:

```json
{
  "allow_models": [
	"qwen25-coder-32b-iq2m-local"
  ],
  "deny_models": [
	"qwen25-mapper-7b-q4km-local"
  ],
  "require_quantization": ["Q4_K_M", "Q6_K", "IQ2_M"],
  "require_provider": "llama.cpp"
}
```

Rules:

- If `allow_models` is present, the selected expert's `id` must be in the list.
- If `allow_models` is empty/unset, all eligible experts remain candidates.
- `deny_models` always rejects, even if the expert would otherwise score highest.
- `require_quantization` and `require_provider` are optional hard filters.
- Violations are recorded in `RoutePlan.rejected` with stable reason codes.

## 5. Per-assignment flow

```text
Task + pack profile
		|
		v
Resolver picks one group per pack layer
		|
		v
Resolver picks one slot per required role
		|
		v
Loader checks whether slot's artifact exists locally
		|
		v
Router applies role eligibility + allow-model filter
		|
		v
Exactly one checkpoint is selected
		|
		v
Provider adapter loads (if local) or calls (if remote)
```

## 6. File changes

- `config/stacks/kimi-3.json` — add `slots` map and `allow_models` arrays.
- `core/providers/include/providers/types.hpp` — add `AllowModelFilter` and friends.
- `core/providers/src/moe_router.cpp` — apply filters in `is_eligible`.
- `core/providers/tests/test_router.cpp` — add allow/deny filter tests.
- `config/experts/*.json` — ensure each logical slot has a matching expert entry.
- `config/packs/*.json` — pack manifests that reference groups and constrain layer activation.

## 7. Acceptance criteria

- [x] WO-035 document created and recorded in evidence log.
- [x] `kimi-3.json` declares `slots` for brain, coder, judge.
- [x] `blue-banyan.json` pack manifest declares layers and groups that can be bound to slots.
- [x] Router rejects an otherwise-eligible expert not in `allow_models`.
- [x] Router accepts an allowed expert and returns stable plan.
- [x] Deny-list rejects even a top-scoring expert.
- [x] Missing `allow_models` on a request leaves filtering open (backward-compatible).
- [x] `leaf-roundtable --group` resolves a pack group and emits a session plan with per-member eligibility.
- [x] `ctest` passes after changes.

## Status

```text
[W] WO-035: Model Garden Slot Binding and Allow-Model Filters
[D] Day closed: 2026-07-28
[I] COMPLETE
[V] VALIDATED: CMake build + ctest pass; leaf-roundtable plan dry-run stable; filter tests pass
[P] LOCAL
[N] Ready for integration: propagate AllowModelFilter from task profile into LaneRequest; wire roundtable --slot
```

## Evidence log

- 2026-07-28: Created WO-035.
- 2026-07-28: core/providers build passes (23 tests).
- 2026-07-28: Added AllowModelFilter to types.hpp and denied/allow/require_quantization/provider enforcement in moe_router.cpp.
- 2026-07-28: Added 3 filter tests; ctest passes (10 assertions).
- 2026-07-28: leaf-roundtable dry-run plan remains stable after filter wiring.
- 2026-07-29: Replaced Yellow Flower with Blue Banyan Council: 16 installed expert profiles derived from flower-pack-1.2.0; `leaf-route list` and `leaf-roundtable plan --group blue.brain --dry-run` show pack/group wiring.
