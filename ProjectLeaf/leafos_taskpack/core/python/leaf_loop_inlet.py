#!/usr/bin/env python3
"""Top-level controller for persistent LeafOS continual loops."""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import re
import secrets
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PYTHON_DIR = Path(__file__).resolve().parent
if str(PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(PYTHON_DIR))

import leaf_agent_loop as engine  # noqa: E402
import leaf_authority as authority  # noqa: E402
try:
    from leaf_authority import AuthorityError
except Exception:  # pragma: no cover - optional during migrations
    AuthorityError = RuntimeError  # type: ignore
import leaf_loop_kernel as kernel  # noqa: E402
import leaf_telemetry  # noqa: E402
import leaf_work_order as work_orders  # noqa: E402

MEMORY_DIR = Path(__file__).resolve().parents[1] / "memory"
if str(MEMORY_DIR) not in sys.path:
    sys.path.insert(0, str(MEMORY_DIR))
import journal as native_journal  # noqa: E402


ROOT = Path(__file__).resolve().parents[2]
RUNS_ROOT = ROOT / "runs" / "agent-loop"
LIVE_INTAKE_ROOT = RUNS_ROOT / "live-intake"
PROVIDER_CONFIG = ROOT / "config" / "vulkan-provider-stack.json"
TERMINAL_STATES = {"complete", "blocked", "stopped", "drained"}
TASK_CONTROL_ACTIONS = {"submit", "prioritize", "retry", "cancel", "approve"}
TASK_MUTABLE_STATES = {"queued", "repair_queued", "blocked", "failed"}
TASK_ID_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9._-]{2,63}$")
WORKER_LEASE_GRACE_SECONDS = 5.0
MONITOR_DEFAULT_INTERVAL_SECONDS = 2.0
MONITOR_DEFAULT_HEARTBEAT_TIMEOUT_SECONDS = 90.0
MONITOR_EXIT_FAILURE = 2
MONITOR_EXIT_STALE = 3
MONITOR_EXIT_TIMEOUT = 4


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_provider_config() -> dict[str, Any]:
    config = engine.read_json(PROVIDER_CONFIG, {})
    if not isinstance(config, dict):
        raise ValueError(f"invalid provider configuration: {PROVIDER_CONFIG}")
    return config


def provider_endpoint(config: dict[str, Any]) -> str:
    server = config.get("server", {})
    api = config.get("api", {})
    host = str(server.get("host", "127.0.0.1"))
    port = int(server.get("port", 8080))
    path = str(api.get("path", "/v1/chat/completions"))
    return f"http://{host}:{port}{path}"


def provider_healthy(endpoint: str, timeout: float = 2.0) -> bool:
    base = endpoint.split("/v1/", 1)[0].rstrip("/")
    try:
        with urllib.request.urlopen(base + "/health", timeout=timeout) as response:
            return 200 <= int(response.status) < 300
    except (OSError, urllib.error.URLError, TimeoutError):
        return False


def _inlet_ticket(capability: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
    response = authority.require_capability(
        capability,
        actor="loop-inlet",
        reason="loop inlet mutation",
        context=context or {},
        source="loop-inlet",
    )
    return response["payload"]["ticket"]


def start_provider_stack(config: dict[str, Any], *, run_dir: Path | None = None) -> tuple[bool, str]:
    ticket = _inlet_ticket("loop.spawn", {"action": "start_provider_stack", "run_dir": str(run_dir)})
    if provider_healthy(provider_endpoint(config)):
        return True, "already healthy"
    command = [
        "pwsh",
        "-NoProfile",
        "-File",
        str(ROOT / "bin" / "vulkan-provider.ps1"),
        "-Action",
        "start",
        "-Json",
    ]
    timeout = int(config.get("lifecycle", {}).get("startup_timeout_seconds", 90)) + 15
    try:
        # Use the loop kernel memory context so a provider spawn is always
        # followed by explicit cleanup discipline.  Track the process if a
        # run directory is supplied so a later cycle can terminate/kill it.
        kd = kernel.RunDirectory(run_dir, run_kind="agent-loop") if run_dir else None
        with kernel.loop_memory_context(kernel.LoopMemoryPolicy(gc_collect=True)):
            with tempfile.TemporaryFile(mode="w+b") as output:
                if kd is not None:
                    kd.append_event("provider.spawn.requested", ticket=ticket, command=command[0])
                result = subprocess.run(
                    command,
                    stdout=output,
                    stderr=subprocess.STDOUT,
                    timeout=timeout,
                )
                output.flush()
                output.seek(0)
                captured = output.read().decode("utf-8", errors="replace").strip()
    except (OSError, subprocess.TimeoutExpired) as error:
        return False, str(error)
    if result.returncode == 0 and provider_healthy(provider_endpoint(config), timeout=5.0):
        return True, captured or "started"
    return False, captured or f"provider stack start exited {result.returncode}"


def ensure_provider(mode: str, start_stack: bool = True) -> tuple[str, str]:
    if mode == "off":
        return "off", "provider disabled by operator"
    config = load_provider_config()
    error = engine.provider_configuration_error(ROOT)
    if error:
        if mode == "required":
            raise RuntimeError(error)
        return "degraded", error
    endpoint = provider_endpoint(config)
    if provider_healthy(endpoint):
        return "ready", "provider health check passed"
    ok, reason = start_provider_stack(config) if start_stack else (False, "provider health check failed")
    if ok:
        return "ready", reason
    if mode == "required":
        raise RuntimeError(f"required provider unavailable: {reason}")
    return "degraded", reason


def _normalize_check(parts: list[str]) -> list[str]:
    command = list(parts)
    if command and command[0] == "--":
        command.pop(0)
    if not command:
        raise ValueError("start requires --check COMMAND [ARGS ...]")
    if any("\x00" in part for part in command):
        raise ValueError("validation command contains a NUL byte")
    return command


def load_work_order(target: Path, value: str) -> dict[str, Any]:
    if not value:
        return {}
    path = Path(value).resolve()
    allowed_roots = (target, ROOT / "docs" / "work-orders")
    if not path.is_file():
        raise ValueError(f"work-order file not found: {path}")
    if not any(path == root or path.is_relative_to(root) for root in allowed_roots):
        raise ValueError(f"work-order file is outside the repository safety boundary: {path}")
    content = path.read_text(encoding="utf-8")
    title = next((line[2:].strip() for line in content.splitlines() if line.startswith("# ")), "")
    return {
        "path": str(path),
        "title": title,
        "sha256": engine.sha256_text(content),
        "bytes": len(content.encode("utf-8")),
    }


def create_repository_run(args: argparse.Namespace) -> Path:
    target = Path(args.target).resolve()
    if not target.is_dir():
        raise ValueError(f"repository directory not found: {target}")
    command = _normalize_check(args.check)
    work_order = load_work_order(target, getattr(args, "work_order", ""))
    provider_status, provider_reason = ensure_provider(args.provider, not args.no_start_provider)
    task_provider = "llamacpp" if provider_status == "ready" else "policy"
    run_id = args.run_id or f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{engine.slug(target.name)}"
    run_dir = (Path(args.run_dir).resolve() if args.run_dir else RUNS_ROOT / run_id).resolve()
    if run_dir.exists() and any(run_dir.iterdir()):
        raise ValueError(f"run directory is not empty: {run_dir}")
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "artifacts").mkdir(exist_ok=True)

    config = load_provider_config() if args.provider != "off" else {}
    endpoint = provider_endpoint(config) if config else ""
    run = {
        "leafos_object": "agent_loop_run",
        "version": 1,
        "run_id": run_id,
        "created_utc": utc_now(),
        "root": str(ROOT),
        "target": str(target),
        "run_dir": str(run_dir),
        "profile": "repository-inlet",
        "projects": [target.name],
        "provider_mode": args.provider,
        "provider_status": provider_status,
        "provider_reason": provider_reason,
        "provider_endpoint": endpoint,
        "stack_entry": "local-stack:repository",
        "safety_policy": "repository-bounded",
        "max_minutes": int(args.max_minutes),
        "max_attempts": 1,
        "first_checkpoint_due_minutes": 30,
        "work_order": work_order,
    }
    task = {
        "task_id": "001-repository-validation",
        "project": target.name,
        "work_order": work_order.get("path", ""),
        "objective": args.objective,
        "workdir": str(target),
        "provider": task_provider,
        "stack_entry": run["stack_entry"],
        "max_attempts": 1,
        "timeout_seconds": int(args.timeout_seconds),
        "validation_command": command,
        "status": "queued",
        "dependencies": [],
        "attempts": 0,
        "evidence": [],
    }
    queue = {"leafos_object": "agent_loop_queue", "version": 1, "run_id": run_id, "tasks": [task]}
    state = {
        "leafos_object": "agent_loop_state",
        "version": 1,
        "run_id": run_id,
        "status": "created",
        "current_task_id": "",
        "last_tick_utc": "",
        "next_action": "loop drive",
        "accepting_tasks": True,
    }
    engine.write_json(run_dir / "run.json", run)
    engine.write_json(run_dir / "queue.json", queue)
    engine.write_json(run_dir / "state.json", state)
    (run_dir / "journal.jsonl").write_text("", encoding="utf-8")
    engine.append_event(
        run_dir,
        "inlet.started",
        target=str(target),
        provider_mode=args.provider,
        command=command,
        work_order=work_order.get("path", ""),
    )
    engine.append_event(run_dir, "task.queued", task_id=task["task_id"], project=target.name)
    if provider_status == "degraded":
        engine.append_event(run_dir, "provider.degraded", reason=provider_reason, fallback="cpu-validation-policy")
    engine.write_checkpoint(run_dir, run, queue, "inlet_created")
    engine.write_report(run_dir)
    RUNS_ROOT.mkdir(parents=True, exist_ok=True)
    engine.write_json(RUNS_ROOT / "active.json", {"run_dir": str(run_dir), "run_id": run_id, "target": str(target)})
    return run_dir


