# WO-006-A - Top-Level Operator Interface

```text
[W] WO-006-A: Build the easy top-level LeafOS operator interface.
[D] Stage 0.6 usability lane opened after provider-spine and root-surface work.
[I] DONE: read-only home state, terminal/JSON home, next action, trace, accelerator state, and shell parity implemented.
[V] PASS: focused home tests, Bash syntax, Bash routes, and PowerShell routes.
[P] LOCAL: source, tests, and completion report in the canonical taskpack.
[N] Configure the Vulkan provider executable/model to advance from CPU fallback to GPU provider ready.
```

## 1. Purpose

Create a single friendly top-level interface for LeafOS.

The operator should not need to remember whether a task starts in Bash,
PowerShell, `leafctl`, `leaf.ps1`, the dashboard, chat, provider status, runtime
selection, or model installer paths.

The interface should answer five questions quickly:

```text
1. Is LeafOS ready?
2. Is my local stack provider running?
3. Is Vulkan/GPU acceleration actually visible?
4. What task or work order am I on?
5. What safe next action can I take?
```

This work order turns the scattered control surfaces into one operator home.

## 2. Existing Surfaces To Unify

Known local entrypoints:

```text
PowerShell-Version/leaf.ps1
ProjectLeaf/leafos_taskpack/bin/leafctl
ProjectLeaf/leafos_taskpack/bin/leafctl.ps1
ProjectLeaf/leafos_taskpack/core/ui/dashboard.py
ProjectLeaf/leafos_taskpack/core/ui/chat.py
ProjectLeaf/leafos_taskpack/core/web/state.py
PowerShell-Version/serve-llamacpp.ps1
```

Known useful commands:

```text
leaf status
leaf doctor
leaf dashboard
leaf web-state --json
leaf runtime select
leaf provider-status
leaf provider test llamacpp --json
leaf chat
leaf model list
leaf models-install plan --profile runtime-default
```

The top-level interface should wrap and explain these routes without duplicating
their core logic.

## 3. Operator Contract

The interface shall support three modes:

```text
friendly home      default guided screen for humans
direct commands    stable subcommands for repeated use
json output        machine-readable status for automation and tests
```

Proposed command map:

```text
leaf home
leaf next
leaf doctor
leaf provider start
leaf provider status
leaf provider test
leaf runtime
leaf task new "TITLE"
leaf task run TASK_OR_GRAPH
leaf task watch TASK_OR_GRAPH
leaf docs
leaf trace latest
```

PowerShell aliases should work from the root surface:

```powershell
.\leaf.ps1 home
.\leaf.ps1 next
.\leaf.ps1 provider status
.\leaf.ps1 trace latest
```

Bash aliases should work from the taskpack surface:

```bash
./bin/leafctl home
./bin/leafctl next
./bin/leafctl provider status
./bin/leafctl trace latest
```

## 4. Home Screen

The default human view should be compact and action-oriented:

```text
LeafOS Home

Readiness      doctor: ok | warn | fail
Provider       llamacpp: running | stopped | timeout | cpu-only | vulkan-visible
Accelerator    gpu-stack: available | disabled | degraded | cpu-fallback
Stack          downloaded/local model inventory, active runtime selections
Runtime        main / coder / scheduler stack entries
GPU            device name, backend, visible layers, last probe time
Work Order     active WO, stage, next gate
Task Loop      latest graph/run state, ready nodes, blocked nodes
Recent Runs    latest reports and logs
Next Actions   safe commands the operator can run now
```

The home screen may be terminal-first. A browser UI is allowed later only if it
is backed by the same JSON state contract.

## 5. Provider And GPU Panel

Because the current local problem is that GPU-backed llama.cpp does not stay up,
the first interface pass must make provider state visible.

Minimum displayed fields:

```text
provider mode
LEAF_LLAMACPP_URL
llama-server process visible: yes/no/unknown
HTTP health check: ok/refused/timeout
backend requested: vulkan/cpu/auto
backend detected: vulkan/cpu/unknown
visible GPU devices
model path
context size
gpu layers
last error summary
safe start command
```

The interface must distinguish these cases:

```text
Vulkan runtime sees GPU, but llama.cpp build is CPU-only.
llama.cpp server started, then exited.
llama.cpp server is running, but HTTP endpoint is not ready.
LeafOS provider env vars are unset.
Provider is healthy enough for a test prompt.
```

