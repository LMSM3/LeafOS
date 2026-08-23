from __future__ import annotations

import ctypes
import hashlib
import json
import os
import re
import secrets
import signal
import subprocess
import time
from contextlib import AbstractContextManager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.state import utc_now


OBJECTIVE_SCHEMA = "leafos.objective.v1"
TASKGRAPH_SCHEMA = "leafos.taskgraph.v1"
EVIDENCE_SCHEMA = "leafos.evidence.v1"
TERMINAL_STATUSES = {"accepted", "failed", "cancelled"}
VERIFIER_VERDICTS = {"accept", "reject", "conflict", "invalid"}
VERIFIER_CONFIDENCE = {"low", "medium", "high", "unverified"}
TASK_ID_PATTERN = re.compile(r"^task-[0-9]{6}$")
LANE_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")
MAX_SOURCE_BYTES = 128 * 1024
MAX_SOURCE_TOTAL_BYTES = 256 * 1024
CURRENT_CONTROL_PHASE = "1.0.0-phase-e"
CONTROL_PHASE_ORDER = (
    "1.0.0-phase-a", "1.0.0-phase-b", "1.0.0-phase-c", "1.0.0-phase-d", CURRENT_CONTROL_PHASE,
)
SCHEDULE_CLASSES = {"interactive", "critical", "verifier", "speculative", "compression"}


class ControlError(ValueError):
    pass


def _identity_key(value: str) -> str:
    windows = value.replace("/", "\\")
    wsl = re.match(r"^\\mnt\\([A-Za-z])(?:\\(.*))?$", windows)
    if wsl:
        windows = f"{wsl.group(1)}:\\{wsl.group(2) or ''}"
    if re.match(r"^[A-Za-z]:\\", windows):
        return windows.casefold().rstrip("\\")
    return os.path.normcase(value).rstrip("/\\")


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _seal(value: dict[str, Any]) -> dict[str, Any]:
    payload = dict(value)
    payload.pop("integrity", None)
    digest = hashlib.sha256(_canonical_bytes(payload)).hexdigest()
    return {**payload, "integrity": f"sha256:{digest}"}


def _verify(value: Any, schema: str, source: Path) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ControlError(f"invalid {schema} document: {source}")
    if value.get("schema") != schema:
        raise ControlError(f"unsupported control schema in {source}: {value.get('schema')!r}")
    expected = value.get("integrity")
    actual = _seal(value).get("integrity")
    if not isinstance(expected, str) or expected != actual:
        raise ControlError(f"control state integrity check failed: {source}")
    return value


def _pid_alive(pid: Any) -> bool:
    if not isinstance(pid, int) or pid <= 0:
        return False
    if pid == os.getpid():
        return True
    try:
        if os.name == "nt":
            process_query_limited_information = 0x1000
            handle = ctypes.windll.kernel32.OpenProcess(process_query_limited_information, False, pid)
            if not handle:
                return False
            exit_code = ctypes.c_ulong()
            try:
                if not ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                    return False
                return exit_code.value == 259
            finally:
                ctypes.windll.kernel32.CloseHandle(handle)
        os.kill(pid, 0)
        return True
    except (OSError, AttributeError):
        return False


def _host_session_id() -> str:
    """Return a boot-scoped host identity so persisted PIDs are never trusted after restart."""
    boot_id = Path("/proc/sys/kernel/random/boot_id")
    if boot_id.is_file():
        try:
            value = boot_id.read_text(encoding="utf-8").strip()
            if value:
                return f"unix:{value}"
        except OSError:
            pass
    if os.name == "nt":
        try:
            uptime_seconds = ctypes.windll.kernel32.GetTickCount64() / 1000.0
            boot_second = int(round(time.time() - uptime_seconds))
            return f"windows:{boot_second}"
        except (AttributeError, OSError):
            pass
    return f"host:{os.name}"


def _lease_process_alive(lease: dict[str, Any], key: str = "pid") -> bool:
    session = lease.get("host_session_id")
    if isinstance(session, str) and session and session != _host_session_id():
        return False
    return _pid_alive(lease.get(key))


def _terminate_process_tree(pid: Any, timeout_seconds: float = 5.0) -> bool:
    """Terminate one lease-owned process tree and confirm it is gone."""
    if not _pid_alive(pid):
        return True
    value = int(pid)
    try:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(value), "/T", "/F"],
                capture_output=True,
                text=True,
                timeout=max(1.0, timeout_seconds),
                check=False,
            )
        else:
            os.kill(value, signal.SIGTERM)
    except (OSError, subprocess.TimeoutExpired):
        pass
    deadline = time.monotonic() + max(0.1, timeout_seconds)
    while _pid_alive(value) and time.monotonic() < deadline:
        time.sleep(0.05)
    if _pid_alive(value) and os.name != "nt":
        try:
            os.kill(value, signal.SIGKILL)
        except OSError:
            pass
    return not _pid_alive(value)


