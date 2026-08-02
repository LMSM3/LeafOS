#!/usr/bin/env python3
"""Work-order intake, plan-v2 policy, and bounded step executor for LeafOS."""

from __future__ import annotations

import hashlib
import json
import os
import re
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable

PYTHON_DIR = Path(__file__).resolve().parent
if str(PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(PYTHON_DIR))

import leaf_agent_loop as engine


PLAN_STEP_KINDS = {
    "read_files",
    "apply_patch",
    "write_file",
    "run_command",
    "run_tests",
    "record_hashes",
    "checkpoint",
    "report",
}
DEFAULT_DENIED_PARTS = {
    ".git",
    ".env",
    "secrets",
    "credentials",
    "id_rsa",
    "id_ed25519",
}
TEXT_SUFFIXES = {
    ".c", ".cc", ".cpp", ".h", ".hpp", ".json", ".md", ".ps1", ".py",
    ".sh", ".toml", ".txt", ".yaml", ".yml",
}
DEFAULT_INSPECTION_CONTENT_BYTES = 4096
DEFAULT_FILE_EXCERPT_BYTES = 2048


class TaskCancelled(RuntimeError):
    pass


def _task_file(run_dir: Path, prefix: str, task_id: str) -> Path:
    safe_id = re.sub(r"[^A-Za-z0-9._-]+", "-", task_id).strip("-")
    return run_dir / "control" / f"{prefix}-{safe_id}.json"


def _cancel_path(run_dir: Path, task_id: str) -> Path:
    return _task_file(run_dir, "cancel", task_id)


def _process_path(run_dir: Path) -> Path:
    return run_dir / "active-process.json"


def terminate_tracked_process(run_dir: Path, task_id: str | None = None) -> bool:
    lease_path = _process_path(run_dir)
    lease = engine.read_json(lease_path, {})
    pid = int(lease.get("pid", 0))
    if pid <= 0 or (task_id and lease.get("task_id") != task_id):
        return False
    try:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
        else:
            os.killpg(pid, signal.SIGTERM)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return True


def run_tracked_command(
    run_dir: Path,
    task: dict[str, Any],
    command: list[str],
    *,
    cwd: Path,
    timeout: int,
) -> subprocess.CompletedProcess[str]:
    process_options: dict[str, Any] = {}
    if os.name == "nt":
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP | getattr(subprocess, "CREATE_NO_WINDOW", 0)
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0  # SW_HIDE
        process_options["creationflags"] = creationflags
        process_options["startupinfo"] = startupinfo
    else:
        process_options["start_new_session"] = True
    process = subprocess.Popen(
        command,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        **process_options,
    )
    lease_path = _process_path(run_dir)
    lease = {
        "pid": process.pid,
        "task_id": task["task_id"],
        "command": command,
        "cwd": str(cwd),
        "started_utc": engine.utc_now(),
    }
    engine.write_json(lease_path, lease)
    started = time.monotonic()
    cancel_path = _cancel_path(run_dir, task["task_id"])
    try:
        while process.poll() is None:
            if cancel_path.is_file():
                terminate_tracked_process(run_dir, task["task_id"])
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
                process.communicate()
                raise TaskCancelled(f"task cancelled by operator: {task['task_id']}")
            if time.monotonic() - started >= timeout:
                terminate_tracked_process(run_dir, task["task_id"])
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
                process.communicate()
                raise subprocess.TimeoutExpired(command, timeout)
            time.sleep(0.05)
        stdout, stderr = process.communicate()
        if cancel_path.is_file():
            raise TaskCancelled(f"task cancelled by operator: {task['task_id']}")
        return subprocess.CompletedProcess(command, int(process.returncode or 0), stdout, stderr)
    finally:
        current = engine.read_json(lease_path, {})
        if int(current.get("pid", 0)) == process.pid:
            lease_path.unlink(missing_ok=True)


def _persist_task(run_dir: Path, queue: dict[str, Any], task: dict[str, Any]) -> None:
    with engine.queue_write_lock(run_dir):
        latest = engine.read_json(run_dir / "queue.json", queue)
        tasks = latest.get("tasks", [])
        current = next((item for item in tasks if item.get("task_id") == task.get("task_id")), None)
        if current is None:
            raise RuntimeError(f"task disappeared from queue: {task.get('task_id')}")
        if current.get("cancel_requested"):
            task["cancel_requested"] = True
        if current.get("status") == "cancelled":
            task["status"] = "cancelled"
            task["reason"] = current.get("reason", "operator_cancelled")
        tasks[tasks.index(current)] = task
        queue.clear()
        queue.update(latest)
        engine.write_json(run_dir / "queue.json", queue)


def _step_state_path(run_dir: Path, task: dict[str, Any]) -> Path:
    if task.get("kind") == "operator":
        return run_dir / f"step-state.{task['task_id']}.json"
    return run_dir / "step-state.json"


def _plan_path(run_dir: Path, task: dict[str, Any]) -> Path:
    if task.get("kind") == "operator":
        return run_dir / "artifacts" / f"{task['task_id']}.plan.v2.json"
    return run_dir / "plan.v2.json"


def _inspection_path(run_dir: Path, work_order: dict[str, Any]) -> Path:
    safe_id = re.sub(r"[^A-Za-z0-9._-]+", "-", str(work_order["work_order_id"])).strip("-")
    return run_dir / "artifacts" / f"{safe_id}.inspection.json"


def _archive_attempt_artifacts(run_dir: Path, task: dict[str, Any]) -> list[str]:
    archived: list[str] = []
    attempt = max(1, int(task.get("attempts", 1)))
    for path in (_plan_path(run_dir, task), _step_state_path(run_dir, task)):
        if not path.is_file():
            continue
        archive = path.with_name(f"{path.stem}.attempt-{attempt}{path.suffix}")
        archive.unlink(missing_ok=True)
        path.replace(archive)
        archived.append(str(archive))
        for evidence in reversed(task.get("evidence", [])):
            if evidence.get("path") == str(path):
                evidence["path"] = str(archive)
                break
    return archived


