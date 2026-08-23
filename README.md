# LeafOS reduced core — Alpha 0.2.4

This is the reduced successor to the 0.2.3 prototype tree. It has one control
surface and one execution path:

```text
leafctl -> scanned real GGUF -> validated pack lane -> llama-cli -> output
```

`🌿` is emitted only when configuration parses, `llama-cli` answers, and the
last real scan contains at least one usable GGUF. Missing files, malformed
packs, and dead runtimes are errors; no placeholder becomes healthy evidence.

## Commands

```text
leafctl doctor
leafctl models scan
leafctl models list
leafctl run MODEL --prompt "Hello"
leafctl pack list
leafctl pack show PACK
leafctl pack use PACK
leafctl route LANE --prompt "Task"
leafctl status
```

The Bash, PowerShell, and CMD files in `bin/` are compatibility launchers for
the same Python CLI. They do not implement alternate behavior.

## Active 1.0 development track

The approved [1.0.0 long-loop plan](plans/LEAFOS_1.0.0_LONG_LOOP_RUNTIME_PLAN.md)
is active. Phases A through D provide the bounded worker, evidence, verification,
and immutable epoch foundation. Phase E recovery controls are implemented and the
clock-dependent six-hour soak is running. The maintained
[runtime diagram](docs/leafos-runtime-diagram.html) shows only verified current
lanes and labels later phases as planned.

```text
leafctl swarm plan --project PATH --objective "Objective"
leafctl task submit --project PATH --goal "Inspect source" --lane fast --input README.md --class critical --defer
leafctl swarm status --project PATH
leafctl swarm run --project PATH --workers 2
leafctl swarm foreground --project PATH on
leafctl swarm stop --project PATH
leafctl swarm checkpoint --project PATH --reason "epoch boundary"
leafctl swarm recover --project PATH
leafctl swarm soak --project PATH --hours 6 --sample-seconds 30
leafctl swarm fault --project PATH --kind worker-kill --outcome passed --detail "verified recovery evidence"
leafctl task tool --project PATH task-000001 --tool search --path README.md --query VERSION
leafctl task verify --project PATH task-000001
leafctl task dispute --project PATH task-000001 --evidence evidence-000003 --reason "Citation conflict"
leafctl task accept --project PATH task-000001 --reason "Primary review passed"
leafctl task inspect --project PATH task-000001
leafctl epoch status --project PATH
leafctl epoch configure --project PATH --minutes 30
leafctl epoch review --project PATH --manual
leafctl context export --project PATH
```

Project control state is stored under the selected project's ignored `.leaf/`
directory. Objective, task graph, journal, evidence, and output records are
integrity checked. Project source inputs are bounded, hashed at submission,
revalidated before execution, and preserved as immutable evidence snapshots.
A sealed `scheduler.json` records one supervisor, 2–4 worker slots, one
verifier slot, queue/resource state, and the foreground gate. Each OS-process
worker holds a task lease token, sends heartbeats, and owns exactly one
task-artifact path. The default is two workers; four is the hard maximum.
A real local-model result stops at `verifying`; a worker cannot accept its own
conclusion. Tools only append bounded evidence. A distinct pack-backed verifier
only appends a verdict. Acceptance remains a separate controller action and is
blocked by failed provenance, rejecting evidence, or a persisted contradiction.
Epoch review defaults to 30 minutes and can be invoked manually. Every review
seals an immutable manifest, evidence index, failure ledger, decision slice,
next plan, and stable text/JSON context packet. The packet records raw and
strategic byte/token estimates, deduplicates repeated text without dropping
evidence IDs, detects contradictions before summarization, and retains a link
from each accepted decision to its supporting evidence.

Phase E extends those records without adding another public control surface.
Worker and verifier leases carry a boot-scoped host-session identity and bind the
llama.cpp child PID they own. Recovery never trusts a recycled PID after a host
restart, and stop/cancel/preemption terminate the owned worker/model process tree
before releasing the lease. Immutable recovery checkpoints seal the objective,
task graph, scheduler, epoch state, acceptance links, and append-only journal and
decision prefixes. Soak telemetry persists resource observations and scheduler
latency across controller restart. A fault can be marked passed only when LeafOS
finds post-soak runtime, evidence, checkpoint, or sealed journal proof.