### 5.1 GPU Sister Stack Boundary

The GPU lane is an optional sister stack, not the authority layer and not a hard
boot dependency.

Design intent:

```text
LeafOS CPU control plane
  -> optional GPU provider stack
  -> bounded model proposal
  -> CPU parser and policy gate
  -> accepted artifact or CPU fallback
```

The GPU stack may be started, stopped, replaced, or upgraded without breaking
the rest of LeafOS. CPU remains the fallback path for readiness checks, graph
state, parsing, validation, filesystem writes, reporting, and recovery.

Required capability states:

```text
gpu_available        operating system sees an accelerator
gpu_backend_ready    provider build exposes Vulkan/CUDA/other supported backend
gpu_provider_ready   provider HTTP/API endpoint is healthy
gpu_degraded         GPU visible but provider stack is missing or unstable
cpu_fallback         CPU path can continue safely
offline              no provider path is available, mock and dry-run remain usable
```

The interface must present GPU as an accelerator, not as the whole system.

Minimum commands:

```text
leaf accelerator status
leaf accelerator test
leaf accelerator start --backend vulkan
leaf accelerator stop
leaf accelerator fallback cpu
```

`provider` remains the model-call abstraction. `accelerator` is the local
hardware/runtime availability surface. This keeps future CUDA, Vulkan, DirectML,
ROCm, NPU, and remote worker lanes from leaking into every task command.
`stack` remains the local downloaded model inventory for this LeafOS instance.

### 5.2 Dual-Run Python Handoff

After the GPU sister stack is stable, it should feed the dual-run Python
architecture as a selectable execution lane.

The interface contract should not assume the final filename yet. The current
repository does not contain a literal `dual-run.py` or `dual run py` path, so
the work order records the handoff by role:

```text
run A: CPU-authoritative state, parser, gate, filesystem, report
run B: optional accelerated proposal lane using llama.cpp/Vulkan or fallback CPU
join: parser accepts, repairs, or rejects the proposal with evidence
```

The later implementation should define a stable JSON handoff object between the
two runs:

```json
{
  "leafos_object": "dual_run_handoff",
  "version": "0.6.0-A",
  "run_id": "run identifier",
  "control_plane": "cpu",
  "proposal_lane": "gpu|cpu|mock",
  "provider": "llamacpp",
  "backend": "vulkan|cpu|unknown",
  "input_hash": "sha256:...",
  "proposal_hash": "sha256:...",
  "accepted": false,
  "evidence": []
}
```

## 6. Trace View

The user should be able to inspect what is happening under the hood without
pretending that hidden model reasoning is a stable API.

Accepted trace surface:

```text
graph nodes
node statuses
selected actions
provider requests
provider response metadata
retry counts
timeouts
tool commands
validation gates
patch previews
test results
logs and report paths
operator confirmations
```

Rejected trace surface:

```text
private chain-of-thought dumps
unverified model self-explanations
uncaptured "internal recursive thinking" claims
```

The interface should name this honestly as:

```text
observable loop trace
```

not:

```text
raw mind
```

## 7. Safety Rules

The top-level interface must remain local-first and explicit.

Forbidden by default:

```text
auto-download model weights
auto-install dependencies
auto-start hidden background services
auto-apply patches
auto-delete or move project files
auto-send data to remote services
```

Actions that mutate files, start persistent providers, download artifacts, or
apply patches require a visible command and a confirmation boundary.

## 8. Implementation Plan

### 8.1 State Contract

Create or extend a JSON state object that can power both terminal and future web
views.

Suggested file:

```text
core/ui/home_state.py
```

Suggested command:

```text
leaf home --json
```

Required top-level keys:

```json
{
  "leafos_object": "home_state",
  "version": "0.6.0-A",
  "generated_at": "ISO-8601 timestamp",
  "root": "project root",
  "readiness": {},
  "provider": {},
  "accelerator": {},
  "stack": {},
  "runtime": {},
  "gpu": {},
  "work_order": {},
  "task_loop": {},
  "recent_runs": [],
  "next_actions": []
}
```

### 8.2 Terminal Home

Create a terminal renderer backed by the state contract.

Suggested file:

```text
core/ui/home.py
```

Suggested commands:

```text
leaf home
leaf home --json
leaf home --watch 2
leaf next
```

### 8.3 Command Routing

Wire the Bash and PowerShell entrypoints to the same behavior.

Suggested files:

