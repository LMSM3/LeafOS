#!/usr/bin/env python3
"""Null-safe telemetry recording and optional tensor tracking for LeafOS runs."""

from __future__ import annotations

import argparse
import contextlib
import ctypes
import json
import os
import platform
import shutil
import subprocess
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from leaf_economics import economics_for_tokens

EVENT_TYPES = {
    "run_start", "task_start", "checkpoint", "sample", "tensor_snapshot",
    "validation", "transition", "recovery", "task_end", "run_end",
}

UNIVERSAL_RUN_KINDS = {
    "agent-loop", "catan2bench", "fullstackbench", "continual-live",
    "dual-harness", "overnight", "oneshot", "manual",
}
UNIVERSAL_EVENT_TYPES = {
    "run_start", "sample", "provider_start", "provider_stop", "task_start",
    "task_end", "validation", "checkpoint", "repair", "run_end", "run_error",
}
UNIVERSAL_PHASES = {
    "startup", "planning", "provider_warmup", "brain", "coder", "execution",
    "validation", "checkpoint", "idle", "shutdown", "error",
}
COUNTER_STATUSES = {
    "collected", "not_collected", "unsupported", "permission_denied", "timeout", "estimated",
}
UNIVERSAL_LOG_NAME = "universal-run-log.jsonl"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_event(event: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for key in ("schema_version", "event_id", "recorded_at", "run_id", "event_type", "task_id", "metrics"):
        if key not in event:
            errors.append(f"missing {key}")
    if event.get("schema_version") != 1:
        errors.append("schema_version must be 1")
    if event.get("event_type") not in EVENT_TYPES:
        errors.append("event_type is unsupported")
    if not isinstance(event.get("metrics"), dict):
        errors.append("metrics must be an object")
    tensor = event.get("tensor")
    if event.get("event_type") == "tensor_snapshot" and not isinstance(tensor, dict):
        errors.append("tensor_snapshot requires tensor metadata")
    if tensor is not None:
        for key in ("name", "shape", "dtype", "placement", "bytes"):
            if key not in tensor:
                errors.append(f"tensor missing {key}")
    return errors


def append_event(path: Path, event: dict[str, Any]) -> None:
    errors = validate_event(event)
    if errors:
        raise ValueError("invalid telemetry event: " + "; ".join(errors))
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line)
        handle.flush()
        os.fsync(handle.fileno())


def make_event(run_id: str, task_id: str | None, event_type: str, metrics: dict[str, Any], **extra: Any) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "event_id": str(uuid.uuid4()),
        "recorded_at": utc_now(),
        "run_id": run_id,
        "task_id": task_id,
        "event_type": event_type,
        "metrics": metrics,
        **extra,
    }


def _nullable_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return round(number, 3)


def _empty_hardware() -> dict[str, Any]:
    return {
        "cpu": {
            "utilization_percent": None,
            "process_percent": None,
            "temperature_celsius": None,
            "threads": os.cpu_count(),
        },
        "gpu": {
            "name": None,
            "utilization_percent": None,
            "vram_used_gb": None,
            "vram_total_gb": None,
            "temperature_celsius": None,
            "power_watts": None,
            "backend": None,
            "active_layers": None,
        },
        "memory": {
            "ram_used_gb": None,
            "ram_total_gb": None,
            "page_cache_residency_percent": None,
            "major_page_faults": None,
            "minor_page_faults": None,
        },
        "io": {
            "nvme_read_mb_s": None,
            "nvme_write_mb_s": None,
            "read_latency_ms": None,
            "write_latency_ms": None,
        },
        "power": {
            "total_watts": None,
            "energy_watt_hours": None,
            "tokens_per_watt_hour": None,
        },
    }


def _empty_availability() -> dict[str, str]:
    return {
        "cpu_counters": "not_collected",
        "gpu_counters": "not_collected",
        "vram_counters": "not_collected",
        "power_counters": "not_collected",
        "io_counters": "not_collected",
        "throughput_counters": "not_collected",
    }