def _pipeline_repair_plan(queue: dict[str, Any], task: dict[str, Any]) -> dict[str, Any] | None:
    source = task.get("work_order")
    plans = [
        item for item in queue.get("tasks", [])
        if item.get("kind") == "plan" and item.get("work_order") == source
    ]
    plan = plans[0] if plans else None
    if plan is None or int(plan.get("attempts", 0)) >= int(plan.get("max_attempts", 1)):
        return None
    return plan


def _rewind_pipeline_for_repair(
    run_dir: Path,
    queue: dict[str, Any],
    failed_task: dict[str, Any],
    plan_task_id: str,
    error: str,
) -> None:
    archived = _archive_attempt_artifacts(run_dir, failed_task)
    with engine.queue_write_lock(run_dir):
        latest = engine.read_json(run_dir / "queue.json", queue)
        source = failed_task.get("work_order")
        for item in latest.get("tasks", []):
            if item.get("work_order") != source:
                continue
            if item.get("task_id") == plan_task_id:
                item.update(status="repair_queued", reason="pipeline_repair")
                archived_plan = next((value for value in archived if "plan.v2" in Path(value).name), None)
                if archived_plan:
                    for evidence in reversed(item.get("evidence", [])):
                        if evidence.get("kind") == "plan_v2":
                            evidence["path"] = archived_plan
                            break
                item.setdefault("evidence", []).append({
                    "kind": "pipeline_repair",
                    "failed_task_id": failed_task["task_id"],
                    "error": error,
                    "archived_artifacts": archived,
                })
            elif item.get("kind") in {"approve", "execute", "validate", "report"}:
                item["status"] = "queued"
                item.pop("reason", None)
        engine.write_json(run_dir / "queue.json", latest)
        queue.clear()
        queue.update(latest)


def _slug(value: str) -> str:
    return engine.slug(value).upper()


def _list_section(text: str, heading: str) -> list[str]:
    match = re.search(
        rf"(?ims)^##+\s+{re.escape(heading)}\s*$\s*(.*?)(?=^##+\s+|\Z)",
        text,
    )
    if not match:
        return []
    return [item.strip().strip("`") for item in re.findall(r"(?m)^\s*[-*]\s+(.+?)\s*$", match.group(1))]


def _text_section(text: str, heading: str) -> str:
    match = re.search(
        rf"(?ims)^##+\s+{re.escape(heading)}\s*$\s*(.*?)(?=^##+\s+|\Z)",
        text,
    )
    return match.group(1).strip() if match else ""


def load_work_order(path: Path) -> dict[str, Any]:
    source = path.resolve()
    if source.is_dir():
        preferred = source / "work-order.json"
        candidates = [preferred] if preferred.is_file() else sorted(source.glob("*.json"))
        if len(candidates) != 1:
            raise ValueError("work-order directory must contain exactly one JSON file or work-order.json")
        source = candidates[0].resolve()
    if not source.is_file():
        raise ValueError(f"work order not found: {source}")
    if source.suffix.lower() == ".json":
        data = engine.read_json(source, {})
        if not isinstance(data, dict):
            raise ValueError("work order JSON must be an object")
        data["source"] = str(source)
        return data
    if source.suffix.lower() not in {".md", ".txt"}:
        raise ValueError("work order must be .json, .md, or .txt")
    companion = source.with_suffix(".json")
    if companion.is_file():
        data = engine.read_json(companion, {})
        if not isinstance(data, dict):
            raise ValueError("work order companion JSON must be an object")
        data["source"] = str(source)
        data["companion"] = str(companion)
        return data
    text = source.read_text(encoding="utf-8")
    title_match = re.search(r"(?m)^#\s+(.+?)\s*$", text)
    identity = _text_section(text, "Identity")
    id_match = re.search(r"\bWO-[A-Za-z0-9._-]+", identity or source.stem, re.IGNORECASE)
    return {
        "work_order_id": (id_match.group(0).upper() if id_match else _slug(source.stem)),
        "title": title_match.group(1).strip() if title_match else source.stem,
        "objective": _text_section(text, "Objective"),
        "scope": _list_section(text, "Scope"),
        "constraints": _list_section(text, "Constraints"),
        "allowed_paths": _list_section(text, "Allowed paths"),
        "required_steps": _list_section(text, "Required steps"),
        "acceptance": _list_section(text, "Acceptance criteria"),
        "commands": {"tests": []},
        "approval_mode": "required",
        "allow_mutation": False,
        "source": str(source),
        "source_format": "markdown",
    }


class PathPolicy:
    def __init__(self, target: Path, allowed_paths: list[str], denied_paths: list[str] | None = None):
        self.target = target.resolve(strict=True)
        if not self.target.is_dir():
            raise ValueError(f"target is not a directory: {self.target}")
        if not allowed_paths:
            raise ValueError("work order requires at least one allowed_paths entry")
        self.denied_parts = {part.lower() for part in DEFAULT_DENIED_PARTS}
        self.denied_parts.update(Path(item).name.lower() for item in (denied_paths or []))
        self.allowed_roots = [self._resolve_declared(item) for item in allowed_paths]

    def _inside_target(self, path: Path) -> bool:
        try:
            path.relative_to(self.target)
            return True
        except ValueError:
            return False

    def _resolve_declared(self, value: str) -> Path:
        raw = Path(value)
        candidate = (raw if raw.is_absolute() else self.target / raw).resolve(strict=False)
        if not self._inside_target(candidate):
            raise ValueError(f"allowed path escapes target: {value}")
        if any(part.lower() in self.denied_parts for part in candidate.relative_to(self.target).parts):
            raise ValueError(f"allowed path enters a denied location: {value}")
        return candidate

    def resolve(self, value: str, *, write: bool = False) -> Path:
        raw = Path(value)
        candidate = (raw if raw.is_absolute() else self.target / raw).resolve(strict=False)
        if not self._inside_target(candidate):
            raise ValueError(f"path escapes target: {value}")
        relative_parts = candidate.relative_to(self.target).parts
        if any(part.lower() in self.denied_parts for part in relative_parts):
            raise ValueError(f"path is denied: {value}")
        if not any(candidate == root or root in candidate.parents for root in self.allowed_roots):
            raise ValueError(f"path is outside allowed_paths: {value}")
        if write:
            parent = candidate.parent.resolve(strict=False)
            if not self._inside_target(parent):
                raise ValueError(f"write parent escapes target: {value}")
        return candidate

    def resolve_cwd(self, value: str) -> Path:
        raw = Path(value)
        candidate = (raw if raw.is_absolute() else self.target / raw).resolve(strict=False)
        if not self._inside_target(candidate):
            raise ValueError(f"cwd escapes target: {value}")
        if any(part.lower() in self.denied_parts for part in candidate.relative_to(self.target).parts):
            raise ValueError(f"cwd enters a denied location: {value}")
        if not candidate.is_dir():
            raise ValueError(f"cwd is not a directory: {value}")
        return candidate

    def relative(self, path: Path) -> str:
        return str(path.resolve(strict=False).relative_to(self.target)).replace("\\", "/")