def create_work_order_run(args: argparse.Namespace) -> Path:
    target_value = args.target or args.target_option
    if not target_value:
        raise ValueError("work-order start requires TARGET or --target DIR")
    target = Path(target_value).resolve(strict=True)
    source = Path(args.work_order).resolve()
    work_order_root = (ROOT / "docs" / "work-orders").resolve()
    live_intake_root = LIVE_INTAKE_ROOT.resolve()
    if not (
        source == target
        or target in source.parents
        or source == work_order_root
        or work_order_root in source.parents
        or source == live_intake_root
        or live_intake_root in source.parents
    ):
        raise ValueError("work-order source must be inside the target or LeafOS docs/work-orders")
    work_order = work_orders.validate_work_order(work_orders.load_work_order(source), target)
    provider_status, provider_reason = ensure_provider(args.provider, not args.no_start_provider)
    task_provider = "llamacpp" if provider_status == "ready" else "off"
    run_id = args.run_id or f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{engine.slug(work_order['work_order_id'])}"
    run_dir = (Path(args.run_dir).resolve() if args.run_dir else RUNS_ROOT / run_id).resolve()
    if run_dir.exists() and any(run_dir.iterdir()):
        raise ValueError(f"run directory is not empty: {run_dir}")
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "artifacts").mkdir(exist_ok=True)
    config = load_provider_config() if args.provider != "off" else {}
    run = {
        "leafos_object": "agent_loop_run",
        "version": 2,
        "run_id": run_id,
        "created_utc": utc_now(),
        "root": str(ROOT),
        "target": str(target),
        "run_dir": str(run_dir),
        "profile": args.profile,
        "projects": [],
        "work_order": {
            "id": work_order["work_order_id"],
            "title": work_order["title"],
            "source": str(source),
        },
        "provider_mode": args.provider,
        "provider_status": provider_status,
        "provider_reason": provider_reason,
        "provider_endpoint": provider_endpoint(config) if config else "",
        "stack_entry": "local-stack:local-coding",
        "safety_policy": "work-order-v2",
        "max_minutes": int(args.max_minutes),
        "max_attempts": int(work_order["max_attempts"]),
        "approval": {
            "mode": work_order["approval_mode"],
            "status": "approved" if args.yes or work_order["approval_mode"] == "automatic" else "pending",
            "approved_utc": utc_now() if args.yes else None,
        },
    }
    queue = {
        "leafos_object": "agent_loop_queue",
        "version": 2,
        "run_id": run_id,
        "work_order_id": work_order["work_order_id"],
        "tasks": work_orders.queue_from_work_order(work_order, task_provider),
    }
    state = {
        "leafos_object": "agent_loop_state",
        "version": 2,
        "run_id": run_id,
        "status": "created",
        "current_task_id": "",
        "last_tick_utc": "",
        "next_action": "loop drive",
        "accepting_tasks": True,
    }
    engine.write_json(run_dir / "run.json", run)
    engine.write_json(run_dir / "queue.json", queue)
    engine.write_json(run_dir / "state.json", state)
    engine.write_json(run_dir / "work-order.json", {key: value for key, value in work_order.items() if not key.startswith("_")})
    engine.write_json(run_dir / "step-state.json", {"completed_step_ids": [], "steps": {}})
    (run_dir / "journal.jsonl").write_text("", encoding="utf-8")
    engine.append_event(run_dir, "work_order.accepted", work_order_id=work_order["work_order_id"], source=str(source))
    engine.append_event(run_dir, "run.started", target=str(target), work_order_id=work_order["work_order_id"], provider_mode=args.provider)
    for task in queue["tasks"]:
        engine.append_event(run_dir, "task.queued", task_id=task["task_id"], task_kind=task["kind"], dependencies=task["dependencies"])
    engine.append_agent_telemetry(
        run_dir,
        "run_start",
        "startup",
        validation_status="pending",
        collect_hardware=True,
    )
    work_orders.write_checkpoint_v2(run_dir, run, work_order, "", [], "work_order_intake")
    engine.write_report(run_dir)
    RUNS_ROOT.mkdir(parents=True, exist_ok=True)
    engine.write_json(RUNS_ROOT / "active.json", {"run_dir": str(run_dir), "run_id": run_id, "target": str(target)})
    return run_dir


def resolve_run(value: str) -> Path:
    if value in {"", "active", "latest"}:
        pointer = engine.read_json(RUNS_ROOT / "active.json", {})
        if pointer.get("run_dir"):
            return engine.resolve_run_dir(str(pointer["run_dir"]))
        raise ValueError("no active loop is recorded")
    try:
        return engine.resolve_run_dir(value)
    except ValueError:
        target = Path(value).resolve()
        matches: list[tuple[float, Path]] = []
        if RUNS_ROOT.is_dir():
            for run_file in RUNS_ROOT.glob("*/run.json"):
                run = engine.read_json(run_file, {})
                if Path(str(run.get("target", ""))).resolve() == target:
                    matches.append((run_file.stat().st_mtime, run_file.parent))
        if matches:
            return max(matches)[1]
        raise


def proposal_schema() -> dict[str, Any]:
    return {
        "name": "leafos_agent_loop_plan",
        "strict": True,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["leafos_object", "version", "task_id", "provider", "stack_entry", "steps"],
            "properties": {
                "leafos_object": {"type": "string", "const": "agent_loop_plan"},
                "version": {"type": "integer", "const": 1},
                "task_id": {"type": "string"},
                "provider": {"type": "string"},
                "stack_entry": {"type": "string"},
                "steps": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 1,
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["kind", "cwd", "command", "timeout_seconds"],
                        "properties": {
                            "kind": {"type": "string", "const": "validation_command"},
                            "cwd": {"type": "string"},
                            "command": {"type": "array", "minItems": 1, "items": {"type": "string"}},
                            "timeout_seconds": {"type": "integer", "minimum": 1},
                        },
                    },
                },
            },
        },
    }


def _stream_provider_json(run_dir: Path, task: dict[str, Any], run: dict[str, Any], event_sink=None) -> str:
    config = load_provider_config()
    endpoint = str(run.get("provider_endpoint") or provider_endpoint(config))
    model = str(config.get("server", {}).get("model", "local"))
    max_tokens = int(config.get("thinking_loop", {}).get("max_output_tokens", 512))
    exact_plan = engine.policy_plan({**task, "provider": "policy"})
    exact_plan["provider"] = "llamacpp"
    prompt = (
        "Review this already allowlisted validation task. Return a plan with exactly the supplied values; "
        "do not add commands or commentary.\n" + json.dumps(exact_plan, ensure_ascii=True)
    )
    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": "You are the proposal-only LeafOS brain stack. Return only schema-valid JSON. You cannot execute actions.",
            },
            {"role": "user", "content": prompt},
        ],
        "max_tokens": max_tokens,
        "temperature": float(config.get("thinking_loop", {}).get("temperature", 0.2)),
        "stream": True,
        "response_format": {"type": "json_schema", "json_schema": proposal_schema()},
    }
    request_path = run_dir / "artifacts" / f"{task['task_id']}.provider-request.json"
    engine.write_json(request_path, payload)
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    content: list[str] = []
    output_buffer: list[str] = []
    output_chars = 0
    reasoning_chars = 0
    next_progress = 256
    timings: dict[str, Any] = {}
    usage: dict[str, Any] = {}
    request_started = time.monotonic()
    first_content_seconds: float | None = None
    timeout = max(30, int(task.get("timeout_seconds", 120)))
    with urllib.request.urlopen(request, timeout=timeout) as response:
        for raw_line in response:
            line = raw_line.decode("utf-8", errors="replace").strip()
            if not line:
                continue
            if line.startswith("data:"):
                line = line[5:].strip()
            if line == "[DONE]":
                break
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(event.get("timings"), dict):
                timings = event["timings"]
            if isinstance(event.get("usage"), dict):
                usage = event["usage"]
            choices = event.get("choices", [])
            choice = choices[0] if isinstance(choices, list) and choices else {}
            delta = choice.get("delta", {}) if isinstance(choice, dict) else {}
            reasoning = delta.get("reasoning_content", "") if isinstance(delta, dict) else ""
            piece = delta.get("content", "") if isinstance(delta, dict) else ""
            if reasoning:
                reasoning_chars += len(reasoning)
                if reasoning_chars >= next_progress:
                    progress_event = engine.append_event(
                        run_dir,
                        "provider.progress",
                        task_id=task["task_id"],
                        phase="THOUGHT",
                        private_reasoning_chars=reasoning_chars,
                    )
                    if event_sink:
                        event_sink(progress_event)
                    next_progress += 256
            if piece:
                if first_content_seconds is None:
                    first_content_seconds = time.monotonic() - request_started
                content.append(piece)
                output_buffer.append(piece)
                output_chars += len(piece)
                if output_chars >= 96:
                    output_event = engine.append_event(
                        run_dir,
                        "provider.output.delta",
                        task_id=task["task_id"],
                        text="".join(output_buffer),
                    )
                    if event_sink:
                        event_sink(output_event)
                    output_buffer.clear()
                    output_chars = 0
    if output_buffer:
        output_event = engine.append_event(
            run_dir,
            "provider.output.delta",
            task_id=task["task_id"],
            text="".join(output_buffer),
        )
        if event_sink:
            event_sink(output_event)
    raw_text = "".join(content).strip()
    (run_dir / "artifacts" / f"{task['task_id']}.provider-response.txt").write_text(raw_text, encoding="utf-8")
    if not raw_text:
        raise RuntimeError("llama.cpp returned no proposal content")
    generated_tokens = usage.get("completion_tokens") or timings.get("predicted_n")
    generation_tk_s = timings.get("predicted_per_second")
    completed_event = engine.append_event(
        run_dir,
        "provider.request.completed",
        task_id=task["task_id"],
        brain_generation_tk_s=generation_tk_s,
        generated_tokens=generated_tokens,
        reasoning_chars=reasoning_chars,
        output_chars=len(raw_text),
    )
    if event_sink:
        event_sink(completed_event)
    telemetry = engine.make_universal_event(
        str(run.get("run_id") or run_dir.name),
        "agent-loop",
        "sample",
        "brain",
        run_dir=run_dir,
        task_id=task.get("task_id"),
        project=task.get("project"),
        stack={
            "local_stack_id": run.get("stack_entry"),
            "brain_stack_entry": run.get("stack_entry"),
            "coder_stack_entry": None,
            "helper_stack_entry": None,
            "quantization": run.get("quantization"),
        },
        provider={
            "mode": run.get("provider_mode", "required"),
            "backend": "vulkan",
            "endpoint": run.get("provider_endpoint"),
            "status": "running",
            "pid": run.get("provider_pid"),
        },
        instances={
            "initiated": 1,
            "alive": 1,
            "brain_initiated": 1,
            "brain_alive": 1,
            "coder_initiated": 0,
            "coder_alive": 0,
            "provider_initiated": 1,
            "provider_alive": 1,
            "crashed": 0,
            "restarted": 0,
        },
        throughput={
            "brain_prompt_tk_s": timings.get("prompt_per_second"),
            "brain_generation_tk_s": generation_tk_s,
            "coder_prompt_tk_s": None,
            "coder_generation_tk_s": None,
            "helper_generation_tk_s": None,
            "aggregate_generation_tk_s": generation_tk_s,
            "time_to_first_token_seconds": first_content_seconds,
            "prompt_tokens": usage.get("prompt_tokens") or timings.get("prompt_n"),
            "generated_tokens": generated_tokens,
        },
        collect_hardware=True,
    )
    engine.append_universal_event(run_dir / engine.UNIVERSAL_LOG_NAME, telemetry)
    return raw_text


