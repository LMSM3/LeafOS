# Test Presentation Sentiment

**Status:** implemented as the test observatory; continue as low-priority polish

Tests should do more than end in a quiet row of dots. When practical, running the LeafOS test suite should make the system's activity understandable: operators should see which subsystem is active, what stage is being exercised, how long it takes, and whether CPU, GPU, memory, provider, or interface behavior is involved.

This presentation layer is especially valuable for tests related to the local stack. The stack means all downloaded and locally available models in this LeafOS instance. A stack-related test is a natural opportunity to demonstrate a bounded real llama.cpp call, Vulkan activity, token throughput, provider health, and CPU validation. Live inference must remain explicit and must not replace deterministic fixture coverage.

For tests that do not need a real model, presentation should favor lightweight animation tied to the subsystem under test:

- Agent loops can show `PLAN -> EXECUTE -> VALIDATE -> CHECKPOINT`.
- Memory tests can show `APPEND -> HASH -> INDEX -> REPLAY`.
- Interface tests can show `INPUT -> SNAPSHOT -> LAYOUT -> PAINT`.
- Telemetry tests can animate CPU and GPU meters.
- Game tests can visualize topology, turns, production, or harvesting.
- Runtime tests can show detection, routing, fallback, and readiness.

The animation is not the test result. Assertions, failure behavior, isolation, reproducibility, and machine-readable evidence remain authoritative. Visual output should make slow work look active without hiding stalls or failures, and redirected or automated runs must retain stable plain-text and JSON output.

Private recursive reasoning must not be printed or persisted. LeafOS may report safe metadata such as phase, elapsed time, token rate, output length, or withheld character count. Visible final model output may be shown when it is bounded and validated by CPU policy.

The current observatory discovers 203 tests and assigns each a subsystem lane,
phase animation, elapsed time, and machine-readable evidence. `--live-stack`
adds one explicitly requested real llama.cpp demonstration after deterministic
tests. Further presentation work remains low priority because it improves
observability and operator confidence rather than core correctness. It should
not turn test code into a separate UI product or materially slow ordinary
regression runs.

The desired feeling is simple: a test run should look alive, honest, and informative while remaining a test first.
