#!/usr/bin/env python3
"""Read-only adapter from LeafOS run artifacts to the TUI snapshot contract."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter, deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


TUI_DIR = Path(__file__).resolve().parent
UI_DIR = TUI_DIR.parent
ROOT = TUI_DIR.parents[2]
PYTHON_DIR = ROOT / "core" / "python"
for path in (UI_DIR, PYTHON_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import home_state  # noqa: E402
import leaf_loop_inlet as inlet  # noqa: E402
import leaf_live_project as live_projects  # noqa: E402
import leaf_telemetry  # noqa: E402


TASK_SYMBOLS = {
    "queued": "o",
    "waiting": "o",
    "executing": "*",
    "running": "*",
    "planning": "*",
    "validating": "*",
    "complete": "+",
    "failed": "!",
    "blocked": "!",
    "repair_queued": "~",
    "paused": "=",
    "review": "?",
}
ROLE_BY_KIND = {
    "inspect": "observer",
    "plan": "architect",
    "approve": "operator",
    "execute": "executor",
    "validate": "validator",
    "report": "publisher",
}
DURABLE_EVENT_PREFIXES = (
    "approval.", "checkpoint.", "file.", "files.", "hashes.", "report.",
    "run.", "step.", "task.", "validation.", "work_order.", "repair.", "project.",
)


def _json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _jsonl_window(path: Path, *, after: int = 0, limit: int = 250) -> tuple[list[dict[str, Any]], int]:
    records: deque[dict[str, Any]] = deque(maxlen=limit)
    matched = 0
    try:
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                try:
                    value = json.loads(line)
                except json.JSONDecodeError:
                    continue
                sequence = int(value.get("seq", value.get("sequence", 0)) or 0)
                if sequence > after:
                    matched += 1
                    records.append(value)
    except OSError:
        return [], 0
    return list(records), max(0, matched - len(records))


def _jsonl(path: Path, *, after: int = 0, limit: int = 250) -> list[dict[str, Any]]:
    return _jsonl_window(path, after=after, limit=limit)[0]


def _parse_time(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def _duration(seconds: float | int | None) -> str:
    if seconds is None:
        return "--:--"
    seconds = max(0, int(seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}" if hours else f"{minutes:02d}:{seconds:02d}"


def _event_summary(event: dict[str, Any]) -> str:
    kind = str(event.get("kind", "event"))
    for key in ("summary", "error", "reason", "path", "stop_reason"):
        if event.get(key):
            return str(event[key])
    if kind == "provider.progress":
        return f"Private reasoning progress: {event.get('private_reasoning_chars', 0)} chars"
    if kind == "provider.output.delta":
        return str(event.get("text", "")).replace("\n", " ").strip()
    if kind.startswith("validation."):
        return f"exit={event.get('exit_code', '?')}"
    if event.get("step_id"):
        return f"{event.get('step_kind', 'step')} {event['step_id']}"
    if event.get("task_kind"):
        return str(event["task_kind"])
    if event.get("status"):
        return str(event["status"])
    return kind.replace(".", " ")


def _task_view(task: dict[str, Any], root_task: str) -> dict[str, Any]:
    status = str(task.get("status", "queued"))
    dependencies = [str(item) for item in task.get("dependencies", [])]
    evidence = task.get("evidence", []) if isinstance(task.get("evidence"), list) else []
    return {
        "id": str(task.get("task_id", "?")),
        "parent_id": dependencies[-1] if dependencies else None,
        "root_id": root_task,
        "kind": str(task.get("kind", "task")),
        "objective": str(task.get("objective", "")),
        "status": status,
        "symbol": TASK_SYMBOLS.get(status, "?"),
        "role": str(task.get("role") or ROLE_BY_KIND.get(str(task.get("kind")), "worker")),
        "priority": int(task.get("priority", 2)),
        "correction_depth": int(task.get("correction_depth", 1 if status == "repair_queued" else 0)),
        "provider": str(task.get("provider", "policy")),
        "model": str(task.get("stack_entry", "CPU policy") if task.get("provider") == "llamacpp" else "CPU policy"),
        "worker": "GPU/provider" if task.get("provider") == "llamacpp" else "CPU",
        "attempts": int(task.get("attempts", 0)),
        "max_attempts": int(task.get("max_attempts", 1)),
        "dependencies": dependencies,
        "blocker": str(task.get("reason", "")),
        "evidence": evidence,
    }


def _milestone(name: str, tasks: list[dict[str, Any]]) -> dict[str, Any]:
    statuses = [task["status"] for task in tasks]
    complete = bool(statuses) and all(status == "complete" for status in statuses)
    active = any(status in {"executing", "running", "planning", "validating", "repair_queued"} for status in statuses)
    blocked = any(status in {"blocked", "failed"} for status in statuses)
    state = "complete" if complete else "blocked" if blocked else "active" if active else "waiting"
    return {"name": name, "state": state, "complete": sum(status == "complete" for status in statuses), "total": len(statuses)}


def _latest_metric(events: list[dict[str, Any]], section: str, key: str) -> Any:
    for event in reversed(events):
        value = event.get(section, {}).get(key) if isinstance(event.get(section), dict) else None
        if value is not None:
            return value
    return None


def _hardware_view(telemetry: list[dict[str, Any]], home: dict[str, Any]) -> dict[str, Any]:
    accelerator = home.get("accelerator", {}) if isinstance(home, dict) else {}
    provider = accelerator.get("provider", {}) if isinstance(accelerator, dict) else {}
    latest_stack = next((event.get("stack", {}) for event in reversed(telemetry) if event.get("stack")), {})
    latest_economics = next((event.get("economics", {}) for event in reversed(telemetry) if event.get("economics")), {})
    return {
        "backend": _latest_metric(telemetry, "hardware", "backend") or accelerator.get("backend") or "unknown",
        "provider_health": provider.get("health", "unknown"),
        "provider_pid": provider.get("pid"),
        "model": Path(str(accelerator.get("model", "unknown"))).name,
        "stack_entry": latest_stack.get("brain_stack_entry") or latest_stack.get("local_stack_id"),
        "gpu": {
            "name": next((event.get("hardware", {}).get("gpu", {}).get("name") for event in reversed(telemetry) if event.get("hardware", {}).get("gpu", {}).get("name")), None),
            "utilization_percent": next((event.get("hardware", {}).get("gpu", {}).get("utilization_percent") for event in reversed(telemetry) if event.get("hardware", {}).get("gpu", {}).get("utilization_percent") is not None), None),
            "vram_used_gb": next((event.get("hardware", {}).get("gpu", {}).get("vram_used_gb") for event in reversed(telemetry) if event.get("hardware", {}).get("gpu", {}).get("vram_used_gb") is not None), None),
            "vram_total_gb": next((event.get("hardware", {}).get("gpu", {}).get("vram_total_gb") for event in reversed(telemetry) if event.get("hardware", {}).get("gpu", {}).get("vram_total_gb") is not None), None),
            "temperature_c": next((event.get("hardware", {}).get("gpu", {}).get("temperature_celsius") for event in reversed(telemetry) if event.get("hardware", {}).get("gpu", {}).get("temperature_celsius") is not None), None),
            "power_watts": next((event.get("hardware", {}).get("gpu", {}).get("power_watts") for event in reversed(telemetry) if event.get("hardware", {}).get("gpu", {}).get("power_watts") is not None), None),
        },
        "cpu_percent": next((event.get("hardware", {}).get("cpu", {}).get("utilization_percent") for event in reversed(telemetry) if event.get("hardware", {}).get("cpu", {}).get("utilization_percent") is not None), None),
        "ram_used_gb": next((event.get("hardware", {}).get("memory", {}).get("ram_used_gb") for event in reversed(telemetry) if event.get("hardware", {}).get("memory", {}).get("ram_used_gb") is not None), None),
        "ram_total_gb": next((event.get("hardware", {}).get("memory", {}).get("ram_total_gb") for event in reversed(telemetry) if event.get("hardware", {}).get("memory", {}).get("ram_total_gb") is not None), None),
        "brain_generation_tk_s": next((event.get("throughput", {}).get("brain_generation_tk_s") for event in reversed(telemetry) if event.get("throughput", {}).get("brain_generation_tk_s") is not None), None),
        "brain_prompt_tk_s": next((event.get("throughput", {}).get("brain_prompt_tk_s") for event in reversed(telemetry) if event.get("throughput", {}).get("brain_prompt_tk_s") is not None), None),
        "generated_tokens": next((event.get("throughput", {}).get("generated_tokens") for event in reversed(telemetry) if event.get("throughput", {}).get("generated_tokens") is not None), None),
        "prompt_tokens": next((event.get("throughput", {}).get("prompt_tokens") for event in reversed(telemetry) if event.get("throughput", {}).get("prompt_tokens") is not None), None),
        "economics": latest_economics,
    }


def _safety_state(state: dict[str, Any], run: dict[str, Any], tasks: list[dict[str, Any]], provider_health: str) -> str:
    status = str(state.get("status", "unknown"))
    if status in {"stopping", "draining", "stopped"}:
        return "STOPPING" if status != "stopped" else "PAUSED"
    if status in {"paused", "drained"}:
        return "PAUSED"
    if any(task["status"] == "failed" for task in tasks):
        return "FAILED"
    if run.get("approval", {}).get("status") == "pending" or any(task["status"] == "blocked" and task["kind"] == "approve" for task in tasks):
        return "REVIEW"
    if run.get("provider_mode") == "required" and provider_health not in {"ok", "ready"}:
        return "DEGRADED"
    return "SAFE"


def _brain_view(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records = []
    category_map = {
        "phase.emitted": "OBSERVE",
        "provider.progress": "OBSERVE",
        "provider.output.delta": "PROPOSAL",
        "provider.proposal.attached": "DECISION",
        "step.started": "ACTION",
        "validation.passed": "RESULT",
        "validation.failed": "WARNING",
        "task.failed": "WARNING",
        "approval.required": "HUMAN",
        "approval.granted": "HUMAN",
    }
    for event in events:
        kind = str(event.get("kind", ""))
        if kind not in category_map:
            continue
        records.append({
            "sequence": int(event.get("seq", 0)),
            "time": str(event.get("time", "")),
            "task_id": event.get("task_id"),
            "category": category_map[kind],
            "summary": _event_summary(event),
            "durable": kind != "provider.output.delta" and kind != "provider.progress",
        })
    return records[-100:]


def _ledger_view(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records = []
    for event in events:
        kind = str(event.get("kind", ""))
        if not kind.startswith(DURABLE_EVENT_PREFIXES):
            continue
        evidence = event.get("path") or event.get("plan") or event.get("artifact") or event.get("queue_digest")
        records.append({
            "sequence": int(event.get("seq", 0)),
            "time": str(event.get("time", "")),
            "type": kind.upper().replace(".", "_"),
            "task_id": event.get("task_id") or "RUN",
            "summary": _event_summary(event),
            "evidence": str(evidence or ""),
        })
    return records[-150:]


def _results_view(tasks: list[dict[str, Any]], step_state: dict[str, Any], checkpoint: dict[str, Any], run_dir: Path) -> dict[str, Any]:
    validation = []
    artifacts = []
    failures = []
    for task in tasks:
        if task["status"] == "failed":
            failures.append({"task_id": task["id"], "summary": task["blocker"] or task["objective"]})
        for evidence in task["evidence"]:
            if not isinstance(evidence, dict):
                continue
            if evidence.get("kind") in {"acceptance_command", "run_tests"}:
                validation.append(evidence)
            for key in ("path", "stdout", "stderr"):
                if evidence.get(key):
                    artifacts.append(str(evidence[key]))
    for step_id, evidence in step_state.get("steps", {}).items():
        if not isinstance(evidence, dict):
            continue
        if evidence.get("kind") == "run_tests":
            validation.append({"step_id": step_id, **evidence})
        for key in ("path", "stdout", "stderr"):
            if evidence.get(key):
                artifacts.append(str(evidence[key]))
    changed = checkpoint.get("changed_file_hashes", {}) if isinstance(checkpoint.get("changed_file_hashes"), dict) else {}
    if (run_dir / "report.md").is_file():
        artifacts.append(str(run_dir / "report.md"))
    return {
        "validation": validation,
        "changed_files": [{"path": path, "sha256": digest} for path, digest in changed.items()],
        "artifacts": list(dict.fromkeys(artifacts)),
        "failures": failures,
        "gate_ready": not failures and all(item.get("exit_code", 0) == 0 for item in validation),
    }


def resolve_run(value: str) -> Path:
    """Resolve inlet aliases, explicit paths, targets, or a bounded run ID."""
    try:
        return inlet.resolve_run(value)
    except ValueError as original_error:
        candidate = (inlet.RUNS_ROOT / value).resolve()
        runs_root = inlet.RUNS_ROOT.resolve()
        if runs_root in candidate.parents and (candidate / "run.json").is_file():
            return candidate
        raise original_error


def controller_request(snapshot: dict[str, Any], request: dict[str, Any]) -> tuple[bool, str]:
    """Route one typed operator request through the authoritative inlet."""
    action = str(request.get("action", ""))
    if action == "live_command":
        try:
            result = live_projects.execute_active_command(
                str(request.get("command", "")), Path(snapshot["run"]["dir"]), spawn=True,
            )
        except (OSError, ValueError, RuntimeError) as error:
            return False, str(error)
        return True, str(result.get("message") or result.get("action") or "live command accepted")
    task_actions = {
        "task_retry": "retry", "task_cancel": "cancel",
        "task_approve": "approve", "task_prioritize": "prioritize",
    }
    if action in task_actions:
        run_dir = Path(snapshot["run"]["dir"])
        task_request: dict[str, Any] = {
            "leafos_object": "leafos.task_control_request",
            "version": 1,
            "action": task_actions[action],
            "task_id": str(request.get("task_id", "")),
        }
        if action == "task_prioritize":
            task_request["priority"] = request.get("priority")
        try:
            task = inlet.apply_task_control(run_dir, task_request)
            if task_actions[action] in {"retry", "approve"}:
                lease = inlet.engine.read_json(run_dir / "worker.lock", {})
                if not inlet._pid_alive(int(lease.get("pid", 0))):
                    inlet.spawn_worker(run_dir, 1.0)
        except (OSError, ValueError, RuntimeError) as error:
            return False, str(error)
        return True, f"{task_actions[action]} accepted for {task['task_id']} ({task['status']})"

    allowed = {"pause_toggle", "approve", "stop"}
    if action not in allowed:
        return False, f"unsupported TUI action: {action}"
    run = snapshot["run"]
    effective = action
    if action == "pause_toggle":
        effective = "resume" if run["state"] == "paused" else "pause"
    if effective == "approve" and run.get("approval", {}).get("status") == "approved":
        return False, "This run is already approved."
    if run["state"] in {"complete", "stopped", "drained"} and effective in {"pause", "resume", "stop"}:
        return False, f"Run is already {run['state']}; no control action sent."
    command = [sys.executable, str(PYTHON_DIR / "leaf_loop_inlet.py"), effective, run["dir"]]
    try:
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=15, check=False)
    except (OSError, subprocess.TimeoutExpired) as error:
        return False, f"inlet control failed: {error}"
    detail = (result.stdout or result.stderr).strip().splitlines()
    return result.returncode == 0, (detail[-1] if detail else f"{effective} returned {result.returncode}")


def controller_action(snapshot: dict[str, Any], action: str) -> tuple[bool, str]:
    return controller_request(snapshot, {"action": action})


def build_snapshot(run_value: str = "active", *, after: int = 0, event_limit: int = 250, health_timeout: float = 0.15) -> dict[str, Any]:
    run_dir = resolve_run(run_value)
    run = _json(run_dir / "run.json", {})
    state = _json(run_dir / "state.json", {})
    queue = _json(run_dir / "queue.json", {})
    checkpoint = _json(run_dir / "checkpoint.json", {})
    work_order = _json(run_dir / "work-order.json", {})
    step_state = _json(run_dir / "step-state.json", {})
    active_process = _json(run_dir / "active-process.json", {})
    resident_state = _json(run_dir / "resident-state.json", {})
    resident_lease = _json(run_dir / "resident.lock", {})
    all_events = _jsonl(run_dir / "events.jsonl", limit=event_limit)
    delta_events, dropped_events = _jsonl_window(run_dir / "events.jsonl", after=after, limit=event_limit)
    telemetry = _jsonl(run_dir / leaf_telemetry.UNIVERSAL_LOG_NAME, limit=event_limit)
    try:
        home = home_state.build_state(ROOT, health_timeout=health_timeout)
    except (OSError, ValueError):
        home = {}
    root_id = str(queue.get("work_order_id") or run.get("work_order", {}).get("id") or run.get("run_id", "RUN"))
    tasks = [_task_view(task, str(task.get("work_order_id") or root_id)) for task in queue.get("tasks", []) if isinstance(task, dict)]
    by_kind = {kind: [task for task in tasks if task["kind"] in kinds] for kind, kinds in {
        "INTAKE": {"inspect"}, "PLAN": {"plan", "approve"}, "EXECUTE": {"execute", "operator"},
        "VALIDATE": {"validate"}, "PUBLISH": {"report"},
    }.items()}
    hardware = _hardware_view(telemetry, home)
    created = _parse_time(run.get("created_utc"))
    now = datetime.now(timezone.utc)
    last_event_time = _parse_time(all_events[-1].get("time")) if all_events else now
    checkpoint_time = _parse_time(checkpoint.get("written_at"))
    terminal = str(state.get("status", "")) in {"complete", "blocked", "stopped", "drained"}
    elapsed_end = last_event_time if terminal else now
    counts = Counter(task["status"] for task in tasks)
    resident_decision = resident_state.get("last_decision", {}) if isinstance(resident_state.get("last_decision"), dict) else {}
    resident_current = resident_decision.get("current", {}) if isinstance(resident_decision.get("current"), dict) else {}
    resident_targets = resident_decision.get("targets", {}) if isinstance(resident_decision.get("targets"), dict) else {}
    resident_pid = int(resident_lease.get("pid", 0))
    active_task = next((task for task in tasks if task["status"] in {"executing", "running", "planning", "validating", "repair_queued"}), None)
    if active_task is None:
        active_task = next((task for task in tasks if task["status"] not in {"complete"}), None)
    latest_validation = next((event for event in reversed(all_events) if str(event.get("kind", "")).startswith("validation.")), None)
    snapshot = {
        "leafos_object": "leafos.tui.snapshot",
        "version": 1,
        "generated_at": now.isoformat(),
        "operator": home.get("operator", {"name": "LeafOS", "engine": "LeafOS", "stage": "unknown"}),
        "benchmark": home.get("benchmark", {"status": "not_run", "completed_cells": 0, "planned_cells": 0}),
        "event_cursor": int(all_events[-1].get("seq", 0)) if all_events else 0,
        "dropped_events": dropped_events,
        "run": {
            "id": str(run.get("run_id", run_dir.name)),
            "dir": str(run_dir),
            "target": str(run.get("target", "")),
            "mode": "RESIDENT" if resident_state.get("enabled") else "LOOP",
            "state": str(state.get("status", "unknown")),
            "elapsed": _duration(((elapsed_end or now) - created).total_seconds() if created else None),
            "safety": _safety_state(state, run, tasks, str(hardware.get("provider_health"))),
            "checkpoint_age": _duration((now - checkpoint_time).total_seconds() if checkpoint_time else None),
            "next_action": str(state.get("next_action") or checkpoint.get("next_action") or "inspect status"),
            "accepting_tasks": bool(state.get("accepting_tasks", False)),
            "provider_mode": str(run.get("provider_mode", "off")),
            "approval": run.get("approval", {}),
        },
        "work_order": {
            "id": str(work_order.get("work_order_id") or root_id),
            "title": str(work_order.get("title") or run.get("work_order", {}).get("title") or "Repository validation"),
            "objective": str(work_order.get("objective") or "Execute the approved repository task."),
            "acceptance": work_order.get("acceptance", []),
            "allow_mutation": bool(work_order.get("allow_mutation", False)),
        },
        "project": {
            "target": str(run.get("target", "")),
            "state": str(run.get("live_project", {}).get("state", "codebase")),
            "iteration": int(run.get("live_project", {}).get("iteration", 0)),
            "catan2": bool(run.get("live_project", {}).get("catan2", False)),
            "last_task_id": str(run.get("live_project", {}).get("last_task_id", "")),
            "syntax": str(run.get("live_project", {}).get("syntax", ":improve | :again | :<objective>")),
        },
        "resident": {
            "enabled": bool(resident_state.get("enabled", False)),
            "status": str(resident_state.get("status", "offline")),
            "mode": str(resident_state.get("mode", "auto")),
            "supervisor_pid": resident_pid or resident_state.get("supervisor_pid"),
            "supervisor_alive": inlet._pid_alive(resident_pid),
            "worker_pid": resident_state.get("worker_pid"),
            "profile": str(resident_decision.get("profile", resident_state.get("status", "offline"))),
            "reason": str(resident_decision.get("reason", "not_started")),
            "claim_allowed": bool(resident_decision.get("claim_allowed", False)),
            "targets": {
                "cpu_percent": resident_targets.get("cpu_percent"),
                "gpu_percent": resident_targets.get("gpu_percent"),
            },
            "current": {
                "cpu_percent": resident_current.get("cpu_percent"),
                "gpu_percent": resident_current.get("gpu_percent"),
            },
            "headroom": {
                "cpu_percent": round(100.0 - float(resident_current["cpu_percent"]), 2) if isinstance(resident_current.get("cpu_percent"), (int, float)) else None,
                "gpu_percent": round(100.0 - float(resident_current["gpu_percent"]), 2) if isinstance(resident_current.get("gpu_percent"), (int, float)) else None,
            },
            "cpu_slots": int(resident_decision.get("cpu_slots", 0)),
            "provider_delay_seconds": resident_decision.get("provider_delay_seconds"),
            "input_idle_seconds": resident_decision.get("input_idle_seconds"),
            "responsiveness_ms": resident_decision.get("responsiveness_ms"),
            "budgets": resident_state.get("budgets", {}),
            "usage": resident_state.get("usage", {}),
        },
        "milestones": [_milestone(name, by_kind[name]) for name in ("INTAKE", "PLAN", "EXECUTE", "VALIDATE", "PUBLISH")],
        "tasks": tasks,
        "active_task": active_task,
        "queue": {
            "counts": dict(counts),
            "waiting": sum(counts[name] for name in ("queued", "waiting", "repair_queued")),
            "running": sum(counts[name] for name in ("executing", "running", "planning", "validating")),
            "blocked": sum(counts[name] for name in ("blocked", "failed")),
            "ready": sum(task["status"] in {"queued", "repair_queued"} for task in tasks),
            "repair": sum(task["status"] == "repair_queued" for task in tasks),
            "generated": sum(task.get("admission_source") == "resident" for task in queue.get("tasks", [])),
            "policy": "DEPENDENCY + BOUNDED RETRY",
        },
        "hardware": hardware,
        "latest_validation": {
            "status": str(latest_validation.get("kind", "none")).split(".")[-1] if latest_validation else "none",
            "summary": _event_summary(latest_validation) if latest_validation else "No validation result recorded.",
            "task_id": latest_validation.get("task_id") if latest_validation else None,
        },
        "brain": _brain_view(all_events),
        "ledger": _ledger_view(all_events),
        "results": _results_view(tasks, step_state, checkpoint, run_dir),
        "control": {
            "transport": "inlet-cli", "authenticated": True, "connected": True,
            "active_process": {
                "pid": active_process.get("pid"),
                "task_id": active_process.get("task_id"),
                "started_utc": active_process.get("started_utc"),
            },
        },
        "events": delta_events,
    }
    return snapshot


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Emit a normalized read-only LeafOS TUI snapshot")
    parser.add_argument("--run", default="active")
    parser.add_argument("--after", type=int, default=0)
    parser.add_argument("--event-limit", type=int, default=250)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        snapshot = build_snapshot(args.run, after=args.after, event_limit=max(20, min(args.event_limit, 1000)))
    except (OSError, ValueError) as error:
        print(json.dumps({"leafos_object": "leafos.tui.error", "error": str(error)}))
        return 2
    print(json.dumps(snapshot, separators=(",", ":") if args.json else None, ensure_ascii=True, indent=None if args.json else 2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
