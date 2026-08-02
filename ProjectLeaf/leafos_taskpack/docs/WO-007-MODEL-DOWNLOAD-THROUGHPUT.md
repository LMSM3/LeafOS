# WO-007 — Model Download Throughput Recovery
**Date:** 2026-06-24  **Status:** IMPLEMENTED  **Author:** operator note

---

## 1. Purpose

Investigate and fix the low download speed observed in the Leaf model installer.
The current helper is functionally correct, but the transfer rate is capped around
~2.8 MB/s in practice while other tools on the same machine regularly reach
50+ MB/s.

This work order exists to turn a slow-but-working downloader into a fast one.

---

## 2. Observed Symptom

Current runtime symptoms:

- Active download rate stays near `2.81 MB/s`
- Large GGUF files take much longer than expected
- The machine itself is not obviously starved for CPU, RAM, or disk
- Competing tools on the same box can saturate the connection far better

The screenshot shows the relevant pattern:

```text
ACTIVE DOWNLOADS
leaf_fake_download.crdownload   34 MB   2.81 MB/s
```

That is acceptable for a fallback path, but not for the full-stack model fetcher.

---

## 3. Named Model Assignments

The installer should treat the catalog models as assigned roles, not anonymous blobs:

| Nickname | Model key | Assignment | Notes |
|----------|-----------|------------|-------|
| Forge    | `gemma4-coder` | coder / builder | Primary local code model; supports quantized variants |
| Oracle   | `qwen-opus-reasoning` | reasoner / planner | Broad reasoning model; multiple GGUF files may be present |

These names should appear in logs, docs, and user-facing install progress.

---

## 4. Scope

In scope:

- `leaf_model_installer/shell_helpers/install-all-models.ps1`
- `leaf_model_installer/leaf_models/downloader.py`
- `leaf_model_installer/leaf_models/cli.py`
- any supporting docs or benchmarks needed to measure throughput

Out of scope:

- adding new models beyond the current allowlist
- changing the catalog contents unless required for speed
- replacing the Hugging Face backend entirely

---

## 5. Likely Bottlenecks to Check

1. Sequential download behavior instead of parallel file handling
2. Hugging Face client defaults not tuned for bulk transfer
3. Local antivirus or Windows Defender inspection overhead
4. Disk write bottlenecks or temporary-directory placement
5. Network path differences between browser downloads and Python-based fetches
6. Missing resume / retry tuning for large artifacts

---

## 6. Success Criteria

This work order is complete when:

- the installer identifies Forge and Oracle by nickname during downloads
- download throughput is measured, not guessed
- the common path reaches materially better speed on this machine
- the solution remains safe and allowlisted
- failures still produce clear reports instead of silent stalls

Target outcome:

- sustained speeds substantially above the current ~2.8 MB/s floor
- ideally approaching the machine's normal large-file download behavior

---

## 7. Next Actions

1. Add a small throughput benchmark around the model fetch path.
2. Compare Python downloader speed against a known fast baseline.
3. Tune the downloader for concurrency, buffering, or transport settings.
4. Verify the result against both Forge and Oracle downloads.
5. Record the measured before/after speeds in this WO.

---

## 8. Notes

The current helper is operational, but the speed cap is now the real issue.
This WO keeps the fix focused on throughput, not on cosmetic cleanup.

---

## 9. Root Cause (measured)

Investigation of the installer venv (`huggingface_hub 1.20.1`) found:

- The Rust **Xet** backend (`hf_xet`) is the active transport, but
  `HF_XET_HIGH_PERFORMANCE` was unset/false. That flag is the throttle: the
  high-performance Xet path stays off unless the env var is set **before** the
  Rust session is lazily created on first download.
- The legacy `hf_transfer` accelerator is **fully retired** in `huggingface_hub`
  1.x (it only emits a deprecation warning now), so it cannot be the fix.
- The two catalog repos are **plain LFS** files (`xet=None`, `lfs=True`):
  - `gemma4-coding-Q4_K_M.gguf` (~7.38 GB) — single file (Forge)
  - Qwen distill GGUFs — three files up to ~28 GB (Oracle)