def attach_provider_proposal(run_dir: Path, task_id: str, event_sink=None) -> dict[str, Any]:
    run = engine.read_json(run_dir / "run.json", {})
    queue = engine.read_json(run_dir / "queue.json", {})
    task = next((item for item in queue.get("tasks", []) if item.get("task_id") == task_id), None)
    if not task:
        raise ValueError(f"task not found: {task_id}")
    phase_event = engine.append_event(
        run_dir,
        "phase.emitted",
        task_id=task_id,
        phase="THOUGHT",
        summary="Requesting a bounded validation proposal from the configured brain stack.",
    )
    if event_sink:
        event_sink(phase_event)
    request_event = engine.append_event(
        run_dir,
        "provider.request.started",
        task_id=task_id,
        endpoint=run.get("provider_endpoint", ""),
    )
    if event_sink:
        event_sink(request_event)
    try:
        raw_text = _stream_provider_json(run_dir, task, run, event_sink)
        proposal = json.loads(raw_text)
        errors = engine.validate_plan(proposal, task)
        if errors:
            raise ValueError("; ".join(errors))
    except (OSError, urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError, RuntimeError) as error:
        with engine.queue_write_lock(run_dir):
            queue = engine.read_json(run_dir / "queue.json", queue)
            current = next(item for item in queue["tasks"] if item.get("task_id") == task_id)
            current["status"] = "blocked"
            current["reason"] = "provider_proposal_failed"
            current.setdefault("evidence", []).append({"kind": "provider_error", "error": str(error)})
            engine.write_json(run_dir / "queue.json", queue)
        engine.append_event(run_dir, "provider.request.failed", task_id=task_id, error=str(error))
        raise RuntimeError(f"provider proposal failed: {error}") from error

    with engine.queue_write_lock(run_dir):
        queue = engine.read_json(run_dir / "queue.json", queue)
        current = next(item for item in queue["tasks"] if item.get("task_id") == task_id)
        if current.get("status") not in {"queued", "repair_queued"}:
            raise RuntimeError(f"task changed state before proposal attachment: {current.get('status')}")
        current["provider_proposal"] = proposal
        engine.write_json(run_dir / "queue.json", queue)
    attached_event = engine.append_event(run_dir, "provider.proposal.attached", task_id=task_id)
    if event_sink:
        event_sink(attached_event)
    action_event = engine.append_event(
        run_dir,
        "phase.emitted",
        task_id=task_id,
        phase="ACTION",
        summary="Validated provider proposal attached atomically to the task queue.",
    )
    if event_sink:
        event_sink(action_event)
    return proposal


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        try:
            import ctypes

            process = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
            if not process:
                return False
            try:
                exit_code = ctypes.c_ulong()
                return bool(ctypes.windll.kernel32.GetExitCodeProcess(process, ctypes.byref(exit_code))) and exit_code.value == 259
            finally:
                ctypes.windll.kernel32.CloseHandle(process)
        except (AttributeError, OSError):
            pass
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _lease_timestamp_fresh(lease: dict[str, Any], grace_seconds: float, now: datetime | None = None) -> bool:
    value = lease.get("heartbeat_utc") or lease.get("started_utc")
    if not value:
        return False
    try:
        timestamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return False
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    age = ((now or datetime.now(timezone.utc)) - timestamp.astimezone(timezone.utc)).total_seconds()
    return age <= max(0.0, grace_seconds)


def worker_lease_status(
    run_dir: Path,
    grace_seconds: float = WORKER_LEASE_GRACE_SECONDS,
    *,
    pid_probe=None,
    now: datetime | None = None,
) -> tuple[bool, int]:
    """Return lease occupancy and PID, including a short process-exit grace."""
    lease = engine.read_json(run_dir / "worker.lock", {})
    pid = int(lease.get("pid", 0))
    probe = pid_probe or _pid_alive
    occupied = bool(pid and (probe(pid) or _lease_timestamp_fresh(lease, grace_seconds, now)))
    return occupied, pid


def _touch_worker_lease(run_dir: Path, *, state: str = "running") -> bool:
    with engine.queue_write_lock(run_dir):
        lease_path = run_dir / "worker.lock"
        lease = engine.read_json(lease_path, {})
        if int(lease.get("pid", 0)) != os.getpid():
            return False
        lease.update(heartbeat_utc=utc_now(), state=state)
        engine.write_json(lease_path, lease)
        return True


def _heartbeat_worker_lease(run_dir: Path, stop: threading.Event, interval: float) -> None:
    while not stop.wait(max(0.25, min(interval, 1.0))):
        if not _touch_worker_lease(run_dir):
            return


def acquire_worker(run_dir: Path) -> Path:
    lease = run_dir / "worker.lock"
    with engine.queue_write_lock(run_dir):
        current = engine.read_json(lease, {})
        if int(current.get("pid", 0)) == os.getpid():
            current.update(heartbeat_utc=utc_now(), state="starting")
            engine.write_json(lease, current)
            return lease
        occupied, pid = worker_lease_status(run_dir)
        if occupied:
            raise RuntimeError(f"loop already has worker pid {pid}")
        lease.unlink(missing_ok=True)
        now = utc_now()
        engine.write_json(lease, {"pid": os.getpid(), "started_utc": now, "heartbeat_utc": now, "state": "starting"})
    return lease


def events_after(run_dir: Path, cursor: int) -> list[dict[str, Any]]:
    return [event for event in engine.read_events(run_dir) if int(event.get("seq", 0)) > cursor]


def _print_event(event: dict[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(event, separators=(",", ":"), ensure_ascii=True), flush=True)
        return
    detail = event.get("summary") or event.get("reason") or event.get("error") or ""
    print(f"{int(event.get('seq', 0)):04d} {event.get('kind', ''):<30} {detail}", flush=True)


def drive_run(run_dir: Path, interval: float = 1.0, echo_events: bool = False, as_json: bool = False) -> int:
    lease = acquire_worker(run_dir)
    heartbeat_stop = threading.Event()
    heartbeat = threading.Thread(
        target=_heartbeat_worker_lease,
        args=(run_dir, heartbeat_stop, interval),
        name=f"leaf-worker-heartbeat-{os.getpid()}",
        daemon=True,
    )
    heartbeat.start()
    cursor = engine.read_events(run_dir)[-1]["seq"] if engine.read_events(run_dir) else 0
    started = time.monotonic()
    try:
        worker_event = engine.append_event(run_dir, "worker.started", pid=os.getpid())
        if echo_events:
            _print_event(worker_event, as_json)
            cursor = int(worker_event["seq"])
        def event_sink(event: dict[str, Any]) -> None:
            nonlocal cursor
            if echo_events:
                _print_event(event, as_json)
            cursor = int(event["seq"])

        while True:
            state = engine.read_json(run_dir / "state.json", {})
            run = engine.read_json(run_dir / "run.json", {})
            if state.get("status") == "stopped":
                break
            if state.get("status") in {"draining", "drained"} or state.get("drain_requested_utc"):
                break
            if state.get("status") == "paused":
                _touch_worker_lease(run_dir, state="paused")
                engine.append_event(run_dir, "worker.heartbeat", pid=os.getpid(), state="paused")
                time.sleep(interval)
                continue
            resident = engine.read_json(run_dir / "resident-state.json", {})
            decision = resident.get("last_decision", {}) if isinstance(resident.get("last_decision"), dict) else {}
            if resident.get("enabled") and decision and not bool(decision.get("claim_allowed", False)):
                engine.append_event(
                    run_dir,
                    "worker.claim_deferred",
                    pid=os.getpid(),
                    profile=decision.get("profile"),
                    reason=decision.get("reason", "resident_claim_gate"),
                )
                break
            queue = engine.read_json(run_dir / "queue.json", {})
            runnable = [
                task
                for task in queue.get("tasks", [])
                if task.get("status") in {"queued", "repair_queued"}
                and engine.dependencies_complete(queue, task)
            ]
            active = min(runnable, key=lambda item: (int(item.get("priority", 2)), queue["tasks"].index(item)), default=None)
            if active is None:
                tasks = queue.get("tasks", [])
                successful = bool(tasks) and all(task.get("status") in {"complete", "cancelled"} for task in tasks)
                state["status"] = "complete" if successful else "blocked"
                state["next_action"] = "loop report" if successful else "loop status"
                state["accepting_tasks"] = False
                engine.write_json(run_dir / "state.json", state)
                terminal_event = engine.append_event(run_dir, "run.completed" if successful else "run.blocked", status=state["status"])
                event_sink(terminal_event)
                break
            if run.get("work_order"):
                _touch_worker_lease(run_dir, state="executing")
                state["status"] = "running"
                state["current_task_id"] = active["task_id"]
                engine.write_json(run_dir / "state.json", state)
                work_orders.run_work_order_task(run_dir, run, queue, active, load_provider_config(), event_sink)
                _touch_worker_lease(run_dir, state="running")
                state = engine.read_json(run_dir / "state.json", state)
                state["current_task_id"] = ""
                state["last_tick_utc"] = utc_now()
                if state.get("status") in {"stopped", "stopping"}:
                    state.update(status="stopped", accepting_tasks=False, next_action="loop report")
                    engine.write_json(run_dir / "state.json", state)
                    break
                if state.get("status") in {"draining", "drained"} or state.get("drain_requested_utc"):
                    state.update(status="draining", accepting_tasks=False, next_action="loop attach")
                    engine.write_json(run_dir / "state.json", state)
                    break
                if state.get("status") == "paused":
                    state.update(accepting_tasks=False, next_action="loop resume")
                    engine.write_json(run_dir / "state.json", state)
                    continue
                if active.get("status") in {"failed", "blocked"}:
                    state["status"] = "blocked"
                    state["next_action"] = "loop status"
                    engine.write_json(run_dir / "state.json", state)
                    break
                state["status"] = "running"
                state["next_action"] = "loop drive"
                engine.write_json(run_dir / "state.json", state)
                time.sleep(interval)
                continue
            if active.get("provider") == "llamacpp" and not active.get("provider_proposal"):
                try:
                    attach_provider_proposal(run_dir, active["task_id"], event_sink)
                except RuntimeError:
                    with contextlib.redirect_stdout(io.StringIO()):
                        engine.tick_run(argparse.Namespace(run=str(run_dir)))
                    if echo_events:
                        for event in events_after(run_dir, cursor):
                            _print_event(event, as_json)
                            cursor = int(event["seq"])
                    break
            with contextlib.redirect_stdout(io.StringIO()):
                engine.tick_run(argparse.Namespace(run=str(run_dir)))
            if echo_events:
                for event in events_after(run_dir, cursor):
                    _print_event(event, as_json)
                    cursor = int(event["seq"])
            state = engine.read_json(run_dir / "state.json", {})
            if state.get("status") in {"complete", "blocked"}:
                break
            if time.monotonic() - started >= int(run.get("max_minutes", 64)) * 60:
                state["status"] = "paused"
                state["next_action"] = "loop resume"
                engine.write_json(run_dir / "state.json", state)
                engine.append_event(run_dir, "worker.time_limit", max_minutes=run.get("max_minutes", 64))
                break
            engine.append_event(run_dir, "worker.heartbeat", pid=os.getpid(), state=state.get("status", "running"))
            time.sleep(interval)
        final_state = engine.read_json(run_dir / "state.json", {})
        if final_state.get("drain_requested_utc"):
            final_state["status"] = "drained"
            final_state["next_action"] = "loop report"
            engine.write_json(run_dir / "state.json", final_state)
            engine.append_event(run_dir, "run.drained")
        if final_state.get("status") in {"complete", "blocked", "stopped", "drained"}:
            final_state["accepting_tasks"] = False
            engine.write_json(run_dir / "state.json", final_state)
        _touch_worker_lease(run_dir, state="stopping")
        stopped_event = engine.append_event(run_dir, "worker.stopped", pid=os.getpid(), state=final_state.get("status", ""))
        if echo_events:
            _print_event(stopped_event, as_json)
        engine.write_report(run_dir)
        return 0 if final_state.get("status") in {"complete", "drained"} else 2
    finally:
        heartbeat_stop.set()
        heartbeat.join(timeout=2.0)
        with engine.queue_write_lock(run_dir):
            current_lease = engine.read_json(lease, {})
            if int(current_lease.get("pid", 0)) == os.getpid():
                lease.unlink(missing_ok=True)


def spawn_worker(run_dir: Path, interval: float) -> int:
    log_path = run_dir / "controller.log"
    command = [sys.executable, str(Path(__file__).resolve()), "drive", str(run_dir), "--interval", str(interval)]
    child_environment = os.environ.copy()
    resident = engine.read_json(run_dir / "resident-state.json", {})
    decision = resident.get("last_decision", {}) if isinstance(resident.get("last_decision"), dict) else {}
    cpu_slots = max(1, min(64, int(decision.get("cpu_slots", 1))))
    child_environment.update({
        "LEAF_CPU_SLOTS": str(cpu_slots),
        "OMP_NUM_THREADS": str(cpu_slots),
        "CMAKE_BUILD_PARALLEL_LEVEL": str(cpu_slots),
    })
    creationflags = 0
    startupinfo = None
    if os.name == "nt":
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS | getattr(subprocess, "CREATE_NO_WINDOW", 0)
        if resident.get("enabled") and resident.get("mode") != "full":
            creationflags |= getattr(subprocess, "BELOW_NORMAL_PRIORITY_CLASS", 0)
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0  # SW_HIDE
    with engine.queue_write_lock(run_dir):
        occupied, existing_pid = worker_lease_status(run_dir)
        if occupied:
            return existing_pid
        with log_path.open("a", encoding="utf-8") as log:
            process = subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
                env=child_environment,
                creationflags=creationflags,
                startupinfo=startupinfo,
                start_new_session=os.name != "nt",
            )
        now = utc_now()
        engine.write_json(
            run_dir / "worker.lock",
            {"pid": process.pid, "started_utc": now, "heartbeat_utc": now, "state": "spawned"},
        )
    engine.append_event(run_dir, "worker.spawned", pid=process.pid, log=str(log_path))
    return process.pid


