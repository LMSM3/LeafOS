from __future__ import annotations

import ctypes
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from core.config import Settings
from core.control.store import (
    ControlError,
    ProjectStore,
    _FileLock,
    _host_session_id,
    _lease_process_alive,
    _pid_alive,
    _terminate_process_tree,
)
from core.models.inventory import load_inventory
from core.routing.packs import PackError, find_pack, route_lane
from core.state import read_json, utc_now


SCHEDULER_SCHEMA = "leafos.scheduler.v1"
SCHEDULE_ORDER = {
    "interactive": 0,
    "critical": 1,
    "verifier": 2,
    "speculative": 3,
    "compression": 4,
}
BACKGROUND_CLASSES = {"speculative", "compression"}
DEFAULT_WORKER_SLOTS = 2
MAX_WORKER_SLOTS = 4
DEFAULT_LEASE_SECONDS = 30


class _MemoryStatus(ctypes.Structure):
    _fields_ = [
        ("length", ctypes.c_ulong),
        ("memory_load", ctypes.c_ulong),
        ("total_physical", ctypes.c_ulonglong),
        ("available_physical", ctypes.c_ulonglong),
        ("total_page_file", ctypes.c_ulonglong),
        ("available_page_file", ctypes.c_ulonglong),
        ("total_virtual", ctypes.c_ulonglong),
        ("available_virtual", ctypes.c_ulonglong),
        ("available_extended_virtual", ctypes.c_ulonglong),
    ]


def _windows_memory() -> tuple[float | None, float | None, float | None]:
    if os.name != "nt":
        return None, None, None
    value = _MemoryStatus()
    value.length = ctypes.sizeof(value)
    try:
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(value)):
            return None, None, None
    except (AttributeError, OSError):
        return None, None, None
    total = value.total_physical / 1024**3
    used = (value.total_physical - value.available_physical) / 1024**3
    return round(used, 3), round(total, 3), round(float(value.memory_load), 2)


def _unix_memory() -> tuple[float | None, float | None, float | None]:
    path = Path("/proc/meminfo")
    if not path.is_file():
        return None, None, None
    try:
        values = {}
        for line in path.read_text(encoding="utf-8").splitlines():
            key, raw = line.split(":", 1)
            values[key] = float(raw.strip().split()[0]) * 1024
        total = values["MemTotal"] / 1024**3
        available = values.get("MemAvailable", values.get("MemFree", 0.0)) / 1024**3
    except (OSError, KeyError, ValueError):
        return None, None, None
    used = total - available
    return round(used, 3), round(total, 3), round(used * 100.0 / total, 2) if total else None


def _cpu_percent() -> float | str:
    if os.name != "nt":
        try:
            return round(min(100.0, os.getloadavg()[0] * 100.0 / max(1, os.cpu_count() or 1)), 2)
        except (AttributeError, OSError):
            return "unavailable"
    idle_a = ctypes.c_ulonglong()
    kernel_a = ctypes.c_ulonglong()
    user_a = ctypes.c_ulonglong()
    idle_b = ctypes.c_ulonglong()
    kernel_b = ctypes.c_ulonglong()
    user_b = ctypes.c_ulonglong()
    try:
        get_times = ctypes.windll.kernel32.GetSystemTimes
        if not get_times(ctypes.byref(idle_a), ctypes.byref(kernel_a), ctypes.byref(user_a)):
            return "unavailable"
        time.sleep(0.05)
        if not get_times(ctypes.byref(idle_b), ctypes.byref(kernel_b), ctypes.byref(user_b)):
            return "unavailable"
    except (AttributeError, OSError):
        return "unavailable"
    idle = idle_b.value - idle_a.value
    total = (kernel_b.value - kernel_a.value) + (user_b.value - user_a.value)
    return round((total - idle) * 100.0 / total, 2) if total > 0 else "unavailable"