def normalize_commands(value: Any) -> dict[str, list[list[str]]]:
    if not isinstance(value, dict):
        return {"tests": []}
    result: dict[str, list[list[str]]] = {}
    for command_class, commands in value.items():
        if not isinstance(commands, list):
            raise ValueError(f"commands.{command_class} must be an array")
        normalized: list[list[str]] = []
        for command in commands:
            if not isinstance(command, list) or not command or not all(isinstance(part, str) and part for part in command):
                raise ValueError(f"commands.{command_class} entries must be non-empty string arrays")
            normalized.append(command)
        result[str(command_class)] = normalized
    result.setdefault("tests", [])
    return result


def validate_work_order(data: dict[str, Any], target_override: Path | None = None) -> dict[str, Any]:
    required = ("work_order_id", "title", "objective", "allowed_paths", "acceptance")
    missing = [key for key in required if not data.get(key)]
    if missing:
        raise ValueError("work order missing required fields: " + ", ".join(missing))
    declared_target = Path(str(data.get("target", target_override or ""))).resolve()
    target = (target_override or declared_target).resolve(strict=True)
    if data.get("target") and declared_target != target:
        raise ValueError(f"work order target does not match --target: {declared_target} != {target}")
    commands = normalize_commands(data.get("commands", {}))
    max_attempts = int(data.get("max_attempts", 2))
    timeout_seconds = int(data.get("timeout_seconds", 300))
    if not 1 <= max_attempts <= 5:
        raise ValueError("max_attempts must be between 1 and 5")
    if not 1 <= timeout_seconds <= 3600:
        raise ValueError("timeout_seconds must be between 1 and 3600")
    policy = PathPolicy(target, list(data["allowed_paths"]), list(data.get("denied_paths", [])))
    return {
        **data,
        "work_order_id": str(data["work_order_id"]),
        "target": str(target),
        "commands": commands,
        "max_attempts": max_attempts,
        "timeout_seconds": timeout_seconds,
        "approval_mode": str(data.get("approval_mode", "required")),
        "allow_mutation": bool(data.get("allow_mutation", False)),
        "_policy": policy,
    }


def queue_from_work_order(work_order: dict[str, Any], provider: str) -> list[dict[str, Any]]:
    wo_id = str(work_order["work_order_id"])
    target = str(work_order["target"])
    common = {
        "project": Path(target).name,
        "work_order": str(work_order.get("source", "")),
        "workdir": target,
        "stack_entry": "local-stack:local-coding",
        "max_attempts": int(work_order["max_attempts"]),
        "timeout_seconds": int(work_order["timeout_seconds"]),
        "attempts": 0,
        "evidence": [],
    }
    specs = [
        ("001", "inspect", "Inspect declared paths and capture bounded repository evidence.", [], "policy"),
        ("002", "plan", "Produce and validate a version 2 bounded action plan.", [f"{wo_id}-001"], provider),
        ("003", "approve", "Apply the configured operator approval policy.", [f"{wo_id}-002"], "policy"),
        ("004", "execute", "Execute approved plan steps one boundary at a time.", [f"{wo_id}-003"], "policy"),
        ("005", "validate", "Run every declared acceptance command.", [f"{wo_id}-004"], "policy"),
        ("006", "report", "Write final evidence and completion status.", [f"{wo_id}-005"], "policy"),
    ]
    return [
        {
            **common,
            "task_id": f"{wo_id}-{number}",
            "kind": kind,
            "objective": objective,
            "dependencies": dependencies,
            "provider": task_provider,
            "status": "queued",
        }
        for number, kind, objective, dependencies, task_provider in specs
    ]


def _approved_commands(work_order: dict[str, Any]) -> list[list[str]]:
    return [command for commands in work_order["commands"].values() for command in commands]


def normalize_plan_v2(plan: Any, work_order: dict[str, Any]) -> Any:
    """Fill only unambiguous fields from the CPU-owned work-order allowlist."""
    if not isinstance(plan, dict) or not isinstance(plan.get("steps"), list):
        return plan
    test_commands = work_order.get("commands", {}).get("tests", [])
    for step in plan["steps"]:
        if not isinstance(step, dict):
            continue
        kind = step.get("kind")
        if kind in {"read_files", "record_hashes"} and not step.get("paths") and isinstance(step.get("path"), str):
            step["paths"] = [step["path"]]
        if kind == "run_tests" and not step.get("command") and len(test_commands) == 1:
            step["command"] = list(test_commands[0])
    return plan


def _validate_paths(values: Any, policy: PathPolicy, *, write: bool = False) -> list[str]:
    if not isinstance(values, list) or not values or not all(isinstance(item, str) for item in values):
        return ["paths must be a non-empty string array"]
    errors: list[str] = []
    for value in values:
        try:
            policy.resolve(value, write=write)
        except ValueError as error:
            errors.append(str(error))
    return errors


