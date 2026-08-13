# LeafOS Inference Benchmark Protocol

## Purpose

LeafOS throughput is not a hardware constant. It is an observation produced by a model artifact, quantization, runtime build and backend, CPU thread count, GPU placement, KV-cache type, prompt and generation workload, temperatures, power state, memory pressure, and competing processes.

The benchmark report therefore keeps raw throughput beside the conditions that produced it. A result may be compared with another result only after those fields have been checked.

Each completed cell also records measured generated tokens and a decode-only hourly projection using the explicit comparison policy in the manifest. The default is USD 10 per million generated output tokens with `pricing_basis=operator_assumption`. This is gross cloud-equivalent output value, not net savings; local costs and cloud input/cache charges remain excluded.

## Historical baseline

The earliest surviving paper records CPU decode samples of 3.81, 3.96, and 3.92 tokens/s, with 39.61 tokens/s prompt processing and a rounded 7.37 GB model footprint. The repository does not preserve the model path, model hash, llama.cpp build, backend, thread count, prompt and generation lengths, thermal state, or process inventory for that run.

A preserved 2026-07-17 raw benchmark reports an internal model size of 7,365,558,464 bytes for the installed Gemma4 Opus Q4 artifact, matching the old rounded 7.37 GB footprint. It is a plausible reconstruction candidate, but matching the footprint does not prove it was the original model. The old result remains useful as dated historical evidence, not as a current executive-rate specification.

The preserved July run used `llama.cpp` build 9957 (`c4ae9a88f`), Vulkan, 24 threads, batch 2048, micro-batch 512, F16 KV, mmap, a 512-token prompt, 128 generated tokens, three repetitions, and no warm-up. It measured CPU decode at 4.051 tokens/s for Gemma4 Opus Q4, 6.269 for Qwen3.5 14B-A3B MXFP4 MoE, and 4.365 for Qwopus3.5 9B Q4. Qwen placement results were 6.259 tokens/s at zero GPU layers, 9.917 at 16 layers, and 107.550 at full Vulkan offload. Thermal and competing-process state were not retained, which is why the new matrix must measure them.

The 65% through 96.5% bandwidth table remains arithmetically valid for a 7.37 GB weight footprint and an idealized 504 GB/s memory-bandwidth denominator. It is a model-specific ceiling calculation, not a prediction that includes KV-cache traffic, kernels, synchronization, sampling, or partial offload.

## Clean-run procedure

1. Connect AC power and keep the Windows power mode unchanged throughout the matrix.
2. Stop LeafOS provider instances and close nonessential user applications.
3. Run the matrix dry check. Do not override a busy preflight for a publishable run.
4. Run the matrix. It checkpoints `report.json` after every cell and can resume after interruption.
5. Preserve the manifest, report, and `raw` directory together.
6. Compare the first and final full-GPU cells for drift before interpreting small differences.

```powershell
pwsh -File bin/leafctl.ps1 realbench matrix `
  --manifest config/inference-benchmark-matrix.json `
  --output-dir reports/inference-benchmark/clean-expanded-20260721 `
  --dry-run

pwsh -File bin/leafctl.ps1 realbench matrix `
  --manifest config/inference-benchmark-matrix.json `
  --output-dir reports/inference-benchmark/clean-expanded-20260721 `
  --resume
```

`--allow-busy` exists for diagnostic runs only. A report produced with idle-policy violations must not replace the clean baseline.

Summarize a saved report or test a different comparison assumption without changing its measurements:

```powershell
pwsh -File bin/flower.ps1 realbench summary `
  --report reports/inference-benchmark/clean-expanded-20260721/report.json

pwsh -File bin/flower.ps1 realbench summary `
  --report reports/inference-benchmark/clean-expanded-20260721/report.json `
  --output-usd-per-million 20
```

## Matrix phases

| Phase | Question |
|---|---|
| Historical reconstruction | Does the surviving 7.37 GB candidate reproduce the old CPU neighborhood under the closest preserved protocol? |
| CPU thread sweep | Which thread count is best for each model on this hybrid-core CPU? |
| Current stack reference | How does the currently routed coder compare under the same workload? |
| Placement sweep | What is the cost of CPU-only, partial Vulkan offload, and full Vulkan offload? |
| Prompt sensitivity | How do prefill and decode respond to different prompt lengths? |
| KV-cache sensitivity | What throughput and VRAM change follows an F16 to Q8 cache change? |
| Drift repeat | Did temperature or host activity move the full-GPU result during the run? |

## Capacity model

Do not calculate work orders per hour from output length alone. For a work order with prompt length `P`, generated length `O`, provider time `Tprovider`, tool time `Ttool`, validation time `Tvalidate`, checkpoint time `Tcheckpoint`, and expected retry time `Tretry`, use:

```text
Torder = P / Rprefill + O / Rdecode
       + Tprovider + Ttool + Tvalidate + Tcheckpoint + Tretry

orders_per_hour <= 3600 / Torder
```

Report the arithmetic decode-only limit separately when it is useful. It is an upper bound, not observed sustained agentic capacity.

## Telemetry limits

The standard-library collector records GPU temperature through `nvidia-smi`. Portable Windows interfaces do not expose a trustworthy CPU package temperature, so that field remains explicitly unavailable until LeafOS integrates a trusted sensor provider. Missing telemetry is evidence about the measurement, not permission to invent a value.