def _next_task_id(queue: dict[str, Any]) -> str:
    used = {str(task.get("task_id", "")) for task in queue.get("tasks", [])}
    index = 1
    while f"TASK-{index:04d}" in used:
        index += 1
    return f"TASK-{index:04d}"


def _normalize_task_control(request: Any) -> dict[str, Any]:
    if not isinstance(request, dict):
        raise ValueError("task control request must be an object")
    allowed = {"leafos_object", "version", "request_id", "action", "task_id", "priority", "task"}
    unknown = sorted(set(request) - allowed)
    if unknown:
        raise ValueError("task control request has unknown fields: " + ", ".join(unknown))
    if request.get("leafos_object") != "leafos.task_control_request" or request.get("version") != 1:
        raise ValueError("task control request requires leafos.task_control_request version 1")
    action = str(request.get("action", ""))
    if action not in TASK_CONTROL_ACTIONS:
        raise ValueError(f"unsupported task control action: {action}")
    normalized = dict(request)
    normalized["request_id"] = str(request.get("request_id") or ("req-" + secrets.token_hex(8)))
    if not TASK_ID_PATTERN.fullmatch(normalized["request_id"]):
        raise ValueError("request_id must be 3-64 letters, numbers, dots, underscores, or hyphens")
    if action == "submit":
        if request.get("task_id") is not None or request.get("priority") is not None:
            raise ValueError("submit uses fields inside task, not top-level task_id or priority")
        task = request.get("task")
        if not isinstance(task, dict):
            raise ValueError("submit requires a task object")
        task_allowed = {
            "task_id", "objective", "allowed_paths", "denied_paths", "commands", "acceptance",
            "constraints", "allow_mutation", "approval_mode", "priority", "max_attempts",
            "timeout_seconds", "stack_role", "dependencies",
        }
        task_unknown = sorted(set(task) - task_allowed)
        if task_unknown:
            raise ValueError("submitted task has unknown fields: " + ", ".join(task_unknown))
        objective = str(task.get("objective", "")).strip()
        if not objective or len(objective) > 2000:
            raise ValueError("task objective must contain 1-2000 characters")
        paths = task.get("allowed_paths")
        if not isinstance(paths, list) or not paths or len(paths) > 64 or not all(isinstance(item, str) and item for item in paths):
            raise ValueError("task allowed_paths must contain 1-64 strings")
        acceptance = task.get("acceptance")
        if not isinstance(acceptance, list) or not acceptance or len(acceptance) > 32 or not all(isinstance(item, str) and item for item in acceptance):
            raise ValueError("task acceptance must contain 1-32 strings")
        commands = work_orders.normalize_commands(task.get("commands", {}))
        if sum(len(items) for items in commands.values()) > 16:
            raise ValueError("submitted task may declare at most 16 commands")
        if any("\x00" in part for items in commands.values() for command in items for part in command):
            raise ValueError("submitted task commands may not contain NUL bytes")
        denied_paths = task.get("denied_paths", [])
        constraints = task.get("constraints", [])
        if not isinstance(denied_paths, list) or not all(isinstance(item, str) and item for item in denied_paths):
            raise ValueError("task denied_paths must be a string array")
        if not isinstance(constraints, list) or not all(isinstance(item, str) for item in constraints):
            raise ValueError("task constraints must be a string array")
        priority = int(task.get("priority", 2))
        max_attempts = int(task.get("max_attempts", 2))
        timeout_seconds = int(task.get("timeout_seconds", 300))
        if not 0 <= priority <= 9:
            raise ValueError("task priority must be between 0 and 9")
        if not 1 <= max_attempts <= 5:
            raise ValueError("task max_attempts must be between 1 and 5")
        if not 1 <= timeout_seconds <= 3600:
            raise ValueError("task timeout_seconds must be between 1 and 3600")
        approval_mode = str(task.get("approval_mode", "required"))
        if approval_mode not in {"required", "automatic"}:
            raise ValueError("task approval_mode must be required or automatic")
        stack_role = str(task.get("stack_role", "auto"))
        if stack_role not in {"auto", "brain", "coder", "helper", "cpu"}:
            raise ValueError("task stack_role must be auto, brain, coder, helper, or cpu")
        dependencies = task.get("dependencies", [])
        if not isinstance(dependencies, list) or len(dependencies) > 32 or not all(isinstance(item, str) and TASK_ID_PATTERN.fullmatch(item) for item in dependencies):
            raise ValueError("task dependencies must be an array of at most 32 task IDs")
        if len(dependencies) != len(set(dependencies)):
            raise ValueError("task dependencies must be unique")
        normalized["task"] = {
            **task,
            "objective": objective,
            "commands": commands,
            "priority": priority,
            "max_attempts": max_attempts,
            "timeout_seconds": timeout_seconds,
            "approval_mode": approval_mode,
            "stack_role": stack_role,
            "dependencies": dependencies,
            "allow_mutation": bool(task.get("allow_mutation", False)),
        }
    else:
        if request.get("task") is not None:
            raise ValueError(f"{action} does not accept a task object")
        if action != "prioritize" and request.get("priority") is not None:
            raise ValueError(f"{action} does not accept priority")
        task_id = str(request.get("task_id", ""))
        if not TASK_ID_PATTERN.fullmatch(task_id):
            raise ValueError(f"{action} requires a valid task_id")
        normalized["task_id"] = task_id
        if action == "prioritize":
            priority = request.get("priority")
            if not isinstance(priority, int) or isinstance(priority, bool) or not 0 <= priority <= 9:
                raise ValueError("prioritize requires integer priority between 0 and 9")
    return normalized


def _journal_task_control(run_dir: Path, run: dict[str, Any], request: dict[str, Any]) -> None:
    journal_path = run_dir / "control.lmem"
    sequence, previous_hash = native_journal.head(journal_path)
    timestamp = utc_now().replace("+00:00", "Z")
    identity = native_journal.canonical_digest({"request": request, "sequence": sequence + 1, "timestamp": timestamp})[:20]
    task_id = request.get("task_id") or request.get("task", {}).get("task_id")
    event = {
        "schema": "leafos.memory.event.v1",
        "event_id": "mem_" + identity,
        "run_id": str(run.get("run_id") or run_dir.name),
        "project_id": str(Path(str(run.get("target", "repository"))).name),
        "sequence": sequence + 1,
        "timestamp_utc": timestamp,
        "kind": "action_request",
        "epistemic_class": "record",
        "source": {"actor": "operator", "model": None, "tool": "leaf-loop-inlet", "parent_event_ids": []},
        "scope": {"task_id": task_id, "paths": [], "symbols": []},
        "content": {"mime": "application/json", "text": f"Accepted task control: {request['action']}", "data": request},
        "retrieval": {"importance": 0.8, "expires_at": None, "sensitivity": "project", "indexable": True},
        "integrity": {"payload_sha256": "0" * 64, "previous_event_sha256": previous_hash, "writer_version": "leaf-memory/0.2.2.1"},
    }
    native_journal.append_native(journal_path, event)


def apply_task_control(run_dir: Path, request: Any) -> dict[str, Any]:
    normalized = _normalize_task_control(request)
    with engine.queue_write_lock(run_dir):
        return _apply_task_control_locked(run_dir, normalized)