def validate_plan_v2(plan: Any, task: dict[str, Any], work_order: dict[str, Any], run_dir: Path) -> list[str]:
    if not isinstance(plan, dict):
        return ["plan must be an object"]
    errors: list[str] = []
    if plan.get("leafos_object") != "agent_loop_plan":
        errors.append("leafos_object must be agent_loop_plan")
    if plan.get("version") != 2:
        errors.append("version must be 2")
    if plan.get("task_id") != task.get("task_id"):
        errors.append("task_id does not match the planning task")
    steps = plan.get("steps")
    if not isinstance(steps, list) or not 1 <= len(steps) <= 6:
        return errors + ["steps must contain between 1 and 6 entries"]
    policy: PathPolicy = work_order["_policy"]
    approved_commands = _approved_commands(work_order)
    seen: set[str] = set()
    for index, step in enumerate(steps):
        if not isinstance(step, dict):
            errors.append(f"step {index} must be an object")
            continue
        step_id = step.get("id")
        kind = step.get("kind")
        if not isinstance(step_id, str) or not step_id or step_id in seen:
            errors.append(f"step {index} has a missing or duplicate id")
        else:
            seen.add(step_id)
        if kind not in PLAN_STEP_KINDS:
            errors.append(f"step {step_id or index} has unsupported kind: {kind}")
            continue
        if kind in {"read_files", "record_hashes"}:
            errors.extend(f"step {step_id}: {error}" for error in _validate_paths(step.get("paths"), policy))
        elif kind == "write_file":
            if not work_order["allow_mutation"]:
                errors.append(f"step {step_id}: mutation is disabled by the work order")
            try:
                policy.resolve(str(step.get("path", "")), write=True)
            except ValueError as error:
                errors.append(f"step {step_id}: {error}")
            if not isinstance(step.get("content"), str):
                errors.append(f"step {step_id}: content must be a string")
            elif len(step["content"].encode("utf-8")) > 131072:
                errors.append(f"step {step_id}: content exceeds 128 KiB")
        elif kind == "apply_patch":
            if not work_order["allow_mutation"]:
                errors.append(f"step {step_id}: mutation is disabled by the work order")
            patch = step.get("patch")
            patch_file = step.get("patch_file")
            if not isinstance(patch, str) and not isinstance(patch_file, str):
                errors.append(f"step {step_id}: apply_patch requires patch or patch_file")
            if isinstance(patch, str) and len(patch.encode("utf-8")) > 262144:
                errors.append(f"step {step_id}: patch exceeds 256 KiB")
            if isinstance(patch_file, str):
                candidate = (run_dir / patch_file).resolve(strict=False)
                artifacts = (run_dir / "artifacts").resolve(strict=False)
                if candidate != artifacts and artifacts not in candidate.parents:
                    errors.append(f"step {step_id}: patch_file must be inside run artifacts")
        elif kind in {"run_command", "run_tests"}:
            command = step.get("command")
            if command not in approved_commands:
                errors.append(f"step {step_id}: command is not declared by the work order")
            try:
                policy.resolve_cwd(str(step.get("cwd", ".")))
            except ValueError as error:
                errors.append(f"step {step_id}: invalid cwd: {error}")
            timeout = step.get("timeout_seconds", work_order["timeout_seconds"])
            if not isinstance(timeout, int) or not 1 <= timeout <= work_order["timeout_seconds"]:
                errors.append(f"step {step_id}: timeout exceeds work-order policy")
    return errors


def plan_v2_schema() -> dict[str, Any]:
    string = {"type": "string"}
    paths = {"type": "array", "minItems": 1, "items": string}
    command = {"type": "array", "minItems": 1, "items": string}

    def step_variant(kind: str, required: list[str], extra: dict[str, Any]) -> dict[str, Any]:
        return {
            "type": "object",
            "additionalProperties": False,
            "required": ["id", "kind", *required],
            "properties": {
                "id": string,
                "kind": {"type": "string", "const": kind},
                **extra,
            },
        }

    step_variants = [
        step_variant("read_files", ["paths"], {"paths": paths}),
        step_variant("write_file", ["path", "content"], {"path": string, "content": string}),
        step_variant("apply_patch", ["patch"], {"patch": string}),
        step_variant("apply_patch", ["patch_file"], {"patch_file": string}),
        step_variant("run_command", ["command"], {
            "command": command, "cwd": string, "timeout_seconds": {"type": "integer", "minimum": 1},
        }),
        step_variant("run_tests", ["command"], {
            "command": command, "cwd": string, "timeout_seconds": {"type": "integer", "minimum": 1},
        }),
        step_variant("record_hashes", ["paths"], {"paths": paths}),
        step_variant("checkpoint", [], {}),
        step_variant("report", [], {}),
    ]
    return {
        "name": "leafos_agent_loop_plan_v2",
        "strict": True,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["leafos_object", "version", "task_id", "steps"],
            "properties": {
                "leafos_object": {"type": "string", "const": "agent_loop_plan"},
                "version": {"type": "integer", "const": 2},
                "task_id": {"type": "string"},
                "steps": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 6,
                    "items": {"oneOf": step_variants},
                },
            },
        },
    }


def inspect_work_order(
    run_dir: Path,
    work_order: dict[str, Any],
    *,
    content_limit: int = DEFAULT_INSPECTION_CONTENT_BYTES,
    file_excerpt_limit: int = DEFAULT_FILE_EXCERPT_BYTES,
) -> Path:
    policy: PathPolicy = work_order["_policy"]
    records: list[dict[str, Any]] = []
    total_content = 0
    for root in policy.allowed_roots:
        candidates = [root] if root.is_file() else sorted(path for path in root.rglob("*") if path.is_file())
        for path in candidates[:200]:
            safe = policy.resolve(str(path))
            data = safe.read_bytes()
            record: dict[str, Any] = {
                "path": policy.relative(safe),
                "size": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
            }
            if safe.suffix.lower() in TEXT_SUFFIXES and total_content < content_limit:
                excerpt = data[: min(len(data), file_excerpt_limit, content_limit - total_content)].decode("utf-8", errors="replace")
                record["excerpt"] = excerpt
                total_content += len(excerpt.encode("utf-8"))
            records.append(record)
    artifact = _inspection_path(run_dir, work_order)
    engine.write_json(artifact, {"work_order_id": work_order["work_order_id"], "files": records})
    return artifact


