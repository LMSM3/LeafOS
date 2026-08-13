#!/usr/bin/env python3
"""Super-minimal LeafOS browser node surface.

This is intentionally small and stdlib-only. It does not implement the full
LeafOS relay plan; it gives the current checkout a real browser/API surface over
file-backed status, event logs, examples, and a task inbox.
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import math
import os
import platform
import shutil
import socket
import subprocess
import sys
import threading
import time
import uuid
from collections import deque
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse


VERSION = "0.1.0"
STARTED_AT = time.time()
DEFAULT_PORT = 8765
TASK_STATES = ("inbox", "queued", "running", "done", "failed")
STREAM_HISTORY_LIMIT = 500


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json_atomic(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    os.replace(tmp, path)


def tail_lines(path: Path, limit: int) -> list[str]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as handle:
        lines = handle.readlines()
    return [line.rstrip("\n") for line in lines[-limit:]]


def safe_int(value: str | None, default: int, low: int, high: int) -> int:
    try:
        parsed = int(value) if value is not None else default
    except (TypeError, ValueError):
        return default
    return max(low, min(high, parsed))


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def to_float(value: Any) -> float | None:
    try:
        if value in (None, "", "N/A", "[N/A]"):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


class TextBus:
    """Small in-process text bus with JSONL persistence and SSE wait support."""

    def __init__(self, path: Path, history_limit: int = STREAM_HISTORY_LIMIT) -> None:
        self.path = path
        self.history_limit = history_limit
        self.messages: deque[dict[str, Any]] = deque(maxlen=history_limit)
        self.condition = threading.Condition()
        self.seq = 0
        self._load_tail()

    def _load_tail(self) -> None:
        for line in tail_lines(self.path, self.history_limit):
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            self.messages.append(msg)
            try:
                self.seq = max(self.seq, int(msg.get("seq", 0)))
            except (TypeError, ValueError):
                pass

    def publish(
        self,
        text: str,
        *,
        channel: str = "text",
        direction: str = "in",
        source: str = "browser",
        meta: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        text = str(text)
        with self.condition:
            self.seq += 1
            msg = {
                "seq": self.seq,
                "time": utc_now(),
                "channel": channel,
                "direction": direction,
                "source": source,
                "text": text,
                "meta": meta or {},
            }
            self.messages.append(msg)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(msg, ensure_ascii=False, sort_keys=True) + "\n")
            self.condition.notify_all()
            return msg

    def history(self, channel: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        with self.condition:
            rows = list(self.messages)
        if channel:
            rows = [row for row in rows if row.get("channel") == channel]
        return rows[-limit:]

    def wait_after(
        self,
        last_seq: int,
        *,
        channels: set[str] | None = None,
        timeout: float = 0.05,
    ) -> list[dict[str, Any]]:
        def wanted(row: dict[str, Any]) -> bool:
            try:
                seq_ok = int(row.get("seq", 0)) > last_seq
            except (TypeError, ValueError):
                seq_ok = False
            channel_ok = channels is None or row.get("channel") in channels
            return seq_ok and channel_ok

        with self.condition:
            rows = [row for row in self.messages if wanted(row)]
            if not rows:
                self.condition.wait(timeout=timeout)
                rows = [row for row in self.messages if wanted(row)]
        return rows


class LeafStore:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.node_root = self.root / "system" / "node"
        self.events_path = self.root / "logs" / "events.jsonl"
        self.text_bus = TextBus(self.node_root / "logs" / "text.jsonl")
        self.brain_label = "0.0.0.2"
        self.stream_hz = 20
        self._monitor_lock = threading.Lock()
        self._last_cpu_times: tuple[float, float] | None = None
        self._last_process_times: tuple[float, float] | None = None
        self._last_net_totals: tuple[int, int] | None = None
        self._last_net_time = time.monotonic()
        self._last_gpu_read = 0.0
        self._gpu_cache: list[dict[str, Any]] = []
        self._psutil = self._load_psutil()
        if self._psutil is not None:
            try:
                self._psutil.cpu_percent(interval=None)
            except Exception:
                pass

    def ensure(self) -> None:
        for state in TASK_STATES:
            (self.node_root / state).mkdir(parents=True, exist_ok=True)
        (self.node_root / "logs").mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _load_psutil() -> Any | None:
        try:
            import psutil  # type: ignore[import-not-found]
        except Exception:
            return None
        return psutil

    def task_counts(self) -> dict[str, int]:
        self.ensure()
        return {
            state: len(list((self.node_root / state).glob("*.json")))
            for state in TASK_STATES
        }

    def _cpu_times(self) -> tuple[float, float] | None:
        system = platform.system().lower()
        if system == "windows":
            try:
                import ctypes

                class FILETIME(ctypes.Structure):
                    _fields_ = [
                        ("dwLowDateTime", ctypes.c_ulong),
                        ("dwHighDateTime", ctypes.c_ulong),
                    ]

                idle = FILETIME()
                kernel = FILETIME()
                user = FILETIME()
                ok = ctypes.windll.kernel32.GetSystemTimes(
                    ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user)
                )
                if not ok:
                    return None

                def as_ticks(value: FILETIME) -> float:
                    return float((value.dwHighDateTime << 32) + value.dwLowDateTime)

                idle_ticks = as_ticks(idle)
                total_ticks = as_ticks(kernel) + as_ticks(user)
                return idle_ticks, total_ticks
            except Exception:
                return None
        stat = Path("/proc/stat")
        if stat.exists():
            try:
                fields = stat.read_text(encoding="utf-8").splitlines()[0].split()[1:]
                values = [float(item) for item in fields]
                idle_ticks = values[3] + (values[4] if len(values) > 4 else 0.0)
                return idle_ticks, sum(values)
            except Exception:
                return None
        return None

    def cpu_snapshot(self) -> dict[str, Any]:
        if self._psutil is not None:
            try:
                percent = clamp(float(self._psutil.cpu_percent(interval=None)), 0.0, 100.0)
                physical = self._psutil.cpu_count(logical=False)
                logical = self._psutil.cpu_count(logical=True)
                freq = self._psutil.cpu_freq()
                return {
                    "percent": round(percent, 1),
                    "physical_cores": physical,
                    "logical_cores": logical,
                    "frequency_mhz": round(float(freq.current), 1) if freq else None,
                    "name": platform.processor() or platform.machine(),
                    "source": "psutil",
                    "estimated": False,
                }
            except Exception:
                pass

        current = self._cpu_times()
        if current is not None:
            with self._monitor_lock:
                previous = self._last_cpu_times
                self._last_cpu_times = current
            if previous is not None and current[1] > previous[1]:
                idle_delta = max(0.0, current[0] - previous[0])
                total_delta = max(1.0, current[1] - previous[1])
                percent = clamp((1.0 - idle_delta / total_delta) * 100.0, 0.0, 100.0)
            else:
                percent = 0.0
            return {
                "percent": round(percent, 1),
                "physical_cores": None,
                "logical_cores": os.cpu_count(),
                "frequency_mhz": None,
                "name": platform.processor() or platform.machine(),
                "source": "os",
                "estimated": False,
            }

        now = time.monotonic()
        proc = time.process_time()
        with self._monitor_lock:
            previous_process = self._last_process_times
            self._last_process_times = (now, proc)
        if previous_process is None or now <= previous_process[0]:
            percent = 0.0
        else:
            cores = max(1, os.cpu_count() or 1)
            percent = clamp(((proc - previous_process[1]) / (now - previous_process[0])) * 100.0 / cores, 0.0, 100.0)
        return {
            "percent": round(percent, 1),
            "physical_cores": None,
            "logical_cores": os.cpu_count(),
            "frequency_mhz": None,
            "name": platform.processor() or platform.machine(),
            "source": "process estimate",
            "estimated": True,
        }

    def memory_snapshot(self) -> dict[str, Any]:
        if self._psutil is not None:
            try:
                ram = self._psutil.virtual_memory()
                return {
                    "total": int(ram.total),
                    "used": int(ram.used),
                    "available": int(ram.available),
                    "percent": round(float(ram.percent), 1),
                    "source": "psutil",
                    "estimated": False,
                }
            except Exception:
                pass

        if platform.system().lower() == "windows":
            try:
                import ctypes

                class MEMORYSTATUSEX(ctypes.Structure):
                    _fields_ = [
                        ("dwLength", ctypes.c_ulong),
                        ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong),
                        ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong),
                        ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong),
                        ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
                    ]

                status = MEMORYSTATUSEX()
                status.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
                if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                    total = int(status.ullTotalPhys)
                    available = int(status.ullAvailPhys)
                    used = max(0, total - available)
                    return {
                        "total": total,
                        "used": used,
                        "available": available,
                        "percent": round((used / total) * 100.0, 1) if total else 0.0,
                        "source": "GlobalMemoryStatusEx",
                        "estimated": False,
                    }
            except Exception:
                pass

        meminfo = Path("/proc/meminfo")
        if meminfo.exists():
            try:
                rows: dict[str, int] = {}
                for line in meminfo.read_text(encoding="utf-8").splitlines():
                    name, rest = line.split(":", 1)
                    rows[name] = int(rest.strip().split()[0]) * 1024
                total = rows.get("MemTotal", 0)
                available = rows.get("MemAvailable", rows.get("MemFree", 0))
                used = max(0, total - available)
                return {
                    "total": total,
                    "used": used,
                    "available": available,
                    "percent": round((used / total) * 100.0, 1) if total else 0.0,
                    "source": "/proc/meminfo",
                    "estimated": False,
                }
            except Exception:
                pass

        return {"total": None, "used": None, "available": None, "percent": 0.0, "source": "unavailable", "estimated": True}

    def disk_snapshot(self) -> dict[str, Any]:
        target = Path(self.root.anchor) if self.root.anchor else self.root
        try:
            usage = shutil.disk_usage(target)
            return {
                "path": str(target),
                "total": int(usage.total),
                "used": int(usage.used),
                "free": int(usage.free),
                "percent": round((usage.used / usage.total) * 100.0, 1) if usage.total else 0.0,
                "source": "shutil.disk_usage",
                "estimated": False,
            }
        except OSError:
            return {"path": str(target), "total": None, "used": None, "free": None, "percent": 0.0, "source": "unavailable", "estimated": True}

    def network_snapshot(self) -> dict[str, Any]:
        now = time.monotonic()
        if self._psutil is not None:
            try:
                current = self._psutil.net_io_counters()
                totals = (int(current.bytes_sent), int(current.bytes_recv))
                with self._monitor_lock:
                    previous = self._last_net_totals
                    previous_time = self._last_net_time
                    self._last_net_totals = totals
                    self._last_net_time = now
                elapsed = max(0.001, now - previous_time)
                if previous is None:
                    sent_bps = recv_bps = 0.0
                else:
                    sent_bps = max(0.0, (totals[0] - previous[0]) / elapsed)
                    recv_bps = max(0.0, (totals[1] - previous[1]) / elapsed)
                return {
                    "sent_bps": round(sent_bps, 1),
                    "recv_bps": round(recv_bps, 1),
                    "source": "psutil",
                    "estimated": False,
                }
            except Exception:
                pass

        text_count = len(self.text_bus.history(limit=STREAM_HISTORY_LIMIT))
        task_total = sum(self.task_counts().values())
        pulse = abs(math.sin(now * 1.7))
        return {
            "sent_bps": round((text_count * 64.0 + task_total * 180.0) * (0.2 + pulse), 1),
            "recv_bps": round((text_count * 42.0 + task_total * 120.0) * (0.2 + abs(math.cos(now * 1.3))), 1),
            "source": "text/task estimate",
            "estimated": True,
        }

    def gpu_snapshot(self) -> list[dict[str, Any]]:
        now = time.monotonic()
        if now - self._last_gpu_read < 5.0:
            return self._gpu_cache
        self._last_gpu_read = now
        tool = shutil.which("nvidia-smi")
        if not tool:
            self._gpu_cache = []
            return []
        query = "name,temperature.gpu,fan.speed,utilization.gpu,memory.used,memory.total"
        command = [tool, f"--query-gpu={query}", "--format=csv,noheader,nounits"]
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=1.5, check=False)
        except (OSError, subprocess.SubprocessError):
            self._gpu_cache = []
            return []
        if result.returncode != 0 or not result.stdout.strip():
            self._gpu_cache = []
            return []
        gpus: list[dict[str, Any]] = []
        for row in csv.reader(result.stdout.splitlines()):
            columns = [column.strip() for column in row]
            if len(columns) < 6:
                continue
            gpus.append(
                {
                    "name": columns[0],
                    "temperature_c": to_float(columns[1]),
                    "fan_percent": to_float(columns[2]),
                    "utilization_percent": to_float(columns[3]),
                    "memory_used_mib": to_float(columns[4]),
                    "memory_total_mib": to_float(columns[5]),
                    "source": "nvidia-smi",
                }
            )
        self._gpu_cache = gpus
        return gpus

    def sensor_snapshot(self, cpu_percent: float, gpus: list[dict[str, Any]]) -> dict[str, Any]:
        temps: list[dict[str, Any]] = []
        fans: list[dict[str, Any]] = []
        notes: list[dict[str, Any]] = []

        if self._psutil is not None:
            if hasattr(self._psutil, "sensors_temperatures"):
                try:
                    for chip, entries in self._psutil.sensors_temperatures(fahrenheit=False).items():
                        for entry in entries:
                            current = to_float(getattr(entry, "current", None))
                            if current is None:
                                continue
                            label = " ".join(part for part in [chip, getattr(entry, "label", "")] if part)
                            temps.append({"name": label or chip, "celsius": round(current, 1), "source": "psutil", "estimated": False})
                except Exception:
                    pass
            if hasattr(self._psutil, "sensors_fans"):
                try:
                    for chip, entries in self._psutil.sensors_fans().items():
                        for entry in entries:
                            rpm = to_float(getattr(entry, "current", None))
                            if rpm is None or rpm <= 0:
                                continue
                            label = " ".join(part for part in [chip, getattr(entry, "label", "")] if part)
                            fans.append({"name": label or chip, "rpm": round(rpm), "percent": None, "source": "psutil", "estimated": False})
                except Exception:
                    pass

        for gpu in gpus:
            temp_c = to_float(gpu.get("temperature_c"))
            fan_percent = to_float(gpu.get("fan_percent"))
            if temp_c is not None:
                temps.append({"name": f"{gpu.get('name', 'GPU')} GPU", "celsius": round(temp_c, 1), "source": "nvidia-smi", "estimated": False})
            if fan_percent is not None:
                fans.append({"name": f"{gpu.get('name', 'GPU')} GPU fan", "rpm": None, "percent": round(fan_percent, 1), "source": "nvidia-smi", "estimated": False})

        if not temps:
            cpu_temp = 34.0 + clamp(cpu_percent, 0.0, 100.0) * 0.38
            ssd_temp = 31.0 + clamp(cpu_percent, 0.0, 100.0) * 0.07 + abs(math.sin(time.monotonic() / 9.0)) * 3.0
            temps.extend(
                [
                    {"name": "CPU Package estimate", "celsius": round(cpu_temp, 1), "source": "estimated", "estimated": True},
                    {"name": "SSD estimate", "celsius": round(ssd_temp, 1), "source": "estimated", "estimated": True},
                ]
            )
            notes.append({"level": "estimate", "message": "No readable temperature sensor found; browser values are estimated from CPU load."})

        if not any(not fan.get("estimated") and "gpu" not in str(fan.get("name", "")).lower() for fan in fans):
            fans.append(self.estimated_fan(cpu_percent, temps))
            notes.append({"level": "estimate", "message": "No readable system fan sensor found; fan RPM is estimated."})

        return {"temperatures": temps[:8], "fans": fans[:6], "notes": notes}

    def estimated_fan(self, cpu_percent: float, temps: list[dict[str, Any]]) -> dict[str, Any]:
        hottest = max((to_float(temp.get("celsius")) or 0.0 for temp in temps), default=0.0)
        if hottest <= 0:
            hottest = 34.0 + clamp(cpu_percent, 0.0, 100.0) * 0.38
        points = [(30.0, 15.0), (40.0, 22.0), (55.0, 38.0), (70.0, 68.0), (82.0, 92.0), (92.0, 100.0)]
        percent = points[-1][1]
        if hottest <= points[0][0]:
            percent = points[0][1]
        else:
            for (left_temp, left_pct), (right_temp, right_pct) in zip(points, points[1:]):
                if hottest <= right_temp:
                    ratio = (hottest - left_temp) / (right_temp - left_temp)
                    percent = left_pct + ratio * (right_pct - left_pct)
                    break
        percent = clamp(max(percent, 18.0 + clamp(cpu_percent, 0.0, 100.0) * 0.45), 15.0, 100.0)
        rpm = 700 + (4200 - 700) * (percent / 100.0)
        return {
            "name": "System fan estimate",
            "rpm": round(rpm),
            "percent": round(percent, 1),
            "source": "estimated",
            "estimated": True,
            "basis": f"hottest {hottest:.1f} C / CPU {cpu_percent:.0f}%",
        }

    def monitor(self) -> dict[str, Any]:
        cpu = self.cpu_snapshot()
        memory = self.memory_snapshot()
        disk = self.disk_snapshot()
        network = self.network_snapshot()
        gpus = self.gpu_snapshot()
        sensors = self.sensor_snapshot(float(cpu.get("percent", 0.0) or 0.0), gpus)
        return {
            "leafos_object": "serve_leaf_monitor",
            "version": VERSION,
            "host": socket.gethostname(),
            "platform": platform.platform(terse=True),
            "time": datetime.now().astimezone().isoformat(timespec="seconds"),
            "uptime_seconds": round(time.time() - STARTED_AT, 3),
            "cpu": cpu,
            "memory": memory,
            "disk": disk,
            "network": network,
            "gpus": gpus,
            "temperatures": sensors["temperatures"],
            "fans": sensors["fans"],
            "notes": sensors["notes"],
            "task_counts": self.task_counts(),
            "text_stream": {
                "messages": len(self.text_bus.history(limit=STREAM_HISTORY_LIMIT)),
                "hz": self.stream_hz,
            },
            "brain_stream": {
                "messages": len(self.text_bus.history(channel="brain", limit=STREAM_HISTORY_LIMIT)),
                "lane": getattr(self, "brain_label", "0.0.0.2"),
                "hz": self.stream_hz,
            },
        }

    def append_event(self, kind: str, message: str, **extra: Any) -> None:
        self.ensure()
        event = {
            "time": utc_now(),
            "kind": kind,
            "message": message,
            **extra,
        }
        with (self.node_root / "logs" / "events.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")

    def submit_task(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.ensure()
        task_id = f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:10]}"
        priority = payload.get("priority", 5)
        try:
            priority = int(priority)
        except (TypeError, ValueError):
            priority = 5
        task = {
            "leafos_object": "leaf_task",
            "version": VERSION,
            "id": task_id,
            "state": "inbox",
            "received_at": utc_now(),
            "kind": payload.get("kind", "echo"),
            "priority": priority,
            "payload": payload.get("payload", {}),
            "note": "Queued only. Minimal serve-leaf does not execute tasks yet.",
        }
        write_json_atomic(self.node_root / "inbox" / f"{task_id}.json", task)
        self.append_event("task", "task submitted", task_id=task_id, state="inbox")
        self.text_bus.publish(
            f"task submitted: {task_id} ({task['kind']})",
            channel="text",
            direction="system",
            source="serve-leaf",
            meta={"task_id": task_id},
        )
        return task

    def status(self, host: str, port: int) -> dict[str, Any]:
        self.ensure()
        task_counts = self.task_counts()
        examples = sorted((self.root / "examples").glob("*.task.json"))
        wakeup = self.root / "examples" / "WO-004-C" / "agent_node.json"
        return {
            "leafos_object": "serve_leaf_status",
            "version": VERSION,
            "host": socket.gethostname(),
            "bind": {"host": host, "port": port},
            "root": str(self.root),
            "uptime_seconds": round(time.time() - STARTED_AT, 3),
            "leafctl_present": {
                "bash": (self.root / "bin" / "leafctl").exists(),
                "powershell": (self.root / "bin" / "leafctl.ps1").exists(),
            },
            "examples": len(examples) + (1 if wakeup.exists() else 0),
            "logs": {
                "taskpack_events": str(self.events_path),
                "serve_leaf_events": str(self.node_root / "logs" / "events.jsonl"),
            },
            "task_counts": task_counts,
            "text_stream": {
                "messages": len(self.text_bus.history(limit=STREAM_HISTORY_LIMIT)),
                "endpoint": "/api/text/stream",
                "hz": self.stream_hz,
            },
            "brain_stream": {
                "messages": len(self.text_bus.history(channel="brain", limit=STREAM_HISTORY_LIMIT)),
                "lane": getattr(self, "brain_label", "0.0.0.2"),
                "endpoint": "/api/brain/stream",
                "hz": self.stream_hz,
                "note": "The lane is a label; bind hosts remain 127.0.0.1 or 0.0.0.0.",
            },
        }

    def tasks(self, limit: int = 50) -> list[dict[str, Any]]:
        self.ensure()
        records: list[dict[str, Any]] = []
        for state in TASK_STATES:
            for path in sorted((self.node_root / state).glob("*.json"), reverse=True):
                try:
                    record = read_json(path)
                except (OSError, json.JSONDecodeError):
                    continue
                record["_state_dir"] = state
                record["_path"] = str(path)
                records.append(record)
        records.sort(key=lambda item: item.get("received_at", ""), reverse=True)
        return records[:limit]

    def task_by_id(self, task_id: str) -> dict[str, Any] | None:
        self.ensure()
        clean = "".join(ch for ch in task_id if ch.isalnum() or ch in "-_")
        if not clean:
            return None
        for state in TASK_STATES:
            path = self.node_root / state / f"{clean}.json"
            if path.exists():
                record = read_json(path)
                record["_state_dir"] = state
                record["_path"] = str(path)
                return record
        return None

    def events(self, limit: int) -> list[dict[str, Any]]:
        lines = tail_lines(self.events_path, limit) + tail_lines(self.node_root / "logs" / "events.jsonl", limit)
        events: list[dict[str, Any]] = []
        for line in lines[-limit:]:
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                events.append({"raw": line})
        return events

    def examples(self) -> list[dict[str, Any]]:
        found: list[dict[str, Any]] = []
        for path in sorted((self.root / "examples").glob("*.task.json")):
            try:
                payload = read_json(path)
            except (OSError, json.JSONDecodeError):
                payload = None
            found.append({"name": path.name, "path": str(path), "payload": payload})
        wakeup = self.root / "examples" / "WO-004-C" / "agent_node.json"
        if wakeup.exists():
            found.append({"name": "WO-004-C wakeup node", "path": str(wakeup), "payload": read_json(wakeup)})
        return found


class LeafHandler(BaseHTTPRequestHandler):
    server_version = f"serve-leaf/{VERSION}"
    protocol_version = "HTTP/1.1"

    @property
    def store(self) -> LeafStore:
        return self.server.store  # type: ignore[attr-defined]

    def log_message(self, fmt: str, *args: Any) -> None:
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        if parsed.path == "/":
            self.send_html(self.render_index())
        elif parsed.path == "/brain":
            self.send_html(self.render_index())
        elif parsed.path == "/api/health":
            self.send_json({"ok": True, "version": VERSION, "time": utc_now()})
        elif parsed.path == "/api/status":
            self.send_json(self.store.status(self.server.bind_host, self.server.bind_port))  # type: ignore[attr-defined]
        elif parsed.path == "/api/monitor":
            self.send_json(self.store.monitor())
        elif parsed.path == "/api/tasks":
            limit = safe_int(query.get("limit", [None])[0], 50, 1, 200)
            self.send_json({"tasks": self.store.tasks(limit)})
        elif parsed.path.startswith("/api/tasks/"):
            task_id = parsed.path.rsplit("/", 1)[-1]
            task = self.store.task_by_id(task_id)
            if task is None:
                self.send_error_json(HTTPStatus.NOT_FOUND, "task not found")
            else:
                self.send_json(task)
        elif parsed.path == "/api/events":
            limit = safe_int(query.get("limit", [None])[0], 50, 1, 300)
            self.send_json({"events": self.store.events(limit)})
        elif parsed.path == "/api/examples":
            self.send_json({"examples": self.store.examples()})
        elif parsed.path == "/api/text":
            limit = safe_int(query.get("limit", [None])[0], 100, 1, STREAM_HISTORY_LIMIT)
            self.send_json({"messages": self.store.text_bus.history(channel="text", limit=limit)})
        elif parsed.path == "/api/brain":
            limit = safe_int(query.get("limit", [None])[0], 100, 1, STREAM_HISTORY_LIMIT)
            self.send_json({"messages": self.store.text_bus.history(channel="brain", limit=limit)})
        elif parsed.path in {"/api/stream", "/api/text/stream", "/api/brain/stream"}:
            self.send_sse(parsed.path, query)
        else:
            self.send_error_json(HTTPStatus.NOT_FOUND, "not found")

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/tasks":
            try:
                payload = self.read_json_body()
            except ValueError as exc:
                self.send_error_json(HTTPStatus.BAD_REQUEST, str(exc))
                return
            if not isinstance(payload, dict):
                self.send_error_json(HTTPStatus.BAD_REQUEST, "body must be a JSON object")
                return
            task = self.store.submit_task(payload)
            self.send_json(task, HTTPStatus.CREATED)
            return
        if parsed.path in {"/api/text", "/api/brain"}:
            try:
                payload = self.read_text_payload()
            except ValueError as exc:
                self.send_error_json(HTTPStatus.BAD_REQUEST, str(exc))
                return
            channel = "brain" if parsed.path == "/api/brain" else "text"
            msg = self.store.text_bus.publish(
                payload["text"],
                channel=channel,
                direction="in",
                source=payload.get("source", "browser"),
                meta=payload.get("meta", {}),
            )
            self.store.append_event("text", f"{channel} text received", channel=channel, seq=msg["seq"])
            self.send_json(msg, HTTPStatus.CREATED)
            return
        else:
            self.send_error_json(HTTPStatus.NOT_FOUND, "not found")
            return

    def read_text_payload(self) -> dict[str, Any]:
        length = safe_int(self.headers.get("Content-Length"), 0, 0, 1_000_000)
        if length <= 0:
            raise ValueError("missing request body")
        raw = self.rfile.read(length)
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError("body must be UTF-8") from exc
        content_type = self.headers.get("Content-Type", "")
        if "application/json" in content_type:
            try:
                payload = json.loads(text)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSON: {exc.msg}") from exc
            if not isinstance(payload, dict):
                raise ValueError("body must be a JSON object")
            message = payload.get("text", payload.get("message", ""))
            if not str(message).strip():
                raise ValueError("text is required")
            return {
                "text": str(message),
                "source": str(payload.get("source", "browser")),
                "meta": payload.get("meta", {}) if isinstance(payload.get("meta", {}), dict) else {},
            }
        if not text.strip():
            raise ValueError("text is required")
        return {"text": text, "source": "browser", "meta": {}}

    def read_json_body(self) -> Any:
        length = safe_int(self.headers.get("Content-Length"), 0, 0, 1_000_000)
        if length <= 0:
            raise ValueError("missing request body")
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except UnicodeDecodeError as exc:
            raise ValueError("body must be UTF-8") from exc
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSON: {exc.msg}") from exc

    def send_json(self, data: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status.value)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def send_html(self, body: str) -> None:
        encoded = body.encode("utf-8")
        self.send_response(HTTPStatus.OK.value)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(encoded)

    def send_error_json(self, status: HTTPStatus, message: str) -> None:
        self.send_json({"ok": False, "error": message}, status)

    def send_sse(self, path: str, query: dict[str, list[str]]) -> None:
        if path == "/api/brain/stream":
            channels = {"brain"}
        elif path == "/api/text/stream":
            channels = {"text"}
        else:
            channels = None
        hz_default = getattr(self.server, "stream_hz", 20)  # type: ignore[attr-defined]
        hz = safe_int(query.get("hz", [None])[0], hz_default, 1, 60)
        last_seq = safe_int(query.get("after", [None])[0], 0, 0, 10**12)
        interval = 1.0 / float(hz)
        self.send_response(HTTPStatus.OK.value)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "keep-alive")
        self.end_headers()
        self.wfile.write(b": serve-leaf stream connected\n\n")
        self.wfile.flush()
        try:
            while True:
                rows = self.store.text_bus.wait_after(last_seq, channels=channels, timeout=interval)
                if rows:
                    for row in rows:
                        try:
                            last_seq = max(last_seq, int(row.get("seq", last_seq)))
                        except (TypeError, ValueError):
                            pass
                        self.write_sse("text", row)
                else:
                    self.write_sse("tick", {"time": utc_now(), "hz": hz, "after": last_seq})
        except (BrokenPipeError, ConnectionResetError, OSError):
            return

    def write_sse(self, event: str, data: dict[str, Any]) -> None:
        body = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
        frame = f"event: {event}\ndata: {body}\n\n".encode("utf-8")
        try:
            self.wfile.write(frame)
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            raise

    def render_index(self) -> str:
        status = self.store.status(self.server.bind_host, self.server.bind_port)  # type: ignore[attr-defined]
        tasks = self.store.tasks(12)
        task_rows = "\n".join(
            f"<tr><td>{html.escape(str(t.get('id', '')))}</td><td>{html.escape(str(t.get('kind', '')))}</td>"
            f"<td>{html.escape(str(t.get('state', '')))}</td><td>{html.escape(str(t.get('priority', '')))}</td>"
            f"<td>{html.escape(str(t.get('received_at', '')))}</td></tr>"
            for t in tasks
        ) or "<tr><td colspan='5' class='empty'>No submitted tasks yet.</td></tr>"
        task_default = {
            "kind": "echo",
            "priority": 5,
            "payload": {"message": "hello from browser"},
        }
        last_task = tasks[0] if tasks else {
            "leafos_object": "leaf_task",
            "state": "empty",
            "note": "No submitted tasks yet.",
        }
        status_json = html.escape(json.dumps(status, ensure_ascii=False, indent=2))
        task_default_json = html.escape(json.dumps(task_default, ensure_ascii=False, indent=2))
        last_task_json = html.escape(json.dumps(last_task, ensure_ascii=False, indent=2))
        brain_label = html.escape(str(getattr(self.store, "brain_label", "0.0.0.2")))
        brain_label_js = json.dumps(str(getattr(self.store, "brain_label", "0.0.0.2")))
        stream_hz = int(getattr(self.server, "stream_hz", 20))  # type: ignore[attr-defined]
        template = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>LeafOS Serve Leaf</title>
  <style>
    :root {
      color-scheme: dark;
      --bg: #00110e;
      --bg-deep: #000806;
      --panel: rgba(0, 28, 22, 0.86);
      --panel-soft: rgba(0, 40, 28, 0.55);
      --green: #62f06b;
      --green-hot: #8cff83;
      --green-dim: #2da842;
      --green-faint: rgba(92, 240, 107, 0.28);
      --black: #000f0b;
      --warn: #d8f55f;
      --bad: #ff7b7b;
      font-family: "Cascadia Mono", "Consolas", "SFMono-Regular", monospace;
      letter-spacing: 0;
    }

    * { box-sizing: border-box; }

    html, body { min-height: 100%; }

    body {
      margin: 0;
      background:
        radial-gradient(circle at 50% 0%, rgba(34, 118, 61, 0.22), transparent 34rem),
        radial-gradient(circle at 15% 18%, rgba(42, 154, 84, 0.12), transparent 30rem),
        linear-gradient(180deg, #00120e 0%, #000806 100%);
      color: var(--green);
      font-size: 15px;
      overflow-x: hidden;
      text-shadow: 0 0 8px rgba(98, 240, 107, 0.34);
    }

    body::before {
      content: "";
      position: fixed;
      inset: 0;
      z-index: 10;
      pointer-events: none;
      background: linear-gradient(rgba(255,255,255,0.035) 50%, rgba(0,0,0,0.08) 50%);
      background-size: 100% 4px;
      mix-blend-mode: soft-light;
    }

    body::after {
      content: "";
      position: fixed;
      inset: 0;
      z-index: 11;
      pointer-events: none;
      box-shadow: inset 0 0 140px rgba(0, 0, 0, 0.82);
    }

    a { color: var(--green-hot); text-decoration: none; }
    a:hover { color: #d7ffca; }

    button,
    input,
    textarea,
    pre {
      font: inherit;
    }

    button {
      min-height: 34px;
      border: 1px solid var(--green-dim);
      background: linear-gradient(180deg, #70ff66, #38b33f);
      color: #00120e;
      padding: 6px 12px;
      cursor: pointer;
      font-weight: 800;
      text-transform: uppercase;
      box-shadow: 0 0 14px rgba(92, 240, 107, 0.28);
    }

    button:hover { filter: brightness(1.12); }

    textarea,
    input {
      width: 100%;
      min-width: 0;
      border: 1px solid var(--green-dim);
      background: rgba(0, 11, 8, 0.94);
      color: var(--green-hot);
      padding: 10px;
      outline: none;
      box-shadow: inset 0 0 18px rgba(39, 145, 61, 0.14);
    }

    textarea:focus,
    input:focus { border-color: var(--green-hot); }

    textarea {
      min-height: 164px;
      resize: vertical;
      line-height: 1.35;
    }

    pre {
      margin: 0;
      white-space: pre-wrap;
      word-break: break-word;
      overflow: auto;
      scrollbar-color: var(--green-dim) transparent;
    }

    table {
      width: 100%;
      border-collapse: collapse;
      table-layout: fixed;
    }

    th, td {
      padding: 8px 10px;
      border-bottom: 1px dashed var(--green-faint);
      text-align: left;
      vertical-align: top;
      overflow-wrap: anywhere;
    }

    th {
      color: var(--green-hot);
      font-weight: 800;
    }

    .shell {
      position: relative;
      z-index: 1;
      min-height: 100vh;
      padding: 10px 12px 12px;
      display: flex;
      flex-direction: column;
      gap: 14px;
    }

    .frame {
      border: 1px solid var(--green-dim);
      background:
        linear-gradient(90deg, rgba(92, 240, 107, 0.035), transparent 18%, transparent 82%, rgba(92, 240, 107, 0.035)),
        var(--panel);
      box-shadow:
        inset 0 0 28px rgba(92, 240, 107, 0.08),
        0 0 20px rgba(0, 0, 0, 0.48);
    }

    .topbar {
      min-height: 124px;
      display: grid;
      grid-template-columns: minmax(0, 1fr) 360px;
      gap: 18px;
      padding: 22px 28px;
      align-items: center;
    }

    .brand {
      min-width: 0;
      display: flex;
      align-items: center;
      gap: 24px;
    }

    .leaf-mark {
      width: 72px;
      min-width: 72px;
      color: var(--green-hot);
      white-space: pre;
      line-height: 0.9;
      font-size: 15px;
      text-align: center;
      filter: drop-shadow(0 0 8px rgba(98, 240, 107, 0.5));
    }

    h1 {
      margin: 0 0 12px;
      color: var(--green-hot);
      font-size: 31px;
      line-height: 1;
      font-weight: 400;
    }

    .subtitle,
    .muted {
      color: #70d971;
    }

    .host-box {
      justify-self: end;
      width: 100%;
      max-width: 360px;
      color: var(--green-hot);
      font-weight: 800;
      line-height: 1.45;
    }

    .dashboard {
      flex: 1;
      display: grid;
      grid-template-columns: 330px minmax(420px, 1fr) minmax(360px, 500px);
      grid-template-areas:
        "monitor queue submit"
        "monitor streams last"
        "monitor tasks tasks";
      gap: 14px;
      align-items: stretch;
    }

    .panel {
      min-width: 0;
      padding: 12px 14px;
    }

    .panel-title {
      display: flex;
      align-items: center;
      gap: 8px;
      margin: 0 0 12px;
      color: var(--green-hot);
      font-weight: 800;
      text-transform: uppercase;
      line-height: 1.1;
      white-space: nowrap;
    }

    .panel-title::before,
    .panel-title::after {
      content: "======";
      color: var(--green-dim);
      overflow: hidden;
    }

    .panel-title::after {
      flex: 1;
      min-width: 12px;
    }

    .monitor-panel { grid-area: monitor; }
    .queue-panel { grid-area: queue; }
    .submit-panel { grid-area: submit; }
    .last-panel { grid-area: last; }
    .streams-panel { grid-area: streams; }
    .tasks-panel { grid-area: tasks; }

    .status-json {
      min-height: 360px;
      max-height: 492px;
      padding: 12px;
      border: 1px solid var(--green-dim);
      background: rgba(0, 10, 8, 0.76);
      line-height: 1.32;
      color: var(--green-hot);
    }

    .api-row {
      margin-top: 12px;
      padding: 9px 10px;
      border: 1px solid var(--green-dim);
      display: flex;
      flex-wrap: wrap;
      gap: 12px;
      color: var(--green-hot);
    }

    .metric {
      margin: 0 0 17px;
    }

    .metric-head {
      display: flex;
      justify-content: space-between;
      gap: 8px;
      color: var(--green-hot);
      line-height: 1.2;
    }

    .metric-sub {
      margin-top: 3px;
      color: #66d966;
      font-size: 13px;
      line-height: 1.25;
    }

    .spark {
      width: 100%;
      height: 72px;
      margin-top: 7px;
      border: 1px solid var(--green-dim);
      background: rgba(0, 8, 6, 0.82);
    }

    .mini-spark {
      height: 36px;
    }

    .bar {
      height: 20px;
      margin-top: 6px;
      border: 1px solid var(--green-dim);
      background: rgba(0, 8, 6, 0.86);
      overflow: hidden;
    }

    .bar span {
      display: block;
      width: 0;
      height: 100%;
      min-width: 2px;
      background:
        repeating-linear-gradient(90deg, var(--green-hot) 0 7px, transparent 7px 10px),
        linear-gradient(90deg, #55f067, #95ff83);
      box-shadow: 0 0 10px rgba(98, 240, 107, 0.42);
    }

    .kv-list {
      display: grid;
      gap: 3px;
      margin-top: 6px;
      color: var(--green-hot);
      line-height: 1.35;
    }

    .kv-list div {
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 12px;
    }

    .task-form {
      display: grid;
      gap: 12px;
    }

    .result-box,
    .last-json {
      min-height: 132px;
      max-height: 280px;
      padding: 12px;
      border: 1px solid var(--green-dim);
      background: rgba(0, 10, 8, 0.76);
      color: var(--green-hot);
      line-height: 1.3;
    }

    .last-json { min-height: 245px; }

    .note-line {
      margin-top: 10px;
      color: var(--green-hot);
      line-height: 1.35;
    }

    .streams-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 12px;
    }

    .stream-card {
      min-width: 0;
      display: grid;
      gap: 9px;
    }

    .stream-log {
      min-height: 126px;
      max-height: 176px;
      padding: 10px;
      border: 1px solid var(--green-dim);
      background: rgba(0, 8, 6, 0.82);
      color: var(--green-hot);
      line-height: 1.3;
    }

    .stream-row {
      display: grid;
      grid-template-columns: minmax(0, 1fr) 60px;
      gap: 8px;
    }

    .table-wrap {
      overflow: auto;
      border-top: 1px solid var(--green-faint);
    }

    .empty {
      text-align: center;
      color: #70d971;
    }

    .footer {
      min-height: 40px;
      display: grid;
      grid-template-columns: minmax(0, 1fr) minmax(0, 2fr) minmax(0, 1fr);
      gap: 12px;
      align-items: center;
      padding: 8px 14px;
      color: var(--green-hot);
    }

    .footer-nav {
      display: flex;
      justify-content: center;
      gap: 36px;
      flex-wrap: wrap;
    }

    .footer-status {
      text-align: right;
      font-weight: 800;
    }

    @media (max-width: 1280px) {
      .dashboard {
        grid-template-columns: 310px minmax(360px, 1fr);
        grid-template-areas:
          "monitor queue"
          "monitor submit"
          "monitor last"
          "streams streams"
          "tasks tasks";
      }

      .topbar {
        grid-template-columns: minmax(0, 1fr);
      }

      .host-box {
        justify-self: start;
      }
    }

    @media (max-width: 860px) {
      body { font-size: 14px; }
      .shell { padding: 8px 8px 58px; }
      .topbar { padding: 18px 16px; }
      .brand { align-items: flex-start; gap: 14px; }
      .leaf-mark { width: 54px; min-width: 54px; font-size: 12px; }
      h1 { font-size: 23px; line-height: 1.12; }
      .dashboard {
        grid-template-columns: minmax(0, 1fr);
        grid-template-areas:
          "monitor"
          "queue"
          "submit"
          "last"
          "streams"
          "tasks";
      }
      .streams-grid { grid-template-columns: minmax(0, 1fr); }
      .footer {
        grid-template-columns: minmax(0, 1fr);
        position: static;
      }
      .footer-nav,
      .footer-status {
        justify-content: flex-start;
        text-align: left;
      }
    }
  </style>
</head>
<body>
  <div class="shell">
    <header class="frame topbar">
      <div class="brand">
        <div class="leaf-mark">  .-.
 /   \\
 |   |
 \\   /
  `-'
 /|\\</div>
        <div>
          <h1>LeafOS Serve Leaf v__VERSION__</h1>
          <div class="subtitle">Minimal browser/API surface. Queue only, no task execution yet.</div>
        </div>
      </div>
      <div class="host-box">
        <div>SYSTEM HOST: <span id="systemHost">__HOST__</span></div>
        <div>UPTIME: <span id="uptime">--:--:--</span></div>
        <div>TIME: <span id="clock">--</span></div>
      </div>
    </header>

    <main class="dashboard">
      <section class="frame panel monitor-panel">
        <h2 class="panel-title">System Monitor</h2>

        <div class="metric">
          <div class="metric-head"><span>CPU [ <span id="cpuPct">--</span>% ]</span><span id="cpuSource">--</span></div>
          <canvas class="spark" id="cpuSpark" width="300" height="72"></canvas>
          <div class="metric-sub" id="cpuName">Detecting CPU</div>
          <div class="metric-sub">Cores: <span id="cpuCores">--</span></div>
        </div>

        <div class="metric">
          <div class="metric-head"><span>RAM [ <span id="ramUsed">--</span> / <span id="ramTotal">--</span> ]</span><span id="ramPct">--%</span></div>
          <div class="bar"><span id="ramBar"></span></div>
        </div>

        <div class="metric">
          <div class="metric-head"><span>VRAM [ <span id="vramUsed">--</span> / <span id="vramTotal">--</span> ]</span><span id="vramPct">--%</span></div>
          <div class="bar"><span id="vramBar"></span></div>
          <div class="metric-sub" id="gpuName">GPU telemetry scanning</div>
        </div>

        <div class="metric">
          <div class="metric-head"><span>DISK [ <span id="diskUsed">--</span> / <span id="diskTotal">--</span> ]</span><span id="diskPct">--%</span></div>
          <div class="bar"><span id="diskBar"></span></div>
          <div class="metric-sub" id="diskPath">--</div>
        </div>

        <div class="metric">
          <div class="metric-head"><span>NETWORK</span><span id="netSource">--</span></div>
          <div class="metric-sub">down <span id="netDown">--</span> | up <span id="netUp">--</span></div>
          <canvas class="spark mini-spark" id="netSpark" width="300" height="36"></canvas>
        </div>

        <div class="metric">
          <div class="metric-head"><span>TEMP (C)</span><span id="tempSource">--</span></div>
          <div class="kv-list" id="tempList"></div>
        </div>

        <div class="metric">
          <div class="metric-head"><span>FAN SPEED</span><span id="fanSource">--</span></div>
          <div class="kv-list" id="fanList"></div>
        </div>
      </section>

      <section class="frame panel queue-panel">
        <h2 class="panel-title">Queue Status</h2>
        <pre class="status-json" id="statusJson">__STATUS_JSON__</pre>
        <div class="api-row">
          <span>[API]</span>
          <a href="/api/status">/api/status</a>
          <a href="/api/monitor">/api/monitor</a>
          <a href="/api/tasks">/api/tasks</a>
          <a href="/api/events">/api/events</a>
          <a href="/api/examples">/api/examples</a>
          <a href="/api/text/stream">/api/text/stream</a>
          <a href="/api/brain/stream">/api/brain/stream</a>
        </div>
      </section>

      <section class="frame panel submit-panel">
        <h2 class="panel-title">Submit Task</h2>
        <div class="task-form">
          <textarea id="taskPayload">__TASK_DEFAULT__</textarea>
          <button onclick="submitTask()">[ Submit To Inbox ]</button>
          <pre class="result-box" id="submitResult">Waiting.</pre>
        </div>
      </section>

      <section class="frame panel streams-panel">
        <h2 class="panel-title">High Hz Text</h2>
        <div class="streams-grid">
          <div class="stream-card">
            <div class="metric-head"><span>TEXT STREAM</span><span id="textStreamState">connecting</span></div>
            <pre id="textStream" class="stream-log"></pre>
            <div class="stream-row">
              <input id="textInput" value="hello leaf stream" onkeydown="if (event.key === 'Enter') sendText('text')">
              <button onclick="sendText('text')">TX</button>
            </div>
          </div>
          <div class="stream-card">
            <div class="metric-head"><span>BRAIN __BRAIN_LABEL__</span><span id="brainStreamState">connecting</span></div>
            <pre id="brainStream" class="stream-log"></pre>
            <div class="stream-row">
              <input id="brainInput" value="brain stream heartbeat" onkeydown="if (event.key === 'Enter') sendText('brain')">
              <button onclick="sendText('brain')">TX</button>
            </div>
          </div>
        </div>
      </section>

      <section class="frame panel last-panel">
        <h2 class="panel-title">Last Submitted Task</h2>
        <pre class="last-json" id="lastSubmitted">__LAST_TASK_JSON__</pre>
        <div class="note-line">NOTE: Queue only. No task execution.</div>
      </section>

      <section class="frame panel tasks-panel">
        <h2 class="panel-title">Recent Tasks</h2>
        <div class="table-wrap">
          <table>
            <thead><tr><th>ID</th><th>KIND</th><th>STATE</th><th>PRIORITY</th><th>RECEIVED</th></tr></thead>
            <tbody id="tasksBody">__TASK_ROWS__</tbody>
          </table>
        </div>
      </section>
    </main>

    <footer class="frame footer">
      <div>LeafOS Serve Leaf v__VERSION__</div>
      <div class="footer-nav">
        <span>[R] Refresh</span>
        <span>[L] Logs</span>
        <span>[Q] Quit</span>
      </div>
      <div class="footer-status">STATUS: <span id="footerStatus">IDLE</span></div>
    </footer>
  </div>

  <script>
    const streamHz = __STREAM_HZ__;
    const brainLabel = __BRAIN_LABEL_JS__;
    const maxLines = 240;
    const cpuHistory = new Array(48).fill(0);
    const netHistory = new Array(48).fill(0);

    function clampValue(value, low, high) {
      return Math.max(low, Math.min(high, value));
    }

    function fmtBytes(value) {
      if (value === null || value === undefined || Number.isNaN(Number(value))) return '--';
      const units = ['B', 'KB', 'MB', 'GB', 'TB'];
      let size = Number(value);
      let index = 0;
      while (size >= 1024 && index < units.length - 1) {
        size = size / 1024;
        index += 1;
      }
      return `${size.toFixed(index === 0 ? 0 : 1)} ${units[index]}`;
    }

    function fmtRate(value) {
      const bytes = fmtBytes(value);
      return bytes === '--' ? '--' : `${bytes}/s`;
    }

    function fmtUptime(seconds) {
      const total = Math.max(0, Math.floor(Number(seconds) || 0));
      const h = String(Math.floor(total / 3600)).padStart(2, '0');
      const m = String(Math.floor((total % 3600) / 60)).padStart(2, '0');
      const s = String(total % 60).padStart(2, '0');
      return `${h}:${m}:${s}`;
    }

    function setText(id, value) {
      const el = document.getElementById(id);
      if (el) el.textContent = value;
    }

    function setBar(id, percent) {
      const el = document.getElementById(id);
      if (el) el.style.width = `${clampValue(Number(percent) || 0, 0, 100)}%`;
    }

    function drawSpark(id, values, maxValue = 100) {
      const canvas = document.getElementById(id);
      if (!canvas) return;
      const ctx = canvas.getContext('2d');
      const w = canvas.width;
      const h = canvas.height;
      ctx.clearRect(0, 0, w, h);
      ctx.fillStyle = 'rgba(0, 12, 8, 0.92)';
      ctx.fillRect(0, 0, w, h);
      ctx.strokeStyle = 'rgba(98, 240, 107, 0.22)';
      ctx.lineWidth = 1;
      for (let i = 0; i < 4; i += 1) {
        const y = (h / 4) * i;
        ctx.beginPath();
        ctx.moveTo(0, y);
        ctx.lineTo(w, y);
        ctx.stroke();
      }
      ctx.strokeStyle = '#62f06b';
      ctx.lineWidth = 2;
      ctx.beginPath();
      values.forEach((value, index) => {
        const x = (index / Math.max(1, values.length - 1)) * w;
        const y = h - (clampValue(value, 0, maxValue) / maxValue) * (h - 4) - 2;
        if (index === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      });
      ctx.stroke();
    }

    function renderPairs(targetId, rows, valueFactory) {
      const target = document.getElementById(targetId);
      target.textContent = '';
      if (!rows || !rows.length) {
        const row = document.createElement('div');
        const name = document.createElement('span');
        const value = document.createElement('span');
        name.textContent = 'No sensor';
        value.textContent = '--';
        row.append(name, value);
        target.appendChild(row);
        return;
      }
      rows.slice(0, 6).forEach((item) => {
        const row = document.createElement('div');
        const name = document.createElement('span');
        const value = document.createElement('span');
        name.textContent = item.name || 'sensor';
        value.textContent = valueFactory(item);
        row.append(name, value);
        target.appendChild(row);
      });
    }

    function renderMonitor(data) {
      setText('systemHost', data.host || '--');
      setText('uptime', fmtUptime(data.uptime_seconds));
      setText('clock', data.time ? data.time.replace('T', ' ').replace(/([+-]\\d\\d:\\d\\d|Z)$/, '') : new Date().toLocaleString());

      const cpu = data.cpu || {};
      const cpuPct = Number(cpu.percent) || 0;
      cpuHistory.push(cpuPct);
      cpuHistory.shift();
      setText('cpuPct', cpuPct.toFixed(1));
      setText('cpuSource', cpu.estimated ? 'EST' : (cpu.source || 'REAL'));
      setText('cpuName', cpu.name || 'CPU');
      const physical = cpu.physical_cores ? `${cpu.physical_cores}P / ` : '';
      setText('cpuCores', `${physical}${cpu.logical_cores || '--'} logical`);
      drawSpark('cpuSpark', cpuHistory);

      const memory = data.memory || {};
      setText('ramUsed', fmtBytes(memory.used));
      setText('ramTotal', fmtBytes(memory.total));
      setText('ramPct', `${(Number(memory.percent) || 0).toFixed(0)}%`);
      setBar('ramBar', memory.percent);

      const gpu = (data.gpus && data.gpus[0]) || {};
      const vramTotal = Number(gpu.memory_total_mib || 0) * 1024 * 1024;
      const vramUsed = Number(gpu.memory_used_mib || 0) * 1024 * 1024;
      const vramPct = vramTotal > 0 ? (vramUsed / vramTotal) * 100 : 0;
      setText('vramUsed', vramTotal > 0 ? fmtBytes(vramUsed) : '--');
      setText('vramTotal', vramTotal > 0 ? fmtBytes(vramTotal) : '--');
      setText('vramPct', vramTotal > 0 ? `${vramPct.toFixed(0)}%` : '--%');
      setText('gpuName', gpu.name || 'GPU telemetry unavailable');
      setBar('vramBar', vramPct);

      const disk = data.disk || {};
      setText('diskUsed', fmtBytes(disk.used));
      setText('diskTotal', fmtBytes(disk.total));
      setText('diskPct', `${(Number(disk.percent) || 0).toFixed(0)}%`);
      setText('diskPath', disk.path || '--');
      setBar('diskBar', disk.percent);

      const network = data.network || {};
      const netCombined = Math.min(100, ((Number(network.recv_bps) || 0) + (Number(network.sent_bps) || 0)) / 2048);
      netHistory.push(netCombined);
      netHistory.shift();
      setText('netDown', fmtRate(network.recv_bps));
      setText('netUp', fmtRate(network.sent_bps));
      setText('netSource', network.estimated ? 'EST' : (network.source || 'REAL'));
      drawSpark('netSpark', netHistory);

      renderPairs('tempList', data.temperatures, (item) => `${Number(item.celsius || 0).toFixed(1)} C${item.estimated ? ' EST' : ''}`);
      renderPairs('fanList', data.fans, (item) => {
        const rpm = item.rpm ? `${item.rpm} RPM` : '';
        const pct = item.percent !== null && item.percent !== undefined ? `${Number(item.percent).toFixed(0)}%` : '';
        const suffix = item.estimated ? ' EST' : '';
        return `${rpm || pct || '--'}${suffix}`;
      });
      const tempEstimated = (data.temperatures || []).some((item) => item.estimated);
      const fanEstimated = (data.fans || []).some((item) => item.estimated);
      setText('tempSource', tempEstimated ? 'EST' : 'REAL');
      setText('fanSource', fanEstimated ? 'EST' : 'REAL');

      const counts = data.task_counts || {};
      const running = Number(counts.running || 0);
      const inbox = Number(counts.inbox || 0);
      setText('footerStatus', running > 0 ? 'RUNNING' : inbox > 0 ? 'QUEUED' : 'IDLE');
    }

    async function refreshMonitor() {
      try {
        const response = await fetch('/api/monitor', { cache: 'no-store' });
        if (!response.ok) return;
        renderMonitor(await response.json());
      } catch (_) {
        setText('footerStatus', 'MONITOR LOST');
      }
    }

    async function refreshStatus() {
      try {
        const response = await fetch('/api/status', { cache: 'no-store' });
        if (!response.ok) return;
        const data = await response.json();
        setText('statusJson', JSON.stringify(data, null, 2));
      } catch (_) {
      }
    }

    function appendTaskCell(row, value) {
      const cell = document.createElement('td');
      cell.textContent = value === undefined || value === null ? '' : String(value);
      row.appendChild(cell);
    }

    async function refreshTasks() {
      try {
        const response = await fetch('/api/tasks?limit=12', { cache: 'no-store' });
        if (!response.ok) return;
        const data = await response.json();
        const tasks = data.tasks || [];
        const body = document.getElementById('tasksBody');
        body.textContent = '';
        if (!tasks.length) {
          const row = document.createElement('tr');
          const cell = document.createElement('td');
          cell.colSpan = 5;
          cell.className = 'empty';
          cell.textContent = 'No submitted tasks yet.';
          row.appendChild(cell);
          body.appendChild(row);
          return;
        }
        tasks.forEach((task, index) => {
          const row = document.createElement('tr');
          appendTaskCell(row, task.id);
          appendTaskCell(row, task.kind);
          appendTaskCell(row, task.state);
          appendTaskCell(row, task.priority);
          appendTaskCell(row, task.received_at);
          body.appendChild(row);
          if (index === 0) setText('lastSubmitted', JSON.stringify(task, null, 2));
        });
      } catch (_) {
      }
    }

    function appendLine(targetId, msg) {
      const target = document.getElementById(targetId);
      const line = `[${msg.time || new Date().toISOString()}] ${msg.channel || 'text'}/${msg.direction || 'in'} ${msg.source || 'unknown'}: ${msg.text || ''}`;
      target.textContent += line + "\\n";
      const lines = target.textContent.split("\\n");
      if (lines.length > maxLines) {
        target.textContent = lines.slice(lines.length - maxLines).join("\\n");
      }
      target.scrollTop = target.scrollHeight;
    }

    function connectStream(targetId, stateId, url) {
      const state = document.getElementById(stateId);
      const events = new EventSource(url);
      events.addEventListener('open', () => {
        state.textContent = `live ${streamHz} Hz`;
      });
      events.addEventListener('text', event => {
        state.textContent = `live ${streamHz} Hz`;
        appendLine(targetId, JSON.parse(event.data));
      });
      events.addEventListener('tick', event => {
        const data = JSON.parse(event.data);
        state.textContent = `tick ${data.hz} Hz`;
      });
      events.addEventListener('error', () => {
        state.textContent = 'reconnecting';
      });
    }

    async function sendText(channel) {
      const input = document.getElementById(channel === 'brain' ? 'brainInput' : 'textInput');
      const path = channel === 'brain' ? '/api/brain' : '/api/text';
      const text = input.value;
      if (!text.trim()) return;
      const response = await fetch(path, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text, source: 'browser' })
      });
      if (response.ok) {
        input.value = '';
      }
    }

    async function submitTask() {
      const out = document.getElementById('submitResult');
      try {
        const body = JSON.parse(document.getElementById('taskPayload').value);
        const response = await fetch('/api/tasks', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body)
        });
        const data = await response.json();
        out.textContent = JSON.stringify(data, null, 2);
        setText('lastSubmitted', JSON.stringify(data, null, 2));
        refreshStatus();
        refreshTasks();
        refreshMonitor();
      } catch (err) {
        out.textContent = String(err);
      }
    }

    document.addEventListener('keydown', (event) => {
      if (event.key.toLowerCase() === 'r' && !['INPUT', 'TEXTAREA'].includes(document.activeElement.tagName)) {
        refreshStatus();
        refreshTasks();
        refreshMonitor();
      }
      if (event.key.toLowerCase() === 'l' && !['INPUT', 'TEXTAREA'].includes(document.activeElement.tagName)) {
        window.open('/api/events', '_blank');
      }
      if (event.key.toLowerCase() === 'q' && !['INPUT', 'TEXTAREA'].includes(document.activeElement.tagName)) {
        setText('footerStatus', 'LOCAL PAGE READY');
      }
    });

    connectStream('textStream', 'textStreamState', `/api/text/stream?hz=${streamHz}`);
    connectStream('brainStream', 'brainStreamState', `/api/brain/stream?hz=${streamHz}`);
    refreshMonitor();
    refreshStatus();
    refreshTasks();
    setInterval(refreshMonitor, 1000);
    setInterval(refreshStatus, 2500);
    setInterval(refreshTasks, 3000);
  </script>
</body>
</html>"""
        return (
            template.replace("__VERSION__", html.escape(VERSION))
            .replace("__HOST__", html.escape(str(status.get("host", ""))))
            .replace("__STATUS_JSON__", status_json)
            .replace("__TASK_DEFAULT__", task_default_json)
            .replace("__TASK_ROWS__", task_rows)
            .replace("__LAST_TASK_JSON__", last_task_json)
            .replace("__BRAIN_LABEL__", brain_label)
            .replace("__BRAIN_LABEL_JS__", brain_label_js)
            .replace("__STREAM_HZ__", str(stream_hz))
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Serve a tiny LeafOS browser/API surface.")
    parser.add_argument("--host", default="127.0.0.1", help="bind host; use 0.0.0.0 for LAN")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"bind port, default {DEFAULT_PORT}")
    parser.add_argument("--root", default=str(Path(__file__).resolve().parents[1]), help="leafos_taskpack root")
    parser.add_argument("--stream-hz", type=int, default=20, help="SSE heartbeat/update rate, 1..60 Hz")
    parser.add_argument("--brain-label", default="0.0.0.2", help="label shown for the brain text lane")
    parser.add_argument("--no-open", action="store_true", help="print URL only; do not open a browser")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = Path(args.root).resolve()
    if not root.exists():
        print(f"serve-leaf: root not found: {root}", file=sys.stderr)
        return 2
    if args.host.startswith("0.0.0.") and args.host != "0.0.0.0":
        print(
            f"serve-leaf: {args.host} is a lane-style label, not a normal bind host; binding 0.0.0.0 instead.",
            file=sys.stderr,
        )
        args.host = "0.0.0.0"
    store = LeafStore(root)
    store.brain_label = args.brain_label
    store.stream_hz = max(1, min(60, int(args.stream_hz)))
    store.ensure()
    server = ThreadingHTTPServer((args.host, args.port), LeafHandler)
    server.store = store  # type: ignore[attr-defined]
    server.bind_host = args.host  # type: ignore[attr-defined]
    server.bind_port = args.port  # type: ignore[attr-defined]
    server.stream_hz = store.stream_hz  # type: ignore[attr-defined]
    url_host = "127.0.0.1" if args.host == "0.0.0.0" else args.host
    url = f"http://{url_host}:{args.port}/"
    if args.host == "0.0.0.0":
        print("serve-leaf: warning: binding to all interfaces with no auth.", file=sys.stderr)
    print(f"serve-leaf: {url}")
    print("serve-leaf: Ctrl+C to stop")
    try:
        if not args.no_open:
            import webbrowser

            webbrowser.open(url)
        store.append_event("serve_leaf", "server started", host=args.host, port=args.port)
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nserve-leaf: stopped")
    finally:
        store.append_event("serve_leaf", "server stopped", host=args.host, port=args.port)
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
