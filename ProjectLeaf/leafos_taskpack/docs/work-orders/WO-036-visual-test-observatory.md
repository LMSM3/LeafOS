# WO-036: Visual Test Observatory

Machine-readable authority: `WO-036-visual-test-observatory.json`

## Objective

Expand the operator-visible behavior of the original 118 Python tests. Stack-related tests should lead naturally into an optional real llama.cpp Vulkan demonstration; other tests should render animation tied to their subsystem rather than emit only dots.

## Boundary

Deterministic tests remain deterministic. The visual controller runs each module in an isolated worker, observes typed lifecycle events, samples CPU/GPU hardware, and writes append-only JSONL evidence. A real stack call is performed only when `--live-stack` is explicitly supplied. All downloaded and locally available models in this instance are the stack.

## Acceptance

- A single `leafctl test visual` command presents every discovered Python test.
- More than half of the original 118 tests receive subsystem-specific animation; the target is all 118.
- Slow tests remain visibly active and modules are process-isolated.
- CPU and GPU utilization are visible and summarized when counters are available.
- `--live-stack` uses the configured real llama.cpp endpoint and CPU-validates a bounded streamed response.
- Private reasoning content is not displayed or persisted.
- Every run writes sequenced JSONL and a machine-readable summary.
