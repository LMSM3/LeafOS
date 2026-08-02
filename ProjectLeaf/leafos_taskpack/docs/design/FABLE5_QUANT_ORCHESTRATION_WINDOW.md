# Fable5 Quant Orchestration Window

## Purpose

Provide a read-only operations surface for the verified Fable5 quantization stack. It orders benchmark work and exposes readiness without granting a model authority over files, graph state, patches, validation, gates, hashes, or reports.

**Authority rule:** models propose; the CPU benchmark runner and validation pipeline own state, acceptance, and reporting.

## Inputs

| Input | Producer | Required fields |
|---|---|---|
| `fable5-benchmark-stack.json` | quant-stack preparation | ordinal, quant, artifact path, bytes, SHA-256, GGUF validity, classification |
| `fable5-all-quants-verify.json` | CPU artifact verification | bytes, SHA-256, GGUF header, interactive eligibility |
| `fable5-benchmark-results.json` | `fullstackbench.py` | quant, timing, synthetic token-pump throughput, checksum, safety notes |

All paths are local. The surface must render an explicit `MISSING`, `INVALID`, or `STALE` state rather than inventing readiness.

## Read-only wireframe

```text
LeafOS / Fable5 Quant Orchestration

STACK: Fable5 Composer2.5 | mode: sequential | network: not required
AUTHORITY: CPU validation, benchmark runner, gates, hashes, reports

#  QUANT    ARTIFACT   INTERACTIVE     BENCHMARK       RESULT
1  Q2_K     VERIFIED   NO (benchmark) queued/completed <timing | failure>
2  Q3_K_M   VERIFIED   YES             queued/completed <timing | failure>
3  Q4_K_M   VERIFIED   YES (default)   queued/completed <timing | failure>
4  Q6_K     VERIFIED   YES             queued/completed <timing | failure>
5  Q8_0     VERIFIED   YES             queued/completed <timing | failure>

Selected: Q4_K_M — default local coder quant
Last validation: <timestamp from verification record>
Last benchmark:  <timestamp from benchmark result>

[Enter] Details  [R] Refresh local state  [L] View reports  [B] Run bounded bench
[I] Prepare install plan  [Q] Back
```

## State model

```json
{
  "leafos_object": "fable5_quant_orchestration_window",
  "schema_version": 1,
  "mode": "read_only",
  "authority": "cpu",
  "stack_source": "fable5-benchmark-stack.json",
  "entries": [
	{
	  "ordinal": 3,
	  "quant": "Q4_K_M",
	  "artifact_state": "verified",
	  "interactive_state": "eligible",
	  "benchmark_state": "completed",
	  "result_ref": "fable5-benchmark-results.json"
	}
  ],
  "actions": {
	"refresh": {"mutates": false},
	"view_reports": {"mutates": false},
	"run_bounded_benchmark": {"mutates": true, "confirmation": "required"},
	"prepare_install_plan": {"mutates": false},
	"apply_install": {"available_here": false, "confirmation": "separate explicit flow"}
  }
}
```

## Safety boundaries

- `Refresh` only rereads local manifests and result files.
- `Run bounded bench` runs the local synthetic orchestration benchmark. It does **not** claim GGUF/llama.cpp inference throughput.
- Q2 is visible and benchmarkable, but `interactive_state` remains `ineligible` until the runtime compatibility issue is independently fixed and revalidated.
- `Prepare install plan` may create an offline plan only. Download/resume/apply remains a separate explicit confirmation flow.
- Any future real inference benchmark must separately record the llama.cpp version, model path/hash, context, thread/GPU settings, prompt, tokens, exit code, and raw logs.