def _nvidia_metrics() -> dict[str, float | str]:
    empty: dict[str, float | str] = {
        "gpu_percent": "unavailable",
        "vram_used_gb": "unavailable",
        "vram_total_gb": "unavailable",
        "vram_percent": "unavailable",
        "thermal_c": "unavailable",
    }
    executable = shutil.which("nvidia-smi") or shutil.which("nvidia-smi.exe")
    if not executable:
        return empty
    try:
        result = subprocess.run(
            [
                executable,
                "--query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
        first = result.stdout.strip().splitlines()[0]
        gpu, used_mb, total_mb, thermal = [float(value.strip()) for value in first.split(",")]
        total_gb = total_mb / 1024.0
        used_gb = used_mb / 1024.0
        return {
            "gpu_percent": round(gpu, 2),
            "vram_used_gb": round(used_gb, 3),
            "vram_total_gb": round(total_gb, 3),
            "vram_percent": round(used_gb * 100.0 / total_gb, 2) if total_gb else "unavailable",
            "thermal_c": round(thermal, 2),
        }
    except (OSError, subprocess.TimeoutExpired, IndexError, ValueError):
        return empty


def observe_resources(project_root: Path, queue: dict[str, int]) -> dict[str, Any]:
    used, total, percent = _windows_memory() if os.name == "nt" else _unix_memory()
    disk = shutil.disk_usage(project_root)
    gpu = _nvidia_metrics()
    return {
        "observed_at": utc_now(),
        "cpu_percent": _cpu_percent(),
        "ram_used_gb": used if used is not None else "unavailable",
        "ram_total_gb": total if total is not None else "unavailable",
        "ram_percent": percent if percent is not None else "unavailable",
        **gpu,
        "queue": queue,
        "disk_free_gb": round(disk.free / 1024**3, 3),
        "disk_total_gb": round(disk.total / 1024**3, 3),
        "disk_throughput_mb_s": "unavailable",
        "kv_cache_gb": "unavailable",
        "sensor_policy": "observed values only; unavailable means no compatible host probe",
    }


class Scheduler:
    def __init__(self, settings: Settings, project_root: Path) -> None:
        self.settings = settings
        self.store = ProjectStore(project_root)
        self.children: dict[str, dict[str, Any]] = {}

    def initialize(self, worker_slots: int = DEFAULT_WORKER_SLOTS, lease_seconds: int = DEFAULT_LEASE_SECONDS) -> dict[str, Any]:
        if not 2 <= worker_slots <= MAX_WORKER_SLOTS:
            raise ControlError("worker slots must be between 2 and 4")
        if not 5 <= lease_seconds <= 300:
            raise ControlError("lease seconds must be between 5 and 300")
        self.store._prepare()
        if self.store.scheduler_path.is_file():
            state = self.store._read_document(self.store.scheduler_path, SCHEDULER_SCHEMA)
            if state.get("project_id") != self.store.project_identity["id"]:
                raise ControlError("scheduler state belongs to a different project")
            policy = state.get("policy", {})
            if policy.get("worker_slots") == worker_slots and policy.get("lease_seconds") == lease_seconds:
                return state
            state["policy"] = {
                "worker_slots": worker_slots,
                "verifier_slots": 1,
                "lease_seconds": lease_seconds,
                "priority": list(SCHEDULE_ORDER),
            }
            state["revision"] = int(state.get("revision", 0)) + 1
            state["updated_at"] = utc_now()
            return self.store._write_document(self.store.scheduler_path, state)
        now = utc_now()
        state = {
            "schema": SCHEDULER_SCHEMA,
            "revision": 1,
            "project_id": self.store.project_identity["id"],
            "status": "stopped",
            "supervisor": {"pid": None, "heartbeat_at": None, "host_session_id": _host_session_id()},
            "policy": {
                "worker_slots": worker_slots,
                "verifier_slots": 1,
                "lease_seconds": lease_seconds,
                "priority": list(SCHEDULE_ORDER),
            },
            "foreground": {"active": False, "changed_at": now},
            "workers": {},
            "resources": {},
            "queue": {},
            "degraded_reasons": [],
            "created_at": now,
            "updated_at": now,
        }
        return self.store._write_document(self.store.scheduler_path, state)

    def _load(self) -> dict[str, Any]:
        if not self.store.scheduler_path.is_file():
            return self.initialize()
        return self.store._read_document(self.store.scheduler_path, SCHEDULER_SCHEMA)

    def _save(self, state: dict[str, Any]) -> dict[str, Any]:
        state["revision"] = int(state.get("revision", 0)) + 1
        state["updated_at"] = utc_now()
        return self.store._write_document(self.store.scheduler_path, state)

    def set_foreground(self, active: bool) -> dict[str, Any]:
        state = self._load()
        state["foreground"] = {"active": bool(active), "changed_at": utc_now()}
        return self._save(state)

    def _graph_facts(self) -> tuple[dict[str, Any], dict[str, int]]:
        self.store.recover()
        graph = self.store.load_taskgraph()
        counts: dict[str, int] = {}
        for task in graph["tasks"].values():
            status = str(task.get("status", "unknown"))
            counts[status] = counts.get(status, 0) + 1
        return graph, counts

    def _role_status(self) -> tuple[dict[str, Any], list[str]]:
        inventory = load_inventory(self.settings.inventory_path)
        runtime_state = read_json(self.settings.state_path, {})
        active_pack = runtime_state.get("active_pack")
        if not isinstance(active_pack, str) or not active_pack:
            return {}, ["active pack unavailable"]
        try:
            _, pack = find_pack(self.settings.packs_dir, active_pack)
        except PackError as error:
            return {}, [str(error)]
        roles: dict[str, Any] = {}
        degraded: list[str] = []
        fallbacks = {
            "interactive": ("fast", "general"),
            "critical": ("reasoning", "general", "fast"),
            "verifier": ("verifier",),
            "speculative": ("fast", "general"),
            "compression": ("writer", "general", "fast"),
        }
        default_lane = str(pack.get("default_lane") or next(iter(pack["lanes"])))
        for role, candidates in fallbacks.items():
            chosen = next((lane for lane in candidates if lane in pack["lanes"]), None)
            if chosen is None and role != "verifier":
                chosen = default_lane if default_lane in pack["lanes"] else None
            if chosen is None:
                roles[role] = {"status": "unavailable", "lane": None, "model": None}
                degraded.append(f"optional {role} role unavailable")
                continue
            try:
                model = route_lane(pack, chosen, inventory)
            except PackError as error:
                roles[role] = {"status": "unavailable", "lane": chosen, "model": None}
                degraded.append(f"{role} role unavailable: {error}")
                continue
            status = "native" if chosen == candidates[0] else "fallback"
            roles[role] = {"status": status, "lane": chosen, "model": model.get("id")}
            if status == "fallback":
                degraded.append(f"{role} role falls back to {chosen}")
        return roles, degraded

    def status(self) -> dict[str, Any]:
        state = self._load()
        graph, queue = self._graph_facts()
        resources = observe_resources(self.store.project_root, queue)
        roles, degraded = self._role_status()
        active = {}
        for task in graph["tasks"].values():
            lease = task.get("lease") if isinstance(task.get("lease"), dict) else {}
            verifier = task.get("verification_lease") if isinstance(task.get("verification_lease"), dict) else {}
            if lease:
                active[str(lease.get("slot") or lease.get("worker_id"))] = {
                    "kind": "worker", "task_id": task["id"], "pid": lease.get("pid"),
                    "heartbeat_at": lease.get("heartbeat_at"), "alive": _lease_process_alive(lease),
                    "runtime_pid": lease.get("runtime_pid"),
                }
            if verifier:
                active[str(verifier.get("slot") or verifier.get("worker_id"))] = {
                    "kind": "verifier", "task_id": task["id"], "pid": verifier.get("pid"),
                    "heartbeat_at": verifier.get("heartbeat_at"), "alive": _lease_process_alive(verifier),
                    "runtime_pid": verifier.get("runtime_pid"),
                }
        state["resources"] = resources
        state["queue"] = queue
        state["workers"] = active
        state["roles"] = roles
        state["degraded_reasons"] = degraded
        return self._save(state)

    @staticmethod
    def _ready_tasks(graph: dict[str, Any], foreground: bool) -> list[dict[str, Any]]:
        tasks = graph["tasks"]
        ready = []
        for task in tasks.values():
            if task.get("status") not in {"ready", "planned"}:
                continue
            dependencies = task.get("dependencies", [])
            if not all(tasks.get(value, {}).get("status") == "accepted" for value in dependencies):
                continue
            schedule_class = str(task.get("schedule_class") or "critical")
            if foreground and schedule_class != "interactive":
                continue
            ready.append(task)
        return sorted(
            ready,
            key=lambda task: (
                SCHEDULE_ORDER.get(str(task.get("schedule_class") or "critical"), 99),
                -int(task.get("priority", 50)),
                str(task.get("created_at", "")),
                str(task.get("id", "")),
            ),
        )

    @staticmethod
    def _verification_tasks(graph: dict[str, Any]) -> list[dict[str, Any]]:
        values = []
        for task in graph["tasks"].values():
            if task.get("status") != "verifying" or task.get("verification_lease"):
                continue
            records = task.get("verifier_evidence", [])
            if records and task.get("confidence") != "unverified":
                continue
            if len(records) >= int(task.get("budget", {}).get("verifier_attempts", 2)):
                continue
            values.append(task)
        return sorted(values, key=lambda task: (-int(task.get("priority", 50)), str(task.get("created_at", ""))))

    @staticmethod
    def _pressure(resources: dict[str, Any]) -> str | None:
        ram = resources.get("ram_percent")
        vram = resources.get("vram_percent")
        thermal = resources.get("thermal_c")
        if isinstance(ram, (int, float)) and ram >= 92:
            return "RAM pressure"
        if isinstance(vram, (int, float)) and vram >= 95:
            return "VRAM pressure"
        if isinstance(thermal, (int, float)) and thermal >= 88:
            return "GPU thermal pressure"
        return None

    def _spawn(self, task: dict[str, Any], slot: str, kind: str, lease_seconds: int) -> None:
        token = os.urandom(16).hex()
        command = [
            sys.executable, "-m", "core.control.worker",
            "--project", str(self.store.project_root),
            "--task", str(task["id"]),
            "--token", token,
            "--worker-id", f"{kind}:{slot}",
            "--kind", kind,
        ]
        log_path = self.store.workers_dir / f"{slot}.log"
        creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        with log_path.open("a", encoding="utf-8") as log:
            process = subprocess.Popen(
                command,
                cwd=self.settings.root,
                stdout=log,
                stderr=subprocess.STDOUT,
                creationflags=creationflags,
            )
        try:
            if kind == "worker":
                claimed = self.store.claim_task(
                    str(task["id"]), worker_id=f"worker:{slot}", slot=slot,
                    pid=process.pid, lease_seconds=lease_seconds, token=token,
                )
            else:
                claimed = self.store.claim_verification(
                    str(task["id"]), worker_id=f"verifier:{slot}", slot=slot,
                    pid=process.pid, lease_seconds=lease_seconds, token=token,
                )
        except Exception:
            process.terminate()
            raise
        self.children[slot] = {
            "process": process,
            "task_id": task["id"],
            "token": token,
            "kind": kind,
            "schedule_class": claimed.get("schedule_class", "verifier"),
        }

    def _poll_children(self) -> None:
        for slot, child in list(self.children.items()):
            process: subprocess.Popen[Any] = child["process"]
            code = process.poll()
            if code is None:
                continue
            task = self.store.get_task(child["task_id"])
            if child["kind"] == "worker" and task.get("status") == "running":
                lease = task.get("lease") if isinstance(task.get("lease"), dict) else {}
                if lease.get("token") == child["token"]:
                    if _lease_process_alive(lease, "runtime_pid"):
                        _terminate_process_tree(lease.get("runtime_pid"))
                    self.store.release_task(child["task_id"], child["token"], f"worker exited with code {code}")
            elif child["kind"] == "verifier" and task.get("status") == "verifying":
                lease = task.get("verification_lease") if isinstance(task.get("verification_lease"), dict) else {}
                if lease.get("token") == child["token"]:
                    if _lease_process_alive(lease, "runtime_pid"):
                        _terminate_process_tree(lease.get("runtime_pid"))
                    self.store.release_verification(child["task_id"], child["token"], f"verifier exited with code {code}")
            self.children.pop(slot, None)

    def _preempt_background(self) -> list[str]:
        preempted = []
        for slot, child in list(self.children.items()):
            if child.get("kind") != "worker" or child.get("schedule_class") not in BACKGROUND_CLASSES:
                continue
            process: subprocess.Popen[Any] = child["process"]
            if process.poll() is None:
                process.terminate()
            task = self.store.get_task(child["task_id"])
            lease = task.get("lease") if isinstance(task.get("lease"), dict) else {}
            if task.get("status") == "running" and lease.get("token") == child["token"]:
                if _lease_process_alive(lease, "runtime_pid"):
                    _terminate_process_tree(lease.get("runtime_pid"))
                self.store.release_task(child["task_id"], child["token"], "preempted for foreground inference")
            preempted.append(child["task_id"])
            self.children.pop(slot, None)
        return preempted

    def tick(self) -> dict[str, Any]:
        state = self._load()
        self._poll_children()
        graph, queue = self._graph_facts()
        resources = observe_resources(self.store.project_root, queue)
        foreground = bool(state.get("foreground", {}).get("active"))
        preempted = self._preempt_background() if foreground else []
        pressure = self._pressure(resources)
        policy = state["policy"]
        active_slots = {
            str(task.get("lease", {}).get("slot"))
            for task in graph["tasks"].values()
            if isinstance(task.get("lease"), dict) and task.get("lease", {}).get("slot")
        }
        started = []
        if pressure is None:
            candidates = self._ready_tasks(graph, foreground)
            for index in range(1, int(policy["worker_slots"]) + 1):
                slot = f"worker-{index}"
                if slot in active_slots or slot in self.children or not candidates:
                    continue
                task = candidates.pop(0)
                self._spawn(task, slot, "worker", int(policy["lease_seconds"]))
                started.append(task["id"])
            graph = self.store.load_taskgraph()
            verifier_active = any(
                isinstance(task.get("verification_lease"), dict) and task.get("verification_lease")
                for task in graph["tasks"].values()
            )
            roles, degraded = self._role_status()
            if not foreground and not verifier_active and "verifier-1" not in self.children and roles.get("verifier", {}).get("status") != "unavailable":
                verifier_candidates = self._verification_tasks(graph)
                if verifier_candidates:
                    self._spawn(verifier_candidates[0], "verifier-1", "verifier", int(policy["lease_seconds"]))
                    started.append(f"verify:{verifier_candidates[0]['id']}")
        else:
            roles, degraded = self._role_status()
            degraded = [*degraded, pressure]
        graph, queue = self._graph_facts()
        state.update(
            {
                "status": "running",
                "supervisor": {"pid": os.getpid(), "heartbeat_at": utc_now(), "host_session_id": _host_session_id()},
                "resources": resources,
                "queue": queue,
                "roles": roles,
                "degraded_reasons": degraded,
            }
        )
        self._save(state)
        return {"started": started, "preempted": preempted, "pressure": pressure, "queue": queue}

    def drive(self, *, until_idle: bool = True, max_ticks: int | None = None, interval: float = 0.25) -> dict[str, Any]:
        with _FileLock(self.store.lock_path):
            state = self._load()
            supervisor = state.get("supervisor", {}) if isinstance(state.get("supervisor"), dict) else {}
            supervisor_pid = supervisor.get("pid")
            same_session = supervisor.get("host_session_id") in {None, _host_session_id()}
            if supervisor_pid != os.getpid() and same_session and _pid_alive(supervisor_pid):
                raise ControlError(f"scheduler supervisor is already running with PID {supervisor_pid}")
            state["status"] = "running"
            state["supervisor"] = {"pid": os.getpid(), "heartbeat_at": utc_now(), "host_session_id": _host_session_id()}
            self._save(state)
        ticks = 0
        while True:
            result = self.tick()
            ticks += 1
            graph = self.store.load_taskgraph()
            foreground = bool(self._load().get("foreground", {}).get("active"))
            pending = bool(self._ready_tasks(graph, foreground))
            verifying = bool(self._verification_tasks(graph))
            active = bool(self.children) or any(task.get("status") == "running" for task in graph["tasks"].values())
            if until_idle and not pending and not verifying and not active:
                break
            if max_ticks is not None and ticks >= max_ticks:
                break
            time.sleep(max(0.05, min(interval, 5.0)))
        state = self._load()
        state["status"] = "idle" if not self.children else "running"
        state["supervisor"] = {
            "pid": None if not self.children else os.getpid(),
            "heartbeat_at": utc_now(),
            "host_session_id": _host_session_id(),
        }
        self._save(state)
        return {"ticks": ticks, "scheduler": self.status()}

    def stop(self) -> dict[str, Any]:
        graph = self.store.load_taskgraph()
        stopped = []
        for task in graph["tasks"].values():
            lease = task.get("lease") if isinstance(task.get("lease"), dict) else {}
            if not lease:
                continue
            if _lease_process_alive(lease, "runtime_pid"):
                _terminate_process_tree(lease.get("runtime_pid"))
            pid = lease.get("pid")
            if _lease_process_alive(lease):
                _terminate_process_tree(pid)
            try:
                self.store.release_task(task["id"], str(lease.get("token")), "scheduler stopped")
            except ControlError:
                pass
            stopped.append(task["id"])
            continue
        for task in graph["tasks"].values():
            lease = task.get("verification_lease") if isinstance(task.get("verification_lease"), dict) else {}
            if not lease:
                continue
            if _lease_process_alive(lease, "runtime_pid"):
                _terminate_process_tree(lease.get("runtime_pid"))
            pid = lease.get("pid")
            if _lease_process_alive(lease):
                _terminate_process_tree(pid)
            try:
                self.store.release_verification(task["id"], str(lease.get("token")), "scheduler stopped")
            except ControlError:
                pass
            stopped.append(f"verify:{task['id']}")
        state = self._load()
        state["status"] = "stopped"
        state["supervisor"] = {"pid": None, "heartbeat_at": utc_now(), "host_session_id": _host_session_id()}
        self._save(state)
        return {"status": "stopped", "tasks": stopped}

    def cancel(self, task_id: str, reason: str) -> dict[str, Any]:
        before = self.store.get_task(task_id)
        verifier_lease = before.get("verification_lease") if isinstance(before.get("verification_lease"), dict) else {}
        if verifier_lease and _lease_process_alive(verifier_lease, "runtime_pid"):
            _terminate_process_tree(verifier_lease.get("runtime_pid"))
        if verifier_lease and _lease_process_alive(verifier_lease):
            _terminate_process_tree(verifier_lease.get("pid"))
        task = self.store.cancel_task(task_id, reason)
        lease = task.get("lease") if isinstance(task.get("lease"), dict) else {}
        if lease:
            pid = lease.get("pid")
            if _lease_process_alive(lease, "runtime_pid"):
                _terminate_process_tree(lease.get("runtime_pid"))
            if _lease_process_alive(lease):
                _terminate_process_tree(pid)
            return self.store.release_task(task_id, str(lease.get("token")), reason, retry=False)
        return task
