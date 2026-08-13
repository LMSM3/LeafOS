# LeafOS MOE-001 Benchmark Demo

Status: isolated demonstration, not integrated into the production LeafOS
installer, launchers, scheduler, taskpack, or model catalog.

This package turns MOE-001 into a reviewable working slice:

1. `inventory` reads bounded GGUF metadata and tensor descriptors, derives the
   logical parameter count without reading tensor payloads, and compares that
   count with the catalog.
2. `probe` hashes and inspects a supplied `llama-bench` executable.
3. `plan` creates deterministic CPU, GPU-fit, and CPU-MoE benchmark commands.
4. `run` executes selected provider-ready entries sequentially and records raw
   output, hashes, process RSS/CPU/I/O counters, a five-sample pre-run NVIDIA
   background envelope, and in-run NVIDIA telemetry.

The normal preparation path never loads a model. Benchmark execution requires
the literal `--execute` flag. Network-backed llama.cpp options are rejected and
every generated command includes `--offline`.

## Safety and evidence boundaries

- No downloads or model mutations.
- No changes to production LeafOS state.
- GGUF tensor payloads are not mapped during inventory. Logical parameter count
  is derived from bounded tensor descriptors only.
- Full model SHA-256 is opt-in because it reads every byte of every selected
  artifact. A no-hash inventory is useful for planning but cannot pass the
  benchmark-admission identity gate.
- A catalog/tensor-count identity mismatch blocks execution unless
  `--allow-experimental-identity` is supplied. A disagreement confined to
  `general.name` is retained as an advisory finding. The override permits
  measurement only; it never removes a promotion blocker.
- The strict CPU control requires all three controls: zero GPU layers,
  `--device none`, and `--no-op-offload 1`. The runner rejects a strict-CPU
  entry if any control is missing or changed.
- GPU placements are marked not ready when the probed binary exposes no GPU
  backend/device.
- Projector GGUFs are inventoried but excluded from language-model benchmarks.
- Runs are sequential. The demo does not claim or manage the production GPU
  lease.
- NVIDIA samples describe total device state, not process-exclusive use.
  Process I/O counters describe bytes attributed by the operating system; they
  are not proof of physical NVMe reads after page-cache effects.
- No-hash plans verify file size and modification time before execution. Only a
  full SHA-256 inventory provides cryptographic model identity.
- A successful run still carries `statistical_promotion_analysis_missing`.
  This demo records measurements; it does not implement the paired baseline,
  confidence interval, and non-regression analysis required for promotion.

## Run from the source tree

```powershell
cd ProjectLeaf\leaf_moe_benchmark_demo
python -m leaf_moe_bench --help
```

An editable installation is optional:

```powershell
python -m pip install -e .
leaf-moe-bench --help
```

The package has no third-party Python dependencies.

## Prepare a plan without inference

The current workspace contains an archived CPU-only llama.cpp build that is
useful for proving the provider probe and CPU planning path:

```powershell
python -m leaf_moe_bench prepare `
  --llama-bench ..\..\archive\2026-07-25-root-cleanup\tmp\llama-cpp-win-cpu-b9828\llama-bench.exe `
  --out-dir ..\..\tmp\moe-001-demo
```

This writes:

```text
tmp/moe-001-demo/
  inventory.json
  provider.json
  plan.json
```

It does not perform an inference benchmark. With the archived CPU build, CPU
entries are ready and GPU/MoE-offload entries are retained with the explicit
`provider_has_no_gpu_device` blocker.

For benchmark-admission-grade model identity, rerun inventory or prepare with:

```powershell
--hash-mode sha256
```

That can take several minutes and perform tens of GiB of reads on the current
model set. It is never implied by the default command.

## Execute one reviewed entry

Open `plan.json`, select one `entry_id`, and then run exactly that entry:

```powershell
python -m leaf_moe_bench run ..\..\tmp\moe-001-demo\plan.json `
  --out-dir ..\..\tmp\moe-001-runs `
  --entry "bench:REVIEWED_ENTRY_ID" `
  --execute
```

The runner verifies the provider hash, model path, offline flag, and absence of
remote-provider arguments before starting the process. A timeout terminates the
benchmark and records the failed evidence rather than implying success.

## Default demonstration matrix

`leaf_moe_bench/default_matrix.json` declares one bounded workload and four
placements:

| Placement | Applies to | Intent |
|---|---|---|
| `cpu-strict-16t` | all language models | Device-isolated CPU control (`device=none`, zero GPU layers, no operation offload) |
| `gpu-fit-1024mib` | all language models | GPU placement with 1024 MiB fit margin |
| `moe-cpu-half` | sparse MoE only | half of MoE layers selected for CPU placement |
| `moe-cpu-all` | sparse MoE only | all model blocks selected for CPU-MoE placement |

The matrix is evidence input, not a promise that these placements are fast or
even supported by a particular build. Provider readiness is decided after the
binary is probed.

## Integration seam

The demo is structured so later integration can be narrow:

- Inventory output can become an adapter behind the existing model installer.
- Provider and benchmark plans can become placement-manifest evidence for the
  GPU lease manager.
- Telemetry can be replaced by the existing FlowerOS hardware-monitor adapter.
- Run results can be appended through the canonical LeafOS journal writer.
- The JSON contracts in `schemas/` can be promoted independently of this CLI.

Production integration should not copy the demo's writer or process ownership
directly. It should preserve the contracts while moving authority into the
existing scheduler, lease manager, and durable event pipeline.
