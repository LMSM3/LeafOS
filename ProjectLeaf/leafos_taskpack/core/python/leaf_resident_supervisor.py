#!/usr/bin/env python3
"""Resident queue and resource supervisor for the LeafOS live stack."""

from __future__ import annotations

import argparse
import json
import os
import secrets
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


PYTHON_DIR = Path(__file__).resolve().parent
if str(PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(PYTHON_DIR))

import leaf_agent_loop as engine  # noqa: E402
import leaf_foreground_activity as foreground  # noqa: E402
import leaf_loop_inlet as inlet  # noqa: E402
import leaf_resource_governor as governor  # noqa: E402
import leaf_telemetry as telemetry  # noqa: E402


ROOT = Path(__file__).resolve().parents[2]
STATE_NAME = "resident-state.json"
LEASE_NAME = "resident.lock"
LOG_NAME = "resident.log"
ACTIVE_TASK_STATES = {"planning", "planned", "executing", "running", "validating"}
READY_TASK_STATES = {"queued", "repair_queued"}
TERMINAL_TASK_STATES = {"complete", "cancelled"}
RECOVERY_DELAYS = (5.0, 15.0, 30.0)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _pid_alive(pid: int) -> bool:
    return inlet._pid_alive(pid)


def _resident_path(run_dir: Path) -> Path:
    return run_dir / STATE_NAME


def _default_state(run_dir: Path, policy: dict[str, Any], mode: str = "auto") -> dict[str, Any]:
    run = engine.read_json(run_dir / "run.json", {})
    return {
        "leafos_object": "leafos.resident_state",
        "version": 1,
        "run_id": str(run.get("run_id") or run_dir.name),
        "enabled": True,
        "status": "starting",
        "mode": mode,
        "started_utc": utc_now(),
        "updated_utc": utc_now(),
        "supervisor_pid": None,
        "worker_pid": None,
        "policy_path": str(governor.DEFAULT_POLICY_PATH),
        "targets_override": {},
        "budgets": dict(policy["budgets"]),
        "usage": {"iterations_generated": 0, "failures": 0, "changed_files": 0, "elapsed_minutes": 0.0},
        "provider_recovery": {"attempts": 0, "next_retry_monotonic": 0.0, "last_error": ""},
        "last_decision": {},
        "last_transition": "",
        "last_transition_utc": "",
    }


def initialize_resident(
    run_value: str | Path,
    *,
    policy_path: str | Path | None = None,
    mode: str | None = None,
    budget_minutes: int | None = None,
) -> dict[str, Any]:
    run_dir = inlet.resolve_run(str(run_value))
    state = engine.read_json(_resident_path(run_dir), {})
    effective_policy_path = Path(policy_path or state.get("policy_path") or governor.DEFAULT_POLICY_PATH).resolve()
    policy = governor.load_policy(effective_policy_path)
    if state.get("leafos_object") != "leafos.resident_state":
        state = _default_state(run_dir, policy, mode or "auto")
    if mode is not None and mode not in {"auto", "quiet", "full"}:
        raise ValueError("resident mode must be auto, quiet, or full")
    state.update(enabled=True, policy_path=str(effective_policy_path), updated_utc=utc_now())
    if mode is not None:
        state["mode"] = mode
    state.setdefault("budgets", {}).update({key: int(value) for key, value in policy["budgets"].items() if key not in state.get("budgets", {})})
    if budget_minutes is not None:
        if not 1 <= int(budget_minutes) <= 10080:
            raise ValueError("resident budget must be between 1 and 10080 minutes")
        state["budgets"]["unattended_minutes"] = int(budget_minutes)
    engine.write_json(_resident_path(run_dir), state)
    run = engine.read_json(run_dir / "run.json", {})
    run["resident"] = {"enabled": True, "state": STATE_NAME, "policy": state["policy_path"]}
    engine.write_json(run_dir / "run.json", run)
    return state


