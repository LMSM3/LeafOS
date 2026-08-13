# Medium MoE Model Policy

## Decision

GLM-5.2 is deprecated as a local LeafOS route because it is outside the practical hardware envelope of the reference home workstation. LeafOS now prefers operator-selected mixture-of-experts candidates with 47-156 billion total parameters.

This is an evidence-gated preference, not a claim that every model in that range will fit or run well. Total parameter count is insufficient for an MoE decision. Every candidate must also declare active parameters per token, expert count, active experts per token, quantization artifact, context, license, pinned revision, and artifact hash.

The stack still means all downloaded and locally available models in this LeafOS instance. This policy selects possible active routes from the stack; it does not rename the stack or delete its other entries.

## Source Classification

The contract preserves where each claim came from:

| Source | Classification | What it establishes |
|---|---|---|
| Development conversation, 2026-07-21 | Operator decision | Deprecate GLM-5.2 locally and investigate medium MoE models in the 47-156B total-parameter band. |
| `reports/brain-selection-20260717/results.json` | Measured repository evidence | A Qwen3.5 14B A3B baseline measured 6.259 tokens/s on CPU, 9.917 with partial Vulkan offload, and 107.550 with full Vulkan offload. This proves the value of measuring placement; it does not prove 47-156B host fit. |
| `docs/RESIDENT_STACK_USAGE.md` | Measured operational evidence | The current Gemma4-Coder Q3 route preserved foreground and execution headroom where larger resident trials reached RAM pressure. |
| `docs/GLM52_OVERNIGHT_RUNBOOK.md` | Historical proposal | The 467 GB GLM placement and SSD-streaming design was a proposed test configuration, not a measured or implemented LeafOS SSD tier manager. |

The incumbent route in `config/vulkan-provider-stack.json` remains active until a named medium-MoE candidate qualifies. Deprecation does not automatically promote an unresolved model.

## Contract Files

| File | Purpose |
|---|---|
| `config/medium_moe_policy.json` | Active selection, placement, evidence, and promotion policy. |
| `schemas/leafos.medium-moe-policy.v1.schema.json` | Strict policy shape. |
| `config/medium_moe_candidate.template.json` | Deliberately unresolved candidate record. |
| `schemas/leafos.medium-moe-candidate.v1.schema.json` | Candidate identity, topology, runtime, and acceptance shape. |
| `config/medium_moe_benchmark_metrics.sample.json` | Null-valued telemetry template; it is not benchmark evidence. |
| `core/python/leaf_moe_contract.py` | Standard-library semantic validator. |
| `core/python/leaf_runtime.py` | Python runtime selection and read-only policy/candidate readiness status. |
| `core/runtime/runtime.sh` | Shell runtime selection and read-only policy/candidate resolution status. |
| `core/python/leaf_overnight.py` | Compatibility CLI for manifest, run, and evaluation operations. |

## Core Runtime Integration

The canonical Bash runtime selector publishes the Medium-MoE policy as an observable research lane alongside the active role selection. The Python selector validates the policy and candidate record; the shell selector reports the configured candidate state, incumbent route, and disabled automatic promotion. `LEAF_MEDIUM_MOE_CANDIDATE` can select a private candidate record for these checks without editing the repository template or changing the provider.

This status is intentionally weaker than qualification. A `resolved` candidate has declared identity and runtime configuration; it is not benchmark-qualified, promotion-eligible, or active. Only a complete passing 4/8/64-minute portfolio followed by operator approval can authorize a separate update to `config/vulkan-provider-stack.json`.

## Placement Truth

The required provider is llama.cpp with Vulkan and a local GGUF artifact. The model path and benchmark command must be explicit. LeafOS never downloads weights from the benchmark command.

SSD access currently means llama.cpp memory mapping backed by the operating system page cache. `leafos_managed_ssd_tiering` is fixed to `false`. LeafOS does not currently pin experts between SSD, RAM, and VRAM, and ordinary llama.cpp output cannot prove per-expert residency. Missing NVMe or page-fault counters must be null with a field-specific availability reason, never fabricated as zero.