The [Verdant Quant Lab](examples/stock-analysis-lab/README.md) is the first
README-and-seed Phase D workload. It is a dependency-free modular Python
research engine covering covariance/shrinkage, tail risk, factor regression,
four portfolio optimizers, correlated GBM simulation, and cost-aware
walk-forward backtesting. Its synthetic report and LeafOS `.leaf` records are
checked in as reproducible workload evidence, not current financial advice.

`VERSION` remains `0.2.4` while the 1.0 track is under development. The 1.0.0
identity is still gated by completion of the active six-hour recovery soak and
interface-freeze evidence. Phase E currently has 76 passing tests with the real
GGUF gate unskipped and five verified live fault classes, but it is not complete
until the duration and multi-epoch gates close.

## 0.2.4 release ledger

| Assumption | Status | Evidence / consequence |
|---|---|---|
| The legacy `leafctl status` proves a usable local lane | CONTRADICTED | It selected configured role names without requiring a real GGUF load path. |
| Calliope and Oxalis are installed packs on this host | CONTRADICTED | Their configured Muse/Oxalis artifacts are absent from the scanned model root. They are not copied here as active packs. |
| llama.cpp and Vulkan are unavailable | CONTRADICTED | Local `llama-cli` build 9957 reports an RTX 4070 Vulkan device. |
| Real GGUF files are available | TIME-SENSITIVE | `~/.leaf/models` contained 11 GGUF paths on 2026-08-20; `models scan` must recheck this mutable fact. |
| All 11 GGUF paths are complete models | CONTRADICTED | Tensor-bound validation found 10 complete files and rejected `_test_direct.gguf` as a 50 MB partial copy of a 5.32 GB model. |
| The reduced runtime path executes real work | TIME-SENSITIVE | Q2_K cold/repeated load, Q3_K_M model switch, interruption, and clean shutdown passed through `leafctl run`; the 76-test suite passed with its real-GGUF gate unskipped on 2026-08-20. Recheck when llama.cpp, drivers, or models change. |
| Calliope is ready for activation | UNVERIFIED | No installed Calliope/Muse artifact maps to a real lane on this host; the pack is intentionally absent. |
| Bounded scheduling is absent | EXPIRED | Phase C now provides dependency-aware OS-process slots, lease/heartbeat recovery, cancellation, resource/foreground policy, and a dedicated verifier slot. |
| Epoch review and bounded strategic context are absent | EXPIRED | Phase D now emits immutable epoch records and stable v2 context packets; unit and live workload packets retain provenance and enforce the 20%/evidence-floor accounting rule. |
| Recovery checkpoints and soak telemetry are absent | EXPIRED | Phase E now seals compact recovery snapshots, verifies append-only prefixes, binds model PIDs to boot-scoped leases, and records resumable resource/latency telemetry. |
| Every scheduling sensor is available | CONTRADICTED | Host CPU, RAM, NVIDIA GPU/VRAM, queue, disk capacity, and GPU thermal values were observed on 2026-08-20; disk throughput and KV-cache use remain explicitly `unavailable`. |
| LeafOS 1.0.0 is released | CONTRADICTED | Phases A–D are complete, but the six-hour recovery soak, interface freeze, and remaining 1.0 gates are not. `VERSION` therefore remains `0.2.4`. |
| Phase E is complete because its tests pass | CONTRADICTED | The 76-test real-GGUF suite and five live fault proofs pass, but the active soak has not yet reached six hours. |

## Gates

- Real Model: implemented by `models scan`; invalid paths never become usable.
- Runtime: one `run` path owns start, interruption, and shutdown state.
- Pack: one small format maps lanes to scanned model IDs.
- Status: eight ordinary diagnostic lines; JSON is optional.
- Recovery: failures are explicit and retain the last error in `logs/state.json`.
- Clean install: the installers only copy files, expose `leafctl`, and run doctor.

The real-runtime test is never satisfied by a generated fixture. Set
`LEAF_TEST_MODEL` to an installed GGUF to run it. The tiny GGUF constructed by
the unit suite tests metadata parsing only and is explicitly marked unusable.

The preserved historical source is `C:\R\LeafOS0.2.3` at commit `b73f1ec` plus
its user-owned working changes. It is not part of the 0.2.4 execution surface.