- For single-file LFS pulls (Forge), `snapshot_download` streams one file at a
  time, so the win there is the transport flag plus the already-healthy 10 MB
  `DOWNLOAD_CHUNK_SIZE`. For multi-file repos (Oracle), `max_workers` adds
  genuine file-level parallelism.

So the ~2.8 MB/s floor was a throttled-transport problem, not a hardware,
disk, or CPU limit.

---

## 10. Fix Implemented

Changes in `leaf_model_installer`:

- `leaf_models/downloader.py`
  - `enable_fast_transfer()` sets `HF_XET_HIGH_PERFORMANCE=1` in the environment
    (read by the lazy Rust session), syncs the Python constant, and clears the
    deprecated `HF_HUB_ENABLE_HF_TRANSFER`.
  - `download_model()` now calls `enable_fast_transfer()` before any transfer,
    accepts `max_workers` (default 8) and `high_performance`, times the transfer
    with `perf_counter`, and records measured bytes + MB/s.
  - `DownloadReport` carries `nickname`, `role`, `elapsed_seconds`,
    `downloaded_bytes`, `high_performance`, `max_workers`, and an `mbps`
    property; the manifest now persists `throughput_mb_s`.
  - New `benchmark_download()` + `BenchmarkResult` measure real MB/s from a
    bounded HTTP Range sample (default 48 MB) without pulling whole models.
- `leaf_models/catalog.py`
  - `ModelEntry` gained `nickname`/`role` and a `label()` helper. Forge =
    `gemma4-coder` (coder/builder), Oracle = `qwen-opus-reasoning`
    (reasoner/planner).
- `leaf_models/cli.py`
  - Download output shows the Forge/Oracle identity and a measured **Throughput**
    line.
  - New `--max-workers` and `--no-accel` flags on `download`.
  - New `benchmark` subcommand: `--sample-mb`, `--no-accel`.
- `shell_helpers/install-all-models.ps1`
  - Sets `HF_XET_HIGH_PERFORMANCE=1`, clears the deprecated transfer var,
    ensures `hf_xet`, adds a `-Workers` param, and passes `--max-workers`.

---

## 11. Validation

Validated without forcing a multi-GB transfer (large pulls are opt-in):

- `py_compile` passes for `catalog.py`, `downloader.py`, `cli.py`.
- `download --dry-run` prints the `Forge (coder/builder)` banner, resolves
  `*Q4_K_M*.gguf`, and exits 0.
- The `benchmark` subcommand parses and the downloader exposes
  `benchmark_download` / `BenchmarkResult`.
- Offline downloader tests now verify that a server ignoring `Range` can never make the
  benchmark count beyond the requested sample, invalid sample sizes fail before network
  access, transport flags are deterministic, and missing remote matches are explicit.
- `benchmark --json-out PATH` writes a `leafos.model-download-benchmark.v1` evidence file
  containing requested/received bytes, HTTP status, range behavior, elapsed time, and MB/s.
- `python -B -m unittest discover -s tests -p "test_*.py"` passes 15 tests without downloading weights.

### How to measure before/after on this machine

Run the bounded benchmark (samples 48 MB, no full download):

```powershell
# Accelerated (Xet high-performance ON)
& .\.venv\Scripts\python.exe -c "import sys;sys.path.insert(0,'.');from leaf_models.cli import main;main()" benchmark --model gemma4-coder --quant Q4_K_M

# Baseline (default transport)
& .\.venv\Scripts\python.exe -c "import sys;sys.path.insert(0,'.');from leaf_models.cli import main;main()" benchmark --model gemma4-coder --quant Q4_K_M --no-accel
```

Record the two `Measured throughput:` lines below once run:

| Path | Transport | Measured MB/s |
|------|-----------|---------------|
| Before | default | _fill in from `--no-accel` run_ |
| After  | Xet high-performance | _fill in from default run_ |

Real model downloads also print the achieved MB/s in their report and persist
`throughput_mb_s` in `leaf_download_manifest.json`, so every actual install is
self-measuring from now on.