def resident_status(run_value: str | Path = "active") -> dict[str, Any]:
    run_dir = inlet.resolve_run(str(run_value))
    state = engine.read_json(_resident_path(run_dir), {})
    run = engine.read_json(run_dir / "run.json", {})
    lease = engine.read_json(run_dir / LEASE_NAME, {})
    pid = int(lease.get("pid", 0))
    worker_alive, worker_pid = inlet.worker_lease_status(run_dir, pid_probe=_pid_alive)
    result = dict(state)
    result.update({
        "run_id": state.get("run_id") or run.get("run_id") or run_dir.name,
        "run_dir": str(run_dir),
        "supervisor_pid": pid or state.get("supervisor_pid"),
        "supervisor_alive": _pid_alive(pid),
        "worker_pid": worker_pid or None,
        "worker_alive": worker_alive,
    })
    return result


def _journal_resident_control(run_dir: Path, action: str, data: dict[str, Any]) -> None:
    run = engine.read_json(run_dir / "run.json", {})
    inlet._journal_task_control(run_dir, run, {
        "leafos_object": "leafos.task_control_request",
        "version": 1,
        "request_id": "req-" + secrets.token_hex(8),
        "action": f"resident.{action}",
        "data": data,
    })


def set_resident_control(run_value: str | Path, action: str, **values: Any) -> dict[str, Any]:
    run_dir = inlet.resolve_run(str(run_value))
    state = engine.read_json(_resident_path(run_dir), {})
    if state.get("leafos_object") != "leafos.resident_state":
        state = initialize_resident(run_dir)
    action = action.lower()
    if action == "mode":
        mode = str(values.get("mode", "")).lower()
        if mode not in {"auto", "quiet", "full"}:
            raise ValueError("resident mode must be auto, quiet, or full")
        state["mode"] = mode
    elif action == "targets":
        cpu = float(values.get("cpu"))
        gpu = float(values.get("gpu"))
        if not 1 <= cpu <= 100 or not 1 <= gpu <= 100:
            raise ValueError("resident CPU and GPU targets must be between 1 and 100")
        state["targets_override"] = {"cpu_percent": cpu, "gpu_percent": gpu}
    elif action == "budget":
        minutes = int(values.get("minutes"))
        if not 1 <= minutes <= 10080:
            raise ValueError("resident budget must be between 1 and 10080 minutes")
        state.setdefault("budgets", {})["unattended_minutes"] = minutes
        if state.get("status") == "awaiting_budget":
            state["status"] = "waiting"
    elif action in {"pause", "resume", "drain", "stop"}:
        inlet.set_control_state(run_dir, action)
        if action == "resume":
            state["enabled"] = True
        if action == "stop":
            state["enabled"] = False
        state["status"] = {"pause": "paused", "resume": "active", "drain": "draining", "stop": "stopped"}[action]
    else:
        raise ValueError(f"unknown resident control: {action}")
    state["updated_utc"] = utc_now()
    _journal_resident_control(run_dir, action, values)
    engine.write_json(_resident_path(run_dir), state)
    engine.append_event(run_dir, "resident.control", action=action, values=values)
    if action == "resume":
        ensure_supervisor(run_dir)
    return state


