#!/usr/bin/env python3
"""Durable top-level LeafOS agent loop runner.

This is the first implementation slice for WO-026. It creates an inspectable
run directory, scaffolds local project workspaces, queues bounded validation
tasks, executes one task per tick, checkpoints accepted state, and can report or
resume from disk without chat context.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PYTHON_DIR = Path(__file__).resolve().parent
if str(PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(PYTHON_DIR))

from leaf_loop_kernel import (  # noqa: E402
    LoopMemoryPolicy,
    RunDirectory,
    atomic_write_json,
    read_json,
    utc_now,
)
from leaf_authority import require_capability  # noqa: E402
try:
    from leaf_authority import AuthorityError
except Exception:  # pragma: no cover - optional during migrations
    AuthorityError = RuntimeError  # type: ignore
from leaf_telemetry import (  # noqa: E402
    UNIVERSAL_LOG_NAME,
    append_universal_event,
    make_universal_event,
    summarize_universal_log,
)


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PROFILES = ROOT / "config" / "agent_loop_profiles.json"
RUNS_ROOT = ROOT / "runs" / "agent-loop"
TASK_STATES_TERMINAL = {"complete", "blocked", "failed"}
SAFE_PROJECTS = {"catan2", "chess3D", "generic-c-game", "generic-python-sim"}


def slug(value: str) -> str:
    out = "".join(ch.lower() if ch.isalnum() else "-" for ch in value.strip())
    out = "-".join(part for part in out.split("-") if part)
    return out or "agent-loop"


# Backwards-compatible aliases delegated to the loop kernel.
write_json = atomic_write_json


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def queue_digest(queue: dict[str, Any]) -> str:
    return "sha256:" + sha256_text(json.dumps(queue, sort_keys=True, separators=(",", ":")))


@contextlib.contextmanager
def event_write_lock(run_dir: Path):
    with RunDirectory(run_dir, run_kind="agent-loop").lock():
        yield


@contextlib.contextmanager
def queue_write_lock(run_dir: Path):
    """Serialize cross-process queue read-modify-write operations."""
    with RunDirectory(run_dir, run_kind="agent-loop").lock():
        yield


def _agent_ticket(capability: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
    response = require_capability(
        capability,
        actor="agent-loop",
        reason="agent loop mutation",
        context=context or {},
        source="agent-loop",
    )
    return response["payload"]["ticket"]


def append_event(run_dir: Path, kind: str, **data: Any) -> dict[str, Any]:
    ticket = data.pop("ticket", None) or _agent_ticket("loop.event.append", {"run_dir": str(run_dir)})
    return RunDirectory(run_dir, run_kind="agent-loop").append_event(kind, ticket=ticket, **data)


def read_events(run_dir: Path) -> list[dict[str, Any]]:
    return RunDirectory(run_dir, run_kind="agent-loop").read_events()


def load_profiles(path: Path = DEFAULT_PROFILES) -> dict[str, Any]:
    profiles = read_json(path, {})
    if not isinstance(profiles, dict) or "profiles" not in profiles:
        raise ValueError(f"invalid agent loop profile config: {path}")
    return profiles


def profile_named(name: str) -> dict[str, Any]:
    profiles = load_profiles().get("profiles", {})
    profile = profiles.get(name)
    if not isinstance(profile, dict):
        raise ValueError(f"unknown agent loop profile: {name}")
    return profile


def split_projects(value: str) -> list[str]:
    projects = [part.strip() for part in value.split(",") if part.strip()]
    unknown = sorted(set(projects) - SAFE_PROJECTS)
    if unknown:
        raise ValueError("unknown project template(s): " + ", ".join(unknown))
    if not projects:
        raise ValueError("at least one project is required")
    return projects


def resolve_run_dir(path_value: str) -> Path:
    candidate = Path(path_value).resolve()
    if (candidate / "run.json").is_file() and (candidate / "queue.json").is_file():
        return candidate
    pointer = candidate / "run.json"
    if pointer.is_file():
        data = read_json(pointer, {})
        run_dir = data.get("run_dir") or data.get("latest_run_dir")
        if run_dir:
            return Path(str(run_dir)).resolve()
    if candidate.is_file() and candidate.name == "run.json":
        return candidate.parent.resolve()
    raise ValueError(f"run directory not found: {path_value}")


def require_provider_configured(root: Path) -> None:
    error = provider_configuration_error(root)
    if error:
        raise ValueError(error)


def provider_configuration_error(root: Path) -> str:
    config = read_json(root / "config" / "vulkan-provider-stack.json", {})
    server = config.get("server", {}) if isinstance(config, dict) else {}
    executable = str(server.get("executable", "")).strip()
    model = str(server.get("model", "")).strip()
    if not executable or not model:
        return "provider-mode required needs config/vulkan-provider-stack.json server.executable and server.model"
    return ""


def _provider_status(value: Any) -> str:
    status = str(value or "unknown")
    return status if status in {"off", "starting", "ready", "running", "stopped", "degraded", "failed", "unknown"} else "unknown"


def append_agent_telemetry(
    run_dir: Path,
    event_type: str,
    phase: str,
    *,
    task: dict[str, Any] | None = None,
    validation_status: str = "unknown",
    checkpoint_valid: bool | None = None,
    score_delta: float | None = None,
    artifacts: list[dict[str, Any]] | None = None,
    notes: list[str] | None = None,
    collect_hardware: bool = False,
) -> dict[str, Any]:
    run = read_json(run_dir / "run.json", {})
    queue = read_json(run_dir / "queue.json", {})
    tasks = queue.get("tasks", []) if isinstance(queue, dict) else []
    queued = sum(item.get("status") in {"queued", "repair_queued"} for item in tasks)
    active = sum(item.get("status") in {"planning", "planned", "executing", "validating"} for item in tasks)
    blocked = sum(item.get("status") in {"blocked", "failed"} for item in tasks)
    repairs = sum(item.get("status") == "repair_queued" for item in tasks)
    provider_mode = str(run.get("provider_mode", "off"))
    provider_status = _provider_status(run.get("provider_status", "off" if provider_mode == "off" else "unknown"))
    provider_alive = 1 if provider_status in {"ready", "running"} else 0
    event = make_universal_event(
        str(run.get("run_id") or run_dir.name),
        "agent-loop",
        event_type,
        phase,
        run_dir=run_dir,
        task_id=task.get("task_id") if task else None,
        project=task.get("project") if task else None,
        stack={
            "local_stack_id": str(run.get("stack_entry") or "") or None,
            "brain_stack_entry": str(run.get("brain_stack_entry") or "") or None,
            "coder_stack_entry": str(run.get("coder_stack_entry") or run.get("stack_entry") or "") or None,
            "helper_stack_entry": None,
            "quantization": str(run.get("quantization") or "") or None,
        },
        provider={
            "mode": provider_mode if provider_mode in {"off", "mock", "auto", "required", "llamacpp", "ollama", "openai", "other"} else "other",
            "backend": "vulkan" if provider_mode in {"auto", "required"} else None,
            "endpoint": str(run.get("provider_endpoint") or "") or None,
            "status": provider_status,
            "pid": run.get("provider_pid") if isinstance(run.get("provider_pid"), int) else None,
        },
        instances={
            "initiated": int(run.get("instances_initiated", provider_alive)),
            "alive": provider_alive,
            "brain_initiated": 0,
            "brain_alive": 0,
            "coder_initiated": 0,
            "coder_alive": 0,
            "provider_initiated": int(run.get("provider_instances_initiated", provider_alive)),
            "provider_alive": provider_alive,
            "crashed": int(run.get("provider_crashes", 0)),
            "restarted": int(run.get("provider_restarts", 0)),
        },
        scheduler={
            "queue_depth": queued,
            "active_task_count": active,
            "blocked_task_count": blocked,
            "repair_task_count": repairs,
            "max_concurrency": 1,
        },
        quality={
            "validation_status": validation_status,
            "checkpoint_valid": checkpoint_valid,
            "accepted_changes": sum(item.get("status") == "complete" for item in tasks),
            "rejected_changes": sum(item.get("status") == "failed" for item in tasks),
            "score_delta": score_delta,
        },
        artifacts=artifacts,
        notes=notes,
        collect_hardware=collect_hardware,
    )
    return append_universal_event(run_dir / UNIVERSAL_LOG_NAME, event)


def project_readme(project: str) -> str:
    titles = {
        "catan2": "Catan2 Benchmark Workspace",
        "chess3D": "Chess3D Workspace",
        "generic-c-game": "Generic C Game Workspace",
        "generic-python-sim": "Generic Python Simulation Workspace",
    }
    return (
        f"# {titles[project]}\n\n"
        "This project was created by `leafctl agent-loop-start` as part of the\n"
        "LeafOS agentic loop. The local stack is the set of downloaded and locally\n"
        "available models for this LeafOS instance; providers only serve selected\n"
        "stack entries as proposal lanes.\n\n"
        "Run `run_tests.ps1` or `run_tests.sh` for the baseline validation.\n"
    )


def project_work_order(project: str) -> str:
    objective = {
        "catan2": "Run the Catan2 real-time resource benchmark and improve measurable play.",
        "chess3D": "Build a deterministic Chess3D rules skeleton before visuals.",
        "generic-c-game": "Create a small C game loop with deterministic tests.",
        "generic-python-sim": "Create a small Python simulation with deterministic tests.",
    }[project]
    return (
        f"# WORK ORDER - {project}\n\n"
        f"Objective: {objective}\n\n"
        "Rules:\n\n"
        "- Keep filesystem changes inside this project directory.\n"
        "- Prefer deterministic tests before visual or provider-heavy work.\n"
        "- Record benchmark or validation evidence under `reports/`.\n"
    )


def write_project_files(target: Path, project: str, force: bool) -> list[str]:
    project_dir = target / project
    if project_dir.exists() and not force:
        raise ValueError(f"refusing to overwrite existing project directory: {project_dir}")
    if project_dir.exists() and force:
        # Only remove directories created for known skeleton projects.
        if project not in SAFE_PROJECTS:
            raise ValueError(f"unsafe project removal refused: {project}")
        shutil.rmtree(project_dir)
    (project_dir / "reports").mkdir(parents=True, exist_ok=True)
    (project_dir / "tests").mkdir(parents=True, exist_ok=True)
    source_dir = project_dir / ("src" if project in {"chess3D", "generic-c-game"} else "core")
    source_dir.mkdir(parents=True, exist_ok=True)

    state = {
        "leafos_object": "project_state",
        "version": 1,
        "project": project,
        "created_at": utc_now(),
        "status": "created",
        "baseline_validation": "queued",
    }
    files = {
        "README.md": project_readme(project),
        "WORK_ORDER.md": project_work_order(project),
        "project_state.json": json.dumps(state, indent=2, ensure_ascii=True) + "\n",
    }
    if project == "catan2":
        ps = (
            "$ErrorActionPreference = 'Stop'\n"
            f"& pwsh -NoProfile -File '{ROOT / 'bin' / 'leafctl.ps1'}' catan2bench --profile 4m --ticks 3 --fast --quiet --provider-mode off --json\n"
        )
        sh = (
            "#!/usr/bin/env bash\nset -euo pipefail\n"
            f"\"{ROOT / 'bin' / 'leafctl'}\" catan2bench --profile 4m --ticks 3 --fast --quiet --provider-mode off --json\n"
        )
    else:
        ps = "$ErrorActionPreference = 'Stop'\nWrite-Host 'baseline skeleton validation passed'\n"
        sh = "#!/usr/bin/env bash\nset -euo pipefail\necho 'baseline skeleton validation passed'\n"
    files["run_tests.ps1"] = ps
    files["run_tests.sh"] = sh
    written: list[str] = []
    for rel, text in files.items():
        path = project_dir / rel
        path.write_text(text, encoding="utf-8")
        written.append(str(path))
    return written


def validation_command(project: str, project_dir: Path, run_dir: Path, profile: dict[str, Any]) -> list[str]:
    if project == "catan2":
        catan = profile.get("catan2", {})
        artifact_dir = run_dir / "artifacts" / "catan2"
        return [
            sys.executable,
            str(ROOT / "core" / "bench" / "catan2bench.py"),
            "--profile",
            str(catan.get("profile", "4m")),
            "--ticks",
            str(catan.get("ticks", 3)),
            "--fast",
            "--quiet",
            "--provider-mode",
            str(catan.get("provider_mode", "off")),
            "--run-dir",
            str(artifact_dir),
            "--out",
            str(artifact_dir / "summary.json"),
            "--json",
        ]
    if os.name == "nt":
        return ["pwsh", "-NoProfile", "-File", str(project_dir / "run_tests.ps1")]
    return ["bash", str(project_dir / "run_tests.sh")]


def initial_tasks(projects: list[str], target: Path, run_dir: Path, profile: dict[str, Any]) -> list[dict[str, Any]]:
    tasks: list[dict[str, Any]] = []
    for index, project in enumerate(projects, start=1):
        project_dir = target / project
        tasks.append(
            {
                "task_id": f"{index:03d}-{slug(project)}-baseline",
                "project": project,
                "work_order": str(project_dir / "WORK_ORDER.md"),
                "objective": f"Run baseline validation for {project}.",
                "workdir": str(project_dir),
                "provider": profile.get("task_provider", "policy"),
                "stack_entry": profile.get("stack_entry", "local-stack:unassigned"),
                "max_attempts": int(profile.get("max_attempts", 1)),
                "timeout_seconds": int(profile.get("task_timeout_seconds", 120)),
                "validation_command": validation_command(project, project_dir, run_dir, profile),
                "status": "queued",
                "dependencies": [],
                "attempts": 0,
                "evidence": [],
            }
        )
    return tasks


def write_checkpoint(
    run_dir: Path,
    run: dict[str, Any],
    queue: dict[str, Any],
    stop_reason: str,
    ticket: dict[str, Any] | None = None,
) -> None:
    ticket = ticket or _agent_ticket("loop.checkpoint", {"run_dir": str(run_dir), "reason": stop_reason})
    events = read_events(run_dir)
    tasks = queue.get("tasks", [])
    checkpoint = {
        "leafos_object": "agent_loop_checkpoint",
        "version": 1,
        "written_at": utc_now(),
        "last_event_sequence": events[-1]["seq"] if events else 0,
        "queue_digest": queue_digest(queue),
        "completed_task_ids": [task["task_id"] for task in tasks if task.get("status") == "complete"],
        "active_task_id": next((task["task_id"] for task in tasks if task.get("status") in {"planning", "planned", "executing", "validating"}), ""),
        "provider_mode": run.get("provider_mode", "off"),
        "stack_entry": run.get("stack_entry", ""),
        "stop_reason": stop_reason,
    }
    write_json(run_dir / "checkpoint.json", checkpoint)
    append_event(run_dir, "checkpoint.written", ticket=ticket, stop_reason=stop_reason, queue_digest=checkpoint["queue_digest"])
    append_agent_telemetry(
        run_dir,
        "checkpoint",
        "checkpoint",
        checkpoint_valid=True,
        artifacts=[{"kind": "checkpoint", "path": str(run_dir / "checkpoint.json"), "sha256": None}],
    )


def create_run(args: argparse.Namespace) -> int:
    profile = profile_named(args.profile)
    projects = split_projects(args.projects)
    target = Path(args.target).resolve()
    provider_mode = args.provider_mode or str(profile.get("provider_mode", "off"))
    provider_error = provider_configuration_error(ROOT) if provider_mode in {"auto", "required"} else ""
    if provider_mode == "required":
        require_provider_configured(ROOT)
    task_provider = "policy" if provider_mode == "off" or (provider_mode == "auto" and provider_error) else "llamacpp"
    run_id = args.run_id or f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{slug(target.name)}"
    run_dir = (Path(args.run_dir).resolve() if args.run_dir else RUNS_ROOT / run_id).resolve()

    planned = {
        "target": str(target),
        "run_dir": str(run_dir),
        "projects": projects,
        "profile": args.profile,
        "provider_mode": provider_mode,
        "writes": [
            str(target / project) for project in projects
        ]
        + [
            str(run_dir / name)
            for name in ("run.json", "queue.json", "state.json", "events.jsonl", "journal.jsonl", "checkpoint.json", "report.md", UNIVERSAL_LOG_NAME)
        ],
    }
    if args.dry_run or not args.yes:
        print(json.dumps({"leafos_object": "agent_loop_dry_run", **planned}, indent=2, ensure_ascii=True))
        if not args.dry_run:
            print("No files written. Re-run with --yes to create the loop.", file=sys.stderr)
        return 0

    create_ticket = _agent_ticket("loop.spawn", {"run_dir": str(run_dir), "action": "create"})
    target.mkdir(parents=True, exist_ok=True)
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "artifacts").mkdir(exist_ok=True)
    (run_dir / "workspaces").mkdir(exist_ok=True)
    (target / "shared").mkdir(exist_ok=True)
    (target / "reports").mkdir(exist_ok=True)

    written: list[str] = []
    for project in projects:
        written.extend(write_project_files(target, project, args.force))

    run = {
        "leafos_object": "agent_loop_run",
        "version": 1,
        "run_id": run_id,
        "created_utc": utc_now(),
        "root": str(ROOT),
        "target": str(target),
        "run_dir": str(run_dir),
        "profile": args.profile,
        "projects": projects,
        "provider_mode": provider_mode,
        "provider_status": "degraded" if provider_mode == "auto" and provider_error else ("off" if provider_mode == "off" else "unknown"),
        "provider_reason": provider_error,
        "stack_entry": profile.get("stack_entry", "local-stack:unassigned"),
        "safety_policy": profile.get("safety_policy", "local-bounded"),
        "max_minutes": int(args.max_minutes or profile.get("max_minutes", 64)),
        "max_attempts": int(profile.get("max_attempts", 1)),
        "first_checkpoint_due_minutes": int(profile.get("first_checkpoint_due_minutes", 30)),
    }
    queue = {
        "leafos_object": "agent_loop_queue",
        "version": 1,
        "run_id": run_id,
        "tasks": initial_tasks(projects, target, run_dir, {**profile, "task_provider": task_provider}),
    }
    state = {
        "leafos_object": "agent_loop_state",
        "version": 1,
        "run_id": run_id,
        "status": "created",
        "current_task_id": "",
        "created_project_files": written,
        "last_tick_utc": "",
        "next_action": "agent-loop-tick",
    }
    write_json(run_dir / "run.json", run)
    write_json(run_dir / "queue.json", queue)
    write_json(run_dir / "state.json", state)
    (run_dir / "journal.jsonl").write_text("", encoding="utf-8")
    write_json(target / "run.json", {"leafos_object": "agent_loop_target_pointer", "latest_run_dir": str(run_dir), "run_id": run_id})
    append_event(run_dir, "run.started", ticket=create_ticket, target=str(target), projects=projects, provider_mode=provider_mode)
    append_agent_telemetry(run_dir, "run_start", "startup", validation_status="pending", collect_hardware=True)
    if provider_mode == "auto" and provider_error:
        append_event(run_dir, "provider.startup_failed", ticket=create_ticket, provider_mode=provider_mode, error=provider_error, fallback="cpu-validation-policy")
        append_agent_telemetry(
            run_dir,
            "provider_start",
            "provider_warmup",
            validation_status="pending",
            notes=[provider_error, "Provider auto mode continued with the bounded CPU validation policy."],
        )
    for project in projects:
        append_event(run_dir, "project.created", ticket=create_ticket, project=project, path=str(target / project))
    for task in queue["tasks"]:
        append_event(run_dir, "task.queued", ticket=create_ticket, task_id=task["task_id"], project=task["project"])
    write_checkpoint(run_dir, run, queue, "created", ticket=create_ticket)
    write_report(run_dir)
    print(str(run_dir))
    return 0


def dependencies_complete(queue: dict[str, Any], task: dict[str, Any]) -> bool:
    tasks_by_id = {item["task_id"]: item for item in queue.get("tasks", [])}
    for dep in task.get("dependencies", []):
        if tasks_by_id.get(dep, {}).get("status") != "complete":
            return False
    return True


def policy_plan(task: dict[str, Any]) -> dict[str, Any]:
    if task.get("provider") not in {"off", "policy"}:
        raise ValueError("policy plans are only valid for provider=off or provider=policy")
    return {
        "leafos_object": "agent_loop_plan",
        "version": 1,
        "task_id": task["task_id"],
        "provider": task.get("provider", "off"),
        "stack_entry": task.get("stack_entry", ""),
        "steps": [
            {
                "kind": "validation_command",
                "cwd": task["workdir"],
                "command": task["validation_command"],
                "timeout_seconds": task.get("timeout_seconds", 120),
            }
        ],
    }


def validate_plan(plan: Any, task: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not isinstance(plan, dict):
        return ["plan must be an object"]
    if plan.get("leafos_object") != "agent_loop_plan":
        errors.append("leafos_object must be agent_loop_plan")
    if plan.get("version") != 1:
        errors.append("version must be 1")
    if plan.get("task_id") != task.get("task_id"):
        errors.append("task_id does not match queued task")
    steps = plan.get("steps")
    if not isinstance(steps, list) or len(steps) != 1:
        errors.append("plan must contain exactly one bounded step")
        return errors
    step = steps[0]
    if not isinstance(step, dict):
        return errors + ["plan step must be an object"]
    if step.get("kind") != "validation_command":
        errors.append("only validation_command steps are allowed")
    command = step.get("command")
    if not isinstance(command, list) or not command or not all(isinstance(part, (str, int, float)) for part in command):
        errors.append("step command must be a non-empty argument array")
    elif [str(part) for part in command] != [str(part) for part in task.get("validation_command", [])]:
        errors.append("provider plan may not replace the queued validation command")
    try:
        cwd = Path(str(step.get("cwd", ""))).resolve()
        workdir = Path(str(task.get("workdir", ""))).resolve()
        if cwd != workdir and not cwd.is_relative_to(workdir):
            errors.append("step cwd is outside the task workdir")
    except (OSError, ValueError):
        errors.append("step cwd is invalid")
    timeout = step.get("timeout_seconds")
    if not isinstance(timeout, int) or timeout < 1 or timeout > int(task.get("timeout_seconds", 120)):
        errors.append("step timeout exceeds the queued task boundary")
    return errors


def run_task(run_dir: Path, run: dict[str, Any], queue: dict[str, Any], task: dict[str, Any]) -> None:
    task["status"] = "planning"
    append_event(run_dir, "task.planning", task_id=task["task_id"])
    append_agent_telemetry(run_dir, "task_start", "planning", task=task, validation_status="pending", collect_hardware=True)
    provider = str(task.get("provider", "off"))
    proposal = task.get("provider_proposal")
    if proposal is None and provider not in {"off", "policy"}:
        task["status"] = "blocked"
        task["reason"] = "provider_proposal_missing"
        task.setdefault("evidence", []).append(
            {
                "kind": "provider_proposal_missing",
                "provider": provider,
                "replacement": "continual-loop inlet must attach a validated provider_proposal",
            }
        )
        append_event(run_dir, "provider.proposal_missing", task_id=task["task_id"], provider=provider)
        append_agent_telemetry(
            run_dir,
            "run_error",
            "planning",
            task=task,
            validation_status="blocked",
            notes=["Live-provider task has no provider proposal; no synthetic plan was generated."],
        )
        return
    plan = proposal if proposal is not None else policy_plan(task)
    plan_errors = validate_plan(plan, task)
    if plan_errors:
        task["status"] = "failed"
        task["reason"] = "invalid_provider_plan"
        task.setdefault("evidence", []).append({"kind": "plan_rejected", "errors": plan_errors})
        append_event(run_dir, "plan.rejected", task_id=task["task_id"], errors=plan_errors)
        append_agent_telemetry(run_dir, "run_error", "planning", task=task, validation_status="failed", notes=plan_errors)
        queue_repair(run_dir, queue, task)
        return
    plan_path = run_dir / "artifacts" / f"{task['task_id']}.plan.json"
    write_json(plan_path, plan)
    task["status"] = "planned"
    append_event(run_dir, "task.planned", task_id=task["task_id"], plan=str(plan_path))
    append_event(run_dir, "plan.validated", task_id=task["task_id"], step_count=1)

    task["status"] = "executing"
    task["attempts"] = int(task.get("attempts", 0)) + 1
    attempt = task["attempts"]
    stdout_path = run_dir / "artifacts" / f"{task['task_id']}.{attempt}.stdout.txt"
    stderr_path = run_dir / "artifacts" / f"{task['task_id']}.{attempt}.stderr.txt"
    append_event(run_dir, "step.started", task_id=task["task_id"], attempt=attempt, cwd=task["workdir"])
    started = time.monotonic()
    try:
        result = subprocess.run(
            [str(part) for part in task["validation_command"]],
            cwd=task["workdir"],
            timeout=int(task.get("timeout_seconds", 120)),
            capture_output=True,
            text=True,
        )
        elapsed = round(time.monotonic() - started, 3)
        stdout_path.write_text(result.stdout, encoding="utf-8")
        stderr_path.write_text(result.stderr, encoding="utf-8")
        task["last_exit_code"] = result.returncode
        task["evidence"].append(
            {
                "attempt": attempt,
                "exit_code": result.returncode,
                "elapsed_seconds": elapsed,
                "stdout": str(stdout_path),
                "stderr": str(stderr_path),
            }
        )
        append_event(
            run_dir,
            "step.completed",
            task_id=task["task_id"],
            attempt=attempt,
            exit_code=result.returncode,
            elapsed_seconds=elapsed,
            stdout=str(stdout_path),
            stderr=str(stderr_path),
        )
        task["status"] = "validating"
        if result.returncode == 0:
            benchmark = capture_benchmark_evidence(run_dir, task)
            score_delta = benchmark.get("score_delta") if benchmark else None
            if isinstance(score_delta, (int, float)) and score_delta < 0:
                task["status"] = "failed"
                task["reason"] = "benchmark_regression"
                append_event(run_dir, "validation.failed", task_id=task["task_id"], attempt=attempt, reason="benchmark_regression", score_delta=score_delta)
                append_agent_telemetry(run_dir, "validation", "validation", task=task, validation_status="failed", score_delta=float(score_delta))
                queue_repair(run_dir, queue, task)
            else:
                task["status"] = "complete"
                repaired_task_id = next(
                    (item.get("failed_task_id") for item in task.get("evidence", []) if item.get("failed_task_id")),
                    None,
                )
                if repaired_task_id:
                    repaired = next((item for item in queue.get("tasks", []) if item.get("task_id") == repaired_task_id), None)
                    if repaired:
                        repaired["status"] = "complete"
                        repaired["repaired_by"] = task["task_id"]
                append_event(run_dir, "validation.passed", task_id=task["task_id"], attempt=attempt, score_delta=score_delta)
                append_agent_telemetry(run_dir, "validation", "validation", task=task, validation_status="passed", score_delta=score_delta)
        else:
            task["status"] = "failed"
            append_event(run_dir, "validation.failed", task_id=task["task_id"], attempt=attempt, exit_code=result.returncode)
            append_agent_telemetry(run_dir, "validation", "validation", task=task, validation_status="failed")
            queue_repair(run_dir, queue, task)
        append_agent_telemetry(run_dir, "task_end", "execution", task=task, validation_status="passed" if task["status"] == "complete" else "failed", collect_hardware=True)
    except subprocess.TimeoutExpired as error:
        elapsed = round(time.monotonic() - started, 3)
        stdout_path.write_text(error.stdout or "", encoding="utf-8")
        stderr_path.write_text(error.stderr or "", encoding="utf-8")
        task["status"] = "failed"
        task["reason"] = "timeout"
        task["evidence"].append(
            {
                "attempt": attempt,
                "exit_code": "timeout",
                "elapsed_seconds": elapsed,
                "stdout": str(stdout_path),
                "stderr": str(stderr_path),
            }
        )
        append_event(run_dir, "step.timeout", task_id=task["task_id"], attempt=attempt, elapsed_seconds=elapsed)
        append_agent_telemetry(run_dir, "run_error", "error", task=task, validation_status="failed", notes=["Task timed out."])
        queue_repair(run_dir, queue, task)


def capture_benchmark_evidence(run_dir: Path, task: dict[str, Any]) -> dict[str, Any]:
    if task.get("project") != "catan2":
        return {}
    summary_path = run_dir / "artifacts" / "catan2" / "summary.json"
    summary = read_json(summary_path, {})
    if not isinstance(summary, dict) or summary.get("leafos_object") != "catan2bench":
        return {}
    players = summary.get("players", [])
    leafos_total = next((item.get("total") for item in players if item.get("role") == "leafos_dual_brain"), None)
    bot_total = next((item.get("total") for item in players if item.get("role") == "bot"), None)
    score_delta = float(leafos_total - bot_total) if isinstance(leafos_total, (int, float)) and isinstance(bot_total, (int, float)) else None
    report_dir = Path(str(task.get("workdir", ""))) / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / f"{task['task_id']}.catan2.summary.json"
    shutil.copy2(summary_path, report_path)
    evidence = {
        "kind": "catan2_benchmark",
        "summary": str(summary_path),
        "project_report": str(report_path),
        "score_delta": score_delta,
        "leafos_total": leafos_total,
        "bot_total": bot_total,
        "provider_status": summary.get("provider", {}).get("status"),
    }
    task.setdefault("evidence", []).append(evidence)
    return evidence


def queue_repair(run_dir: Path, queue: dict[str, Any], failed_task: dict[str, Any]) -> None:
    repair_id = f"{failed_task['task_id']}-repair-{failed_task.get('attempts', 1)}"
    if any(task.get("task_id") == repair_id for task in queue.get("tasks", [])):
        return
    repair = {
        "task_id": repair_id,
        "project": failed_task.get("project", ""),
        "work_order": failed_task.get("work_order", ""),
        "objective": "Inspect failed validation evidence and propose a bounded repair.",
        "workdir": failed_task.get("workdir", ""),
        "provider": failed_task.get("provider", "off"),
        "stack_entry": failed_task.get("stack_entry", ""),
        "max_attempts": 1,
        "timeout_seconds": 30,
        "validation_command": failed_task.get("validation_command", []),
        "status": "repair_queued",
        "dependencies": [],
        "attempts": 0,
        "evidence": [{"failed_task_id": failed_task["task_id"]}],
    }
    queue.setdefault("tasks", []).append(repair)
    append_event(run_dir, "repair.queued", task_id=repair_id, failed_task_id=failed_task["task_id"])
    append_agent_telemetry(run_dir, "repair", "planning", task=repair, validation_status="pending")


def tick_run(args: argparse.Namespace) -> int:
    run_dir = resolve_run_dir(args.run)
    read_events(run_dir)
    run = read_json(run_dir / "run.json", {})
    queue = read_json(run_dir / "queue.json", {})
    state = read_json(run_dir / "state.json", {})
    active = next((task for task in queue.get("tasks", []) if task.get("status") in {"queued", "repair_queued"} and dependencies_complete(queue, task)), None)
    if not active:
        previous_status = state.get("status")
        terminal = all(task.get("status") in TASK_STATES_TERMINAL for task in queue.get("tasks", []))
        successful = terminal and all(task.get("status") == "complete" for task in queue.get("tasks", []))
        state["status"] = "complete" if successful else "blocked"
        state["current_task_id"] = ""
        state["last_tick_utc"] = utc_now()
        state["next_action"] = "agent-loop-status"
        if previous_status != state["status"]:
            append_event(run_dir, "run.completed" if state["status"] == "complete" else "run.blocked", status=state["status"])
        write_json(run_dir / "state.json", state)
        write_json(run_dir / "queue.json", queue)
        write_checkpoint(run_dir, run, queue, state["status"])
        append_agent_telemetry(run_dir, "run_end", "shutdown" if state["status"] == "complete" else "error", validation_status="passed" if state["status"] == "complete" else "failed")
        write_report(run_dir)
        print(status_text(run_dir))
        return 0

    state["status"] = "running"
    state["current_task_id"] = active["task_id"]
    state["last_tick_utc"] = utc_now()
    write_json(run_dir / "state.json", state)
    run_task(run_dir, run, queue, active)
    state["current_task_id"] = ""
    all_done = all(task.get("status") in TASK_STATES_TERMINAL for task in queue.get("tasks", []))
    all_successful = all_done and all(task.get("status") == "complete" for task in queue.get("tasks", []))
    state["status"] = "complete" if all_successful else ("blocked" if all_done else "running")
    state["last_tick_utc"] = utc_now()
    state["next_action"] = "agent-loop-report" if all_done else "agent-loop-tick"
    if all_done:
        append_event(run_dir, "run.completed" if all_successful else "run.blocked", status=state["status"])
    write_json(run_dir / "queue.json", queue)
    write_json(run_dir / "state.json", state)
    write_checkpoint(run_dir, run, queue, f"tick:{active['task_id']}")
    if all_done:
        append_agent_telemetry(
            run_dir,
            "run_end",
            "shutdown" if all_successful else "error",
            validation_status="passed" if all_successful else "failed",
        )
    write_report(run_dir)
    print(status_text(run_dir))
    return 0


def status_data(run_dir: Path) -> dict[str, Any]:
    events = read_events(run_dir)
    run = read_json(run_dir / "run.json", {})
    queue = read_json(run_dir / "queue.json", {})
    state = read_json(run_dir / "state.json", {})
    checkpoint = read_json(run_dir / "checkpoint.json", {})
    tasks = queue.get("tasks", [])
    counts: dict[str, int] = {}
    for task in tasks:
        counts[task.get("status", "unknown")] = counts.get(task.get("status", "unknown"), 0) + 1
    next_task = next((task for task in tasks if task.get("status") in {"queued", "repair_queued"}), None)
    current_task_id = state.get("current_task_id", "")
    current_task = next((task for task in tasks if task.get("task_id") == current_task_id), None)
    telemetry_path = run_dir / UNIVERSAL_LOG_NAME
    telemetry = summarize_universal_log(telemetry_path) if telemetry_path.exists() else {}
    return {
        "leafos_object": "agent_loop_status",
        "run_id": run.get("run_id", ""),
        "run_dir": str(run_dir),
        "target": run.get("target", ""),
        "profile": run.get("profile", ""),
        "provider_mode": run.get("provider_mode", ""),
        "stack_entry": run.get("stack_entry", ""),
        "state": state.get("status", ""),
        "current_task": current_task_id,
        "current_project": current_task.get("project", "") if current_task else "",
        "task_counts": counts,
        "last_event": events[-1] if events else {},
        "last_checkpoint": checkpoint,
        "validation_status": "failed" if counts.get("failed") else ("passed" if counts.get("complete") else "pending"),
        "telemetry": telemetry,
        "next_action": "agent-loop-tick" if next_task else "agent-loop-report",
    }


def status_text(run_dir: Path) -> str:
    data = status_data(run_dir)
    last = data.get("last_event", {})
    counts = data.get("task_counts", {})
    return "\n".join(
        [
            f"run id       : {data['run_id']}",
            f"run dir      : {data['run_dir']}",
            f"target       : {data['target']}",
            f"state        : {data['state']}",
            f"provider     : {data['provider_mode']}",
            f"stack entry  : {data['stack_entry']}",
            f"project      : {data['current_project'] or 'none'}",
            f"tasks        : {counts}",
            f"last event   : {last.get('seq', 0)} {last.get('kind', '')}",
            f"validation   : {data['validation_status']}",
            f"next action  : {data['next_action']}",
        ]
    )


def status_run(args: argparse.Namespace) -> int:
    run_dir = resolve_run_dir(args.run)
    data = status_data(run_dir)
    if args.json:
        print(json.dumps(data, indent=2, ensure_ascii=True))
    else:
        print(status_text(run_dir))
    return 0


def resume_run(args: argparse.Namespace) -> int:
    run_dir = resolve_run_dir(args.run)
    ticket = _agent_ticket("loop.event.append", {"run_dir": str(run_dir), "action": "resume"})
    read_events(run_dir)
    state = read_json(run_dir / "state.json", {})
    state["status"] = "resumed"
    state["last_tick_utc"] = utc_now()
    state["next_action"] = "agent-loop-tick"
    write_json(run_dir / "state.json", state)
    append_event(run_dir, "run.resumed", ticket=ticket)
    print(status_text(run_dir))
    return 0


def stop_run(args: argparse.Namespace) -> int:
    run_dir = resolve_run_dir(args.run)
    ticket = _agent_ticket("loop.checkpoint", {"run_dir": str(run_dir), "action": "stop"})
    read_events(run_dir)
    run = read_json(run_dir / "run.json", {})
    queue = read_json(run_dir / "queue.json", {})
    state = read_json(run_dir / "state.json", {})
    state["status"] = "paused"
    state["stop_requested_utc"] = utc_now()
    state["stop_policy"] = "after-current-step" if args.after_current_step else "now"
    state["next_action"] = "agent-loop-resume"
    write_json(run_dir / "state.json", state)
    append_event(run_dir, "run.paused", ticket=ticket, stop_policy=state["stop_policy"])
    write_checkpoint(run_dir, run, queue, "operator_paused", ticket=ticket)
    write_report(run_dir)
    print(status_text(run_dir))
    return 0


def write_report(run_dir: Path) -> Path:
    data = status_data(run_dir)
    queue = read_json(run_dir / "queue.json", {})
    events = read_events(run_dir)
    provider_failures = [event for event in events if event.get("kind") == "provider.startup_failed"]
    telemetry = data.get("telemetry", {})
    warnings = telemetry.get("warnings", {}) if isinstance(telemetry, dict) else {}
    lines = [
        "# LeafOS Agent Loop Report",
        "",
        f"- Run id: `{data['run_id']}`",
        f"- Target: `{data['target']}`",
        f"- Provider mode: `{data['provider_mode']}`",
        f"- Stack entry: `{data['stack_entry']}`",
        f"- State: `{data['state']}`",
        f"- Validation: `{data['validation_status']}`",
        f"- Universal telemetry events: `{telemetry.get('event_count', 0)}`",
        "",
        "## Tasks",
        "",
    ]
    for task in queue.get("tasks", []):
        lines.append(f"- `{task.get('task_id')}`: {task.get('status')} ({task.get('project')})")
        for evidence in task.get("evidence", [])[-2:]:
            if "stdout" in evidence:
                lines.append(f"  evidence: exit={evidence.get('exit_code')} stdout=`{evidence.get('stdout')}`")
            if evidence.get("kind") == "catan2_benchmark":
                lines.append(
                    f"  benchmark: score delta={evidence.get('score_delta')} "
                    f"LeafOS={evidence.get('leafos_total')} bot={evidence.get('bot_total')} "
                    f"report=`{evidence.get('project_report')}`"
                )
    lines.extend(["", "## Provider And Hardware", ""])
    if provider_failures:
        for event in provider_failures:
            lines.append(f"- Provider fallback: {event.get('error', 'unknown error')}")
    else:
        lines.append("- Provider startup failures: none recorded")
    lines.append(f"- Telemetry warnings: `{json.dumps(warnings, sort_keys=True)}`")
    lines.extend(["", "## Next Action", "", f"`{data['next_action']}`", ""])
    report = run_dir / "report.md"
    report.write_text("\n".join(lines), encoding="utf-8")
    return report


def report_run(args: argparse.Namespace) -> int:
    run_dir = resolve_run_dir(args.run)
    report = write_report(run_dir)
    if args.json:
        print(json.dumps({"report": str(report), "status": status_data(run_dir)}, indent=2, ensure_ascii=True))
    else:
        print(report.read_text(encoding="utf-8"))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    create = sub.add_parser("create", help="create a new agent-loop run")
    create.add_argument("--target", required=True)
    create.add_argument("--projects", required=True, help="comma-separated project templates")
    create.add_argument("--profile", default="repository")
    create.add_argument("--provider-mode", choices=("off", "auto", "required"), default="")
    create.add_argument("--run-id", default="")
    create.add_argument("--run-dir", default="")
    create.add_argument("--max-minutes", type=int, default=0)
    create.add_argument("--dry-run", action="store_true")
    create.add_argument("--yes", action="store_true")
    create.add_argument("--force", action="store_true")

    status = sub.add_parser("status", help="inspect a run or target")
    status.add_argument("run")
    status.add_argument("--json", action="store_true")

    tick = sub.add_parser("tick", help="process one queued task")
    tick.add_argument("run")
    tick.add_argument("--max-minutes", type=int, default=0, help="accepted for operator parity; one tick remains bounded")
    tick.add_argument("--yes", action="store_true", help="accepted for noninteractive parity")

    resume = sub.add_parser("resume", help="mark a run resumed after validating its journal")
    resume.add_argument("run")
    resume.add_argument("--yes", action="store_true", help="accepted for noninteractive parity")

    stop = sub.add_parser("stop", help="pause a run at a safe boundary")
    stop.add_argument("run")
    stop.add_argument("--after-current-step", action="store_true")

    report = sub.add_parser("report", help="write and print a report")
    report.add_argument("run")
    report.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "create":
            return create_run(args)
        if args.command == "status":
            return status_run(args)
        if args.command == "tick":
            return tick_run(args)
        if args.command == "resume":
            return resume_run(args)
        if args.command == "stop":
            return stop_run(args)
        if args.command == "report":
            return report_run(args)
    except ValueError as error:
        print(f"agent loop error: {error}", file=sys.stderr)
        return 1
    raise AssertionError(args.command)


if __name__ == "__main__":
    raise SystemExit(main())