class _FileLock(AbstractContextManager["_FileLock"]):
    def __init__(self, path: Path, timeout_seconds: float = 5.0) -> None:
        self.path = path
        self.timeout_seconds = timeout_seconds
        self.acquired = False

    def __enter__(self) -> "_FileLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        deadline = time.monotonic() + self.timeout_seconds
        payload = json.dumps({"pid": os.getpid(), "created_at": utc_now()}) + "\n"
        while True:
            try:
                descriptor = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                try:
                    os.write(descriptor, payload.encode("utf-8"))
                    os.fsync(descriptor)
                finally:
                    os.close(descriptor)
                self.acquired = True
                return self
            except FileExistsError:
                lock_is_parseable = True
                try:
                    current = json.loads(self.path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    current = {}
                    lock_is_parseable = False
                if not isinstance(current, dict):
                    current = {}
                    lock_is_parseable = False
                stale_unparseable = False
                if not lock_is_parseable:
                    try:
                        stale_unparseable = time.time() - self.path.stat().st_mtime > 30
                    except OSError:
                        stale_unparseable = False
                if (lock_is_parseable and not _pid_alive(current.get("pid"))) or stale_unparseable:
                    try:
                        self.path.unlink()
                        continue
                    except OSError:
                        pass
                if time.monotonic() >= deadline:
                    raise ControlError(f"control state is locked: {self.path}")
                time.sleep(0.05)

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        if self.acquired:
            try:
                self.path.unlink()
            except FileNotFoundError:
                pass
            self.acquired = False


class ProjectStore:
    def __init__(self, project_root: Path) -> None:
        root = project_root.expanduser().resolve()
        if not root.is_dir():
            raise ControlError(f"project directory is missing: {root}")
        self.project_root = root
        self.leaf_dir = root / ".leaf"
        self.state_dir = self.leaf_dir / "state"
        self.tasks_dir = self.leaf_dir / "tasks"
        self.epochs_dir = self.leaf_dir / "epochs"
        self.evidence_dir = self.leaf_dir / "evidence"
        self.workers_dir = self.leaf_dir / "workers"
        self.context_dir = self.leaf_dir / "context"
        self.objective_path = self.state_dir / "objective.json"
        self.taskgraph_path = self.state_dir / "taskgraph.json"
        self.scheduler_path = self.state_dir / "scheduler.json"
        self.decisions_path = self.state_dir / "decisions.jsonl"
        self.journal_path = self.state_dir / "journal.jsonl"
        self.lock_path = self.leaf_dir / "control.lock"

    @property
    def initialized(self) -> bool:
        return self.objective_path.is_file() or self.taskgraph_path.is_file()

    @property
    def project_identity(self) -> dict[str, str]:
        normalized = _identity_key(str(self.project_root))
        digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]
        return {"id": f"project-{digest}", "name": self.project_root.name, "root": str(self.project_root)}

    def _prepare(self) -> None:
        for directory in (
            self.state_dir,
            self.tasks_dir,
            self.epochs_dir,
            self.evidence_dir,
            self.workers_dir,
            self.context_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)

    def _atomic_bytes(self, path: Path, data: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f"{path.name}.tmp.{os.getpid()}")
        with temporary.open("wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)

    def _atomic_text(self, path: Path, text: str) -> None:
        self._atomic_bytes(path, text.encode("utf-8"))

    def _write_document(self, path: Path, value: dict[str, Any]) -> dict[str, Any]:
        sealed = _seal(value)
        self._atomic_text(path, json.dumps(sealed, indent=2, ensure_ascii=False) + "\n")
        return sealed

    def _read_document(self, path: Path, schema: str) -> dict[str, Any]:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as error:
            raise ControlError(f"control state is not initialized: {path}") from error
        except (OSError, json.JSONDecodeError) as error:
            raise ControlError(f"malformed control state: {path}: {error}") from error
        return _verify(value, schema, path)

    def _append_record(self, path: Path, value: dict[str, Any]) -> None:
        record = _seal(value)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(record, separators=(",", ":"), ensure_ascii=False) + "\n")
            stream.flush()
            os.fsync(stream.fileno())

    def _journal(self, kind: str, **fields: Any) -> None:
        self._append_record(
            self.journal_path,
            {
                "schema": "leafos.control-event.v1",
                "time": utc_now(),
                "kind": kind,
                "project_id": self.project_identity["id"],
                **fields,
            },
        )

    def initialize(self, objective_text: str, *, replace: bool = False) -> dict[str, Any]:
        objective_text = objective_text.strip()
        if not objective_text:
            raise ControlError("objective cannot be empty")
        if len(objective_text) > 16_384:
            raise ControlError("objective is too large")
        self._prepare()
        with _FileLock(self.lock_path):
            if self.objective_path.exists() or self.taskgraph_path.exists():
                if not (self.objective_path.exists() and self.taskgraph_path.exists()):
                    raise ControlError("partial control state: objective and task graph must both exist")
                objective = self._read_document(self.objective_path, OBJECTIVE_SCHEMA)
                graph = self._read_document(self.taskgraph_path, TASKGRAPH_SCHEMA)
                if objective.get("text") == objective_text:
                    return objective
                if not replace:
                    raise ControlError("a different objective already exists; use --replace only before tasks are created")
                if graph.get("tasks"):
                    raise ControlError("cannot replace an objective after tasks are created")
                revision = int(objective.get("revision", 1)) + 1
            else:
                revision = 1
                graph = {
                    "schema": TASKGRAPH_SCHEMA,
                    "revision": 1,
                    "updated_at": utc_now(),
                    "project_id": self.project_identity["id"],
                    "next_task": 1,
                    "next_evidence": 1,
                    "tasks": {},
                }
                self._write_document(self.taskgraph_path, graph)
            objective = {
                "schema": OBJECTIVE_SCHEMA,
                "revision": revision,
                "updated_at": utc_now(),
                "project": self.project_identity,
                "text": objective_text,
                "phase": CURRENT_CONTROL_PHASE,
                "mode": (
                    "recovery-swarm" if CURRENT_CONTROL_PHASE.endswith("phase-e")
                    else "epoch-swarm" if CURRENT_CONTROL_PHASE.endswith("phase-d")
                    else "bounded-swarm" if CURRENT_CONTROL_PHASE.endswith("phase-c")
                    else "single-worker"
                ),
            }
            objective = self._write_document(self.objective_path, objective)
            self.decisions_path.touch(exist_ok=True)
            self._journal("objective.planned", revision=revision)
            return objective

    def advance_phase(self, phase: str) -> dict[str, Any]:
        if phase not in CONTROL_PHASE_ORDER:
            raise ControlError(f"unsupported control phase: {phase}")
        with _FileLock(self.lock_path):
            objective = self.load_objective()
            current = objective.get("phase")
            if current == phase:
                return objective
            if current not in CONTROL_PHASE_ORDER or CONTROL_PHASE_ORDER.index(phase) < CONTROL_PHASE_ORDER.index(current):
                raise ControlError(f"control phase cannot move backward or skip authority: {current} -> {phase}")
            now = utc_now()
            objective["phase"] = phase
            if phase == "1.0.0-phase-c":
                objective["mode"] = "bounded-swarm"
            elif phase == "1.0.0-phase-d":
                objective["mode"] = "epoch-swarm"
            elif phase == "1.0.0-phase-e":
                objective["mode"] = "recovery-swarm"
            objective["revision"] = int(objective.get("revision", 0)) + 1
            objective["updated_at"] = now
            objective = self._write_document(self.objective_path, objective)
            decisions = self._read_records(self.decisions_path)
            decision_id = f"decision-{len(decisions) + 1:06d}"
            self._append_record(
                self.decisions_path,
                {
                    "schema": "leafos.decision.v1",
                    "id": decision_id,
                    "kind": "phase-transition",
                    "from": current,
                    "to": phase,
                    "producer": "leafos:controller",
                    "observed_at": now,
                },
            )
            self._journal("control.phase_advanced", decision_id=decision_id, previous=current, phase=phase)
            return objective

    def load_objective(self) -> dict[str, Any]:
        objective = self._read_document(self.objective_path, OBJECTIVE_SCHEMA)
        if objective.get("project", {}).get("id") != self.project_identity["id"]:
            raise ControlError(f"objective belongs to a different project: {self.objective_path}")
        return objective

    def load_taskgraph(self) -> dict[str, Any]:
        graph = self._read_document(self.taskgraph_path, TASKGRAPH_SCHEMA)
        if graph.get("project_id") != self.project_identity["id"]:
            raise ControlError(f"task graph belongs to a different project: {self.taskgraph_path}")
        if not isinstance(graph.get("tasks"), dict):
            raise ControlError(f"task graph has invalid tasks: {self.taskgraph_path}")
        return graph

    def recover(self) -> list[str]:
        if not self.initialized:
            return []
        recovered: list[str] = []
        with _FileLock(self.lock_path):
            graph = self.load_taskgraph()
            for task_id, task in graph["tasks"].items():
                if task.get("status") != "running":
                    continue
                lease = task.get("lease") if isinstance(task.get("lease"), dict) else {}
                lease_seconds = lease.get("lease_seconds")
                heartbeat = lease.get("heartbeat_at")
                heartbeat_alive = True
                if isinstance(lease_seconds, int) and isinstance(heartbeat, str):
                    try:
                        heartbeat_at = datetime.fromisoformat(heartbeat.replace("Z", "+00:00"))
                        heartbeat_alive = (datetime.now(timezone.utc) - heartbeat_at).total_seconds() <= lease_seconds
                    except ValueError:
                        heartbeat_alive = False
                if _lease_process_alive(lease) and heartbeat_alive:
                    continue
                if _lease_process_alive(lease, "runtime_pid"):
                    _terminate_process_tree(lease.get("runtime_pid"))
                attempts = int(task.get("attempt", 0))
                maximum = int(task.get("budget", {}).get("attempts", 1))
                task["status"] = "ready" if attempts < maximum else "failed"
                task["lease"] = None
                task["updated_at"] = utc_now()
                task["last_error"] = "recovered an abandoned worker lease"
                self._release_ownership(task_id, lease.get("token"))
                recovered.append(task_id)
            for task_id, task in graph["tasks"].items():
                if task.get("status") != "verifying":
                    continue
                lease = task.get("verification_lease") if isinstance(task.get("verification_lease"), dict) else {}
                if not lease:
                    continue
                lease_seconds = lease.get("lease_seconds")
                heartbeat = lease.get("heartbeat_at")
                heartbeat_alive = True
                if isinstance(lease_seconds, int) and isinstance(heartbeat, str):
                    try:
                        heartbeat_at = datetime.fromisoformat(heartbeat.replace("Z", "+00:00"))
                        heartbeat_alive = (datetime.now(timezone.utc) - heartbeat_at).total_seconds() <= lease_seconds
                    except ValueError:
                        heartbeat_alive = False
                if _lease_process_alive(lease) and heartbeat_alive:
                    continue
                if _lease_process_alive(lease, "runtime_pid"):
                    _terminate_process_tree(lease.get("runtime_pid"))
                task["verification_lease"] = None
                task["updated_at"] = utc_now()
                task["last_error"] = "recovered an abandoned verifier lease"
                self._release_verification_ownership(task_id, lease.get("token"))
                recovered.append(task_id)
            if recovered:
                graph["revision"] = int(graph.get("revision", 0)) + 1
                graph["updated_at"] = utc_now()
                self._write_document(self.taskgraph_path, graph)
                self._journal("task.leases_recovered", task_ids=recovered)
        return recovered

    def create_task(
        self,
        goal: str,
        lane: str,
        *,
        prompt: str | None = None,
        input_paths: list[str] | None = None,
        dependencies: list[str] | None = None,
        tokens: int = 128,
        context: int | None = None,
        timeout_seconds: int = 300,
        attempts: int = 2,
        tool_attempts: int = 3,
        verifier_attempts: int = 2,
        priority: int = 50,
        schedule_class: str = "critical",
    ) -> dict[str, Any]:
        goal = goal.strip()
        if not goal:
            raise ControlError("task goal cannot be empty")
        if len(goal) > 16_384:
            raise ControlError("task goal is too large")
        if not LANE_PATTERN.fullmatch(lane):
            raise ControlError(f"invalid task lane: {lane}")
        if not 1 <= tokens <= 32_768:
            raise ControlError("task token budget must be between 1 and 32768")
        if context is not None and not 256 <= context <= 1_048_576:
            raise ControlError("task context must be between 256 and 1048576")
        if not 1 <= timeout_seconds <= 86_400:
            raise ControlError("task timeout must be between 1 and 86400 seconds")
        if not 1 <= attempts <= 10:
            raise ControlError("task attempt budget must be between 1 and 10")
        if not 1 <= tool_attempts <= 10:
            raise ControlError("task tool attempt budget must be between 1 and 10")
        if not 1 <= verifier_attempts <= 10:
            raise ControlError("task verifier attempt budget must be between 1 and 10")
        if not 0 <= priority <= 100:
            raise ControlError("task priority must be between 0 and 100")
        if schedule_class not in SCHEDULE_CLASSES:
            raise ControlError("task schedule class must be interactive, critical, verifier, speculative, or compression")
        dependency_ids = list(dict.fromkeys(dependencies or []))
        if any(not TASK_ID_PATTERN.fullmatch(value) for value in dependency_ids):
            raise ControlError("task dependencies must use task-NNNNNN IDs")
        if prompt is not None and len(prompt) > 65_536:
            raise ControlError("task prompt is too large")
        sources = [self._source_record(value) for value in dict.fromkeys(input_paths or [])]
        if sum(int(source["bytes"]) for source in sources) > MAX_SOURCE_TOTAL_BYTES:
            raise ControlError(f"task source inputs exceed {MAX_SOURCE_TOTAL_BYTES} bytes")
        if context is not None:
            available_input_tokens = context - tokens - 128
            if available_input_tokens < 1:
                raise ControlError("task context is too small for the requested output budget")
            estimated_prompt_bytes = (
                768
                + len(goal.encode("utf-8"))
                + len((prompt or goal).encode("utf-8"))
                + sum(int(source["bytes"]) + len(str(source["path"]).encode("utf-8")) + 96 for source in sources)
            )
            if estimated_prompt_bytes > available_input_tokens * 3:
                raise ControlError("task source inputs exceed the selected context policy")
        with _FileLock(self.lock_path):
            self.load_objective()
            graph = self.load_taskgraph()
            missing = [value for value in dependency_ids if value not in graph["tasks"]]
            if missing:
                raise ControlError("task dependencies do not exist: " + ", ".join(missing))
            number = int(graph.get("next_task", 1))
            task_id = f"task-{number:06d}"
            ready = all(graph["tasks"][value].get("status") == "accepted" for value in dependency_ids)
            now = utc_now()
            task = {
                "id": task_id,
                "goal": goal,
                "owner": "leafos:worker-pool",
                "lane": lane,
                "inputs": {"prompt": prompt, "sources": sources},
                "dependencies": dependency_ids,
                "budget": {
                    "tokens": tokens,
                    "context": context,
                    "timeout_seconds": timeout_seconds,
                    "attempts": attempts,
                    "tool_attempts": tool_attempts,
                    "verifier_attempts": verifier_attempts,
                },
                "priority": priority,
                "schedule_class": schedule_class,
                "mutation_policy": "read-only",
                "status": "ready" if ready else "planned",
                "attempt": 0,
                "lease": None,
                "verification_lease": None,
                "cancellation_requested": False,
                "evidence": [],
                "tool_evidence": [],
                "verifier_evidence": [],
                "contradictions": [],
                "decision": None,
                "confidence": "unverified",
                "output": None,
                "last_error": None,
                "created_at": now,
                "updated_at": now,
            }
            graph["tasks"][task_id] = task
            graph["next_task"] = number + 1
            graph["revision"] = int(graph.get("revision", 0)) + 1
            graph["updated_at"] = now
            self._write_document(self.taskgraph_path, graph)
            self._journal("task.submitted", task_id=task_id, lane=lane, status=task["status"])
            return dict(task)

    def evidence_records(self, task_id: str) -> list[dict[str, Any]]:
        task = self.get_task(task_id)
        return [self._read_evidence(evidence_id) for evidence_id in task.get("evidence", [])]

    def record_tool_execution(self, task_id: str, result: dict[str, Any]) -> dict[str, Any]:
        stdout = str(result.get("stdout") or "")
        stderr = str(result.get("stderr") or "")
        exit_code = int(result.get("exit_code", 2))
        tool = str(result.get("tool") or "unknown")
        if tool not in {"artifact", "inspect", "search", "test"}:
            raise ControlError(f"tool is not allowlisted: {tool}")
        with _FileLock(self.lock_path):
            graph = self.load_taskgraph()
            task = graph["tasks"].get(task_id)
            if not isinstance(task, dict):
                raise ControlError(f"task not found: {task_id}")
            if task.get("status") != "verifying":
                raise ControlError(f"tool evidence requires a verifying task: {task_id} ({task.get('status')})")
            existing = task.get("tool_evidence", [])
            if not isinstance(existing, list):
                raise ControlError(f"task has invalid tool evidence state: {task_id}")
            attempt = len(existing) + 1
            maximum = int(task.get("budget", {}).get("tool_attempts", 3))
            if attempt > maximum:
                raise ControlError(f"task tool attempt budget exhausted: {task_id}")
            attempt_directory = self.tasks_dir / task_id / "tools" / f"attempt-{attempt:03d}-{tool}"
            stdout_path = attempt_directory / "stdout.txt"
            stderr_path = attempt_directory / "stderr.txt"
            self._atomic_text(stdout_path, stdout)
            self._atomic_text(stderr_path, stderr)
            artifacts = [
                {
                    "role": "tool-stdout",
                    "path": stdout_path.relative_to(self.project_root).as_posix(),
                    "sha256": hashlib.sha256(stdout.encode("utf-8")).hexdigest(),
                    "bytes": len(stdout.encode("utf-8")),
                },
                {
                    "role": "tool-stderr",
                    "path": stderr_path.relative_to(self.project_root).as_posix(),
                    "sha256": hashlib.sha256(stderr.encode("utf-8")).hexdigest(),
                    "bytes": len(stderr.encode("utf-8")),
                },
            ]
            capture = result.get("capture")
            if capture is not None:
                if not isinstance(capture, dict) or not isinstance(capture.get("data"), bytes):
                    raise ControlError(f"tool capture is invalid: {task_id}")
                data = capture["data"]
                digest = hashlib.sha256(data).hexdigest()
                if capture.get("sha256") != digest or capture.get("bytes") != len(data):
                    raise ControlError(f"tool capture integrity check failed: {task_id}")
                capture_relative = Path(str(capture.get("path") or "artifact.bin"))
                if capture_relative.is_absolute() or ".." in capture_relative.parts:
                    raise ControlError(f"tool capture path is invalid: {task_id}")
                captured_path = (attempt_directory / "artifact" / capture_relative).resolve()
                try:
                    captured_path.relative_to(attempt_directory.resolve())
                except ValueError as error:
                    raise ControlError(f"tool capture path escapes task ownership: {task_id}") from error
                self._atomic_bytes(captured_path, data)
                artifacts.append(
                    {
                        "role": "captured-artifact",
                        "source_path": capture.get("path"),
                        "path": captured_path.relative_to(self.project_root).as_posix(),
                        "sha256": digest,
                        "bytes": len(data),
                    }
                )
            evidence_number = int(graph.get("next_evidence", 1))
            evidence_id = f"evidence-{evidence_number:06d}"
            evidence = {
                "schema": EVIDENCE_SCHEMA,
                "id": evidence_id,
                "task_id": task_id,
                "producer": "leafos:controller",
                "kind": "tool-execution",
                "source": {
                    "tool": tool,
                    "mutation_policy": result.get("mutation_policy", "read-only"),
                },
                "command": result.get("command", {"tool": tool}),
                "attempt": attempt,
                "exit_code": exit_code,
                "artifacts": artifacts,
                "started_at": result.get("started_at"),
                "observed_at": result.get("finished_at") or utc_now(),
                "confidence": "observed" if exit_code == 0 else "unverified",
                "claims": [],
                "next_action": result.get("next_action"),
            }
            self._write_document(self.evidence_dir / f"{evidence_id}.json", evidence)
            now = utc_now()
            task["tool_evidence"] = [*existing, evidence_id]
            task["evidence"] = [*task.get("evidence", []), evidence_id]
            task["updated_at"] = now
            graph["next_evidence"] = evidence_number + 1
            graph["revision"] = int(graph.get("revision", 0)) + 1
            graph["updated_at"] = now
            self._write_document(self.taskgraph_path, graph)
            self._journal(
                "task.tool_recorded",
                task_id=task_id,
                evidence_id=evidence_id,
                tool=tool,
                attempt=attempt,
                exit_code=exit_code,
            )
            return dict(task)

    def record_verification(
        self,
        task_id: str,
        result: dict[str, Any],
        parsed: dict[str, Any],
        *,
        lane: str,
        model: dict[str, Any],
        verifier_token: str | None = None,
    ) -> dict[str, Any]:
        stdout = str(result.get("stdout") or "")
        response = str(result.get("response") if result.get("response") is not None else stdout)
        stderr = str(result.get("stderr") or "")
        exit_code = int(result.get("return_code", 1))
        verdict = str(parsed.get("verdict") or "invalid").casefold()
        confidence = str(parsed.get("confidence") or "unverified").casefold()
        if verdict not in VERIFIER_VERDICTS:
            verdict = "invalid"
        if confidence not in VERIFIER_CONFIDENCE:
            confidence = "unverified"
        claims = parsed.get("claims") if isinstance(parsed.get("claims"), list) else []
        contradictions = parsed.get("contradictions") if isinstance(parsed.get("contradictions"), list) else []
        with _FileLock(self.lock_path):
            graph = self.load_taskgraph()
            task = graph["tasks"].get(task_id)
            if not isinstance(task, dict):
                raise ControlError(f"task not found: {task_id}")
            if task.get("status") != "verifying":
                raise ControlError(f"verification requires a verifying task: {task_id} ({task.get('status')})")
            verification_lease = task.get("verification_lease") if isinstance(task.get("verification_lease"), dict) else {}
            if verifier_token is not None and verification_lease.get("token") != verifier_token:
                raise ControlError(f"task verifier lease token does not match: {task_id}")
            prior_records = [self._read_evidence(value) for value in task.get("evidence", [])]
            worker_model_ids = {
                record.get("source", {}).get("model_id")
                for record in prior_records
                if record.get("kind") == "local-model-inference"
            }
            if model.get("id") in worker_model_ids:
                raise ControlError("verifier model must be independent from the worker model")
            existing = task.get("verifier_evidence", [])
            if not isinstance(existing, list):
                raise ControlError(f"task has invalid verifier evidence state: {task_id}")
            attempt = len(existing) + 1
            maximum = int(task.get("budget", {}).get("verifier_attempts", 2))
            if attempt > maximum:
                raise ControlError(f"task verifier attempt budget exhausted: {task_id}")
            attempt_directory = self.tasks_dir / task_id / "verifiers" / f"attempt-{attempt:03d}"
            output_path = attempt_directory / "verifier-output.txt"
            raw_path = attempt_directory / "verifier-raw-stdout.txt"
            error_path = attempt_directory / "verifier-stderr.txt"
            self._atomic_text(output_path, response)
            self._atomic_text(raw_path, stdout)
            self._atomic_text(error_path, stderr)
            artifacts = []
            for role, path, text in (
                ("verifier-output", output_path, response),
                ("verifier-raw-stdout", raw_path, stdout),
                ("verifier-stderr", error_path, stderr),
            ):
                data = text.encode("utf-8")
                artifacts.append(
                    {
                        "role": role,
                        "path": path.relative_to(self.project_root).as_posix(),
                        "sha256": hashlib.sha256(data).hexdigest(),
                        "bytes": len(data),
                    }
                )
            evidence_number = int(graph.get("next_evidence", 1))
            evidence_id = f"evidence-{evidence_number:06d}"
            evidence = {
                "schema": EVIDENCE_SCHEMA,
                "id": evidence_id,
                "task_id": task_id,
                "producer": "leafos:verifier",
                "kind": "verification",
                "source": {
                    "pack_lane": lane,
                    "model_id": model.get("id"),
                    "model_path": model.get("path"),
                    "architecture": model.get("architecture"),
                    "quant": model.get("quant"),
                    "evidence_ids": list(task.get("evidence", [])),
                },
                "command": {
                    "backend": "llama.cpp",
                    "tokens": parsed.get("tokens"),
                    "context": parsed.get("context"),
                    "timeout_seconds": parsed.get("timeout_seconds"),
                },
                "attempt": attempt,
                "exit_code": exit_code,
                "artifacts": artifacts,
                "started_at": result.get("started_at"),
                "observed_at": result.get("finished_at") or utc_now(),
                "confidence": confidence,
                "verdict": verdict,
                "claims": claims,
                "contradictions": [str(value) for value in contradictions],
                "parse_error": parsed.get("parse_error"),
            }
            self._write_document(self.evidence_dir / f"{evidence_id}.json", evidence)

            prior_verdicts = {
                record.get("verdict")
                for record in prior_records
                if record.get("kind") == "verification" and record.get("verdict") in {"accept", "reject", "conflict"}
            }
            conflict = verdict == "conflict" or (
                verdict in {"accept", "reject"} and bool(prior_verdicts - {verdict})
            )
            current_contradictions = task.get("contradictions", [])
            if not isinstance(current_contradictions, list):
                current_contradictions = []
            if conflict:
                contradiction_id = f"{task_id}-contradiction-{len(current_contradictions) + 1:03d}"
                related = [
                    record["id"]
                    for record in prior_records
                    if record.get("kind") == "verification" and record.get("verdict") != verdict
                ]
                contradiction = {
                    "id": contradiction_id,
                    "task_id": task_id,
                    "evidence_ids": [*related, evidence_id],
                    "reason": "independent verifier verdicts conflict",
                    "observed_at": utc_now(),
                }
                current_contradictions = [*current_contradictions, contradiction]
                self._append_record(
                    self.decisions_path,
                    {"schema": "leafos.decision.v1", "kind": "contradiction", **contradiction},
                )
            now = utc_now()
            task["verifier_evidence"] = [*existing, evidence_id]
            task["evidence"] = [*task.get("evidence", []), evidence_id]
            task["contradictions"] = current_contradictions
            task["confidence"] = (
                "conflicted" if current_contradictions else (
                    "supported" if verdict == "accept" and confidence in {"medium", "high"} else (
                        "rejected" if verdict == "reject" else "unverified"
                    )
                )
            )
            task["verification_lease"] = None
            self._release_verification_ownership(task_id, verification_lease.get("token"))
            task["updated_at"] = now
            graph["next_evidence"] = evidence_number + 1
            graph["revision"] = int(graph.get("revision", 0)) + 1
            graph["updated_at"] = now
            self._write_document(self.taskgraph_path, graph)
            self._journal(
                "task.verification_recorded",
                task_id=task_id,
                evidence_id=evidence_id,
                verdict=verdict,
                confidence=confidence,
            )
            return dict(task)

    def accept_task(self, task_id: str, reason: str) -> dict[str, Any]:
        reason = reason.strip()
        if not reason:
            raise ControlError("acceptance reason cannot be empty")
        with _FileLock(self.lock_path):
            graph = self.load_taskgraph()
            task = graph["tasks"].get(task_id)
            if not isinstance(task, dict):
                raise ControlError(f"task not found: {task_id}")
            if task.get("status") != "verifying":
                raise ControlError(f"task cannot be accepted from status {task.get('status')}: {task_id}")
            if task.get("contradictions"):
                raise ControlError(f"task has unresolved verifier contradictions: {task_id}")
            records = {value: self._read_evidence(value) for value in task.get("evidence", [])}
            verifier_records = [records[value] for value in task.get("verifier_evidence", []) if value in records]
            if any(record.get("verdict") in {"reject", "conflict"} for record in verifier_records):
                raise ControlError(f"task has rejecting or conflicting verifier evidence: {task_id}")
            worker_model_ids = {
                record.get("source", {}).get("model_id")
                for record in records.values()
                if record.get("kind") == "local-model-inference"
            }
            eligible = []
            accepted_claims = []
            for verifier in verifier_records:
                if verifier.get("verdict") != "accept" or verifier.get("confidence") not in {"medium", "high"}:
                    continue
                if verifier.get("source", {}).get("model_id") in worker_model_ids:
                    continue
                claims = verifier.get("claims")
                if not isinstance(claims, list) or not claims:
                    continue
                supported = True
                for claim in claims:
                    evidence_ids = claim.get("evidence_ids") if isinstance(claim, dict) else None
                    if not isinstance(claim, dict) or not str(claim.get("text") or "").strip() or not evidence_ids:
                        supported = False
                        break
                    for evidence_id in evidence_ids:
                        support = records.get(evidence_id)
                        if not support or support.get("exit_code") != 0:
                            supported = False
                            break
                        source_backed = bool(support.get("input_sources"))
                        tool_backed = support.get("kind") == "tool-execution"
                        if not (source_backed or tool_backed):
                            supported = False
                            break
                    if not supported:
                        break
                if supported:
                    eligible.append(verifier)
                    accepted_claims.extend(claims)
            if not eligible:
                raise ControlError("task lacks an independent, evidence-resolved accepting verifier record")
            decisions = self._read_records(self.decisions_path)
            decision_id = f"decision-{len(decisions) + 1:06d}"
            now = utc_now()
            decision = {
                "schema": "leafos.decision.v1",
                "id": decision_id,
                "kind": "acceptance",
                "task_id": task_id,
                "reason": reason,
                "verifier_evidence": [record["id"] for record in eligible],
                "claims": accepted_claims,
                "producer": "leafos:controller",
                "observed_at": now,
            }
            self._append_record(self.decisions_path, decision)
            task["status"] = "accepted"
            task["confidence"] = "verified"
            task["decision"] = decision_id
            task["updated_at"] = now
            graph["revision"] = int(graph.get("revision", 0)) + 1
            graph["updated_at"] = now
            self._write_document(self.taskgraph_path, graph)
            self._journal("task.accepted", task_id=task_id, decision_id=decision_id)
            return dict(task)

    def dispute_task(self, task_id: str, evidence_ids: list[str], reason: str) -> dict[str, Any]:
        reason = reason.strip()
        if not reason:
            raise ControlError("dispute reason cannot be empty")
        requested = list(dict.fromkeys(evidence_ids))
        if not requested:
            raise ControlError("dispute must reference at least one evidence ID")
        with _FileLock(self.lock_path):
            graph = self.load_taskgraph()
            task = graph["tasks"].get(task_id)
            if not isinstance(task, dict):
                raise ControlError(f"task not found: {task_id}")
            if task.get("status") != "verifying":
                raise ControlError(f"task cannot be disputed from status {task.get('status')}: {task_id}")
            available = set(task.get("evidence", []))
            missing = [value for value in requested if value not in available]
            if missing:
                raise ControlError("dispute references evidence outside the task: " + ", ".join(missing))
            current = task.get("contradictions", [])
            if not isinstance(current, list):
                current = []
            contradiction_id = f"{task_id}-contradiction-{len(current) + 1:03d}"
            now = utc_now()
            contradiction = {
                "id": contradiction_id,
                "task_id": task_id,
                "evidence_ids": requested,
                "reason": reason,
                "producer": "leafos:primary-agent",
                "observed_at": now,
            }
            self._append_record(
                self.decisions_path,
                {"schema": "leafos.decision.v1", "kind": "contradiction", **contradiction},
            )
            task["contradictions"] = [*current, contradiction]
            task["confidence"] = "conflicted"
            task["updated_at"] = now
            graph["revision"] = int(graph.get("revision", 0)) + 1
            graph["updated_at"] = now
            self._write_document(self.taskgraph_path, graph)
            self._journal(
                "task.disputed",
                task_id=task_id,
                contradiction_id=contradiction_id,
                evidence_ids=requested,
            )
            return dict(task)

    def _source_record(self, value: str) -> dict[str, Any]:
        if not isinstance(value, str) or not value.strip():
            raise ControlError("task source path cannot be empty")
        candidate = Path(value).expanduser()
        if not candidate.is_absolute():
            candidate = self.project_root / candidate
        resolved = candidate.resolve()
        try:
            relative = resolved.relative_to(self.project_root)
        except ValueError as error:
            raise ControlError(f"task source escapes the project: {value}") from error
        if relative.parts and relative.parts[0].casefold() == ".leaf":
            raise ControlError("task source cannot read LeafOS runtime state")
        if not resolved.is_file():
            raise ControlError(f"task source is missing or not a file: {resolved}")
        size = resolved.stat().st_size
        if size > MAX_SOURCE_BYTES:
            raise ControlError(f"task source exceeds {MAX_SOURCE_BYTES} bytes: {relative.as_posix()}")
        data = resolved.read_bytes()
        if b"\x00" in data:
            raise ControlError(f"task source is not text: {relative.as_posix()}")
        try:
            data.decode("utf-8")
        except UnicodeDecodeError as error:
            raise ControlError(f"task source is not UTF-8 text: {relative.as_posix()}") from error
        return {
            "path": relative.as_posix(),
            "sha256": hashlib.sha256(data).hexdigest(),
            "bytes": len(data),
            "encoding": "utf-8",
        }

    def source_contents(self, task: dict[str, Any]) -> list[dict[str, Any]]:
        values: list[dict[str, Any]] = []
        sources = task.get("inputs", {}).get("sources", [])
        if not isinstance(sources, list):
            raise ControlError(f"task has invalid source inputs: {task.get('id')}")
        for source in sources:
            if not isinstance(source, dict) or not isinstance(source.get("path"), str):
                raise ControlError(f"task has invalid source input: {task.get('id')}")
            current = self._source_record(source["path"])
            if current != source:
                raise ControlError(f"task source changed after submission: {source['path']}")
            path = self.project_root / source["path"]
            data = path.read_bytes()
            values.append({**source, "content": data.decode("utf-8"), "data": data})
        return values

    def _ownership_path(self, task_id: str) -> Path:
        return self.workers_dir / f"{task_id}.owner.json"

    def _verification_ownership_path(self, task_id: str) -> Path:
        return self.workers_dir / f"{task_id}.verifier-owner.json"

    def _release_ownership(self, task_id: str, token: str | None = None) -> None:
        path = self._ownership_path(task_id)
        if token is not None and path.is_file():
            try:
                current = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                current = {}
            if current.get("token") != token:
                return
        try:
            path.unlink()
        except FileNotFoundError:
            pass

    def _release_verification_ownership(self, task_id: str, token: str | None = None) -> None:
        path = self._verification_ownership_path(task_id)
        if token is not None and path.is_file():
            try:
                current = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                current = {}
            if current.get("token") != token:
                return
        try:
            path.unlink()
        except FileNotFoundError:
            pass

    def claim_task(
        self,
        task_id: str,
        *,
        worker_id: str | None = None,
        slot: str | None = None,
        pid: int | None = None,
        lease_seconds: int | None = None,
        token: str | None = None,
    ) -> dict[str, Any]:
        with _FileLock(self.lock_path):
            self._prepare()
            graph = self.load_taskgraph()
            task = graph["tasks"].get(task_id)
            if not isinstance(task, dict):
                raise ControlError(f"task not found: {task_id}")
            if task.get("status") == "planned":
                ready = all(graph["tasks"].get(value, {}).get("status") == "accepted" for value in task["dependencies"])
                if ready:
                    task["status"] = "ready"
            if task.get("status") != "ready":
                raise ControlError(f"task is not ready: {task_id} ({task.get('status')})")
            attempt = int(task.get("attempt", 0)) + 1
            maximum = int(task.get("budget", {}).get("attempts", 1))
            if attempt > maximum:
                task["status"] = "failed"
                task["last_error"] = "task attempt budget exhausted"
                task["updated_at"] = utc_now()
                self._write_document(self.taskgraph_path, graph)
                raise ControlError(f"task attempt budget exhausted: {task_id}")
            now = utc_now()
            lease_token = token or secrets.token_hex(16)
            owner_path = self._ownership_path(task_id)
            owner_payload = {
                "task_id": task_id,
                "worker_id": worker_id or "direct-worker",
                "slot": slot,
                "pid": pid or os.getpid(),
                "token": lease_token,
                "claimed_at": now,
                "host_session_id": _host_session_id(),
            }
            try:
                descriptor = os.open(owner_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            except FileExistsError as error:
                raise ControlError(f"task artifact ownership is already held: {task_id}") from error
            try:
                os.write(descriptor, (json.dumps(owner_payload, sort_keys=True) + "\n").encode("utf-8"))
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            lease = {
                "pid": pid or os.getpid(),
                "worker_id": worker_id or "direct-worker",
                "slot": slot,
                "token": lease_token,
                "claimed_at": now,
                "heartbeat_at": now,
                "host_session_id": _host_session_id(),
            }
            if lease_seconds is not None:
                lease["lease_seconds"] = max(1, int(lease_seconds))
            task.update(
                {
                    "status": "running",
                    "attempt": attempt,
                    "lease": lease,
                    "updated_at": now,
                    "last_error": None,
                }
            )
            graph["revision"] = int(graph.get("revision", 0)) + 1
            graph["updated_at"] = now
            self._write_document(self.taskgraph_path, graph)
            self._journal(
                "task.started", task_id=task_id, attempt=attempt,
                worker_id=lease["worker_id"], slot=slot,
            )
            return dict(task)

    def bind_runtime_process(self, task_id: str, token: str, runtime_pid: int, *, verifier: bool = False) -> dict[str, Any]:
        if not isinstance(runtime_pid, int) or runtime_pid <= 0:
            raise ControlError(f"runtime PID is invalid: {runtime_pid!r}")
        key = "verification_lease" if verifier else "lease"
        required_status = "verifying" if verifier else "running"
        with _FileLock(self.lock_path):
            graph = self.load_taskgraph()
            task = graph["tasks"].get(task_id)
            if not isinstance(task, dict) or task.get("status") != required_status:
                raise ControlError(f"task is not {required_status}: {task_id}")
            lease = task.get(key) if isinstance(task.get(key), dict) else {}
            if lease.get("token") != token:
                raise ControlError(f"task lease token does not match: {task_id}")
            lease["runtime_pid"] = runtime_pid
            lease["runtime_started_at"] = utc_now()
            lease["host_session_id"] = _host_session_id()
            task[key] = lease
            task["updated_at"] = utc_now()
            graph["revision"] = int(graph.get("revision", 0)) + 1
            graph["updated_at"] = task["updated_at"]
            self._write_document(self.taskgraph_path, graph)
            self._journal(
                "task.runtime_bound",
                task_id=task_id,
                worker_id=lease.get("worker_id"),
                runtime_pid=runtime_pid,
                runtime_kind="verifier" if verifier else "worker",
            )
            return dict(task)

    def heartbeat_task(self, task_id: str, token: str) -> dict[str, Any]:
        with _FileLock(self.lock_path):
            graph = self.load_taskgraph()
            task = graph["tasks"].get(task_id)
            if not isinstance(task, dict) or task.get("status") != "running":
                raise ControlError(f"task is not running: {task_id}")
            lease = task.get("lease") if isinstance(task.get("lease"), dict) else {}
            if lease.get("token") != token:
                raise ControlError(f"task lease token does not match: {task_id}")
            now = utc_now()
            lease["heartbeat_at"] = now
            task["lease"] = lease
            task["updated_at"] = now
            graph["revision"] = int(graph.get("revision", 0)) + 1
            graph["updated_at"] = now
            self._write_document(self.taskgraph_path, graph)
            return dict(task)

    def release_task(self, task_id: str, token: str, reason: str, *, retry: bool = True) -> dict[str, Any]:
        with _FileLock(self.lock_path):
            graph = self.load_taskgraph()
            task = graph["tasks"].get(task_id)
            if not isinstance(task, dict) or task.get("status") != "running":
                raise ControlError(f"task is not running: {task_id}")
            lease = task.get("lease") if isinstance(task.get("lease"), dict) else {}
            if lease.get("token") != token:
                raise ControlError(f"task lease token does not match: {task_id}")
            maximum = int(task.get("budget", {}).get("attempts", 1))
            retry_allowed = retry and int(task.get("attempt", 0)) < maximum and not task.get("cancellation_requested")
            task["status"] = "ready" if retry_allowed else ("cancelled" if task.get("cancellation_requested") else "failed")
            task["lease"] = None
            task["last_error"] = reason
            task["updated_at"] = utc_now()
            self._release_ownership(task_id, token)
            graph["revision"] = int(graph.get("revision", 0)) + 1
            graph["updated_at"] = task["updated_at"]
            self._write_document(self.taskgraph_path, graph)
            self._journal("task.lease_released", task_id=task_id, status=task["status"], reason=reason)
            return dict(task)

    def cancel_task(self, task_id: str, reason: str) -> dict[str, Any]:
        reason = reason.strip()
        if not reason:
            raise ControlError("cancellation reason cannot be empty")
        with _FileLock(self.lock_path):
            graph = self.load_taskgraph()
            task = graph["tasks"].get(task_id)
            if not isinstance(task, dict):
                raise ControlError(f"task not found: {task_id}")
            if task.get("status") in TERMINAL_STATUSES:
                return dict(task)
            task["cancellation_requested"] = True
            if task.get("status") != "running":
                task["status"] = "cancelled"
            verification_lease = task.get("verification_lease") if isinstance(task.get("verification_lease"), dict) else {}
            if verification_lease:
                task["verification_lease"] = None
                self._release_verification_ownership(task_id, verification_lease.get("token"))
            task["last_error"] = reason
            task["updated_at"] = utc_now()
            graph["revision"] = int(graph.get("revision", 0)) + 1
            graph["updated_at"] = task["updated_at"]
            self._write_document(self.taskgraph_path, graph)
            self._journal("task.cancellation_requested", task_id=task_id, status=task["status"], reason=reason)
            return dict(task)

    def claim_verification(
        self,
        task_id: str,
        *,
        worker_id: str,
        slot: str,
        pid: int,
        lease_seconds: int = 30,
        token: str | None = None,
    ) -> dict[str, Any]:
        with _FileLock(self.lock_path):
            self._prepare()
            graph = self.load_taskgraph()
            task = graph["tasks"].get(task_id)
            if not isinstance(task, dict) or task.get("status") != "verifying":
                raise ControlError(f"verification requires a verifying task: {task_id}")
            if task.get("verification_lease"):
                raise ControlError(f"task verification is already leased: {task_id}")
            attempts = len(task.get("verifier_evidence", []))
            maximum = int(task.get("budget", {}).get("verifier_attempts", 2))
            if attempts >= maximum:
                raise ControlError(f"task verifier attempt budget exhausted: {task_id}")
            lease_token = token or secrets.token_hex(16)
            now = utc_now()
            payload = {
                "task_id": task_id, "worker_id": worker_id, "slot": slot,
                "pid": pid, "token": lease_token, "claimed_at": now,
                "host_session_id": _host_session_id(),
            }
            path = self._verification_ownership_path(task_id)
            try:
                descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            except FileExistsError as error:
                raise ControlError(f"task verifier ownership is already held: {task_id}") from error
            try:
                os.write(descriptor, (json.dumps(payload, sort_keys=True) + "\n").encode("utf-8"))
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            task["verification_lease"] = {
                **payload, "heartbeat_at": now, "lease_seconds": max(1, int(lease_seconds)),
            }
            task["updated_at"] = now
            graph["revision"] = int(graph.get("revision", 0)) + 1
            graph["updated_at"] = now
            self._write_document(self.taskgraph_path, graph)
            self._journal("task.verification_started", task_id=task_id, worker_id=worker_id, slot=slot)
            return dict(task)

    def heartbeat_verification(self, task_id: str, token: str) -> dict[str, Any]:
        with _FileLock(self.lock_path):
            graph = self.load_taskgraph()
            task = graph["tasks"].get(task_id)
            if not isinstance(task, dict) or task.get("status") != "verifying":
                raise ControlError(f"task is not verifying: {task_id}")
            lease = task.get("verification_lease") if isinstance(task.get("verification_lease"), dict) else {}
            if lease.get("token") != token:
                raise ControlError(f"task verifier lease token does not match: {task_id}")
            now = utc_now()
            lease["heartbeat_at"] = now
            task["verification_lease"] = lease
            task["updated_at"] = now
            graph["revision"] = int(graph.get("revision", 0)) + 1
            graph["updated_at"] = now
            self._write_document(self.taskgraph_path, graph)
            return dict(task)

    def release_verification(self, task_id: str, token: str, reason: str) -> dict[str, Any]:
        with _FileLock(self.lock_path):
            graph = self.load_taskgraph()
            task = graph["tasks"].get(task_id)
            if not isinstance(task, dict) or task.get("status") != "verifying":
                raise ControlError(f"task is not verifying: {task_id}")
            lease = task.get("verification_lease") if isinstance(task.get("verification_lease"), dict) else {}
            if lease.get("token") != token:
                raise ControlError(f"task verifier lease token does not match: {task_id}")
            task["verification_lease"] = None
            task["last_error"] = reason
            task["updated_at"] = utc_now()
            self._release_verification_ownership(task_id, token)
            graph["revision"] = int(graph.get("revision", 0)) + 1
            graph["updated_at"] = task["updated_at"]
            self._write_document(self.taskgraph_path, graph)
            self._journal("task.verifier_lease_released", task_id=task_id, reason=reason)
            return dict(task)

    def finalize_execution(
        self,
        task_id: str,
        result: dict[str, Any],
        *,
        lane: str,
        model: dict[str, Any],
        input_sources: list[dict[str, Any]] | None = None,
        lease_token: str | None = None,
    ) -> dict[str, Any]:
        stdout = str(result.get("stdout") or "")
        response = str(result.get("response") if result.get("response") is not None else stdout)
        stderr = str(result.get("stderr") or "")
        return_code = int(result.get("return_code", 1))
        with _FileLock(self.lock_path):
            graph = self.load_taskgraph()
            task = graph["tasks"].get(task_id)
            if not isinstance(task, dict):
                raise ControlError(f"task not found: {task_id}")
            if task.get("status") != "running":
                raise ControlError(f"task result cannot be recorded from status {task.get('status')}: {task_id}")
            lease = task.get("lease") if isinstance(task.get("lease"), dict) else {}
            if lease_token is not None and lease.get("token") != lease_token:
                raise ControlError(f"task lease token does not match: {task_id}")
            if task.get("cancellation_requested"):
                self._release_ownership(task_id, lease.get("token"))
                task.update({"status": "cancelled", "lease": None, "updated_at": utc_now()})
                graph["revision"] = int(graph.get("revision", 0)) + 1
                graph["updated_at"] = task["updated_at"]
                self._write_document(self.taskgraph_path, graph)
                self._journal("task.cancelled", task_id=task_id)
                return dict(task)
            task_directory = self.tasks_dir / task_id
            output_path = task_directory / "worker-output.txt"
            raw_output_path = task_directory / "worker-raw-stdout.txt"
            error_path = task_directory / "worker-stderr.txt"
            self._atomic_text(output_path, response)
            self._atomic_text(raw_output_path, stdout)
            self._atomic_text(error_path, stderr)
            output_hash = hashlib.sha256(response.encode("utf-8")).hexdigest()
            raw_output_hash = hashlib.sha256(stdout.encode("utf-8")).hexdigest()
            error_hash = hashlib.sha256(stderr.encode("utf-8")).hexdigest()
            expected_sources = task.get("inputs", {}).get("sources", [])
            provided_sources = input_sources or []
            if len(expected_sources) != len(provided_sources):
                raise ControlError(f"task source snapshots are incomplete: {task_id}")
            evidence_sources = []
            source_artifacts = []
            for expected, source in zip(expected_sources, provided_sources, strict=True):
                metadata = {key: source.get(key) for key in ("path", "sha256", "bytes", "encoding")}
                if metadata != expected or not isinstance(source.get("data"), bytes):
                    raise ControlError(f"task source snapshot does not match submission: {task_id}")
                data = source["data"]
                if hashlib.sha256(data).hexdigest() != source["sha256"] or len(data) != source["bytes"]:
                    raise ControlError(f"task source snapshot integrity check failed: {source['path']}")
                snapshot_path = task_directory / "inputs" / Path(source["path"])
                self._atomic_bytes(snapshot_path, data)
                snapshot_relative = snapshot_path.relative_to(self.project_root).as_posix()
                evidence_sources.append({**metadata, "snapshot": snapshot_relative})
                source_artifacts.append(
                    {
                        "role": "input-source",
                        "path": snapshot_relative,
                        "sha256": source["sha256"],
                        "bytes": source["bytes"],
                    }
                )
            evidence_number = int(graph.get("next_evidence", 1))
            evidence_id = f"evidence-{evidence_number:06d}"
            evidence = {
                "schema": EVIDENCE_SCHEMA,
                "id": evidence_id,
                "task_id": task_id,
                "producer": "leafos:worker-pool",
                "kind": "local-model-inference",
                "source": {
                    "pack_lane": lane,
                    "model_id": model.get("id"),
                    "model_path": model.get("path"),
                    "architecture": model.get("architecture"),
                    "quant": model.get("quant"),
                },
                "input_sources": evidence_sources,
                "command": {
                    "backend": "llama.cpp",
                    "tokens": task["budget"]["tokens"],
                    "context": task["budget"]["context"],
                    "timeout_seconds": task["budget"]["timeout_seconds"],
                },
                "exit_code": return_code,
                "artifacts": [
                    {
                        "path": output_path.relative_to(self.project_root).as_posix(),
                        "sha256": output_hash,
                        "bytes": len(response.encode("utf-8")),
                    },
                    {
                        "path": raw_output_path.relative_to(self.project_root).as_posix(),
                        "sha256": raw_output_hash,
                        "bytes": len(stdout.encode("utf-8")),
                    },
                    {
                        "path": error_path.relative_to(self.project_root).as_posix(),
                        "sha256": error_hash,
                        "bytes": len(stderr.encode("utf-8")),
                    },
                    *source_artifacts,
                ],
                "started_at": result.get("started_at"),
                "observed_at": result.get("finished_at") or utc_now(),
                "confidence": "unverified",
                "claims": [],
            }
            evidence_path = self.evidence_dir / f"{evidence_id}.json"
            evidence = self._write_document(evidence_path, evidence)
            success = return_code == 0 and bool(response.strip())
            now = utc_now()
            task.update(
                {
                    "status": "verifying" if success else "failed",
                    "lease": None,
                    "evidence": [*task.get("evidence", []), evidence_id],
                    "confidence": "unverified",
                    "output": {
                        "path": output_path.relative_to(self.project_root).as_posix(),
                        "sha256": output_hash,
                        "bytes": len(response.encode("utf-8")),
                    },
                    "last_error": None if success else (
                        f"llama.cpp exited with code {return_code}" if return_code else "worker produced no output"
                    ),
                    "updated_at": now,
                }
            )
            self._release_ownership(task_id, lease.get("token"))
            graph["next_evidence"] = evidence_number + 1
            graph["revision"] = int(graph.get("revision", 0)) + 1
            graph["updated_at"] = now
            self._write_document(self.taskgraph_path, graph)
            self._journal(
                "task.result_recorded",
                task_id=task_id,
                evidence_id=evidence_id,
                status=task["status"],
                exit_code=return_code,
            )
            return dict(task)

    def get_task(self, task_id: str) -> dict[str, Any]:
        self.recover()
        graph = self.load_taskgraph()
        task = graph["tasks"].get(task_id)
        if not isinstance(task, dict):
            raise ControlError(f"task not found: {task_id}")
        return dict(task)

    def summary(self) -> dict[str, Any]:
        self.recover()
        objective = self.load_objective()
        graph = self.load_taskgraph()
        counts: dict[str, int] = {}
        for task in graph["tasks"].values():
            status = str(task.get("status", "unknown"))
            counts[status] = counts.get(status, 0) + 1
        return {
            "project": objective["project"],
            "objective": objective["text"],
            "phase": objective["phase"],
            "mode": objective["mode"],
            "tasks": counts,
            "task_total": len(graph["tasks"]),
            "objective_revision": objective["revision"],
            "taskgraph_revision": graph["revision"],
        }

    def _read_evidence(self, evidence_id: str) -> dict[str, Any]:
        evidence = self._read_document(self.evidence_dir / f"{evidence_id}.json", EVIDENCE_SCHEMA)
        for artifact in evidence.get("artifacts", []):
            if not isinstance(artifact, dict) or not isinstance(artifact.get("path"), str):
                raise ControlError(f"evidence has an invalid artifact reference: {evidence_id}")
            artifact_path = (self.project_root / artifact["path"]).resolve()
            try:
                artifact_path.relative_to(self.project_root)
            except ValueError as error:
                raise ControlError(f"evidence artifact escapes the project: {artifact['path']}") from error
            if not artifact_path.is_file():
                raise ControlError(f"evidence artifact is missing: {artifact_path}")
            digest = hashlib.sha256()
            size = 0
            with artifact_path.open("rb") as stream:
                while chunk := stream.read(1024 * 1024):
                    digest.update(chunk)
                    size += len(chunk)
            if artifact.get("sha256") != digest.hexdigest() or artifact.get("bytes") != size:
                raise ControlError(f"evidence artifact integrity check failed: {artifact_path}")
        return evidence

    def audit(self) -> dict[str, int]:
        self.recover()
        self.load_objective()
        graph = self.load_taskgraph()
        evidence_ids = sorted({value for task in graph["tasks"].values() for value in task.get("evidence", [])})
        for evidence_id in evidence_ids:
            self._read_evidence(evidence_id)
        journal = self._read_records(self.journal_path)
        decisions = self._read_records(self.decisions_path)
        decisions_by_id = {record.get("id"): record for record in decisions if record.get("id")}
        for task_id, task in graph["tasks"].items():
            if task.get("status") != "accepted":
                continue
            decision = decisions_by_id.get(task.get("decision"))
            if not decision or decision.get("kind") != "acceptance" or decision.get("task_id") != task_id:
                raise ControlError(f"accepted task lacks a valid acceptance decision: {task_id}")
        return {
            "tasks": len(graph["tasks"]),
            "evidence": len(evidence_ids),
            "journal_records": len(journal),
            "decisions": len(decisions),
        }

    def _read_records(self, path: Path) -> list[dict[str, Any]]:
        if not path.is_file():
            return []
        records: list[dict[str, Any]] = []
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as error:
                raise ControlError(f"malformed append-only state: {path}:{number}: {error}") from error
            if not isinstance(value, dict) or _seal(value).get("integrity") != value.get("integrity"):
                raise ControlError(f"append-only state integrity check failed: {path}:{number}")
            records.append(value)
        return records

    def export_context(self) -> dict[str, Any]:
        self.recover()
        objective = self.load_objective()
        graph = self.load_taskgraph()
        tasks = list(graph["tasks"].values())
        evidence_ids = [value for task in tasks for value in task.get("evidence", [])]
        evidence = []
        for evidence_id in evidence_ids:
            record = self._read_evidence(evidence_id)
            evidence.append(
                {
                    "id": record["id"],
                    "task_id": record["task_id"],
                    "kind": record["kind"],
                    "model_id": record["source"].get("model_id"),
                    "exit_code": record["exit_code"],
                    "input_sources": record.get("input_sources", []),
                    "artifacts": record["artifacts"],
                    "confidence": record["confidence"],
                    "tool": record.get("source", {}).get("tool"),
                    "verdict": record.get("verdict"),
                    "claims": record.get("claims", []),
                    "contradictions": record.get("contradictions", []),
                    "next_action": record.get("next_action"),
                }
            )
        counts: dict[str, int] = {}
        for task in tasks:
            status = str(task.get("status", "unknown"))
            counts[status] = counts.get(status, 0) + 1
        active = [
            {
                "id": task["id"],
                "goal": task["goal"],
                "status": task["status"],
                "lane": task["lane"],
                "attempt": task["attempt"],
                "dependencies": task["dependencies"],
                "evidence": task["evidence"],
                "output": task["output"],
                "inputs": task.get("inputs", {}).get("sources", []),
                "tool_evidence": task.get("tool_evidence", []),
                "verifier_evidence": task.get("verifier_evidence", []),
                "contradictions": task.get("contradictions", []),
                "confidence": task.get("confidence", "unverified"),
                "decision": task.get("decision"),
            }
            for task in tasks
            if task.get("status") not in TERMINAL_STATUSES
        ]
        failures = [
            {"id": task["id"], "goal": task["goal"], "error": task.get("last_error"), "evidence": task["evidence"]}
            for task in tasks
            if task.get("status") == "failed"
        ]
        failures.extend(
            {
                "id": record["id"],
                "task_id": record["task_id"],
                "error": "bounded tool execution failed",
                "exit_code": record["exit_code"],
                "next_action": record.get("next_action"),
                "artifacts": record["artifacts"],
            }
            for record in evidence
            if record.get("kind") == "tool-execution" and record.get("exit_code") != 0
        )
        unknowns = []
        if any(task.get("status") == "verifying" for task in tasks):
            unknowns.append("Worker output is unaccepted until independent verification or a primary-agent decision.")
        if any(task.get("status") == "planned" for task in tasks):
            unknowns.append("Planned tasks are waiting for accepted dependencies.")
        if any(task.get("contradictions") for task in tasks):
            unknowns.append("Conflicting verifier records block controller acceptance until explicitly resolved.")
        if not tasks:
            next_actions = ["Submit one bounded task with leafctl task submit."]
        elif any(task.get("contradictions") for task in tasks):
            next_actions = ["Inspect conflicting verifier evidence; do not accept the task while contradictions remain."]
        elif any(task.get("status") == "verifying" for task in tasks):
            next_actions = ["Attach bounded tool evidence, run an independent verifier, then apply the controller acceptance gate."]
        elif failures:
            next_actions = ["Inspect failed task evidence before retrying or revising the plan."]
        else:
            next_actions = ["Inspect the active task graph and choose the next evidence-producing action."]
        decisions = [
            {key: value for key, value in record.items() if key != "integrity"}
            for record in self._read_records(self.decisions_path)
        ]
        return {
            "schema": "leafos.context-packet.v1",
            "generated_at": utc_now(),
            "objective": objective["text"],
            "project": objective["project"],
            "current_state": {"phase": objective["phase"], "mode": objective["mode"], "tasks": counts},
            "last_decisions": decisions[-10:],
            "active_tasks": active,
            "new_evidence": evidence,
            "unresolved_failures": failures,
            "unknown_or_conflicting": unknowns,
            "next_recommended_actions": next_actions,
            "provenance": {
                "objective_integrity": objective["integrity"],
                "taskgraph_integrity": graph["integrity"],
                "project_state": str(self.leaf_dir),
            },
        }
