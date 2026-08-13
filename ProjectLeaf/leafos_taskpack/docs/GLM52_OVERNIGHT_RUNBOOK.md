# GLM-5.2 Q4 Overnight Inference Runbook

> **Deprecated historical profile, 2026-07-21.** GLM-5.2 is no longer a
> local LeafOS target for the reference home workstation. This document is
> retained to explain the prior experiment. Use
> `MEDIUM_MOE_MODEL_POLICY.md`, `config/medium_moe_policy.json`, and
> `config/medium_moe_candidate.template.json` for current work. The command
> examples below preserve retired syntax only; the current runner
> intentionally rejects this archived profile.

For a current candidate, first use the status-first instructions in
[`MEDIUM_MOE_MODEL_POLICY.md`](MEDIUM_MOE_MODEL_POLICY.md): inspect the
read-only runtime lane, validate a private candidate, collect the required
4/8/64-minute evidence portfolio, and obtain operator approval before any
provider-route change.

This is a no-download scaffold for evaluating whether FlowerOS and LeafOS can sustain useful overnight GLM-5.2 Q4 inference. It does not include model weights or a hard-coded `llama.cpp` command.

## Profile

`config/glm52_overnight.json` defines the fixed evaluation contract:

- 467 GB stored Q4 weights;
- 256 routed experts with 8 active experts;
- 48 GB RAM hot cache;
- 12 GB RTX 4070 selective-offload budget; and
- fast-NVMe memory-mapped streaming.

The three comparison modes are:

1. `raw`: minimal `llama.cpp` configuration.
2. `floweros`: CPU MoE placement, mmap, GPU auto-fit, I/O priority, cache warming, and thread tuning.
3. `leafos`: FlowerOS plus state compaction, persistent state, sandboxed code work, and validation.

## Validate the profile

```powershell
pwsh -File bin/leaf-overnight.ps1 --profile config/glm52_overnight.json validate
```

```bash
./bin/leaf-overnight --profile config/glm52_overnight.json validate
```

## Create a run manifest

A manifest records the selected mode, model placement, required telemetry, and no-download safety contract before any external benchmark executes.

```powershell
pwsh -File bin/leaf-overnight.ps1 manifest --mode floweros --output runs/glm52/floweros.manifest.json
```

## Configure a real benchmark

Set `runtime.model_path` and `runtime.benchmark_command` in a private copy of the profile. The command is an explicit argument array; this scaffold intentionally does not infer a model path or download weights.

```json
"benchmark_command": [
  "C:/tools/llama.cpp/llama-bench.exe",
  "--model",
  "D:/models/GLM-5.2-Q4.gguf"
]
```

Then execute only after reviewing the configured command:

```powershell
pwsh -File bin/leaf-overnight.ps1 --profile config/glm52_overnight.local.json run --mode floweros --manifest runs/glm52/floweros.manifest.json
```

## Record and evaluate metrics

Use `config/glm52_overnight_metrics.sample.json` as the required telemetry template. Fill it with data from the actual run, then evaluate it:

```powershell
pwsh -File bin/leaf-overnight.ps1 evaluate --mode leafos --metrics runs/glm52/leafos.metrics.json --output runs/glm52/leafos.report.json
```

The evaluator rejects incomplete metric records and classifies generation rate using these gates:

| Generation rate | Classification |
|---:|---|
| `< 0.10` tokens/s | Operationally useless |
| `0.10–0.29` tokens/s | Experimental persistence |
| `0.30` tokens/s | Minimum success |
| `0.40` tokens/s | Practical overnight target |
| `0.66` tokens/s | FlowerOS optimization success |
| `>= 1.0` tokens/s | Exceptional |

## Primary outcome

Raw generation speed is not the final outcome. The primary metric is:

`validated useful changes per seven-hour run`.

A lower raw rate can remain useful when state persistence and compaction reduce repeated context work, while sandboxed changes are tested and retained.