```text
ProjectLeaf/leafos_taskpack/bin/leafctl
ProjectLeaf/leafos_taskpack/bin/leafctl.ps1
PowerShell-Version/leaf.ps1
```

Do not duplicate provider, runtime, graph, task, or model logic in wrappers.
Wrappers should delegate to the existing modules.

### 8.4 Trace View

Add an operator trace command that reads existing run artifacts first.

Suggested command:

```text
leaf trace latest
leaf trace RUN_ID
leaf trace latest --json
```

The first version may read:

```text
tasks/
runs/
reports/
logs/
agent.graph.json
provider test output
```

### 8.5 Provider Convenience

Add a friendly route for llama.cpp provider checks.

Suggested commands:

```text
leaf provider status
leaf provider test
leaf provider start
leaf provider start --backend vulkan --model fable
```

On Windows, `provider start` may delegate to:

```text
PowerShell-Version/serve-llamacpp.ps1
```

On Bash, it may print the equivalent supported start command until a stable
Bash launcher exists.

## 9. Acceptance Criteria

This work order is complete when:

```bash
./bin/leafctl home --json
./bin/leafctl home
./bin/leafctl next
./bin/leafctl provider status
./bin/leafctl provider test --json
./bin/leafctl accelerator status --json
./bin/leafctl accelerator fallback cpu
./bin/leafctl trace latest --json
```

run without unhandled exceptions from the taskpack root.

PowerShell parity is complete when:

```powershell
.\leaf.ps1 home --json
.\leaf.ps1 home
.\leaf.ps1 next
.\leaf.ps1 provider status
.\leaf.ps1 provider test --json
.\leaf.ps1 accelerator status --json
.\leaf.ps1 accelerator fallback cpu
.\leaf.ps1 trace latest --json
```

run without unhandled exceptions from `PowerShell-Version`.

Expected behavior with no provider running:

```text
home renders
provider status reports stopped/refused/timeout
provider test exits non-zero with a useful message
accelerator status reports gpu_degraded, cpu_fallback, or offline without crashing
next actions include a safe llama.cpp start command
```

Expected behavior with a CPU-only llama.cpp build:

```text
home renders
GPU panel reports that Vulkan may be visible to the OS while llama.cpp exposes no Vulkan device
accelerator status reports cpu_fallback
next actions recommend using a Vulkan-enabled llama.cpp build
```

Expected behavior with healthy llama.cpp provider:

```text
home renders
provider status is ok
provider test passes
accelerator status reports gpu_provider_ready when a GPU backend is active
next actions include task creation or chat
```

## 10. Verification Commands

Recommended initial checks:

```bash
bash -n ProjectLeaf/leafos_taskpack/bin/leafctl
bash ProjectLeaf/leafos_taskpack/tests/spine.sh
bash ProjectLeaf/leafos_taskpack/tests/graph.sh
```

Recommended PowerShell checks:

```powershell
pwsh -NoProfile -File PowerShell-Version\leaf.ps1 home --json
pwsh -NoProfile -File PowerShell-Version\leaf.ps1 doctor
pwsh -NoProfile -File PowerShell-Version\leaf.ps1 provider test llamacpp --json
pwsh -NoProfile -File PowerShell-Version\leaf.ps1 accelerator status --json
```

Optional provider check:

```powershell
pwsh -NoProfile -File PowerShell-Version\serve-llamacpp.ps1 --check-only --backend vulkan
```

## 11. Deliverables

```text
docs/work-orders/WO-006-A-top-level-interface.md
core/ui/home_state.py
core/ui/home.py
core/ui/trace.py
core/ui/accelerator_state.py
bin/leafctl home route
bin/leafctl next route
bin/leafctl trace route
bin/leafctl accelerator route
bin/leafctl.ps1 home route
bin/leafctl.ps1 next route
bin/leafctl.ps1 trace route
bin/leafctl.ps1 accelerator route
PowerShell-Version/leaf.ps1 provider-start delegation if needed
tests/home_state smoke check
reports/wo-006-a-top-level-interface.md
```

## 12. Done Means

The operator can open one LeafOS surface, see readiness, provider health,
runtime selection, GPU/provider mismatch hints, current work-order context, and
safe next actions.

The operator can also inspect an observable loop trace made from real artifacts:
graphs, logs, commands, test results, provider calls, and reports.

The interface does not claim access to hidden model thought. It shows the real
system loop LeafOS can audit and improve.