GPU layer count is measured per candidate. KV cache must be compared at least with `f16` and `q8_0`; neither is assumed to win before the candidate benchmark.

## Qualification

A candidate advances through a fixed sequence: 4 minutes with a cold cache, 8 minutes with a warm cache, and 64 minutes in resident-foreground operation. Each run produces one report. Only the portfolio qualifier may combine all three passing reports into promotion eligibility.

Before the first run, the resolved candidate must define minimum generation rate, maximum time to first token, minimum validated useful changes per hour, and threshold provenance. This prevents selecting thresholds after seeing results.

Hard gates require:

- the GPU provider process to remain alive for the whole run with zero restarts;
- no out-of-memory event;
- baseline validation to pass;
- RAM, VRAM, and foreground latency to remain within `config/resident-stack-policy.json`;
- all required telemetry to be measured or carry an explicit unavailability reason; and
- an operator to approve promotion after the evidence is reviewed.

The primary ranking measure is validated useful changes per hour. Token rate, first-token latency, provider restarts, and foreground responsiveness remain visible supporting measures.

## Usage

### 1. Inspect the non-mutating runtime status

Run this through the canonical Bash CLI before preparing or benchmarking a candidate. It reads policy and candidate state only: it does not download weights, start the provider, execute inference, or alter the incumbent route.

```powershell
C:\msys64\usr\bin\bash.exe -lc 'cd /c/R/LeafOS0.2.2/ProjectLeaf/leafos_taskpack && ./bin/leafctl runtime select --json | jq ".selection.medium_moe"'
```

The default output must show `active_route` as `incumbent`, `automatic_promotion` as `false`, and the repository template as unresolved. To inspect a private candidate without modifying the template, set `LEAF_MEDIUM_MOE_CANDIDATE` in the Bash environment before the command. A `resolved` status is declared configuration only; it does not authorize provider activation.

### 2. Validate the policy and candidate record

```powershell
python .\core\python\leaf_moe_contract.py
.\bin\leaf-overnight.ps1 validate
```

Create a private candidate JSON from the template, fill every identity, topology, runtime, and acceptance field, then require readiness:

```powershell
.\bin\leaf-overnight.ps1 --profile C:\Models\candidate.json validate --require-resolved
```

### 3. Create audited manifests and run each required slot

Create the audited 4-minute manifest before starting inference. Repeat the manifest, `run`, and `evaluate` sequence for the policy's 4-minute cold-cache, 8-minute warm-cache, and 64-minute resident-foreground slots; do not combine or substitute scenarios.

```powershell
.\bin\leaf-overnight.ps1 --profile C:\Models\candidate.json manifest `
  --mode leafos `
  --scenario resident_foreground `
  --duration-minutes 4 `
  --output runs\medium-moe\4m.manifest.json
```

`run` additionally verifies that the local GGUF exists and that the explicit command contains the same model path. `evaluate` applies the predeclared candidate thresholds and resident resource limits. A single passing report qualifies only for the evidence portfolio.

### 4. Qualify the complete portfolio and request approval

After all three reports exist, evaluate the portfolio:

```powershell
.\bin\leaf-overnight.ps1 --profile C:\Models\candidate.json qualify `
  --reports runs\medium-moe\4m.report.json runs\medium-moe\8m.report.json runs\medium-moe\64m.report.json `
  --output runs\medium-moe\qualification.json
```

The qualifier verifies the policy, candidate identity, exact run slots, report gates, and report hashes. A complete passing portfolio becomes eligible for operator review. Automatic promotion remains disabled; only a subsequent operator-approved change to `config/vulkan-provider-stack.json` may alter the active route.

## Home Assistant Fit

The winning model is not simply the largest one that can emit a token. It must coexist with the TUI, executor, tests, telemetry, project memory, optional annotation database, and ordinary foreground computer use. That shared-machine behavior is part of model quality for an at-home local assistant.