def _provider_plan(
    run_dir: Path,
    run: dict[str, Any],
    task: dict[str, Any],
    work_order: dict[str, Any],
    config: dict[str, Any],
    emit: Callable[..., dict[str, Any]],
) -> dict[str, Any]:
    inspection = engine.read_json(_inspection_path(run_dir, work_order), {})
    provider_view = {key: value for key, value in work_order.items() if not key.startswith("_")}
    repair_errors = [
        {key: item.get(key) for key in ("kind", "failed_task_id", "error") if item.get(key) is not None}
        for item in task.get("evidence", [])
        if item.get("kind") in {"error", "pipeline_repair"}
    ][-4:]
    prompt = json.dumps(
        {
            "work_order": provider_view,
            "inspection": inspection,
            "repair_context": {
                "attempt": int(task.get("attempts", 1)),
                "prior_failures": repair_errors,
            },
            "policy": {
                "step_kinds": sorted(PLAN_STEP_KINDS),
                "approved_commands": _approved_commands(work_order),
                "instruction": "Use only declared paths and exact approved commands. Produce at most six concise steps. Fix prior failures when present.",
            },
            "task_id": task["task_id"],
        },
        ensure_ascii=True,
    )
    endpoint = str(run["provider_endpoint"])
    context_tokens = int(config.get("server", {}).get("context_tokens", 8192))
    configured_output = int(config.get("thinking_loop", {}).get("work_order_max_output_tokens", 4096))
    max_output_tokens = max(512, min(configured_output, max(512, context_tokens // 2)))
    payload = {
        "model": str(config.get("server", {}).get("model", "local")),
        "messages": [
            {"role": "system", "content": "You are the proposal-only LeafOS coding brain. Return only compact plan-v2 JSON. Keep code minimal and internally consistent. Never claim execution or validation."},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": max_output_tokens,
        "temperature": float(config.get("thinking_loop", {}).get("temperature", 0.2)),
        "stream": True,
        "response_format": {"type": "json_schema", "json_schema": plan_v2_schema()},
    }
    request_bytes = json.dumps(payload).encode("utf-8")
    request_byte_limit = max(16384, context_tokens * 3)
    if len(request_bytes) > request_byte_limit:
        compact_files = []
        for item in inspection.get("files", []):
            if isinstance(item, dict):
                compact_files.append({key: value for key, value in item.items() if key != "excerpt"})
        compact_prompt = json.loads(prompt)
        compact_prompt["inspection"] = {**inspection, "files": compact_files, "compacted": True}
        payload["messages"][1]["content"] = json.dumps(compact_prompt, ensure_ascii=True)
        request_bytes = json.dumps(payload).encode("utf-8")
    if len(request_bytes) > request_byte_limit:
        raise ValueError(f"provider request exceeds bounded context budget: {len(request_bytes)} bytes > {request_byte_limit}")
    engine.write_json(run_dir / "artifacts" / f"{task['task_id']}.provider-request.json", payload)
    request = urllib.request.Request(endpoint, data=request_bytes, headers={"Content-Type": "application/json"}, method="POST")
    pieces: list[str] = []
    buffer: list[str] = []
    buffer_chars = 0
    reasoning_chars = 0
    next_progress = 256
    timings: dict[str, Any] = {}
    usage: dict[str, Any] = {}
    finish_reason = ""
    request_started = time.monotonic()
    first_content_seconds: float | None = None
    emit("provider.request.started", task_id=task["task_id"], endpoint=endpoint)
    try:
        response_context = urllib.request.urlopen(request, timeout=max(60, int(work_order["timeout_seconds"])))
    except urllib.error.HTTPError as error:
        detail = error.read(2048).decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"provider HTTP {error.code}: {detail or error.reason}") from error
    with response_context as response:
        for raw in response:
            if _cancel_path(run_dir, task["task_id"]).is_file():
                raise TaskCancelled(f"task cancelled by operator: {task['task_id']}")
            line = raw.decode("utf-8", errors="replace").strip()
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
            if isinstance(choice, dict) and choice.get("finish_reason"):
                finish_reason = str(choice["finish_reason"])
            delta = choice.get("delta", {}) if isinstance(choice, dict) else {}
            reasoning = delta.get("reasoning_content", "") if isinstance(delta, dict) else ""
            content = delta.get("content", "") if isinstance(delta, dict) else ""
            if reasoning:
                reasoning_chars += len(reasoning)
                if reasoning_chars >= next_progress:
                    emit("provider.progress", task_id=task["task_id"], phase="THOUGHT", private_reasoning_chars=reasoning_chars)
                    next_progress += 256
            if content:
                if first_content_seconds is None:
                    first_content_seconds = time.monotonic() - request_started
                pieces.append(content)
                buffer.append(content)
                buffer_chars += len(content)
                if buffer_chars >= 192:
                    emit("provider.output.delta", task_id=task["task_id"], text="".join(buffer))
                    buffer.clear()
                    buffer_chars = 0
    if buffer:
        emit("provider.output.delta", task_id=task["task_id"], text="".join(buffer))
    text = "".join(pieces).strip()
    response_path = run_dir / "artifacts" / f"{task['task_id']}.provider-response.json"
    response_path.write_text(text, encoding="utf-8")
    if not text:
        raise RuntimeError("provider returned no plan-v2 content")
    if finish_reason in {"length", "max_tokens"}:
        raise RuntimeError(f"provider plan reached the {max_output_tokens}-token output limit")
    plan = normalize_plan_v2(json.loads(text), work_order)
    errors = validate_plan_v2(plan, task, work_order, run_dir)
    if errors:
        raise ValueError("; ".join(errors))
    generated_tokens = usage.get("completion_tokens") or timings.get("predicted_n")
    generation_tk_s = timings.get("predicted_per_second")
    emit(
        "provider.request.completed",
        task_id=task["task_id"],
        brain_generation_tk_s=generation_tk_s,
        generated_tokens=generated_tokens,
        reasoning_chars=reasoning_chars,
        output_chars=len(text),
    )
    telemetry = engine.make_universal_event(
        str(run.get("run_id") or run_dir.name),
        "agent-loop",
        "sample",
        "brain",
        run_dir=run_dir,
        task_id=task.get("task_id"),
        project=work_order.get("work_order_id"),
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
    emit("provider.proposal.attached", task_id=task["task_id"], plan=str(response_path))
    return plan


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _patch_paths(patch: str) -> list[str]:
    paths = []
    for line in patch.splitlines():
        if line.startswith("+++ "):
            value = line[4:].split("\t", 1)[0]
            if value == "/dev/null":
                continue
            paths.append(value[2:] if value.startswith("b/") else value)
    return paths


def execute_plan_v2(
    run_dir: Path,
    run: dict[str, Any],
    task: dict[str, Any],
    work_order: dict[str, Any],
    plan: dict[str, Any],
    emit: Callable[..., dict[str, Any]],
) -> None:
    policy: PathPolicy = work_order["_policy"]
    state_path = _step_state_path(run_dir, task)
    step_state = engine.read_json(state_path, {"completed_step_ids": [], "steps": {}})
    completed = set(step_state.get("completed_step_ids", []))
    approved = task.get("approval_status") == "approved" or run.get("approval", {}).get("status") == "approved"
    for step in plan["steps"]:
        step_id = step["id"]
        kind = step["kind"]
        if step_id in completed:
            emit("step.skipped", task_id=task["task_id"], step_id=step_id, reason="checkpointed")
            continue
        mutation = kind in {"apply_patch", "write_file"}
        if mutation and not work_order["allow_mutation"]:
            raise RuntimeError(f"mutation is disabled by the work order: {step_id}")
        if mutation and not approved:
            raise RuntimeError(f"approval required before mutation step: {step_id}")
        emit("step.started", task_id=task["task_id"], step_id=step_id, step_kind=kind)
        evidence: dict[str, Any] = {"kind": kind}
        if kind == "read_files":
            files = []
            for value in step["paths"]:
                path = policy.resolve(value)
                content = path.read_text(encoding="utf-8", errors="replace")
                files.append({"path": policy.relative(path), "content": content[:65536], "sha256": _hash_file(path)})
            artifact = run_dir / "artifacts" / f"{task['task_id']}.{step_id}.files.json"
            engine.write_json(artifact, {"files": files})
            evidence.update(path=str(artifact), paths_count=len(files))
            emit("files.read", task_id=task["task_id"], step_id=step_id, paths_count=len(files), artifact=str(artifact))
        elif kind == "write_file":
            path = policy.resolve(step["path"], write=True)
            before = _hash_file(path) if path.is_file() else None
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(step["content"], encoding="utf-8")
            evidence.update(path=policy.relative(path), before_sha256=before, after_sha256=_hash_file(path))
            emit("file.written", task_id=task["task_id"], step_id=step_id, path=policy.relative(path))
        elif kind == "apply_patch":
            patch_path = run_dir / "artifacts" / f"{task['task_id']}.{step_id}.patch"
            if isinstance(step.get("patch"), str):
                patch_path.write_text(step["patch"], encoding="utf-8")
            else:
                patch_path = (run_dir / step["patch_file"]).resolve(strict=True)
            patch_text = patch_path.read_text(encoding="utf-8")
            for value in _patch_paths(patch_text):
                policy.resolve(value, write=True)
            check = subprocess.run(["git", "-C", str(policy.target), "apply", "--check", str(patch_path)], capture_output=True, text=True)
            if check.returncode != 0:
                raise RuntimeError(f"patch gate failed: {check.stderr.strip()}")
            applied = subprocess.run(["git", "-C", str(policy.target), "apply", str(patch_path)], capture_output=True, text=True)
            if applied.returncode != 0:
                raise RuntimeError(f"patch apply failed: {applied.stderr.strip()}")
            evidence.update(patch=str(patch_path), files_changed=len(_patch_paths(patch_text)))
            emit("patch.applied", task_id=task["task_id"], step_id=step_id, files_changed=evidence["files_changed"])
        elif kind in {"run_command", "run_tests"}:
            cwd = policy.resolve_cwd(step.get("cwd", "."))
            result = run_tracked_command(
                run_dir,
                task,
                step["command"],
                cwd=cwd,
                timeout=int(step.get("timeout_seconds", work_order["timeout_seconds"])),
            )
            stdout = run_dir / "artifacts" / f"{task['task_id']}.{step_id}.stdout.txt"
            stderr = run_dir / "artifacts" / f"{task['task_id']}.{step_id}.stderr.txt"
            stdout.write_text(result.stdout, encoding="utf-8")
            stderr.write_text(result.stderr, encoding="utf-8")
            evidence.update(exit_code=result.returncode, stdout=str(stdout), stderr=str(stderr))
            if result.returncode != 0:
                raise RuntimeError(f"command failed with exit code {result.returncode}: {step_id}")
            emit("validation.passed" if kind == "run_tests" else "command.completed", task_id=task["task_id"], step_id=step_id, exit_code=0)
        elif kind == "record_hashes":
            hashes = {policy.relative(policy.resolve(value)): _hash_file(policy.resolve(value)) for value in step["paths"]}
            artifact = run_dir / "artifacts" / f"{task['task_id']}.{step_id}.hashes.json"
            engine.write_json(artifact, hashes)
            evidence.update(path=str(artifact), files=len(hashes))
            emit("hashes.recorded", task_id=task["task_id"], step_id=step_id, files=len(hashes))
        elif kind == "checkpoint":
            evidence["checkpoint_requested"] = True
        elif kind == "report":
            evidence["report_requested"] = True
        step_state.setdefault("steps", {})[step_id] = evidence
        completed.add(step_id)
        step_state["completed_step_ids"] = list(completed)
        engine.write_json(state_path, step_state)
        emit("step.completed", task_id=task["task_id"], step_id=step_id, step_kind=kind)
        write_checkpoint_v2(run_dir, run, work_order, task["task_id"], list(completed), f"step:{step_id}")


def write_checkpoint_v2(
    run_dir: Path,
    run: dict[str, Any],
    work_order: dict[str, Any],
    task_id: str,
    completed_steps: list[str],
    stop_reason: str,
) -> None:
    queue = engine.read_json(run_dir / "queue.json", {})
    task_view = {"task_id": task_id, "kind": "operator"} if (run_dir / f"step-state.{task_id}.json").is_file() else {"task_id": task_id}
    step_state = engine.read_json(_step_state_path(run_dir, task_view), {})
    checkpoint = {
        "leafos_object": "agent_loop_checkpoint",
        "version": 2,
        "written_at": engine.utc_now(),
        "work_order_id": work_order["work_order_id"],
        "task_id": task_id,
        "completed_step_ids": completed_steps,
        "queue_digest": engine.queue_digest(queue),
        "changed_file_hashes": {
            value.get("path"): value.get("after_sha256")
            for value in step_state.get("steps", {}).values()
            if value.get("after_sha256")
        },
        "validation_results": [
            value for value in step_state.get("steps", {}).values() if value.get("kind") == "run_tests"
        ],
        "provider": {
            "mode": run.get("provider_mode"),
            "endpoint": run.get("provider_endpoint"),
            "stack_entry": run.get("stack_entry"),
        },
        "approval_state": run.get("approval", {}),
        "stop_reason": stop_reason,
        "next_action": "loop drive",
    }
    engine.write_json(run_dir / "checkpoint.json", checkpoint)
    engine.append_event(run_dir, "checkpoint.written", task_id=task_id, stop_reason=stop_reason, queue_digest=checkpoint["queue_digest"])


def hydrate_work_order(run: dict[str, Any], task: dict[str, Any] | None = None) -> dict[str, Any]:
    source_value = task.get("work_order_source") if task else None
    source = Path(str(source_value or run["work_order"]["source"]))
    data = load_work_order(source)
    return validate_work_order(data, Path(str(run["target"])))


def run_work_order_task(
    run_dir: Path,
    run: dict[str, Any],
    queue: dict[str, Any],
    task: dict[str, Any],
    config: dict[str, Any],
    event_sink: Callable[[dict[str, Any]], None] | None = None,
) -> None:
    work_order = hydrate_work_order(run, task)
    telemetry_phase = {
        "inspect": "planning",
        "plan": "planning",
        "approve": "checkpoint",
        "execute": "execution",
        "validate": "validation",
        "report": "checkpoint",
        "operator": "execution",
    }.get(str(task.get("kind")), "idle")

    def emit(kind: str, **data: Any) -> dict[str, Any]:
        event = engine.append_event(run_dir, kind, **data)
        if event_sink:
            event_sink(event)
        return event

    task["status"] = "executing"
    task["attempts"] = int(task.get("attempts", 0)) + 1
    _persist_task(run_dir, queue, task)
    emit("task.started", task_id=task["task_id"], task_kind=task["kind"], attempt=task["attempts"])
    engine.append_agent_telemetry(
        run_dir,
        "task_start",
        telemetry_phase,
        task=task,
        validation_status="pending",
        collect_hardware=task["kind"] in {"plan", "execute", "validate"},
    )
    try:
        if task["kind"] == "inspect":
            thinking = config.get("thinking_loop", {})
            content_limit = max(0, min(int(thinking.get("work_order_inspection_content_bytes", DEFAULT_INSPECTION_CONTENT_BYTES)), 16384))
            excerpt_limit = max(0, min(int(thinking.get("work_order_file_excerpt_bytes", DEFAULT_FILE_EXCERPT_BYTES)), 8192))
            artifact = inspect_work_order(run_dir, work_order, content_limit=content_limit, file_excerpt_limit=excerpt_limit)
            task["evidence"].append({"kind": "inspection", "path": str(artifact)})
        elif task["kind"] == "plan":
            plan = _provider_plan(run_dir, run, task, work_order, config, emit)
            engine.write_json(_plan_path(run_dir, task), plan)
            task["evidence"].append({"kind": "plan_v2", "path": str(_plan_path(run_dir, task))})
        elif task["kind"] == "approve":
            if work_order["approval_mode"] == "required" and run.get("approval", {}).get("status") != "approved":
                task["status"] = "blocked"
                task["reason"] = "approval_required"
                emit("approval.required", task_id=task["task_id"])
                return
            emit("approval.passed", task_id=task["task_id"], mode=work_order["approval_mode"])
        elif task["kind"] == "execute":
            plan = engine.read_json(_plan_path(run_dir, task), {})
            errors = validate_plan_v2(plan, queue["tasks"][1], work_order, run_dir)
            if errors:
                raise RuntimeError("stored plan-v2 failed revalidation: " + "; ".join(errors))
            execute_plan_v2(run_dir, run, task, work_order, plan, emit)
        elif task["kind"] == "validate":
            for index, command in enumerate(work_order["commands"].get("tests", []), start=1):
                result = run_tracked_command(run_dir, task, command, cwd=Path(work_order["target"]), timeout=work_order["timeout_seconds"])
                stdout = run_dir / "artifacts" / f"{task['task_id']}.acceptance-{index}.stdout.txt"
                stderr = run_dir / "artifacts" / f"{task['task_id']}.acceptance-{index}.stderr.txt"
                stdout.write_text(result.stdout, encoding="utf-8")
                stderr.write_text(result.stderr, encoding="utf-8")
                task["evidence"].append({"kind": "acceptance_command", "command": command, "exit_code": result.returncode, "stdout": str(stdout), "stderr": str(stderr)})
                emit("validation.passed" if result.returncode == 0 else "validation.failed", task_id=task["task_id"], command_index=index, exit_code=result.returncode)
                if result.returncode != 0:
                    raise RuntimeError(f"acceptance command {index} failed with exit code {result.returncode}")
        elif task["kind"] == "operator":
            artifact = inspect_work_order(run_dir, work_order)
            task["evidence"].append({"kind": "inspection", "path": str(artifact)})
            if task.get("provider") == "llamacpp":
                plan_path = _plan_path(run_dir, task)
                plan = engine.read_json(plan_path, {}) if plan_path.is_file() else {}
                if not plan:
                    plan = _provider_plan(run_dir, run, task, work_order, config, emit)
                    engine.write_json(plan_path, plan)
                    task["evidence"].append({"kind": "plan_v2", "path": str(plan_path)})
                errors = validate_plan_v2(plan, task, work_order, run_dir)
                if errors:
                    raise RuntimeError("stored operator plan-v2 failed revalidation: " + "; ".join(errors))
                if work_order["approval_mode"] == "required" and task.get("approval_status") != "approved":
                    task["status"] = "blocked"
                    task["reason"] = "approval_required"
                    task["attempts"] = max(0, int(task.get("attempts", 1)) - 1)
                    _persist_task(run_dir, queue, task)
                    emit("approval.required", task_id=task["task_id"])
                    return
                execute_plan_v2(run_dir, run, task, work_order, plan, emit)
            else:
                emit("task.cpu_fallback", task_id=task["task_id"], summary="CPU fallback performs declared validation only.")
            for index, command in enumerate(work_order["commands"].get("tests", []), start=1):
                result = run_tracked_command(run_dir, task, command, cwd=Path(work_order["target"]), timeout=work_order["timeout_seconds"])
                stdout = run_dir / "artifacts" / f"{task['task_id']}.acceptance-{index}.stdout.txt"
                stderr = run_dir / "artifacts" / f"{task['task_id']}.acceptance-{index}.stderr.txt"
                stdout.write_text(result.stdout, encoding="utf-8")
                stderr.write_text(result.stderr, encoding="utf-8")
                task["evidence"].append({"kind": "acceptance_command", "command": command, "exit_code": result.returncode, "stdout": str(stdout), "stderr": str(stderr)})
                emit("validation.passed" if result.returncode == 0 else "validation.failed", task_id=task["task_id"], command_index=index, exit_code=result.returncode)
                if result.returncode != 0:
                    raise RuntimeError(f"acceptance command {index} failed with exit code {result.returncode}")
        elif task["kind"] == "report":
            engine.write_report(run_dir)
            emit("report.written", task_id=task["task_id"], path=str(run_dir / "report.md"))
        if _cancel_path(run_dir, task["task_id"]).is_file() or task.get("cancel_requested"):
            raise TaskCancelled(f"task cancelled by operator: {task['task_id']}")
        task["status"] = "complete"
        _persist_task(run_dir, queue, task)
        emit("task.completed", task_id=task["task_id"], task_kind=task["kind"])
        engine.append_agent_telemetry(
            run_dir,
            "task_end",
            telemetry_phase,
            task=task,
            validation_status="passed",
            checkpoint_valid=True,
            collect_hardware=task["kind"] in {"execute", "validate"},
        )
    except TaskCancelled as error:
        task["status"] = "cancelled"
        task["reason"] = "operator_cancelled"
        task.setdefault("evidence", []).append({"kind": "cancellation", "error": str(error)})
        _persist_task(run_dir, queue, task)
        emit("task.cancelled", task_id=task["task_id"], task_kind=task["kind"], reason=str(error))
    except (OSError, subprocess.TimeoutExpired, urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError, RuntimeError) as error:
        can_repair = int(task.get("attempts", 0)) < int(task.get("max_attempts", 1))
        repair_task_id = task["task_id"]
        pipeline_plan = _pipeline_repair_plan(queue, task) if can_repair and task.get("kind") in {"execute", "validate"} else None
        if task.get("kind") in {"execute", "validate"} and pipeline_plan is None:
            can_repair = False
        task["status"] = "queued" if pipeline_plan is not None else ("repair_queued" if can_repair else "failed")
        task["reason"] = "pipeline_repair" if pipeline_plan is not None else "work_order_task_failed"
        task.setdefault("evidence", []).append({"kind": "error", "error": str(error)})
        if can_repair and task.get("kind") == "operator":
            archived = _archive_attempt_artifacts(run_dir, task)
            task["evidence"][-1]["archived_artifacts"] = archived
        _persist_task(run_dir, queue, task)
        emit("task.failed", task_id=task["task_id"], task_kind=task["kind"], error=str(error))
        if can_repair:
            if pipeline_plan is not None:
                repair_task_id = str(pipeline_plan["task_id"])
                _rewind_pipeline_for_repair(run_dir, queue, task, repair_task_id, str(error))
            emit(
                "repair.queued",
                task_id=repair_task_id,
                failed_task_id=task["task_id"],
                next_attempt=int((pipeline_plan or task).get("attempts", 0)) + 1,
            )
        engine.append_agent_telemetry(
            run_dir,
            "repair" if can_repair else "run_error",
            "planning" if can_repair else "error",
            task=task,
            validation_status="failed",
            checkpoint_valid=False,
            notes=[str(error)],
            collect_hardware=True,
        )
    finally:
        _persist_task(run_dir, queue, task)
        write_checkpoint_v2(run_dir, run, work_order, task["task_id"], engine.read_json(_step_state_path(run_dir, task), {}).get("completed_step_ids", []), f"task:{task['task_id']}")
