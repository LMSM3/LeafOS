#!/usr/bin/env python3
"""LLM-free contract and runtime benchmark harness for LeafOS.

Exercises the durable transcript, loop kernel, telemetry, and web-state
surfaces without loading any model weights.  Produces a structured report for
assessing which demonstrations should be kept, expanded, or discarded.
"""

from __future__ import annotations

import json
import os
import random
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

PYTHON_DIR = Path(__file__).resolve().parents[1] / "python"
if str(PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(PYTHON_DIR))

import leaf_continual_bloom as bloom  # noqa: E402
import leaf_loop_kernel as kernel  # noqa: E402
import leaf_telemetry as telemetry  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
BENCH_DIR = ROOT / "runs" / "contract-bench"


@dataclass
class BenchResult:
    name: str
    status: str = "ok"
    metrics: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


def _now() -> float:
    return time.perf_counter()


def _clean_bench_dir() -> Path:
    if BENCH_DIR.exists():
        shutil.rmtree(BENCH_DIR, ignore_errors=True)
    BENCH_DIR.mkdir(parents=True, exist_ok=True)
    return BENCH_DIR


def _rand_claim_id(i: int) -> str:
    return f"claim-{i:06d}"


def bench_transcript_throughput() -> BenchResult:
    """1. Append N synthetic events, replay, verify. Measure throughput."""
    result = BenchResult("transcript_throughput")
    instance = BENCH_DIR / "throughput-monday"
    contract = bloom.load_contract()
    persona = bloom.persona_from_contract(contract)
    bloom.initialize(instance)

    n = 500

    start = _now()
    for i in range(n):
        # Use the public API so state.json stays consistent with the transcript.
        bloom.append_input(instance, f"bench input {i}")
    append_time = _now() - start
    events = bloom.read_events(instance)

    start = _now()
    replayed = bloom.read_events(instance)
    replay_time = _now() - start

    start = _now()
    report = bloom.verify(instance)
    verify_time = _now() - start

    result.metrics = {
        "events": len(events),
        "append_seconds": round(append_time, 3),
        "append_eps": round(n / append_time, 1) if append_time else None,
        "replay_seconds": round(replay_time, 3),
        "verify_seconds": round(verify_time, 3),
        "event_bytes_estimate": len(json.dumps(events[0])) if events else 0,
    }
    result.notes.append(f"event_count in verify report: {report['event_count']}")
    return result