def _apply_task_control_locked(run_dir: Path, normalized: dict[str, Any]) -> dict[str, Any]:
    run = engine.read_json(run_dir / "run.json", {})
    queue = engine.read_json(run_dir / "queue.json", {})
    state = engine.read_json(run_dir / "state.json", {})
    if int(run.get("version", 1)) < 2 or not run.get("work_order"):
        raise ValueError("typed task controls require a version 2 work-order run")
    action = normalized["action"]
    target = Path(str(run["target"])).resolve(strict=True)

    if action == "submit":
        if state.get("status") in {"stopped", "drained", "stopping", "draining"}:
            raise ValueError(f"run does not accept new tasks while {state.get('status')}")
        submitted = normalized["task"]
        task_id = str(submitted.get("task_id") or _next_task_id(queue))
        if not TASK_ID_PATTERN.fullmatch(task_id):
            raise ValueError("submitted task_id must be 3-64 letters, numbers, dots, underscores, or hyphens")
        if any(item.get("task_id") == task_id for item in queue.get("tasks", [])):
            raise ValueError(f"task already exists: {task_id}")
        known_ids = {str(item.get("task_id")) for item in queue.get("tasks", [])}
        unknown_dependencies = sorted(set(submitted["dependencies"]) - known_ids)
        if unknown_dependencies:
            raise ValueError("unknown task dependencies: " + ", ".join(unknown_dependencies))
        work_order_data = {
            "work_order_id": task_id,
            "title": f"Operator task {task_id}",
            "target": str(target),
            "objective": submitted["objective"],
            "allowed_paths": submitted["allowed_paths"],
            "denied_paths": submitted.get("denied_paths", []),
            "constraints": submitted.get("constraints", []),
            "acceptance": submitted["acceptance"],
            "commands": submitted["commands"],
            "approval_mode": submitted["approval_mode"],
            "allow_mutation": submitted["allow_mutation"],
            "max_attempts": submitted["max_attempts"],
            "timeout_seconds": submitted["timeout_seconds"],
        }
        work_orders.validate_work_order(work_order_data, target)
        work_order_dir = run_dir / "work-orders"
        work_order_dir.mkdir(exist_ok=True)
        work_order_path = work_order_dir / f"{task_id}.json"
        work_order_data["source"] = str(work_order_path)
        normalized["task"]["task_id"] = task_id
        _journal_task_control(run_dir, run, normalized)
        engine.write_json(work_order_path, work_order_data)
        provider = "off" if submitted["stack_role"] == "cpu" or run.get("provider_status") != "ready" else "llamacpp"
        task = {
            "task_id": task_id,
            "kind": "operator",
            "project": target.name,
            "work_order_id": task_id,
            "work_order_source": str(work_order_path),
            "objective": submitted["objective"],
            "workdir": str(target),
            "provider": provider,
            "stack_entry": run.get("stack_entry", "local-stack:local-coding"),
            "role": submitted["stack_role"],
            "priority": submitted["priority"],
            "max_attempts": submitted["max_attempts"],
            "timeout_seconds": submitted["timeout_seconds"],
            "approval_status": "approved" if submitted["approval_mode"] == "automatic" else "pending",
            "status": "queued",
            "dependencies": submitted["dependencies"],
            "attempts": 0,
            "evidence": [],
            "request_id": normalized["request_id"],
        }
        queue.setdefault("tasks", []).append(task)
        active_task_id = str(state.get("current_task_id", "")).strip()
        if active_task_id or state.get("status") in {"running", "paused"}:
            state["accepting_tasks"] = True
        else:
            state.update(status="resumed", accepting_tasks=True, current_task_id="", next_action="loop drive")
        engine.write_json(run_dir / "queue.json", queue)
        engine.write_json(run_dir / "state.json", state)
        engine.append_event(run_dir, "task.submitted", task_id=task_id, request_id=normalized["request_id"], priority=task["priority"], stack_role=task["role"])
        return task

    task = next((item for item in queue.get("tasks", []) if item.get("task_id") == normalized["task_id"]), None)
    if task is None:
        raise ValueError(f"task not found: {normalized['task_id']}")
    if action == "prioritize":
        if task.get("status") not in {"queued", "repair_queued", "blocked"}:
            raise ValueError(f"cannot prioritize task in state {task.get('status')}")
        _journal_task_control(run_dir, run, normalized)
        previous = int(task.get("priority", 2))
        task["priority"] = normalized["priority"]
        event_kind = "task.prioritized"
        event_data = {"previous_priority": previous, "priority": task["priority"]}
    elif action == "retry":
        if task.get("status") not in {"failed", "blocked"}:
            raise ValueError(f"cannot retry task in state {task.get('status')}")
        if task.get("reason") == "approval_required":
            raise ValueError("task requires approval, not retry")
        if int(task.get("attempts", 0)) >= int(task.get("max_attempts", 1)):
            raise ValueError("task retry budget is exhausted")
        _journal_task_control(run_dir, run, normalized)
        task.update(status="repair_queued", cancel_requested=False)
        task.pop("reason", None)
        work_orders._cancel_path(run_dir, task["task_id"]).unlink(missing_ok=True)
        for dependent in queue.get("tasks", []):
            if dependent.get("reason") == "dependency_cancelled" and task["task_id"] in dependent.get("dependencies", []):
                dependent.update(status="queued")
                dependent.pop("reason", None)
        state.update(status="resumed", accepting_tasks=True, next_action="loop drive")
        event_kind = "task.retry_requested"
        event_data = {"next_attempt": int(task.get("attempts", 0)) + 1}
    elif action == "approve":
        if task.get("reason") != "approval_required" and task.get("approval_status") != "pending":
            raise ValueError("task is not waiting for approval")
        _journal_task_control(run_dir, run, normalized)
        task.update(status="queued", approval_status="approved")
        task.pop("reason", None)
        state.update(status="resumed", accepting_tasks=True, next_action="loop drive")
        event_kind = "task.approved"
        event_data = {}
    else:
        if task.get("status") in {"complete", "cancelled"}:
            raise ValueError(f"cannot cancel task in state {task.get('status')}")
        _journal_task_control(run_dir, run, normalized)
        marker = work_orders._cancel_path(run_dir, task["task_id"])
        marker.parent.mkdir(exist_ok=True)
        engine.write_json(marker, {"task_id": task["task_id"], "requested_utc": utc_now(), "request_id": normalized["request_id"]})
        task["cancel_requested"] = True
        if task.get("status") not in {"executing", "running", "planning", "validating"}:
            task.update(status="cancelled", reason="operator_cancelled")
            for dependent in queue.get("tasks", []):
                if task["task_id"] in dependent.get("dependencies", []) and dependent.get("status") in {"queued", "repair_queued"}:
                    dependent.update(status="blocked", reason="dependency_cancelled")
        engine.write_json(run_dir / "queue.json", queue)
        interrupted = work_orders.terminate_tracked_process(run_dir, task["task_id"])
        engine.write_json(run_dir / "state.json", state)
        engine.append_event(run_dir, "task.cancel_requested", task_id=task["task_id"], request_id=normalized["request_id"], process_interrupted=interrupted)
        latest = engine.read_json(run_dir / "queue.json", queue)
        return next(item for item in latest.get("tasks", []) if item.get("task_id") == task["task_id"])
    engine.write_json(run_dir / "queue.json", queue)
    engine.write_json(run_dir / "state.json", state)
    engine.append_event(run_dir, event_kind, task_id=task["task_id"], request_id=normalized["request_id"], **event_data)
    return task


def set_control_state(
    run_dir: Path,
    action: str,
    *,
    request_id: str = "",
    request_digest: str = "",
    capability_id: str = "",
) -> None:
    state = engine.read_json(run_dir / "state.json", {})
    run = engine.read_json(run_dir / "run.json", {})
    _journal_task_control(run_dir, run, {
        "leafos_object": "leafos.task_control_request", "version": 1,
        "request_id": request_id or "req-" + secrets.token_hex(8), "action": f"run.{action}",
        "request_digest": request_digest, "capability_id": capability_id,
    })
    if action == "pause":
        state.update(status="paused", accepting_tasks=False, next_action="loop resume")
        kind = "run.paused"
    elif action == "resume":
        state.update(status="resumed", accepting_tasks=True, next_action="loop drive")
        kind = "run.resumed"
    elif action == "stop":
        state.update(status="stopped", accepting_tasks=False, next_action="loop report")
        kind = "run.stopped"
        active_task = str(state.get("current_task_id", ""))
        if active_task:
            marker = work_orders._cancel_path(run_dir, active_task)
            marker.parent.mkdir(exist_ok=True)
            engine.write_json(marker, {"task_id": active_task, "requested_utc": utc_now(), "reason": "run_stopped"})
            work_orders.terminate_tracked_process(run_dir, active_task)
    elif action == "drain":
        state.update(status="draining", accepting_tasks=False, next_action="loop attach", drain_requested_utc=utc_now())
        kind = "run.drain_requested"
    else:
        raise ValueError(f"unknown control action: {action}")
    state["control_updated_utc"] = utc_now()
    engine.write_json(run_dir / "state.json", state)
    engine.append_event(
        run_dir,
        kind,
        operator_action=action,
        request_id=request_id,
        request_digest=request_digest,
        capability_id=capability_id,
    )


def approve_run(run_dir: Path) -> None:
    run = engine.read_json(run_dir / "run.json", {})
    if not run.get("work_order"):
        raise ValueError("approval is only used by work-order runs")
    _journal_task_control(run_dir, run, {
        "leafos_object": "leafos.task_control_request", "version": 1,
        "request_id": "req-" + secrets.token_hex(8), "action": "run.approve",
    })
    run["approval"] = {"mode": run.get("approval", {}).get("mode", "required"), "status": "approved", "approved_utc": utc_now()}
    engine.write_json(run_dir / "run.json", run)
    with engine.queue_write_lock(run_dir):
        queue = engine.read_json(run_dir / "queue.json", {})
        for task in queue.get("tasks", []):
            if task.get("kind") == "approve" and task.get("status") == "blocked":
                task["status"] = "queued"
                task.pop("reason", None)
        engine.write_json(run_dir / "queue.json", queue)
    state = engine.read_json(run_dir / "state.json", {})
    state.update(status="resumed", accepting_tasks=True, next_action="loop drive")
    engine.write_json(run_dir / "state.json", state)
    engine.append_event(run_dir, "approval.granted", operator_action="approve")


def status_payload(run_dir: Path) -> dict[str, Any]:
    data = engine.status_data(run_dir)
    lease = engine.read_json(run_dir / "worker.lock", {})
    pid = int(lease.get("pid", 0))
    run = engine.read_json(run_dir / "run.json", {})
    endpoint = str(run.get("provider_endpoint", ""))
    data["controller"] = {
        "worker_pid": pid or None,
        "worker_alive": _pid_alive(pid),
        "event_cursor": int(data.get("last_event", {}).get("seq", 0)),
        "accepting_tasks": bool(engine.read_json(run_dir / "state.json", {}).get("accepting_tasks", False)),
        "active_process": engine.read_json(run_dir / "active-process.json", {}),
    }
    data["provider_health"] = "ready" if endpoint and provider_healthy(endpoint) else ("off" if not endpoint else "unavailable")
    return data


def _monitor_heartbeat(run_dir: Path, state: str, timeout_seconds: float) -> dict[str, Any]:
    lease = engine.read_json(run_dir / "worker.lock", {})
    pid = int(lease.get("pid", 0))
    alive = _pid_alive(pid)
    value = lease.get("heartbeat_utc") or lease.get("started_utc")
    timestamp: datetime | None = None
    if value:
        try:
            timestamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=timezone.utc)
            timestamp = timestamp.astimezone(timezone.utc)
        except ValueError:
            timestamp = None

    age = None
    if timestamp is not None:
        age = max(0.0, (datetime.now(timezone.utc) - timestamp).total_seconds())
    terminal = state in TERMINAL_STATES and not alive
    expects_worker = state in {"running", "resumed", "draining"}
    stale = expects_worker and not terminal and (
        not alive or timestamp is None or (age is not None and age > timeout_seconds)
    )
    if not lease:
        reason = "no_worker_lease"
    elif not alive:
        reason = "worker_not_alive"
    elif timestamp is None:
        reason = "missing_or_invalid_heartbeat"
    elif age is not None and age > timeout_seconds:
        reason = "heartbeat_expired"
    else:
        reason = "healthy"
    return {
        "available": bool(lease),
        "worker_alive": alive,
        "pid": pid or None,
        "last_utc": timestamp.isoformat() if timestamp is not None else None,
        "age_seconds": round(age, 3) if age is not None else None,
        "timeout_seconds": timeout_seconds,
        "stale": stale,
        "reason": reason,
    }