def _cpu_sample_windows(interval: float) -> tuple[float | None, float | None, str]:
    class FileTime(ctypes.Structure):
        _fields_ = [("low", ctypes.c_uint32), ("high", ctypes.c_uint32)]

    def integer(value: FileTime) -> int:
        return (int(value.high) << 32) | int(value.low)

    def system_times() -> tuple[int, int, int]:
        idle, kernel, user = FileTime(), FileTime(), FileTime()
        if not ctypes.windll.kernel32.GetSystemTimes(  # type: ignore[attr-defined]
            ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user)
        ):
            raise OSError("GetSystemTimes failed")
        return integer(idle), integer(kernel), integer(user)

    def process_times() -> tuple[int, int]:
        created, exited, kernel, user = FileTime(), FileTime(), FileTime(), FileTime()
        get_current_process = ctypes.windll.kernel32.GetCurrentProcess  # type: ignore[attr-defined]
        get_current_process.restype = ctypes.c_void_p
        handle = get_current_process()
        get_process_times = ctypes.windll.kernel32.GetProcessTimes  # type: ignore[attr-defined]
        get_process_times.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(FileTime),
            ctypes.POINTER(FileTime),
            ctypes.POINTER(FileTime),
            ctypes.POINTER(FileTime),
        ]
        if not get_process_times(
            handle, ctypes.byref(created), ctypes.byref(exited), ctypes.byref(kernel), ctypes.byref(user)
        ):
            raise OSError("GetProcessTimes failed")
        return integer(kernel), integer(user)

    try:
        sys_a, proc_a = system_times(), process_times()
        time.sleep(max(0.02, interval))
        sys_b, proc_b = system_times(), process_times()
        total = (sys_b[1] - sys_a[1]) + (sys_b[2] - sys_a[2])
        idle = sys_b[0] - sys_a[0]
        process = (proc_b[0] - proc_a[0]) + (proc_b[1] - proc_a[1])
        if total <= 0:
            return None, None, "not_collected"
        return (
            round(max(0.0, min(100.0, 100.0 * (total - idle) / total)), 3),
            round(max(0.0, 100.0 * process / total), 3),
            "collected",
        )
    except (AttributeError, OSError):
        return None, None, "not_collected"


def _read_proc_cpu() -> tuple[int, int] | None:
    try:
        parts = (Path("/proc/stat").read_text(encoding="utf-8").splitlines()[0]).split()[1:]
        values = [int(item) for item in parts]
    except (OSError, ValueError, IndexError):
        return None
    idle = values[3] + (values[4] if len(values) > 4 else 0)
    return sum(values), idle


def _cpu_sample_posix(interval: float) -> tuple[float | None, float | None, str]:
    before = _read_proc_cpu()
    process_before = time.process_time()
    if before is None:
        try:
            estimate = min(100.0, 100.0 * os.getloadavg()[0] / max(1, os.cpu_count() or 1))
            return round(estimate, 3), None, "estimated"
        except (AttributeError, OSError):
            return None, None, "unsupported"
    time.sleep(max(0.02, interval))
    after = _read_proc_cpu()
    process_elapsed = time.process_time() - process_before
    if after is None or after[0] <= before[0]:
        return None, None, "not_collected"
    total = after[0] - before[0]
    idle = after[1] - before[1]
    wall = max(interval, 0.02)
    process_percent = 100.0 * process_elapsed / wall / max(1, os.cpu_count() or 1)
    return (
        round(max(0.0, min(100.0, 100.0 * (total - idle) / total)), 3),
        round(max(0.0, process_percent), 3),
        "collected",
    )


def _memory_sample() -> tuple[float | None, float | None, str]:
    gib = float(1024 ** 3)
    if platform.system() == "Windows":
        class MemoryStatus(ctypes.Structure):
            _fields_ = [
                ("length", ctypes.c_ulong), ("memory_load", ctypes.c_ulong),
                ("total_physical", ctypes.c_ulonglong), ("available_physical", ctypes.c_ulonglong),
                ("total_page_file", ctypes.c_ulonglong), ("available_page_file", ctypes.c_ulonglong),
                ("total_virtual", ctypes.c_ulonglong), ("available_virtual", ctypes.c_ulonglong),
                ("available_extended_virtual", ctypes.c_ulonglong),
            ]
        status = MemoryStatus()
        status.length = ctypes.sizeof(MemoryStatus)
        try:
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):  # type: ignore[attr-defined]
                total = status.total_physical / gib
                used = (status.total_physical - status.available_physical) / gib
                return round(used, 3), round(total, 3), "collected"
        except AttributeError:
            pass
        return None, None, "not_collected"
    try:
        values: dict[str, int] = {}
        for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
            key, raw = line.split(":", 1)
            values[key] = int(raw.strip().split()[0]) * 1024
        total_bytes = values["MemTotal"]
        available_bytes = values.get("MemAvailable", values.get("MemFree", 0))
        return round((total_bytes - available_bytes) / gib, 3), round(total_bytes / gib, 3), "collected"
    except (OSError, ValueError, KeyError):
        return None, None, "unsupported"