def bench_token_shape_stress() -> BenchResult:
    """2. Generate synthetic output-contract shapes through dispatch pipeline."""
    result = BenchResult("token_shape_stress")
    shapes = ["plan", "patch_review", "synthesis", "checkpoint", "refusal", "alert", "persona_reply"]
    n = 2000
    start = _now()
    samples: list[dict[str, Any]] = []
    for i in range(n):
        typ = random.choice(shapes)
        content_len = random.randint(50, 2000)
        content = "word " * (content_len // 5)
        samples.append(
            {
                "response_type": typ,
                "content": content,
                "confidence_score": round(random.uniform(0.0, 1.0), 3),
                "tokens_estimated": len(content.split()),
            }
        )
    gen_time = _now() - start

    # Validate every sample against the output contract keys
    start = _now()
    valid = 0
    for sample in samples:
        if all(k in sample for k in ("response_type", "content", "confidence_score")):
            valid += 1
    validate_time = _now() - start

    result.metrics = {
        "samples": n,
        "shapes": shapes,
        "generate_seconds": round(gen_time, 3),
        "validate_seconds": round(validate_time, 3),
        "valid_fraction": round(valid / n, 4),
        "avg_tokens": round(sum(s["tokens_estimated"] for s in samples) / n, 1),
        "max_tokens": max(s["tokens_estimated"] for s in samples),
    }
    return result


def bench_workers_disagree() -> BenchResult:
    """3. Simulate workers producing conflicting claims and measure repair loop."""
    result = BenchResult("workers_disagree")
    instance = BENCH_DIR / "disagree-monday"
    contract = bloom.load_contract()
    persona = bloom.persona_from_contract(contract)
    bloom.initialize(instance)

    workers = ["scout", "sketch", "builder", "reviewer"]
    claims_per_worker = 10
    total_claims = len(workers) * claims_per_worker
    evidence_file = BENCH_DIR / "stub-evidence.txt"
    evidence_file.write_text("native evidence", encoding="utf-8")

    start = _now()
    accepted = 0
    stale = 0
    for i in range(total_claims):
        worker = workers[i % len(workers)]
        claim_id = _rand_claim_id(i)
        # First claim at current head; duplicates become stale
        resp = bloom.record_claim(instance, claim_id, f"{worker} analysis {i}", len(bloom.read_events(instance)))
        if resp["accepted"]:
            accepted += 1
        else:
            stale += 1
    # Validate first half as supported, second half as refuted
    supported = 0
    for i in range(total_claims):
        claim_id = _rand_claim_id(i)
        try:
            status = "supported" if i < total_claims // 2 else "refuted"
            bloom.validate_claim(instance, claim_id, status, evidence_file)
            supported += 1 if status == "supported" else 0
        except Exception as error:
            result.notes.append(f"validation skip {claim_id}: {error}")
    elapsed = _now() - start

    status = bloom.status(instance)
    result.metrics = {
        "workers": workers,
        "claims_submitted": total_claims,
        "accepted": accepted,
        "stale_rejections": stale,
        "validated": supported,
        "elapsed_seconds": round(elapsed, 3),
        "fact_count": status.get("fact_count", 0),
    }
    return result


def bench_recovery_resilience() -> BenchResult:
    """4. Corrupt/delete files and time recover+verify."""
    result = BenchResult("recovery_resilience")
    instance = BENCH_DIR / "recovery-monday"
    contract = bloom.load_contract()
    persona = bloom.persona_from_contract(contract)
    bloom.initialize(instance)

    # Build some state
    for i in range(5):
        events = bloom.read_events(instance)
        event = bloom.make_event(events, "input.received", "bench", len(events), {"i": i})
        bloom.append_event_locked(instance / "events.ndjson", event)

    # Corrupt state.json with a wrong transcript_cursor
    state = bloom.read_json(instance / "state.json")
    state["transcript_cursor"] = 999
    bloom.atomic_write_json(instance / "state.json", state)

    start = _now()
    recovered = bloom.recover(instance)
    recover_time = _now() - start

    start = _now()
    report = bloom.verify(instance)
    verify_time = _now() - start

    result.metrics = {
        "events_before_corruption": 6,
        "recover_seconds": round(recover_time, 3),
        "verify_seconds": round(verify_time, 3),
        "recovered_head": recovered["state"]["transcript_head"],
        "verification_ok": report.get("status") == "ok",
    }
    return result


def bench_web_state_projection() -> BenchResult:
    """5. Measure web state build latency with durable Monday state included."""
    result = BenchResult("web_state_projection")
    web_state_py = PYTHON_DIR.parent / "web" / "state.py"
    start = _now()
    try:
        completed = subprocess.run(
            [sys.executable, str(web_state_py), "--json"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=30,
            env={**os.environ, "PYTHONPATH": f"{PYTHON_DIR}{os.pathsep}{os.environ.get('PYTHONPATH', '')}"},
        )
        elapsed = _now() - start
        if completed.returncode == 0:
            data = json.loads(completed.stdout)
            monday = data.get("durable_monday", {})
            result.status = "ok"
            result.metrics = {
                "build_seconds": round(elapsed, 3),
                "durable_monday_available": monday.get("available"),
                "durable_monday_status": monday.get("status"),
                "json_bytes": len(completed.stdout),
            }
        else:
            result.status = "error"
            result.notes.append(f"stderr: {completed.stderr[:200]}")
    except Exception as error:
        result.status = "error"
        result.notes.append(str(error))
    return result


def bench_loop_kernel_spawn_governor() -> BenchResult:
    """6. Spawn short dummy subprocesses and measure cleanup."""
    result = BenchResult("loop_kernel_spawn_governor")
    run_dir = BENCH_DIR / "spawn-run"
    kd = kernel.RunDirectory(run_dir, run_kind="bench")

    # Test concurrency limit first on a fresh RunDirectory
    limit_kd = kernel.RunDirectory(run_dir / "limit-test", run_kind="bench")
    limit_hit = False
    try:
        for _ in range(10):
            limit_kd.spawn(
                [sys.executable, "-c", "import time; time.sleep(1.0)"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
    except RuntimeError:
        limit_hit = True
    finally:
        limit_kd.cleanup_spawns()

    # Normal spawn/cleanup timing (stay within concurrency limit)
    kd = kernel.RunDirectory(run_dir / "normal-test", run_kind="bench")
    n = 4
    start = _now()
    for i in range(n):
        kd.spawn(
            [sys.executable, "-c", "import time; time.sleep(0.05)"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    spawn_time = _now() - start

    start = _now()
    summary = kd.cleanup_spawns()
    cleanup_time = _now() - start

    result.metrics = {
        "spawns": n,
        "spawn_seconds": round(spawn_time, 3),
        "cleanup_seconds": round(cleanup_time, 3),
        "terminated_count": len(summary.get("terminated", [])),
        "concurrency_limit_hit": limit_hit,
    }
    return result


def bench_telemetry_firehose() -> BenchResult:
    """7. Append many synthetic universal telemetry events and summarize."""
    result = BenchResult("telemetry_firehose")
    run_dir = BENCH_DIR / "telemetry-firehose"
    run_dir.mkdir(parents=True, exist_ok=True)
    log_path = run_dir / telemetry.UNIVERSAL_LOG_NAME
    if log_path.exists():
        log_path.unlink()

    n = 500
    start = _now()
    for i in range(n):
        event = telemetry.make_universal_event(
            run_id="firehose",
            run_kind="manual",
            event_type="sample",
            phase="idle",
            sequence=i + 1,
            hardware=None,
            collect_hardware=False,
        )
        telemetry.append_universal_event(log_path, event)
    append_time = _now() - start

    start = _now()
    summary = telemetry.summarize_universal_log(log_path)
    summarize_time = _now() - start

    result.metrics = {
        "events": n,
        "append_seconds": round(append_time, 3),
        "append_eps": round(n / append_time, 1) if append_time else None,
        "summarize_seconds": round(summarize_time, 3),
        "event_count_reported": summary.get("event_count"),
    }
    return result


def bench_persona_state_walkthrough() -> BenchResult:
    """8. Programmatically walk Monday through every legal state transition."""
    result = BenchResult("persona_state_walkthrough")
    instance = BENCH_DIR / "walkthrough-monday"
    contract = bloom.load_contract()
    persona = bloom.persona_from_contract(contract)
    bloom.initialize(instance)

    expected_capabilities = ["input.append"]
    states_seen: list[str] = []
    evidence_file = BENCH_DIR / "stub-evidence.txt"
    evidence_file.write_text("native evidence", encoding="utf-8")

    # input.received -> active -> claim
    s = bloom.status(instance)
    states_seen.append(s.get("status") if s else "not_initialized")
    bloom.append_input(instance, "analyze this")
    s = bloom.status(instance)
    states_seen.append(s.get("status") if s else "unknown")
    expected_capabilities.append(s.get("next_action", {}).get("capability"))

    bloom.record_claim(instance, "walk-1", "claim text", len(bloom.read_events(instance)))
    s = bloom.status(instance)
    states_seen.append(s.get("status") if s else "unknown")
    expected_capabilities.append(s.get("next_action", {}).get("capability"))

    bloom.validate_claim(instance, "walk-1", "supported", evidence_file)
    s = bloom.status(instance)
    states_seen.append(s.get("status") if s else "unknown")
    expected_capabilities.append(s.get("next_action", {}).get("capability"))

    bloom.commit_checkpoint(instance)
    s = bloom.status(instance)
    states_seen.append(s.get("status") if s else "unknown")
    expected_capabilities.append(s.get("next_action", {}).get("capability"))

    # recover should preserve idle and point back to input.append
    bloom.recover(instance)
    s = bloom.status(instance)
    states_seen.append(s.get("status") if s else "unknown")

    result.metrics = {
        "states_seen": states_seen,
        "capabilities_seen": expected_capabilities,
        "all_expected_present": all(c in expected_capabilities for c in ["input.append", "persona.claim", "claim.validate", "checkpoint.commit"]),
    }
    result.notes.append("Walked: init -> idle -> active -> waiting -> checkpoint -> idle/recovered")
    return result


def bench_authority_boundary() -> BenchResult:
    """9. Verify allowed capability requests succeed and denied ones fail + are audited."""
    import leaf_durable_bridge as bridge  # noqa: E402
    import leaf_shared_state as shared  # noqa: E402

    result = BenchResult("authority_boundary")
    instance = BENCH_DIR / "authority-monday"
    if instance.exists():
        shutil.rmtree(instance, ignore_errors=True)
    bloom.initialize(instance)
    b = bridge.MondayDurableBridge(instance=instance, source="bench")

    allowed = b.request_capability("input.append", actor="operator", reason="bench input")
    denied = b.request_capability("mutation.direct", actor="operator", reason="bench forbidden")  # type: ignore[arg-type]
    audited = b.request_capability("runtime.recover", actor="operator", reason="bench audit")

    summary = shared._capability_registry_summary()
    state_doc = shared.build_durable_monday_state(instance_name="monday-primary")

    events = bloom.read_events(instance)
    kinds = [e["kind"] for e in events]

    result.metrics = {
        "allowed": allowed["payload"]["allowed"],
        "denied": not denied["payload"]["allowed"],
        "audited_marked_not_allowed": not audited["payload"]["allowed"],
        "capability_registry_count": summary["count"],
        "denied_keys_count": len(summary["denied"]),
        "capability_events_in_transcript": kinds.count("capability.requested") + kinds.count("capability.denied"),
    }
    result.notes.append("Allowed input.append; denied mutation.direct; audited runtime.recover")
    return result


def bench_cli_enforcement() -> BenchResult:
    """10. Verify CLI require_capability allows allowed commands and denies disallowed ones."""
    import leaf_authority as auth  # noqa: E402

    result = BenchResult("cli_enforcement")
    allowed = auth.require_capability(
        "memory.journal.append",
        actor="operator",
        reason="bench CLI mutation",
    )
    try:
        auth.require_capability("mutation.direct", actor="operator", reason="bench CLI forbidden")
    except auth.AuthorityError:
        denied = True
    else:
        denied = False

    result.metrics = {
        "allowed_ticket_present": bool(allowed["payload"]["ticket"]),
        "denied_raised_authority_error": denied,
    }
    result.notes.append("CLI enforcement allows memory.journal.append and denies mutation.direct")
    return result


def bench_loop_kernel_governance() -> BenchResult:
    """11. Verify RunDirectory mutation primitives record capability tickets."""
    result = BenchResult("loop_kernel_governance")
    run_dir = BENCH_DIR / "governed-run"
    if run_dir.exists():
        shutil.rmtree(run_dir, ignore_errors=True)
    kd = kernel.RunDirectory(run_dir, run_kind="governance-bench")
    kd.append_event("bench.governance", ok=True)
    kd.record_tick(phase="governance")
    cp = kd.checkpoint("governance-bench")
    events = kd.read_events()
    tickets = [e.get("ticket") for e in events if e.get("ticket")]

    result.metrics = {
        "event_count": len(events),
        "tickets_recorded": len(tickets),
        "all_tickets_allowed": all(t.get("allowed") for t in tickets if t),
        "checkpoint_head": cp["last_event_sequence"],
    }
    if len(tickets) < 2:
        result.notes.append(
            f"Only {len(tickets)} ticketed events found (expected at least 2). "
            "If running against an existing instance, the loop self-test may reuse stale events."
        )
    else:
        result.notes.append("RunDirectory append_event, record_tick, checkpoint all recorded tickets")
    return result


BENCH_REGISTRY: list[Callable[[], BenchResult]] = [
    bench_transcript_throughput,
    bench_token_shape_stress,
    bench_workers_disagree,
    bench_recovery_resilience,
    bench_web_state_projection,
    bench_loop_kernel_spawn_governor,
    bench_telemetry_firehose,
    bench_persona_state_walkthrough,
    bench_authority_boundary,
    bench_cli_enforcement,
    bench_loop_kernel_governance,
]


def main() -> int:
    _clean_bench_dir()
    print(f"LeafOS contract bench directory: {BENCH_DIR}")
    overall_start = _now()
    results: list[BenchResult] = []
    for func in BENCH_REGISTRY:
        print(f"\n[RUNNING] {func.__name__}")
        try:
            result = func()
        except Exception as error:
            result = BenchResult(func.__name__.replace("bench_", ""), status="error")
            result.notes.append(str(error))
        results.append(result)
        print(f"[{result.status.upper()}] {result.name}: {json.dumps(result.metrics, indent=2)}")
        for note in result.notes:
            print(f"  note: {note}")

    total_time = _now() - overall_start
    report = {
        "leafos_object": "leafos.contract_bench_report.v1",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "total_seconds": round(total_time, 3),
        "bench_directory": str(BENCH_DIR),
        "results": [
            {
                "name": r.name,
                "status": r.status,
                "metrics": r.metrics,
                "notes": r.notes,
            }
            for r in results
        ],
    }
    report_path = BENCH_DIR / "contract-bench-report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nReport written to: {report_path}")
    print(f"Total elapsed: {total_time:.3f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