def monitor_snapshot(run_dir: Path, cursor: int, heartbeat_timeout: float) -> dict[str, Any]:
    """Read one reconnectable monitor snapshot without mutating the run."""
    run_status = status_payload(run_dir)
    state = str(run_status.get("state", ""))
    new_events = events_after(run_dir, cursor)
    next_cursor = max([cursor, *[int(event.get("seq", 0)) for event in new_events]])
    heartbeat = _monitor_heartbeat(run_dir, state, heartbeat_timeout)
    terminal = state in TERMINAL_STATES and not heartbeat["worker_alive"]
    return {
        "leafos_object": "leafos.loop_monitor.snapshot",
        "version": 1,
        "observed_utc": utc_now(),
        "run_id": run_status.get("run_id", ""),
        "run_dir": str(run_dir),
        "state": state,
        "current_task": run_status.get("current_task", ""),
        "event_cursor": next_cursor,
        "terminal": terminal,
        "heartbeat": heartbeat,
        "run_status": run_status,
        "new_events": new_events,
    }


def _monitor_cursor(path: Path | None, fallback: int) -> int:
    if path is None or not path.is_file():
        return fallback
    try:
        return max(fallback, int(path.read_text(encoding="utf-8").strip() or "0"))
    except (OSError, ValueError) as error:
        raise ValueError(f"invalid monitor cursor file: {path}") from error


def _write_monitor_cursor(path: Path | None, cursor: int) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(f"{cursor}\n", encoding="utf-8")
    temporary.replace(path)


def _monitor_text(snapshot: dict[str, Any]) -> str:
    run_status = snapshot["run_status"]
    heartbeat = snapshot["heartbeat"]
    controller = run_status.get("controller", {})
    last_event = run_status.get("last_event", {})
    age = heartbeat.get("age_seconds")
    heartbeat_text = heartbeat["reason"]
    if age is not None:
        heartbeat_text += f" ({age:.1f}s)"
    lines = [
        "LeafOS loop monitor",
        f"run         : {snapshot['run_id']}",
        f"state       : {snapshot['state']}",
        f"worker      : {controller.get('worker_pid') or 'none'} ({'alive' if controller.get('worker_alive') else 'stopped'})",
        f"heartbeat   : {heartbeat_text}",
        f"task        : {snapshot['current_task'] or 'none'}",
        f"events      : cursor {snapshot['event_cursor']} ({len(snapshot['new_events'])} new)",
        f"last event  : {last_event.get('seq', 0)} {last_event.get('kind', '')}",
        f"validation  : {run_status.get('validation_status', 'unknown')}",
        f"next action : {run_status.get('next_action', '')}",
    ]
    if snapshot["new_events"]:
        lines.append("recent events:")
        for event in snapshot["new_events"][-5:]:
            detail = event.get("summary") or event.get("reason") or event.get("error") or ""
            lines.append(f"  {int(event.get('seq', 0)):04d} {event.get('kind', ''):<28} {detail}")
    return "\n".join(lines)


def _monitor_mode(args: argparse.Namespace) -> str:
    if args.interactive and (args.json or args.jsonl):
        raise ValueError("--interactive cannot be combined with --json or --jsonl")
    if args.interactive:
        return "interactive"
    if args.noninteractive or args.json or args.jsonl:
        return "noninteractive"
    return "interactive" if sys.stdin.isatty() and sys.stdout.isatty() else "noninteractive"


def _monitor_exit_code(snapshot: dict[str, Any]) -> int:
    if snapshot["heartbeat"]["stale"]:
        return MONITOR_EXIT_STALE
    if snapshot["state"] in {"blocked", "stopped"}:
        return MONITOR_EXIT_FAILURE
    return 0


def _print_monitor_snapshot(snapshot: dict[str, Any], mode: str, as_json: bool) -> None:
    if mode == "interactive":
        if sys.stdout.isatty():
            print("\033[2J\033[H", end="")
        print(_monitor_text(snapshot), flush=True)
        return
    if as_json:
        print(json.dumps(snapshot, indent=2, ensure_ascii=True), flush=True)
    else:
        print(json.dumps(snapshot, separators=(",", ":"), ensure_ascii=True), flush=True)


def command_monitor(args: argparse.Namespace) -> int:
    if args.interval <= 0:
        raise ValueError("monitor interval must be greater than zero")
    if args.heartbeat_timeout <= 0:
        raise ValueError("heartbeat timeout must be greater than zero")
    if args.timeout < 0:
        raise ValueError("monitor timeout cannot be negative")
    run_dir = resolve_run(args.run)
    cursor_path = Path(args.cursor_file).resolve() if args.cursor_file else None
    if cursor_path is not None:
        try:
            cursor_path.relative_to(run_dir)
        except ValueError:
            pass
        else:
            raise ValueError("--cursor-file must be outside the run directory")
    cursor = _monitor_cursor(cursor_path, args.after)
    mode = _monitor_mode(args)
    one_shot = args.once or args.json
    deadline = time.monotonic() + args.timeout if args.timeout else None

    while True:
        snapshot = monitor_snapshot(run_dir, cursor, args.heartbeat_timeout)
        cursor = int(snapshot["event_cursor"])
        _write_monitor_cursor(cursor_path, cursor)
        _print_monitor_snapshot(snapshot, mode, args.json)

        if one_shot or snapshot["terminal"]:
            return _monitor_exit_code(snapshot)
        if snapshot["heartbeat"]["stale"] and mode == "noninteractive":
            return MONITOR_EXIT_STALE
        if deadline is not None and time.monotonic() >= deadline:
            return MONITOR_EXIT_TIMEOUT
        try:
            time.sleep(args.interval)
        except KeyboardInterrupt:
            return 130


def command_start(args: argparse.Namespace) -> int:
    run_dir = create_work_order_run(args) if args.work_order else create_repository_run(args)
    if args.create_only:
        print(run_dir)
        return 0
    if args.foreground:
        if args.json:
            print(json.dumps({"kind": "inlet.ready", "run_dir": str(run_dir)}, separators=(",", ":")))
        else:
            print(run_dir)
        return drive_run(run_dir, args.interval, echo_events=True, as_json=args.json)
    pid = spawn_worker(run_dir, args.interval)
    print(json.dumps({"run_dir": str(run_dir), "worker_pid": pid}, indent=2) if args.json else f"{run_dir}\nworker pid: {pid}")
    return 0


def command_attach(args: argparse.Namespace) -> int:
    run_dir = resolve_run(args.run)
    cursor = args.after
    while True:
        new_events = events_after(run_dir, cursor)
        for event in new_events:
            _print_event(event, args.json)
            cursor = int(event["seq"])
        state = engine.read_json(run_dir / "state.json", {}).get("status", "")
        worker = engine.read_json(run_dir / "worker.lock", {})
        alive = _pid_alive(int(worker.get("pid", 0)))
        if args.once or (state in TERMINAL_STATES and not alive):
            break
        time.sleep(args.interval)
    return 0


def command_control(args: argparse.Namespace) -> int:
    run_dir = resolve_run(args.run)
    if args.command == "approve":
        approve_run(run_dir)
    else:
        set_control_state(run_dir, args.command)
    if args.command in {"resume", "approve"}:
        lease = engine.read_json(run_dir / "worker.lock", {})
        if not _pid_alive(int(lease.get("pid", 0))):
            spawn_worker(run_dir, args.interval)
    print(json.dumps(status_payload(run_dir), indent=2) if args.json else engine.status_text(run_dir))
    return 0


def command_task(args: argparse.Namespace) -> int:
    run_dir = resolve_run(args.run)
    if args.task_command == "submit":
        request_path = Path(args.request).resolve(strict=True)
        request = json.loads(request_path.read_text(encoding="utf-8"))
        if request.get("action") != "submit":
            raise ValueError("task submit request must declare action=submit")
    else:
        request = {
            "leafos_object": "leafos.task_control_request",
            "version": 1,
            "request_id": "req-" + secrets.token_hex(8),
            "action": args.task_command,
            "task_id": args.task_id,
        }
        if args.task_command == "prioritize":
            request["priority"] = args.priority
    task = apply_task_control(run_dir, request)
    if args.task_command in {"submit", "retry", "approve"} and not args.no_spawn:
        lease = engine.read_json(run_dir / "worker.lock", {})
        if not _pid_alive(int(lease.get("pid", 0))):
            spawn_worker(run_dir, args.interval)
    payload = {"run_dir": str(run_dir), "action": args.task_command, "task": task, "status": status_payload(run_dir)}
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=True))
    else:
        print(f"{args.task_command}: {task['task_id']} -> {task['status']}")
    return 0


def command_status(args: argparse.Namespace) -> int:
    run_dir = resolve_run(args.run)
    data = status_payload(run_dir)
    if args.json:
        print(json.dumps(data, indent=2, ensure_ascii=True))
    else:
        print(engine.status_text(run_dir))
        print(f"worker       : {data['controller']['worker_pid'] or 'none'} ({'alive' if data['controller']['worker_alive'] else 'stopped'})")
        print(f"event cursor : {data['controller']['event_cursor']}")
        print(f"provider     : {data['provider_health']}")
    return 0


def _parse_benchmark_duration(value: str) -> float:
    value = str(value).strip().lower()
    if not value:
        raise ValueError("duration is required")
    if value.endswith("s"):
        return float(value[:-1])
    if value.endswith("m"):
        return float(value[:-1]) * 60
    if value.endswith("h"):
        return float(value[:-1]) * 3600
    raise ValueError("duration must end with s, m, or h")