def _gpu_sample(timeout: float) -> tuple[dict[str, Any], dict[str, str]]:
    empty = _empty_hardware()["gpu"]
    status = {"gpu_counters": "not_collected", "vram_counters": "not_collected", "power_counters": "not_collected"}
    executable = shutil.which("nvidia-smi")
    if not executable:
        return empty, status
    query = "name,utilization.gpu,memory.used,memory.total,temperature.gpu,power.draw"
    try:
        result = subprocess.run(
            [executable, f"--query-gpu={query}", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=max(0.1, timeout),
            check=False,
        )
    except subprocess.TimeoutExpired:
        return empty, {key: "timeout" for key in status}
    except OSError:
        return empty, status
    if result.returncode != 0:
        return empty, status
    rows: list[dict[str, Any]] = []
    for line in result.stdout.splitlines():
        parts = [item.strip() for item in line.split(",")]
        if len(parts) < 6:
            continue
        rows.append({
            "name": parts[0] or None,
            "utilization_percent": _nullable_float(parts[1]),
            "vram_used_gb": None if _nullable_float(parts[2]) is None else round(float(parts[2]) / 1024.0, 3),
            "vram_total_gb": None if _nullable_float(parts[3]) is None else round(float(parts[3]) / 1024.0, 3),
            "temperature_celsius": _nullable_float(parts[4]),
            "power_watts": _nullable_float(parts[5]),
            "backend": "nvidia-smi",
            "active_layers": None,
        })
    if not rows:
        return empty, status
    primary = max(rows, key=lambda row: row.get("utilization_percent") or 0.0)
    status["gpu_counters"] = "collected" if primary["utilization_percent"] is not None else "not_collected"
    status["vram_counters"] = "collected" if primary["vram_used_gb"] is not None else "not_collected"
    status["power_counters"] = "collected" if primary["power_watts"] is not None else "not_collected"
    return primary, status


def _io_sample(timeout: float) -> tuple[dict[str, Any], str]:
    empty = _empty_hardware()["io"]
    if platform.system() != "Windows":
        return empty, "unsupported"
    powershell = shutil.which("pwsh") or shutil.which("powershell")
    if not powershell:
        return empty, "not_collected"
    command = (
        "$x=Get-CimInstance Win32_PerfFormattedData_PerfDisk_PhysicalDisk "
        "-Filter \"Name='_Total'\" -ErrorAction Stop; "
        "[pscustomobject]@{read_bps=$x.DiskReadBytesPersec;write_bps=$x.DiskWriteBytesPersec;"
        "read_latency_ms=([double]$x.AvgDisksecPerRead*1000);"
        "write_latency_ms=([double]$x.AvgDisksecPerWrite*1000)} | ConvertTo-Json -Compress"
    )
    try:
        result = subprocess.run(
            [powershell, "-NoProfile", "-Command", command],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=max(0.5, timeout),
            check=False,
        )
    except subprocess.TimeoutExpired:
        return empty, "timeout"
    except OSError:
        return empty, "not_collected"
    if result.returncode != 0 or not result.stdout.strip():
        return empty, "not_collected"
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return empty, "not_collected"
    read_bps = _nullable_float(payload.get("read_bps"))
    write_bps = _nullable_float(payload.get("write_bps"))
    return {
        "nvme_read_mb_s": round(read_bps / 1_000_000.0, 3) if read_bps is not None else None,
        "nvme_write_mb_s": round(write_bps / 1_000_000.0, 3) if write_bps is not None else None,
        "read_latency_ms": _nullable_float(payload.get("read_latency_ms")),
        "write_latency_ms": _nullable_float(payload.get("write_latency_ms")),
    }, "collected" if read_bps is not None or write_bps is not None else "not_collected"


def collect_universal_hardware(timeout: float = 2.0, cpu_interval: float = 0.1) -> dict[str, Any]:
    """Collect live counters without making any counter mandatory."""
    hardware = _empty_hardware()
    availability = _empty_availability()
    if platform.system() == "Windows":
        cpu, process, cpu_status = _cpu_sample_windows(cpu_interval)
    else:
        cpu, process, cpu_status = _cpu_sample_posix(cpu_interval)
    used, total, _memory_status = _memory_sample()
    gpu, gpu_status = _gpu_sample(timeout)
    io, io_status = _io_sample(timeout)
    hardware["cpu"].update({"utilization_percent": cpu, "process_percent": process})
    hardware["memory"].update({"ram_used_gb": used, "ram_total_gb": total})
    hardware["gpu"] = gpu
    hardware["io"] = io
    hardware["power"]["total_watts"] = gpu.get("power_watts")
    availability["cpu_counters"] = cpu_status
    availability.update(gpu_status)
    availability["io_counters"] = io_status
    return {"hardware": hardware, "availability": availability}


def collect_fast_hardware(timeout: float = 0.25, cpu_interval: float = 0.03) -> dict[str, Any]:
    """Collect low-latency TUI counters without disk or other slow probes."""
    hardware = _empty_hardware()
    availability = _empty_availability()
    if platform.system() == "Windows":
        cpu, process, cpu_status = _cpu_sample_windows(cpu_interval)
    else:
        cpu, process, cpu_status = _cpu_sample_posix(cpu_interval)
    used, total, _memory_status = _memory_sample()
    gpu, gpu_status = _gpu_sample(timeout)
    hardware["cpu"].update({"utilization_percent": cpu, "process_percent": process})
    hardware["memory"].update({"ram_used_gb": used, "ram_total_gb": total})
    hardware["gpu"] = gpu
    hardware["power"]["total_watts"] = gpu.get("power_watts")
    availability["cpu_counters"] = cpu_status
    availability.update(gpu_status)
    availability["io_counters"] = "not_collected"
    return {"hardware": hardware, "availability": availability}


def validate_universal_event(event: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    required = (
        "leafos_object", "schema_version", "event_id", "sequence", "recorded_at",
        "run_id", "run_kind", "event_type", "phase", "instances", "throughput",
        "hardware", "availability",
    )
    for key in required:
        if key not in event:
            errors.append(f"missing {key}")
    if event.get("leafos_object") != "leafos.universal_run_log.event":
        errors.append("leafos_object must be leafos.universal_run_log.event")
    if event.get("schema_version") != 1:
        errors.append("schema_version must be 1")
    if event.get("run_kind") not in UNIVERSAL_RUN_KINDS:
        errors.append("run_kind is unsupported")
    if event.get("event_type") not in UNIVERSAL_EVENT_TYPES:
        errors.append("event_type is unsupported")
    if event.get("phase") not in UNIVERSAL_PHASES:
        errors.append("phase is unsupported")
    if not isinstance(event.get("sequence"), int) or int(event.get("sequence", 0)) < 1:
        errors.append("sequence must be a positive integer")
    instances = event.get("instances")
    if not isinstance(instances, dict):
        errors.append("instances must be an object")
    else:
        for key in ("initiated", "alive"):
            if not isinstance(instances.get(key), int) or instances.get(key, -1) < 0:
                errors.append(f"instances.{key} must be a non-negative integer")
    hardware = event.get("hardware")
    if not isinstance(hardware, dict):
        errors.append("hardware must be an object")
    else:
        for key in ("cpu", "gpu", "memory", "io"):
            if not isinstance(hardware.get(key), dict):
                errors.append(f"hardware.{key} must be an object")
    availability = event.get("availability")
    if not isinstance(availability, dict):
        errors.append("availability must be an object")
    else:
        for key, value in availability.items():
            if value not in COUNTER_STATUSES:
                errors.append(f"availability.{key} has unsupported status")
    economics = event.get("economics")
    if economics is not None and not isinstance(economics, dict):
        errors.append("economics must be an object when present")
    elif isinstance(economics, dict):
        rate = economics.get("comparison_output_usd_per_million")
        if rate is not None and (not isinstance(rate, (int, float)) or isinstance(rate, bool) or rate < 0):
            errors.append("economics comparison rate must be a non-negative number or null")
        gross = economics.get("gross_cloud_equivalent_usd")
        if gross is not None and (not isinstance(gross, (int, float)) or isinstance(gross, bool) or gross < 0):
            errors.append("economics gross value must be a non-negative number or null")
    return errors


def make_universal_event(
    run_id: str,
    run_kind: str,
    event_type: str = "sample",
    phase: str = "idle",
    *,
    sequence: int = 1,
    run_dir: str | Path | None = None,
    task_id: str | None = None,
    project: str | None = None,
    stack: dict[str, Any] | None = None,
    provider: dict[str, Any] | None = None,
    instances: dict[str, Any] | None = None,
    throughput: dict[str, Any] | None = None,
    hardware: dict[str, Any] | None = None,
    scheduler: dict[str, Any] | None = None,
    quality: dict[str, Any] | None = None,
    economics: dict[str, Any] | None = None,
    availability: dict[str, str] | None = None,
    artifacts: list[dict[str, Any]] | None = None,
    notes: list[str] | None = None,
    collect_hardware: bool = True,
) -> dict[str, Any]:
    collected = collect_universal_hardware() if collect_hardware and hardware is None else {
        "hardware": hardware or _empty_hardware(),
        "availability": _empty_availability(),
    }
    availability_value = dict(collected["availability"])
    if availability:
        availability_value.update(availability)
    throughput_value = throughput or {
        "brain_prompt_tk_s": None, "brain_generation_tk_s": None,
        "coder_prompt_tk_s": None, "coder_generation_tk_s": None,
        "helper_generation_tk_s": None, "aggregate_generation_tk_s": None,
        "time_to_first_token_seconds": None, "prompt_tokens": None, "generated_tokens": None,
    }
    if any(value is not None for value in throughput_value.values()):
        availability_value["throughput_counters"] = "collected"
    event = {
        "leafos_object": "leafos.universal_run_log.event",
        "schema_version": 1,
        "event_id": str(uuid.uuid4()),
        "sequence": sequence,
        "recorded_at": utc_now(),
        "run_id": run_id,
        "run_kind": run_kind,
        "run_dir": str(run_dir) if run_dir is not None else None,
        "task_id": task_id,
        "project": project,
        "event_type": event_type,
        "phase": phase,
        "stack": stack or {
            "local_stack_id": None, "brain_stack_entry": None, "coder_stack_entry": None,
            "helper_stack_entry": None, "quantization": None,
        },
        "provider": provider or {"mode": "off", "backend": None, "endpoint": None, "status": "off", "pid": None},
        "instances": instances or {
            "initiated": 0, "alive": 0, "brain_initiated": 0, "brain_alive": 0,
            "coder_initiated": 0, "coder_alive": 0, "provider_initiated": 0,
            "provider_alive": 0, "crashed": 0, "restarted": 0,
        },
        "throughput": throughput_value,
        "hardware": collected["hardware"],
        "scheduler": scheduler or {
            "queue_depth": None, "active_task_count": None, "blocked_task_count": None,
            "repair_task_count": None, "max_concurrency": None,
            "governor_profile": None, "governor_reason": None,
            "cpu_target_percent": None, "gpu_target_percent": None,
            "claim_allowed": None, "input_idle_seconds": None,
            "responsiveness_ms": None, "provider_delay_seconds": None,
        },
        "quality": quality or {
            "validation_status": "unknown", "checkpoint_valid": None,
            "accepted_changes": None, "rejected_changes": None, "score_delta": None,
        },
        "economics": economics or economics_for_tokens(None, scope="unknown"),
        "availability": availability_value,
        "artifacts": artifacts or [],
        "notes": notes or [],
    }
    errors = validate_universal_event(event)
    if errors:
        raise ValueError("invalid universal telemetry event: " + "; ".join(errors))
    return event


def read_universal_events(path: Path) -> list[dict[str, Any]]:
    events = read_events(path)
    for index, event in enumerate(events, start=1):
        errors = validate_universal_event(event)
        if errors:
            raise ValueError(f"invalid universal telemetry at line {index}: " + "; ".join(errors))
        if event.get("sequence") != index:
            raise ValueError(f"universal telemetry sequence mismatch at line {index}")
    return events


def append_universal_event(path: Path, event: dict[str, Any]) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    with _universal_write_lock(path):
        existing = read_universal_events(path) if path.exists() else []
        written = dict(event)
        written["sequence"] = len(existing) + 1
        errors = validate_universal_event(written)
        if errors:
            raise ValueError("invalid universal telemetry event: " + "; ".join(errors))
        with path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(written, ensure_ascii=True, separators=(",", ":")) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        return written


@contextlib.contextmanager
def _universal_write_lock(path: Path):
    lock_path = path.with_name(f".{path.name}.lock")
    with lock_path.open("a+b") as handle:
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
            try:
                yield
            finally:
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _numeric(events: Iterable[dict[str, Any]], *path: str) -> list[float]:
    values: list[float] = []
    for event in events:
        value: Any = event
        for key in path:
            value = value.get(key) if isinstance(value, dict) else None
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            values.append(float(value))
    return values


def summarize_universal_log(events_or_path: Iterable[dict[str, Any]] | Path) -> dict[str, Any]:
    events = read_universal_events(events_or_path) if isinstance(events_or_path, Path) else list(events_or_path)
    samples = [event for event in events if event.get("event_type") == "sample"]
    gpu_low_streak = 0
    gpu_starved = False
    for event in samples:
        alive = event.get("instances", {}).get("alive", 0)
        gpu = event.get("hardware", {}).get("gpu", {}).get("utilization_percent")
        gpu_low_streak = gpu_low_streak + 1 if alive > 0 and isinstance(gpu, (int, float)) and gpu < 35 else 0
        gpu_starved = gpu_starved or gpu_low_streak >= 3
    cpu_bound = any(
        isinstance(event.get("hardware", {}).get("cpu", {}).get("utilization_percent"), (int, float))
        and event["hardware"]["cpu"]["utilization_percent"] > 85
        and isinstance(event.get("hardware", {}).get("gpu", {}).get("utilization_percent"), (int, float))
        and event["hardware"]["gpu"]["utilization_percent"] < 50
        for event in samples
    )
    coder_idle = any(
        event.get("instances", {}).get("coder_alive", 0) > 0
        and (event.get("throughput", {}).get("coder_generation_tk_s") in (None, 0))
        for event in samples
    )
    brain_idle = any(
        event.get("instances", {}).get("brain_alive", 0) > 0
        and (event.get("throughput", {}).get("brain_generation_tk_s") in (None, 0))
        for event in samples
    )
    provider_churn = any(
        (event.get("instances", {}).get("crashed") or 0) > 0
        or (event.get("instances", {}).get("restarted") or 0) > 0
        for event in events
    ) or sum(event.get("event_type") == "provider_start" for event in events) > 1
    brain_rates = _numeric(samples, "throughput", "brain_generation_tk_s")
    coder_rates = _numeric(samples, "throughput", "coder_generation_tk_s")
    gpu_rates = _numeric(samples, "hardware", "gpu", "utilization_percent")
    cpu_rates = _numeric(samples, "hardware", "cpu", "utilization_percent")
    ratios = [
        event["throughput"]["brain_generation_tk_s"] / event["throughput"]["coder_generation_tk_s"]
        for event in samples
        if isinstance(event.get("throughput", {}).get("brain_generation_tk_s"), (int, float))
        and isinstance(event.get("throughput", {}).get("coder_generation_tk_s"), (int, float))
        and event["throughput"]["brain_generation_tk_s"] > 0
        and event["throughput"]["coder_generation_tk_s"] > 0
    ]
    def average(values: list[float]) -> float | None:
        return round(sum(values) / len(values), 3) if values else None
    economic_events = [
        event.get("economics", {}) for event in events
        if event.get("economics", {}).get("token_count_scope") == "interval"
    ]
    gross_values = [
        float(item["gross_cloud_equivalent_usd"]) for item in economic_events
        if isinstance(item.get("gross_cloud_equivalent_usd"), (int, float))
    ]
    local_tokens = [
        float(item["generated_tokens"]) for item in economic_events
        if isinstance(item.get("generated_tokens"), (int, float))
    ]
    return {
        "leafos_object": "leafos.universal_run_log.summary",
        "schema_version": 1,
        "run_id": events[0].get("run_id") if events else None,
        "event_count": len(events),
        "sample_count": len(samples),
        "last_sequence": events[-1].get("sequence", 0) if events else 0,
        "instances": {
            "initiated_peak": max((event.get("instances", {}).get("initiated", 0) for event in events), default=0),
            "alive_peak": max((event.get("instances", {}).get("alive", 0) for event in events), default=0),
        },
        "averages": {
            "brain_generation_tk_s": average(brain_rates),
            "coder_generation_tk_s": average(coder_rates),
            "gpu_utilization_percent": average(gpu_rates),
            "cpu_utilization_percent": average(cpu_rates),
            "brain_coder_ratio": average(ratios),
        },
        "warnings": {
            "gpu_starved": gpu_starved,
            "cpu_bound": cpu_bound,
            "coder_idle": coder_idle,
            "brain_idle": brain_idle,
            "provider_churn": provider_churn,
        },
        "economics": {
            "token_count_scope": "summed_interval_events",
            "generated_tokens": int(sum(local_tokens)),
            "gross_cloud_equivalent_usd": round(sum(gross_values), 8),
            "local_energy_cost_usd": None,
            "net_savings_usd": None,
        },
    }


def tensor_event(run_id: str, task_id: str | None, tensor: dict[str, Any], metrics: dict[str, Any] | None = None) -> dict[str, Any]:
    return make_event(run_id, task_id, "tensor_snapshot", metrics or {}, tensor=tensor)


def read_events(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    events: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError(f"invalid JSONL at line {line_number}: {error.msg}") from error
        if not isinstance(value, dict):
            raise ValueError(f"telemetry line {line_number} must be an object")
        events.append(value)
    return events


def summarize(events: Iterable[dict[str, Any]]) -> dict[str, Any]:
    items = list(events)
    tasks = sorted({item.get("task_id") for item in items if item.get("task_id")})
    tensor_events = [item for item in items if item.get("event_type") == "tensor_snapshot"]
    valid_checkpoints = [item for item in items if item.get("metrics", {}).get("checkpoint_valid") is True]
    rates = [item["metrics"]["generation_tokens_per_second"] for item in items if isinstance(item.get("metrics", {}).get("generation_tokens_per_second"), (int, float))]
    return {
        "leafos_object": "overnight_telemetry_summary",
        "event_count": len(items),
        "task_ids": tasks,
        "tensor_snapshot_count": len(tensor_events),
        "valid_checkpoint_count": len(valid_checkpoints),
        "generation_rate": {
            "samples": len(rates),
            "minimum": min(rates) if rates else None,
            "maximum": max(rates) if rates else None,
            "average": sum(rates) / len(rates) if rates else None,
        },
    }


def cmd_append(args: argparse.Namespace) -> int:
    event = load_json(Path(args.event))
    if not isinstance(event, dict):
        raise ValueError("event file must contain a JSON object")
    append_event(Path(args.log), event)
    print(args.log)
    return 0


def cmd_tensor(args: argparse.Namespace) -> int:
    tensor = load_json(Path(args.tensor))
    if not isinstance(tensor, dict):
        raise ValueError("tensor file must contain a JSON object")
    event = tensor_event(args.run_id, args.task_id, tensor, {"elapsed_seconds": args.elapsed_seconds})
    append_event(Path(args.log), event)
    print(args.log)
    return 0


def cmd_summary(args: argparse.Namespace) -> int:
    summary = summarize(read_events(Path(args.log)))
    output = Path(args.output) if args.output else None
    rendered = json.dumps(summary, indent=2) + "\n"
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=output.parent, delete=False) as handle:
            handle.write(rendered)
            temporary = Path(handle.name)
        temporary.replace(output)
        print(output)
    else:
        print(rendered, end="")
    return 0


def cmd_universal_sample(args: argparse.Namespace) -> int:
    run_dir = Path(args.run_dir).expanduser().resolve()
    event = make_universal_event(
        args.run_id or run_dir.name,
        args.run_kind,
        args.event_type,
        args.phase,
        run_dir=run_dir,
        task_id=args.task_id,
        project=args.project,
        stack={
            "local_stack_id": args.stack_id or None,
            "brain_stack_entry": args.brain_stack_entry or None,
            "coder_stack_entry": args.coder_stack_entry or None,
            "helper_stack_entry": None,
            "quantization": args.quantization or None,
        },
        provider={
            "mode": args.provider_mode,
            "backend": args.provider_backend or None,
            "endpoint": args.provider_endpoint or None,
            "status": args.provider_status,
            "pid": args.provider_pid,
        },
        instances={
            "initiated": args.instances_initiated,
            "alive": args.instances_alive,
            "brain_initiated": args.brain_initiated,
            "brain_alive": args.brain_alive,
            "coder_initiated": args.coder_initiated,
            "coder_alive": args.coder_alive,
            "provider_initiated": args.provider_initiated,
            "provider_alive": args.provider_alive,
            "crashed": args.instances_crashed,
            "restarted": args.instances_restarted,
        },
        throughput={
            "brain_prompt_tk_s": None,
            "brain_generation_tk_s": args.brain_tk_s,
            "coder_prompt_tk_s": None,
            "coder_generation_tk_s": args.coder_tk_s,
            "helper_generation_tk_s": None,
            "aggregate_generation_tk_s": None,
            "time_to_first_token_seconds": None,
            "prompt_tokens": args.prompt_tokens,
            "generated_tokens": args.generated_tokens,
        },
        scheduler={
            "queue_depth": args.queue_depth,
            "active_task_count": args.active_tasks,
            "blocked_task_count": args.blocked_tasks,
            "repair_task_count": args.repair_tasks,
            "max_concurrency": args.max_concurrency,
        },
        quality={
            "validation_status": args.validation_status,
            "checkpoint_valid": None,
            "accepted_changes": None,
            "rejected_changes": None,
            "score_delta": None,
        },
        economics=economics_for_tokens(
            args.generated_tokens,
            {
                "comparison_output_usd_per_million": args.output_usd_per_million,
                "pricing_basis": args.pricing_basis,
            },
            scope=args.token_count_scope,
        ),
        collect_hardware=not args.no_hardware,
    )
    written = append_universal_event(run_dir / UNIVERSAL_LOG_NAME, event)
    print(json.dumps(written, indent=2, ensure_ascii=True) if args.json else str(run_dir / UNIVERSAL_LOG_NAME))
    return 0


def cmd_universal_summary(args: argparse.Namespace) -> int:
    source = Path(args.path).expanduser().resolve()
    log = source / UNIVERSAL_LOG_NAME if source.is_dir() else source
    summary = summarize_universal_log(log)
    rendered = json.dumps(summary, indent=2, ensure_ascii=True) + "\n"
    if args.output:
        output = Path(args.output).expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8")
        print(output)
    else:
        print(rendered, end="")
    return 0


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    commands = result.add_subparsers(dest="command", required=True)
    append = commands.add_parser("append")
    append.add_argument("--log", required=True)
    append.add_argument("--event", required=True)
    tensor = commands.add_parser("tensor")
    tensor.add_argument("--log", required=True)
    tensor.add_argument("--run-id", required=True)
    tensor.add_argument("--task-id")
    tensor.add_argument("--tensor", required=True)
    tensor.add_argument("--elapsed-seconds", type=float, default=0)
    summary = commands.add_parser("summary")
    summary.add_argument("--log", required=True)
    summary.add_argument("--output")
    universal = commands.add_parser("universal-sample", help="append one universal run telemetry sample")
    universal.add_argument("run_dir")
    universal.add_argument("--run-id", default="")
    universal.add_argument("--run-kind", choices=sorted(UNIVERSAL_RUN_KINDS), default="manual")
    universal.add_argument("--event-type", choices=sorted(UNIVERSAL_EVENT_TYPES), default="sample")
    universal.add_argument("--phase", choices=sorted(UNIVERSAL_PHASES), default="idle")
    universal.add_argument("--task-id")
    universal.add_argument("--project")
    universal.add_argument("--stack-id", default="")
    universal.add_argument("--brain-stack-entry", default="")
    universal.add_argument("--coder-stack-entry", default="")
    universal.add_argument("--quantization", default="")
    universal.add_argument("--provider-mode", choices=("off", "mock", "auto", "required", "llamacpp", "ollama", "openai", "other"), default="off")
    universal.add_argument("--provider-backend", default="")
    universal.add_argument("--provider-endpoint", default="")
    universal.add_argument("--provider-status", choices=("off", "starting", "ready", "running", "stopped", "degraded", "failed", "unknown"), default="off")
    universal.add_argument("--provider-pid", type=int)
    universal.add_argument("--instances-initiated", type=int, default=0)
    universal.add_argument("--instances-alive", type=int, default=0)
    universal.add_argument("--brain-initiated", type=int, default=0)
    universal.add_argument("--brain-alive", type=int, default=0)
    universal.add_argument("--coder-initiated", type=int, default=0)
    universal.add_argument("--coder-alive", type=int, default=0)
    universal.add_argument("--provider-initiated", type=int, default=0)
    universal.add_argument("--provider-alive", type=int, default=0)
    universal.add_argument("--instances-crashed", type=int, default=0)
    universal.add_argument("--instances-restarted", type=int, default=0)
    universal.add_argument("--brain-tk-s", type=float)
    universal.add_argument("--coder-tk-s", type=float)
    universal.add_argument("--prompt-tokens", type=int)
    universal.add_argument("--generated-tokens", type=int)
    universal.add_argument("--output-usd-per-million", type=float, default=10.0)
    universal.add_argument("--pricing-basis", choices=("operator_assumption", "provider_quote"), default="operator_assumption")
    universal.add_argument("--token-count-scope", choices=("interval", "cumulative", "unknown"), default="interval")
    universal.add_argument("--queue-depth", type=int)
    universal.add_argument("--active-tasks", type=int)
    universal.add_argument("--blocked-tasks", type=int)
    universal.add_argument("--repair-tasks", type=int)
    universal.add_argument("--max-concurrency", type=int)
    universal.add_argument("--validation-status", choices=("pending", "passed", "failed", "skipped", "unknown"), default="unknown")
    universal.add_argument("--no-hardware", action="store_true")
    universal.add_argument("--json", action="store_true")
    universal_summary = commands.add_parser("universal-summary", help="summarize a universal JSONL log")
    universal_summary.add_argument("path", help="run directory or universal-run-log.jsonl")
    universal_summary.add_argument("--output")
    return result


def main() -> int:
    args = parser().parse_args()
    try:
        return {
            "append": cmd_append,
            "tensor": cmd_tensor,
            "summary": cmd_summary,
            "universal-sample": cmd_universal_sample,
            "universal-summary": cmd_universal_summary,
        }[args.command](args)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"telemetry error: {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