def acquire_lease(run_dir: Path) -> Path:
    lease = run_dir / LEASE_NAME
    if lease.exists():
        current = engine.read_json(lease, {})
        if int(current.get("pid", 0)) == os.getpid():
            return lease
        if _pid_alive(int(current.get("pid", 0))):
            raise RuntimeError(f"resident supervisor already has pid {current.get('pid')}")
        lease.unlink(missing_ok=True)
    fd = os.open(lease, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump({"pid": os.getpid(), "started_utc": utc_now()}, handle)
        handle.flush()
        os.fsync(handle.fileno())
    return lease


def spawn_supervisor(run_value: str | Path, interval: float = 1.0) -> int:
    run_dir = inlet.resolve_run(str(run_value))
    initialize_resident(run_dir)
    with engine.queue_write_lock(run_dir):
        current = resident_status(run_dir)
        if current.get("supervisor_alive"):
            return int(current["supervisor_pid"])
        log_path = run_dir / LOG_NAME
        command = [sys.executable, str(Path(__file__).resolve()), "drive", str(run_dir), "--interval", str(interval)]
        creationflags = 0
        if os.name == "nt":
            creationflags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
        with log_path.open("a", encoding="utf-8") as log:
            process = subprocess.Popen(
                command,
                cwd=ROOT,
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
                creationflags=creationflags,
                start_new_session=os.name != "nt",
            )
        engine.write_json(run_dir / LEASE_NAME, {"pid": process.pid, "started_utc": utc_now()})
    engine.append_event(run_dir, "resident.spawned", pid=process.pid, log=str(log_path))
    return process.pid


def ensure_supervisor(run_value: str | Path, interval: float = 1.0) -> int:
    status = resident_status(run_value)
    return int(status["supervisor_pid"]) if status.get("supervisor_alive") else spawn_supervisor(status["run_dir"], interval)


class ResidentSupervisor:
    def __init__(
        self,
        run_dir: Path,
        *,
        interval: float = 1.0,
        collector: Callable[..., dict[str, Any]] = telemetry.collect_fast_hardware,
        input_probe: Callable[[], float | None] = foreground.input_idle_seconds,
        clock: Callable[[], float] = time.monotonic,
        worker_spawner: Callable[[Path, float], int] = inlet.spawn_worker,
        provider_refresher: Callable[[str], tuple[str, str]] | None = None,
        refill: Callable[..., dict[str, Any]] | None = None,
    ):
        self.run_dir = run_dir.resolve()
        self.interval = max(0.1, min(float(interval), 30.0))
        self.collector = collector
        self.input_probe = input_probe
        self.clock = clock
        self.worker_spawner = worker_spawner
        self.provider_refresher = provider_refresher
        self.refill = refill
        self.probe = foreground.ResponsivenessProbe(self.interval, clock)

    def _queue_facts(self, queue: dict[str, Any]) -> dict[str, Any]:
        tasks = queue.get("tasks", []) if isinstance(queue.get("tasks"), list) else []
        ready = [task for task in tasks if task.get("status") in READY_TASK_STATES and engine.dependencies_complete(queue, task)]
        active = [task for task in tasks if task.get("status") in ACTIVE_TASK_STATES]
        blocked = [task for task in tasks if task.get("status") in {"blocked", "failed"}]
        return {
            "tasks": tasks,
            "ready": ready,
            "active": active,
            "blocked": blocked,
            "repair": [task for task in tasks if task.get("status") == "repair_queued"],
            "gpu_needed": any(task.get("provider") == "llamacpp" for task in ready),
            "all_terminal": bool(tasks) and all(task.get("status") in TERMINAL_TASK_STATES for task in tasks),
        }

    def _elapsed_minutes(self, state: dict[str, Any]) -> float:
        try:
            started = datetime.fromisoformat(str(state["started_utc"]))
            if started.tzinfo is None:
                started = started.replace(tzinfo=timezone.utc)
            return max(0.0, (datetime.now(timezone.utc) - started).total_seconds() / 60.0)
        except (KeyError, TypeError, ValueError):
            return 0.0

    def _update_usage(self, resident: dict[str, Any], queue_facts: dict[str, Any]) -> str:
        checkpoint = engine.read_json(self.run_dir / "checkpoint.json", {})
        changed = checkpoint.get("changed_file_hashes", {})
        failures = sum(
            task.get("status") in {"failed", "blocked"} and task.get("reason") not in {"approval_required", "dependency_cancelled"}
            for task in queue_facts["tasks"]
        )
        usage = resident.setdefault("usage", {})
        usage.update(
            elapsed_minutes=round(self._elapsed_minutes(resident), 3),
            failures=failures,
            changed_files=len(changed) if isinstance(changed, dict) else 0,
        )
        budgets = resident["budgets"]
        if usage["elapsed_minutes"] >= int(budgets["unattended_minutes"]):
            return "unattended_time_exhausted"
        if int(usage.get("iterations_generated", 0)) >= int(budgets["max_iterations"]):
            return "iteration_budget_exhausted"
        if failures >= int(budgets["max_failures"]):
            return "failure_budget_exhausted"
        if usage["changed_files"] >= int(budgets["max_changed_files"]):
            return "change_budget_exhausted"
        return ""

    def _provider_health(self, run: dict[str, Any]) -> str:
        mode = str(run.get("provider_mode", "off"))
        endpoint = str(run.get("provider_endpoint", ""))
        if mode == "off":
            return "off"
        return "ready" if endpoint and inlet.provider_healthy(endpoint, timeout=0.25) else "unavailable"

    def _launch_provider_recovery(self) -> int:
        log_path = self.run_dir / "provider-recovery.log"
        command = [
            "pwsh", "-NoProfile", "-File", str(ROOT / "bin" / "vulkan-provider.ps1"),
            "-Action", "start", "-Json",
        ]
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
        with log_path.open("a", encoding="utf-8") as log:
            process = subprocess.Popen(
                command, cwd=ROOT, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                creationflags=creationflags, start_new_session=os.name != "nt",
            )
        return process.pid

    def _recover_provider(self, run: dict[str, Any], resident: dict[str, Any], now: float) -> str:
        health = self._provider_health(run)
        recovery = resident.setdefault("provider_recovery", {"attempts": 0, "next_retry_monotonic": 0.0, "last_error": ""})
        if health == "ready" or str(run.get("provider_mode")) == "off":
            recovery.update(attempts=0, next_retry_monotonic=0.0, last_error="", process_pid=None)
            return health
        attempts = int(recovery.get("attempts", 0))
        recovery_pid = int(recovery.get("process_pid") or 0)
        if recovery_pid and _pid_alive(recovery_pid):
            return health
        if recovery_pid:
            recovery["process_pid"] = None
            if self._provider_health(run) == "ready":
                run.update(provider_status="ready", provider_reason="provider recovered asynchronously")
                run["provider_restarts"] = int(run.get("provider_restarts", 0)) + 1
                recovery.update(attempts=0, next_retry_monotonic=0.0, last_error="")
                engine.write_json(self.run_dir / "run.json", run)
                engine.append_event(self.run_dir, "provider.recovered", attempts=attempts + 1)
                return "ready"
            attempts += 1
            recovery.update(
                attempts=attempts,
                next_retry_monotonic=now + RECOVERY_DELAYS[min(attempts - 1, len(RECOVERY_DELAYS) - 1)],
                last_error="provider recovery process exited without a healthy endpoint",
            )
        if attempts >= len(RECOVERY_DELAYS) or now < float(recovery.get("next_retry_monotonic", 0.0)):
            return health
        if self.provider_refresher is None:
            try:
                recovery["process_pid"] = self._launch_provider_recovery()
                run.update(provider_status="starting", provider_reason="resident recovery process is running")
                engine.write_json(self.run_dir / "run.json", run)
                engine.append_event(self.run_dir, "provider.recovery_started", pid=recovery["process_pid"], attempt=attempts + 1)
            except OSError as exception:
                attempts += 1
                recovery.update(
                    attempts=attempts,
                    next_retry_monotonic=now + RECOVERY_DELAYS[min(attempts - 1, len(RECOVERY_DELAYS) - 1)],
                    last_error=str(exception), process_pid=None,
                )
                engine.append_event(self.run_dir, "provider.recovery_deferred", attempts=attempts, error=str(exception))
            return health
        try:
            status, reason = self.provider_refresher(str(run.get("provider_mode", "required")))
            run.update(provider_status=status, provider_reason=reason)
            if status == "ready":
                run["provider_endpoint"] = inlet.provider_endpoint(inlet.load_provider_config())
                run["provider_restarts"] = int(run.get("provider_restarts", 0)) + 1
                recovery.update(attempts=0, next_retry_monotonic=0.0, last_error="")
                engine.write_json(self.run_dir / "run.json", run)
                engine.append_event(self.run_dir, "provider.recovered", attempts=attempts + 1)
                return "ready"
            error = reason or status
        except (OSError, RuntimeError, ValueError) as exception:
            error = str(exception)
        attempts += 1
        recovery.update(
            attempts=attempts,
            next_retry_monotonic=now + RECOVERY_DELAYS[min(attempts - 1, len(RECOVERY_DELAYS) - 1)],
            last_error=error,
        )
        run["provider_status"] = "degraded"
        run["provider_crashes"] = int(run.get("provider_crashes", 0)) + 1
        engine.write_json(self.run_dir / "run.json", run)
        engine.append_event(self.run_dir, "provider.recovery_deferred", attempts=attempts, error=error)
        return "unavailable"

    def _refill(self, resident: dict[str, Any]) -> dict[str, Any]:
        if self.refill:
            result = self.refill(str(self.run_dir), objective="", spawn=False, source="resident")
        else:
            import leaf_live_project as live_projects
            result = live_projects.queue_improvement(self.run_dir, spawn=False, source="resident")
        resident.setdefault("usage", {})["iterations_generated"] = int(resident.get("usage", {}).get("iterations_generated", 0)) + 1
        engine.append_event(
            self.run_dir, "resident.queue_refilled", task_id=result["task"]["task_id"],
            iteration=result.get("iteration"), source="validated_project_state",
        )
        return result

    def _record_transition(self, resident: dict[str, Any], decision: dict[str, Any], sample: dict[str, Any], queue_facts: dict[str, Any]) -> None:
        signature = f"{decision['profile']}:{decision['reason']}:{decision['claim_allowed']}:{decision['cpu_slots']}:{decision['provider_delay_seconds']}"
        if signature == resident.get("last_transition"):
            return
        resident["last_transition"] = signature
        resident["last_transition_utc"] = utc_now()
        engine.append_event(
            self.run_dir, "resource.decision", profile=decision["profile"], reason=decision["reason"],
            claim_allowed=decision["claim_allowed"], cpu_target=decision["targets"]["cpu_percent"],
            gpu_target=decision["targets"]["gpu_percent"], cpu_slots=decision["cpu_slots"],
        )
        run = engine.read_json(self.run_dir / "run.json", {})
        hardware = sample.get("hardware", {}) if isinstance(sample.get("hardware"), dict) else {}
        event = telemetry.make_universal_event(
            str(run.get("run_id") or self.run_dir.name), "agent-loop", "sample", "idle",
            run_dir=self.run_dir, hardware=hardware,
            provider={
                "mode": str(run.get("provider_mode", "off")), "backend": "vulkan" if run.get("provider_mode") != "off" else None,
                "endpoint": str(run.get("provider_endpoint") or "") or None,
                "status": str(run.get("provider_status", "unknown")) if run.get("provider_status") in {"off", "starting", "ready", "running", "stopped", "degraded", "failed", "unknown"} else "unknown",
                "pid": run.get("provider_pid") if isinstance(run.get("provider_pid"), int) else None,
            },
            scheduler={
                "queue_depth": len(queue_facts["ready"]), "active_task_count": len(queue_facts["active"]),
                "blocked_task_count": len(queue_facts["blocked"]), "repair_task_count": len(queue_facts["repair"]),
                "max_concurrency": max(1, int(decision["cpu_slots"])),
                "governor_profile": decision["profile"], "governor_reason": decision["reason"],
                "cpu_target_percent": decision["targets"]["cpu_percent"],
                "gpu_target_percent": decision["targets"]["gpu_percent"],
                "claim_allowed": decision["claim_allowed"],
                "input_idle_seconds": decision.get("input_idle_seconds"),
                "responsiveness_ms": decision.get("responsiveness_ms"),
                "provider_delay_seconds": decision["provider_delay_seconds"],
            },
            notes=[f"governor_profile={decision['profile']}", f"governor_reason={decision['reason']}",
                   f"cpu_target={decision['targets']['cpu_percent']}", f"gpu_target={decision['targets']['gpu_percent']}"],
            collect_hardware=False,
        )
        telemetry.append_universal_event(self.run_dir / telemetry.UNIVERSAL_LOG_NAME, event)

    def tick_once(self) -> dict[str, Any]:
        now = self.clock()
        run = engine.read_json(self.run_dir / "run.json", {})
        state = engine.read_json(self.run_dir / "state.json", {})
        resident = engine.read_json(_resident_path(self.run_dir), {})
        if resident.get("leafos_object") != "leafos.resident_state":
            resident = initialize_resident(self.run_dir)
        policy = governor.load_policy(resident.get("policy_path", governor.DEFAULT_POLICY_PATH))
        queue = engine.read_json(self.run_dir / "queue.json", {})
        facts = self._queue_facts(queue)
        budget_reason = self._update_usage(resident, facts)
        approval_waiting = any(task.get("reason") == "approval_required" for task in facts["blocked"])
        if (
            not budget_reason and not approval_waiting and facts["all_terminal"]
            and run.get("live_project") and state.get("status") not in {"paused", "draining", "drained", "stopping", "stopped"}
        ):
            self._refill(resident)
            queue = engine.read_json(self.run_dir / "queue.json", {})
            facts = self._queue_facts(queue)
            run = engine.read_json(self.run_dir / "run.json", run)
        provider_health = self._recover_provider(run, resident, now) if facts["ready"] else self._provider_health(run)
        try:
            sample = self.collector(timeout=0.25, cpu_interval=0.03)
        except (OSError, RuntimeError, ValueError):
            sample = {"hardware": {}, "availability": {}}
        try:
            input_idle = self.input_probe()
        except (OSError, RuntimeError, ValueError):
            input_idle = None
        decision_facts = {
            "mode": resident.get("mode", "auto"),
            "queue_ready": len(facts["ready"]),
            "queue_active": len(facts["active"]),
            "gpu_needed": facts["gpu_needed"],
            "provider_health": provider_health,
            "input_idle_seconds": input_idle,
            "responsiveness_ms": self.probe.sample(),
            "run_state": state.get("status", "running"),
            "target_overrides": resident.get("targets_override", {}),
        }
        decision = governor.decide(policy, sample, decision_facts, resident.get("last_decision"), now_monotonic=now)
        if budget_reason:
            decision.update(profile="awaiting_budget", reason=budget_reason, claim_allowed=False, cpu_slots=0)
        elif approval_waiting and not facts["ready"] and not facts["active"]:
            decision.update(profile="waiting", reason="approval_required", claim_allowed=False, cpu_slots=0)
        worker_alive, worker_pid = inlet.worker_lease_status(self.run_dir, pid_probe=_pid_alive)
        if decision["claim_allowed"] and facts["ready"] and not worker_alive:
            delay_until = float(resident.get("next_dispatch_monotonic", 0.0))
            if now >= delay_until:
                worker_pid = self.worker_spawner(self.run_dir, self.interval)
                worker_alive = True
                resident["next_dispatch_monotonic"] = now + float(decision["provider_delay_seconds"])
                engine.append_event(self.run_dir, "resident.worker_started", pid=worker_pid, reason=decision["reason"])
        resident.update(
            status=decision["profile"], updated_utc=utc_now(), supervisor_pid=os.getpid(),
            worker_pid=worker_pid if worker_alive else None, last_decision=decision,
        )
        self._record_transition(resident, decision, sample, facts)
        engine.write_json(_resident_path(self.run_dir), resident)
        return resident

    def drive(self, *, max_ticks: int | None = None) -> int:
        lease = acquire_lease(self.run_dir)
        ticks = 0
        engine.append_event(self.run_dir, "resident.started", pid=os.getpid(), interval=self.interval)
        try:
            while True:
                tick_started = time.monotonic()
                resident = self.tick_once()
                state = engine.read_json(self.run_dir / "state.json", {})
                ticks += 1
                if not resident.get("enabled", True) or state.get("status") in {"stopped", "drained"}:
                    break
                if max_ticks is not None and ticks >= max_ticks:
                    break
                remaining = self.interval - (time.monotonic() - tick_started)
                if remaining > 0:
                    time.sleep(remaining)
            return 0
        finally:
            latest = engine.read_json(_resident_path(self.run_dir), {})
            latest.update(supervisor_pid=None, updated_utc=utc_now())
            if latest.get("status") not in {"stopped", "drained", "awaiting_budget"}:
                latest["status"] = "offline"
            engine.write_json(_resident_path(self.run_dir), latest)
            lease.unlink(missing_ok=True)
            engine.append_event(self.run_dir, "resident.stopped", pid=os.getpid(), status=latest.get("status"))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="LeafOS resident stack supervisor")
    sub = parser.add_subparsers(dest="command", required=True)
    start = sub.add_parser("start")
    start.add_argument("run", nargs="?", default="active")
    start.add_argument("--mode", choices=("auto", "quiet", "full"), default="auto")
    start.add_argument("--budget", type=int)
    start.add_argument("--interval", type=float, default=1.0)
    start.add_argument("--foreground", action="store_true")
    start.add_argument("--json", action="store_true")
    drive = sub.add_parser("drive")
    drive.add_argument("run")
    drive.add_argument("--interval", type=float, default=1.0)
    drive.add_argument("--max-ticks", type=int)
    status = sub.add_parser("status")
    status.add_argument("run", nargs="?", default="active")
    status.add_argument("--json", action="store_true")
    for name in ("pause", "resume", "drain", "stop"):
        child = sub.add_parser(name)
        child.add_argument("run", nargs="?", default="active")
        child.add_argument("--json", action="store_true")
    mode = sub.add_parser("mode")
    mode.add_argument("run")
    mode.add_argument("value", choices=("auto", "quiet", "full"))
    mode.add_argument("--json", action="store_true")
    targets = sub.add_parser("targets")
    targets.add_argument("run")
    targets.add_argument("--cpu", type=float, required=True)
    targets.add_argument("--gpu", type=float, required=True)
    targets.add_argument("--json", action="store_true")
    budget = sub.add_parser("budget")
    budget.add_argument("run")
    budget.add_argument("minutes", type=int)
    budget.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "start":
            state = initialize_resident(args.run, mode=args.mode, budget_minutes=args.budget)
            if args.foreground:
                return ResidentSupervisor(inlet.resolve_run(args.run), interval=args.interval).drive()
            state["supervisor_pid"] = spawn_supervisor(args.run, args.interval)
            result = state
        elif args.command == "drive":
            return ResidentSupervisor(inlet.resolve_run(args.run), interval=args.interval).drive(max_ticks=args.max_ticks)
        elif args.command == "status":
            result = resident_status(args.run)
        elif args.command in {"pause", "resume", "drain", "stop"}:
            result = set_resident_control(args.run, args.command)
        elif args.command == "mode":
            result = set_resident_control(args.run, "mode", mode=args.value)
        elif args.command == "targets":
            result = set_resident_control(args.run, "targets", cpu=args.cpu, gpu=args.gpu)
        else:
            result = set_resident_control(args.run, "budget", minutes=args.minutes)
        print(json.dumps(result, indent=2, ensure_ascii=True) if getattr(args, "json", False) else result.get("status", "ok"))
        return 0
    except (OSError, RuntimeError, ValueError) as error:
        print(f"resident: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