def _benchmark_llm_round(
    endpoint: str,
    timeout: float,
    *,
    messages: list[dict[str, str]] | None = None,
    max_tokens: int = 128,
) -> dict[str, Any]:
    """Execute one conversational turn and return updated state plus token counts."""
    started = time.perf_counter()
    conversation = list(messages) if messages else [
        {"role": "system", "content": "You are a concise technical assistant."},
        {"role": "user", "content": "Write one sentence explaining how to benchmark a local language model installation."},
    ]
    payload = json.dumps({
        "model": "local",
        "messages": conversation,
        "max_tokens": max_tokens,
        "stream": False,
    }).encode("utf-8")
    request = urllib.request.Request(endpoint, data=payload, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8", errors="replace"))
        choices = data.get("choices", []) if isinstance(data, dict) else []
        message = choices[0].get("message", {}) if isinstance(choices, list) and choices else {}
        content = (message.get("content") or "").strip()
        usage = data.get("usage", {}) if isinstance(data, dict) else {}
        conversation.append({"role": "assistant", "content": content})
        return {
            "ok": True,
            "latency_seconds": round(time.perf_counter() - started, 3),
            "content": content,
            "messages": conversation,
            "prompt_tokens": usage.get("prompt_tokens"),
            "completion_tokens": usage.get("completion_tokens"),
            "total_tokens": usage.get("total_tokens"),
        }
    except (OSError, urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError, TimeoutError) as error:
        return {
            "ok": False,
            "latency_seconds": round(time.perf_counter() - started, 3),
            "error": str(error),
            "messages": conversation,
            "prompt_tokens": None,
            "completion_tokens": None,
            "total_tokens": None,
        }


_TASK_PROMPTS = [
    "Create a Python function that returns the sum of even numbers in a list.",
    "Write a small utility that parses a JSON file and prints its top-level keys.",
    "Add a factorial function with a simple doctest.",
]

# Realistic multi-turn conversation prompts used in llm benchmark mode.
_CONVERSATION_PROMPTS = [
    "What is the difference between Continuous Integration and Continuous Deployment?",
    "Summarize the tradeoffs of using Python versus Go for a small backend service.",
    "How can I reduce the VRAM usage of a locally running large language model?",
    "List three ways to make a REST API idempotent and give a short example.",
    "Explain why a benchmark should report latency percentiles, not just averages.",
    "What is the purpose of a run telemetry log like universal-run-log.jsonl?",
]


def _next_llm_prompt(iteration: int, previous_content: str) -> str:
    """Pick a prompt that builds on the previous assistant reply or restarts a topic."""
    if iteration == 0 or not previous_content:
        return _CONVERSATION_PROMPTS[0]
    follow_up = _CONVERSATION_PROMPTS[iteration % len(_CONVERSATION_PROMPTS)]
    return f"You previously said: '{previous_content[:200]}'. {follow_up}"


def _safe_id(text: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "_.-" else "_" for ch in text)[:40]


def _append_conversation(path: Path, role: str, message: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    item = {"time": datetime.now(timezone.utc).isoformat(), "role": role, "message": message}
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(item, ensure_ascii=True) + "\n")


def _append_llm_telemetry(
    log_path: Path,
    run_dir: Path,
    iteration: int,
    turn: dict[str, Any],
    provider_mode: str,
    provider_status: str,
    outcome: str,
) -> None:
    """Append one universal-run-log sample event for an LLM benchmark turn."""
    run_id = f"{run_dir.name}-turn-{iteration}"
    provider_requested = provider_mode != "off"
    provider_alive = provider_status == "running"
    event = leaf_telemetry.make_universal_event(
        run_id,
        run_kind="fullstackbench",
        event_type="sample",
        phase="execution",
        run_dir=run_dir,
        task_id=f"benchmark-llm-turn-{iteration}",
        provider={
            "mode": provider_mode,
            "backend": "vulkan" if provider_requested else None,
            "endpoint": None,
            "status": provider_status,
            "pid": None,
        },
        instances={
            "initiated": 1 if provider_requested else 0,
            "alive": 1 if provider_alive else 0,
            "brain_initiated": 1 if provider_requested else 0,
            "brain_alive": 1 if provider_alive else 0,
            "coder_initiated": 0,
            "coder_alive": 0,
            "provider_initiated": 1 if provider_requested else 0,
            "provider_alive": 1 if provider_alive else 0,
            "crashed": 0,
            "restarted": 0,
        },
        throughput={
            "brain_prompt_tk_s": None,
            "brain_generation_tk_s": None,
            "coder_prompt_tk_s": None,
            "coder_generation_tk_s": None,
            "helper_generation_tk_s": None,
            "aggregate_generation_tk_s": None,
            "time_to_first_token_seconds": None,
            "prompt_tokens": turn.get("prompt_tokens"),
            "generated_tokens": turn.get("completion_tokens"),
        },
        quality={
            "validation_status": "passed" if turn.get("ok") else "failed",
            "checkpoint_valid": None,
            "accepted_changes": None,
            "rejected_changes": None,
            "score_delta": None,
        },
        notes=[
            f"outcome={outcome}",
            f"latency_seconds={turn.get('latency_seconds')}",
            f"error=" + (turn.get("error") or ""),
        ],
    )
    leaf_telemetry.append_universal_event(log_path, event)


def _benchmark_brain_coder_round(run_dir: Path, iteration: int, provider: str) -> dict[str, Any]:
    started = time.perf_counter()
    node_id = f"bench-{iteration:04d}"
    task_file = run_dir / "tasks" / f"{node_id}.md"
    task_file.parent.mkdir(parents=True, exist_ok=True)
    prompt = _TASK_PROMPTS[iteration % len(_TASK_PROMPTS)]
    task_file.write_text(f"# {node_id}\n\n{prompt}\n", encoding="utf-8")

    conversation_path = run_dir / "conversation.jsonl"
    _append_conversation(conversation_path, "user", prompt)

    root_posix = ROOT.as_posix()
    run_dir_posix = run_dir.as_posix()
    task_posix = task_file.as_posix()
    env = os.environ.copy()
    env["LEAF_RUN_DIR"] = run_dir_posix
    env["_ACTIONS_ROOT"] = root_posix
    input_json = json.dumps({"task_file": task_posix})

    # Sanity-check environment prerequisites so we log a clear reason instead of silently failing.
    try:
        jq_check = subprocess.run(
            ["bash", "-c", "command -v jq"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
    except (OSError, subprocess.TimeoutExpired):
        jq_check = None
    if jq_check is None or jq_check.returncode != 0:
        reason = "jq not found in bash PATH; install jq to enable the Brain/Coder thinking trace"
        _append_conversation(conversation_path, "system", reason)
        return {
            "ok": False, "latency_seconds": round(time.perf_counter() - started, 3),
            "error": reason, "thinking": {"planner": {"status": "failed"}, "coder": {"status": "failed"}, "patch_gate": {"status": "failed", "reason": reason}},
        }

    try:
        script = (ROOT / "core" / "agent" / "actions.sh").as_posix()
        command = f"source {script!r}; agent_run_action agent.dual_think {node_id!r} {input_json!r}"
        result = subprocess.run(
            ["bash", "-c", command],
            cwd=ROOT,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=60,
            creationflags=(subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP) if os.name == "nt" else 0,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        reason = f"brain-coder invocation failed: {error}"
        _append_conversation(conversation_path, "system", reason)
        return {
            "ok": False, "latency_seconds": round(time.perf_counter() - started, 3),
            "error": reason, "thinking": {"planner": {"status": "failed"}, "coder": {"status": "failed"}, "patch_gate": {"status": "failed", "reason": str(error)}},
        }

    stream_dir = run_dir / "dual-thinking" / node_id
    state_file = stream_dir / "dual-thinking.json"
    state: dict[str, Any] = {}
    if state_file.is_file():
        try:
            state = json.loads(state_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass

    planner_status = state.get("planner", {}).get("status", "unknown")
    coder_status = state.get("coder", {}).get("status", "unknown")
    failure = state.get("failure", "")
    patch_path = stream_dir / "coder" / "patch.diff"
    patch_ok = patch_path.is_file() and patch_path.stat().st_size > 0

    graph_summary = "no graph"
    graph_file = stream_dir / "brain.graph.json"
    if graph_file.is_file():
        try:
            graph = json.loads(graph_file.read_text(encoding="utf-8"))
            nodes = graph.get("nodes", []) if isinstance(graph, dict) else []
            graph_summary = f"graph with {len(nodes)} node(s)"
        except json.JSONDecodeError:
            graph_summary = "graph unreadable"

    _append_conversation(conversation_path, "brain", f"planner status: {planner_status}; {graph_summary}")
    _append_conversation(conversation_path, "coder", f"coder status: {coder_status}; patch present: {patch_ok}")

    thinking = {
        "planner": {"status": planner_status, "graph_path": str(graph_file) if graph_file.is_file() else None},
        "coder": {"status": coder_status, "handoff_path": str(stream_dir / "coder.handoff.md") if (stream_dir / "coder.handoff.md").is_file() else None, "patch_path": str(patch_path) if patch_ok else None},
        "patch_gate": {"status": "passed" if patch_ok else "failed", "reason": failure or ("patch missing" if not patch_ok else "")},
    }

    stderr_tail = result.stderr.strip()[-250:] if result.stderr else ""
    system_msg = f"dual-think done: planner={planner_status}, coder={coder_status}, patch={'ok' if patch_ok else 'missing'}"
    if failure:
        system_msg += f", failure={failure}"
    if stderr_tail:
        system_msg += f"; stderr tail: {stderr_tail}"
    _append_conversation(conversation_path, "system", system_msg)

    if stderr_tail and not failure:
        thinking["patch_gate"]["reason"] = stderr_tail

    return {
        "ok": result.returncode == 0 and patch_ok,
        "latency_seconds": round(time.perf_counter() - started, 3),
        "returncode": result.returncode,
        "thinking": thinking,
        "stderr": result.stderr[:300],
    }


def _benchmark_skeleton_project(work_root: Path, provider: str) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        result = subprocess.run(
            [
                sys.executable, str(ROOT / "core" / "python" / "leaf_live_project.py"),
                str(work_root), "--new", "--template", "generic",
                "--objective", "Installation benchmark skeleton project",
                "--provider", provider, "--yes", "--no-worker", "--no-tui", "--json",
            ],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=60,
            creationflags=(subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP) if os.name == "nt" else 0,
        )
        payload = {}
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError:
            pass
        return {
            "ok": result.returncode == 0,
            "latency_seconds": round(time.perf_counter() - started, 3),
            "action": payload.get("action"),
            "run_dir": payload.get("run_dir"),
            "stderr": result.stderr[:300],
        }
    except (OSError, subprocess.TimeoutExpired) as error:
        return {"ok": False, "latency_seconds": round(time.perf_counter() - started, 3), "error": str(error)}


def command_benchmark(args: argparse.Namespace) -> int:
    duration = _parse_benchmark_duration(args.duration)
    if not 1 <= duration <= 3600:
        raise ValueError("benchmark duration must be between 1s and 1h")
    sample_interval = max(0.5, min(10.0, 1.0 / max(0.1, args.sample_hz)))
    bench_dir = ROOT / "runs" / "bench" / f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-install"
    bench_dir.mkdir(parents=True, exist_ok=True)
    universal_log = bench_dir / leaf_telemetry.UNIVERSAL_LOG_NAME

    provider_status, provider_reason = ensure_provider(args.provider, start_stack=(args.provider != "off"))
    config = load_provider_config() if args.provider != "off" else {}
    endpoint = provider_endpoint(config) if config else ""

    health_samples: list[bool] = []
    cpu_samples: list[float] = []
    gpu_samples: list[float] = []
    work_iterations: list[dict[str, Any]] = []
    llm_conversation: list[dict[str, str]] = []
    conversation_path = bench_dir / "conversation.jsonl"
    started = time.monotonic()
    deadline = started + duration
    next_sample = started

    while time.monotonic() < deadline:
        now = time.monotonic()
        if now >= next_sample:
            sample = leaf_telemetry.collect_fast_hardware()
            cpu_samples.append(float(sample.get("hardware", {}).get("cpu", {}).get("utilization_percent", 0) or 0))
            gpu_samples.append(float(sample.get("hardware", {}).get("gpu", {}).get("utilization_percent", 0) or 0))
            if args.provider != "off":
                health_samples.append(provider_healthy(endpoint))
            next_sample += sample_interval

        work_start = time.monotonic()
        iteration = len(work_iterations)
        if args.mode == "llm":
            previous_content = work_iterations[-1].get("content", "") if work_iterations else ""
            user_prompt = _next_llm_prompt(iteration, previous_content)
            llm_conversation.append({"role": "user", "content": user_prompt})
            _append_conversation(conversation_path, "user", user_prompt)
            if endpoint and provider_healthy(endpoint):
                turn = _benchmark_llm_round(
                    endpoint,
                    timeout=30,
                    messages=llm_conversation,
                    max_tokens=args.max_tokens,
                )
                work_iterations.append(turn)
                if turn.get("ok"):
                    llm_conversation = list(turn.get("messages", llm_conversation))
                    _append_conversation(conversation_path, "assistant", turn.get("content", ""))
                    _append_llm_telemetry(
                        universal_log, bench_dir, iteration, turn,
                        args.provider, provider_status, "ok",
                    )
                else:
                    _append_llm_telemetry(
                        universal_log, bench_dir, iteration, turn,
                        args.provider, provider_status, "error",
                    )
            else:
                failure = {"ok": False, "error": "provider not healthy", "latency_seconds": 0}
                work_iterations.append(failure)
                _append_llm_telemetry(
                    universal_log, bench_dir, iteration, failure,
                    args.provider, provider_status, "provider_unhealthy",
                )
        elif args.mode == "brain-coder":
            work_iterations.append(_benchmark_brain_coder_round(bench_dir, iteration, args.provider))
            if not args.json:
                sample = work_iterations[-1]
                print(f"  [{iteration + 1}] brain={sample['thinking']['planner']['status']} coder={sample['thinking']['coder']['status']} patch={sample['thinking']['patch_gate']['status']} ({sample['latency_seconds']}s)")
        else:
            skeleton_root = bench_dir / f"skeleton-{iteration}"
            work_iterations.append(_benchmark_skeleton_project(skeleton_root, args.provider))

        # pace to sample interval without exceeding deadline
        elapsed_work = time.monotonic() - work_start
        sleep_for = max(0.0, min(sample_interval - elapsed_work, deadline - time.monotonic()))
        if sleep_for > 0:
            time.sleep(sleep_for)

    actual_duration = time.monotonic() - started
    ok_iterations = [item for item in work_iterations if item.get("ok")]
    latencies = [item["latency_seconds"] for item in work_iterations if "latency_seconds" in item]

    # Persist normalized meta-artifacts for special modes.
    thinking_summary: dict[str, Any] = {}
    llm_summary: dict[str, Any] = {}
    if args.mode == "brain-coder":
        thinking_summary = {
            "iterations": len(work_iterations),
            "successful_thinking": len([item for item in work_iterations if item.get("thinking", {}).get("patch_gate", {}).get("status") == "passed"]),
            "last_thinking": work_iterations[-1].get("thinking") if work_iterations else None,
        }
        (bench_dir / "thinking.json").write_text(json.dumps(thinking_summary, indent=2) + "\n", encoding="utf-8")
    elif args.mode == "llm":
        llm_summary = {
            "iterations": len(work_iterations),
            "successful_turns": len(ok_iterations),
            "total_prompt_tokens": int(sum(
                item.get("prompt_tokens") or 0 for item in work_iterations
            )),
            "total_completion_tokens": int(sum(
                item.get("completion_tokens") or 0 for item in work_iterations
            )),
            "last_turn": work_iterations[-1] if work_iterations else None,
        }

    result = {
        "leafos_object": "leafos.install_benchmark",
        "version": 1,
        "mode": args.mode,
        "duration_requested_sec": duration,
        "duration_actual_sec": round(actual_duration, 3),
        "provider_mode": args.provider,
        "provider_health": provider_status,
        "provider_reason": provider_reason,
        "samples": {
            "count": len(cpu_samples),
            "cpu_avg": round(sum(cpu_samples) / len(cpu_samples), 3) if cpu_samples else None,
            "cpu_max": round(max(cpu_samples), 3) if cpu_samples else None,
            "gpu_avg": round(sum(gpu_samples) / len(gpu_samples), 3) if gpu_samples else None,
            "gpu_max": round(max(gpu_samples), 3) if gpu_samples else None,
            "provider_healthy_samples": sum(health_samples) if health_samples else None,
        },
        "work": {
            "iterations": len(work_iterations),
            "successful": len(ok_iterations),
            "avg_latency_seconds": round(sum(latencies) / len(latencies), 3) if latencies else None,
            "max_latency_seconds": round(max(latencies), 3) if latencies else None,
            "last_sample": work_iterations[-1] if work_iterations else None,
        },
        "thinking_process": thinking_summary,
        "llm_conversation": llm_summary,
        "run_dir": str(bench_dir),
    }
    (bench_dir / "benchmark.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"install benchmark complete: {result['duration_actual_sec']}s  mode={args.mode}")
        print(f"  telemetry samples: {result['samples']['count']}")
        print(f"  CPU avg/max: {result['samples']['cpu_avg']}% / {result['samples']['cpu_max']}%")
        print(f"  GPU avg/max: {result['samples']['gpu_avg']}% / {result['samples']['gpu_max']}%")
        print(f"  work iterations: {result['work']['iterations']} successful={result['work']['successful']}")
        print(f"  avg latency: {result['work']['avg_latency_seconds']}s")
        if args.mode == "brain-coder":
            print(f"  thinking trace: {bench_dir / 'conversation.jsonl'}")
            print(f"  thinking summary: {bench_dir / 'thinking.json'}")
        if args.mode == "llm":
            print(f"  conversation trace: {bench_dir / 'conversation.jsonl'}")
            print(f"  universal telemetry: {bench_dir / leaf_telemetry.UNIVERSAL_LOG_NAME}")
        print(f"  report: {bench_dir / 'benchmark.json'}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    start = sub.add_parser("start", help="start a bounded continual loop for an existing repository")
    start.add_argument("target", nargs="?")
    start.add_argument("--target", dest="target_option", default="")
    start.add_argument("--profile", default="local-coding")
    start.add_argument("--work-order", default="", help="path to a work-order file inside the repository or LeafOS work-order directory")
    start.add_argument("--objective", default="Review and execute the queued repository validation command.")
    start.add_argument("--provider", choices=("required", "auto", "off"), default="required")
    start.add_argument("--run-id", default="")
    start.add_argument("--run-dir", default="")
    start.add_argument("--max-minutes", type=int, default=64)
    start.add_argument("--timeout-seconds", type=int, default=600)
    start.add_argument("--interval", type=float, default=1.0)
    start.add_argument("--no-start-provider", action="store_true")
    start.add_argument("--yes", action="store_true", help="approve work-order mutation steps")
    mode = start.add_mutually_exclusive_group()
    mode.add_argument("--foreground", action="store_true")
    mode.add_argument("--create-only", action="store_true")
    start.add_argument("--json", action="store_true")
    start.add_argument("--check", nargs=argparse.REMAINDER, default=[], metavar="COMMAND")
    start.set_defaults(handler=command_start)

    drive = sub.add_parser("drive", help="run the continual worker in the current process")
    drive.add_argument("run")
    drive.add_argument("--interval", type=float, default=1.0)
    drive.add_argument("--json", action="store_true")
    drive.set_defaults(handler=lambda args: drive_run(resolve_run(args.run), args.interval, True, args.json))

    attach = sub.add_parser("attach", help="stream recorded loop events from a reconnect cursor")
    attach.add_argument("run", nargs="?", default="active")
    attach.add_argument("--after", type=int, default=0)
    attach.add_argument("--interval", type=float, default=0.5)
    attach.add_argument("--once", action="store_true")
    attach.add_argument("--json", action="store_true")
    attach.set_defaults(handler=command_attach)

    monitor = sub.add_parser("monitor", help="monitor a loop in interactive or detached mode")
    monitor.add_argument("run", nargs="?", default="active")
    monitor.add_argument("--after", type=int, default=0, help="start after this event sequence")
    monitor.add_argument("--interval", type=float, default=MONITOR_DEFAULT_INTERVAL_SECONDS)
    monitor.add_argument("--heartbeat-timeout", type=float, default=MONITOR_DEFAULT_HEARTBEAT_TIMEOUT_SECONDS)
    monitor.add_argument("--timeout", type=float, default=0.0, help="stop after N seconds; zero means no limit")
    monitor.add_argument("--cursor-file", default="", help="persist the reconnect cursor outside the run")
    monitor.add_argument("--once", action="store_true", help="emit one snapshot and exit")
    output = monitor.add_mutually_exclusive_group()
    output.add_argument("--json", action="store_true", help="emit one indented JSON snapshot")
    output.add_argument("--jsonl", action="store_true", help="emit newline-delimited JSON snapshots")
    mode = monitor.add_mutually_exclusive_group()
    mode.add_argument("--interactive", action="store_true", help="force terminal rendering")
    mode.add_argument("--noninteractive", action="store_true", help="force detached JSONL rendering")
    monitor.set_defaults(handler=command_monitor)

    task = sub.add_parser("task", help="submit and control typed tasks through the authoritative inlet")
    task_sub = task.add_subparsers(dest="task_command", required=True)
    submit = task_sub.add_parser("submit", help="submit a schema-constrained task request JSON")
    submit.add_argument("run")
    submit.add_argument("request")
    for name in ("retry", "cancel", "approve"):
        child = task_sub.add_parser(name, help=f"{name} a task by ID")
        child.add_argument("run")
        child.add_argument("task_id")
    prioritize = task_sub.add_parser("prioritize", help="set queue priority 0 (highest) through 9")
    prioritize.add_argument("run")
    prioritize.add_argument("task_id")
    prioritize.add_argument("priority", type=int)
    for child in (submit, *[task_sub.choices[name] for name in ("retry", "cancel", "approve", "prioritize")]):
        child.add_argument("--interval", type=float, default=1.0)
        child.add_argument("--no-spawn", action="store_true")
        child.add_argument("--json", action="store_true")
        child.set_defaults(handler=command_task)

    control_help = {
        "pause": "pause task claiming after the current command",
        "resume": "resume a paused loop and ensure a worker is running",
        "stop": "stop the worker after the current command",
        "drain": "finish queued work without accepting new tasks",
        "approve": "approve mutation steps for a blocked work-order run",
    }
    for name in ("pause", "resume", "stop", "drain", "approve"):
        control = sub.add_parser(name, help=control_help[name])
        control.add_argument("run", nargs="?", default="active")
        control.add_argument("--interval", type=float, default=1.0)
        control.add_argument("--json", action="store_true")
        control.set_defaults(handler=command_control)

    status = sub.add_parser("status", help="show the active run, worker, cursor, and provider state")
    status.add_argument("run", nargs="?", default="active")
    status.add_argument("--json", action="store_true")
    status.set_defaults(handler=command_status)

    report = sub.add_parser("report", help="render the persistent run report")
    report.add_argument("run", nargs="?", default="active")
    report.add_argument("--json", action="store_true")
    report.set_defaults(
        handler=lambda args: engine.report_run(argparse.Namespace(run=str(resolve_run(args.run)), json=args.json))
    )

    benchmark = sub.add_parser("benchmark", help="run a lightweight installation readiness benchmark")
    benchmark.add_argument("duration", help="benchmark wall time, e.g. 30s, 60s, 5m")
    benchmark.add_argument("--json", action="store_true")
    benchmark.add_argument("--provider", choices=("required", "auto", "off"), default="auto")
    benchmark.add_argument("--sample-hz", type=float, default=1.0, help="telemetry samples per second")
    benchmark.add_argument("--mode", choices=("llm", "skeleton", "brain-coder"), default="llm", help="workload: llm conversation, demo skeleton project, or brain->coder thinking trace")
    benchmark.add_argument("--max-tokens", type=int, default=128, help="max completion tokens for each llm benchmark turn")
    benchmark.set_defaults(handler=command_benchmark)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return int(args.handler(args) or 0)
    except (ValueError, RuntimeError) as error:
        print(f"loop: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
