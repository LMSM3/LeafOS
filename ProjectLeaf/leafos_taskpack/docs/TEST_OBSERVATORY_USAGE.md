# LeafOS Test Observatory

The test observatory turns the Python regression suite into an operator-visible run while preserving the deterministic assertions in each test.

## Basic Usage

```powershell
.\bin\leafctl.ps1 test visual
```

```bash
./bin/leafctl test visual
```

The original 118 tests are classified into stack, loop, memory, interface, telemetry, game, runtime, and general lanes. WO-036 added six observatory contracts; later live-project, resident-scheduler, resource-governor, benchmark, and TUI coverage brings current discovery to 167. Interactive terminals animate the active lane and hardware meters. Redirected output receives a stable start and result trace for every test.

## Real Stack Demonstration

```powershell
.\bin\leafctl.ps1 test visual --live-stack
```

`--live-stack` adds one bounded call to the configured local llama.cpp Vulkan stack after deterministic tests finish. It checks provider health, streams a short response through the production chat adapter, withholds private reasoning content, and applies a CPU-side response contract. Failure of this explicitly requested demonstration fails the observatory run.

The stack means all downloaded and locally available models in this LeafOS instance. The demo does not give a model filesystem authority and does not replace fixture-based unit tests.

## Focused Runs

```powershell
.\bin\leafctl.ps1 test visual --match tui
.\bin\leafctl.ps1 test visual --match provider --live-stack
.\bin\leafctl.ps1 test visual --plain
.\bin\leafctl.ps1 test visual --list --json
```

Use `--no-hardware` on machines without counters and `--no-animation` when only the structured visual trace is wanted.

## Evidence

Each run writes:

- `runs/test-observatory/<run-id>/events.jsonl`: sequenced test, module, stack, and hardware events.
- `runs/test-observatory/<run-id>/summary.json`: counts, domains, duration, and average/maximum hardware utilization.
- `runs/test-observatory/<run-id>/live-stack.json`: bounded final-output evidence, a visible-response hash, and the withheld reasoning character count when the live demo is requested.
- `runs/test-observatory/latest.json`: pointer to the newest observatory run.

Private recursive reasoning is neither printed nor stored. The evidence records only its character count; visible final output and its hash remain available for validation.
