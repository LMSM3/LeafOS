"""Guarded sequential execution for MOE-001 benchmark plans."""

from __future__ import annotations

import ctypes
import json
import os
import shutil
import subprocess
import time
from ctypes import wintypes
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from .plan import PLAN_SCHEMA
from .util import atomic_write_json, atomic_write_text, sha256_file, utc_now


RUN_SCHEMA = "leafos.moe.benchmark-run/0.1"


class ExecutionRefused(RuntimeError):
    pass


def _safe_name(entry_id: str) -> str:
    return "".join(character if character.isalnum() or character in "-_" else "_" for character in entry_id)


def _validate_command(entry: Dict[str, Any], provider: Dict[str, Any]) -> None:
    command = entry.get("command")
    if not isinstance(command, list) or not command or not all(isinstance(item, str) for item in command):
        raise ExecutionRefused(f"{entry.get('entry_id')}: command must be a non-empty string array")
    executable = str(Path(provider["executable"]).expanduser().resolve())
    if str(Path(command[0]).expanduser().resolve()) != executable:
        raise ExecutionRefused(f"{entry.get('entry_id')}: command executable differs from the probed provider")
    if "--offline" not in command:
        raise ExecutionRefused(f"{entry.get('entry_id')}: command must force llama.cpp offline mode")
    forbidden = {"--hf-repo", "-hf", "-hfr", "--hf-file", "-hff", "--hf-token", "-hft", "--rpc", "-rpc"}
    if forbidden.intersection(command):
        raise ExecutionRefused(f"{entry.get('entry_id')}: command contains a network or remote-provider option")
    try:
        model_index = command.index("--model") + 1
        model_argument = str(Path(command[model_index]).expanduser().resolve())
    except (ValueError, IndexError):
        raise ExecutionRefused(f"{entry.get('entry_id')}: command has no valid --model argument")
    expected_model = str(Path(entry["absolute_path"]).expanduser().resolve())
    if model_argument != expected_model:
        raise ExecutionRefused(f"{entry.get('entry_id')}: command model differs from the planned artifact")
    if not Path(expected_model).is_file():
        raise ExecutionRefused(f"{entry.get('entry_id')}: model artifact no longer exists")
    if entry.get("placement_id") == "cpu-strict-16t":
        strict_options = {
            "--n-gpu-layers": "0",
            "--device": "none",
            "--no-op-offload": "1",
        }
        for option, expected in strict_options.items():
            try:
                actual = command[command.index(option) + 1]
            except (ValueError, IndexError):
                raise ExecutionRefused(
                    f"{entry.get('entry_id')}: strict CPU placement requires {option} {expected}"
                )
            if actual.casefold() != expected:
                raise ExecutionRefused(
                    f"{entry.get('entry_id')}: strict CPU placement requires {option} {expected}, got {actual}"
                )


def _filetime_seconds(value: Any) -> float:
    return ((int(value.dwHighDateTime) << 32) + int(value.dwLowDateTime)) / 10_000_000.0


def _windows_process_sample(pid: int) -> Optional[Dict[str, Any]]:
    if os.name != "nt":
        return None

    class PROCESS_MEMORY_COUNTERS_EX(ctypes.Structure):
        _fields_ = [
            ("cb", wintypes.DWORD),
            ("PageFaultCount", wintypes.DWORD),
            ("PeakWorkingSetSize", ctypes.c_size_t),
            ("WorkingSetSize", ctypes.c_size_t),
            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
            ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
            ("PagefileUsage", ctypes.c_size_t),
            ("PeakPagefileUsage", ctypes.c_size_t),
            ("PrivateUsage", ctypes.c_size_t),
        ]

    class IO_COUNTERS(ctypes.Structure):
        _fields_ = [
            ("ReadOperationCount", ctypes.c_ulonglong),
            ("WriteOperationCount", ctypes.c_ulonglong),
            ("OtherOperationCount", ctypes.c_ulonglong),
            ("ReadTransferCount", ctypes.c_ulonglong),
            ("WriteTransferCount", ctypes.c_ulonglong),
            ("OtherTransferCount", ctypes.c_ulonglong),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    kernel32.GetProcessTimes.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(wintypes.FILETIME),
        ctypes.POINTER(wintypes.FILETIME),
        ctypes.POINTER(wintypes.FILETIME),
        ctypes.POINTER(wintypes.FILETIME),
    ]
    kernel32.GetProcessTimes.restype = wintypes.BOOL
    kernel32.GetProcessIoCounters.argtypes = [wintypes.HANDLE, ctypes.POINTER(IO_COUNTERS)]
    kernel32.GetProcessIoCounters.restype = wintypes.BOOL
    psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD]
    psapi.GetProcessMemoryInfo.restype = wintypes.BOOL

    process_query_limited_information = 0x1000
    process_vm_read = 0x0010
    handle = kernel32.OpenProcess(
        process_query_limited_information | process_vm_read,
        False,
        pid,
    )
    if not handle:
        return None
    try:
        counters = PROCESS_MEMORY_COUNTERS_EX()
        counters.cb = ctypes.sizeof(counters)
        memory_ok = psapi.GetProcessMemoryInfo(
            handle,
            ctypes.byref(counters),
            counters.cb,
        )
        creation = wintypes.FILETIME()
        exit_time = wintypes.FILETIME()
        kernel_time = wintypes.FILETIME()
        user_time = wintypes.FILETIME()
        times_ok = kernel32.GetProcessTimes(
            handle,
            ctypes.byref(creation),
            ctypes.byref(exit_time),
            ctypes.byref(kernel_time),
            ctypes.byref(user_time),
        )
        io = IO_COUNTERS()
        io_ok = kernel32.GetProcessIoCounters(handle, ctypes.byref(io))
        return {
            "sampled_at": utc_now(),
            "source": "win32-process",
            "rss_bytes": int(counters.WorkingSetSize) if memory_ok else None,
            "peak_rss_bytes": int(counters.PeakWorkingSetSize) if memory_ok else None,
            "page_fault_count": int(counters.PageFaultCount) if memory_ok else None,
            "cpu_user_seconds": _filetime_seconds(user_time) if times_ok else None,
            "cpu_kernel_seconds": _filetime_seconds(kernel_time) if times_ok else None,
            "io_read_bytes": int(io.ReadTransferCount) if io_ok else None,
            "io_write_bytes": int(io.WriteTransferCount) if io_ok else None,
        }
    finally:
        kernel32.CloseHandle(handle)


def _linux_process_sample(pid: int) -> Optional[Dict[str, Any]]:
    status = Path(f"/proc/{pid}/status")
    if not status.is_file():
        return None
    rss = None
    peak_rss = None
    try:
        for line in status.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("VmRSS:"):
                rss = int(line.split()[1]) * 1024
            elif line.startswith("VmHWM:"):
                peak_rss = int(line.split()[1]) * 1024
    except (OSError, ValueError, IndexError):
        return None

    user_seconds = None
    kernel_seconds = None
    try:
        stat_text = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8", errors="replace")
        fields = stat_text.rsplit(")", 1)[1].split()
        ticks = float(os.sysconf("SC_CLK_TCK"))
        user_seconds = float(fields[11]) / ticks
        kernel_seconds = float(fields[12]) / ticks
    except (OSError, ValueError, IndexError):
        pass

    io_values: Dict[str, int] = {}
    try:
        for line in Path(f"/proc/{pid}/io").read_text(encoding="utf-8", errors="replace").splitlines():
            key, value = line.split(":", 1)
            if key in {"read_bytes", "write_bytes"}:
                io_values[key] = int(value.strip())
    except (OSError, ValueError):
        pass
    return {
        "sampled_at": utc_now(),
        "source": "procfs",
        "rss_bytes": rss,
        "peak_rss_bytes": peak_rss,
        "page_fault_count": None,
        "cpu_user_seconds": user_seconds,
        "cpu_kernel_seconds": kernel_seconds,
        "io_read_bytes": io_values.get("read_bytes"),
        "io_write_bytes": io_values.get("write_bytes"),
    }


def process_resource_sample(pid: int) -> Optional[Dict[str, Any]]:
    return _windows_process_sample(pid) if os.name == "nt" else _linux_process_sample(pid)


def process_rss_bytes(pid: int) -> Optional[int]:
    sample = process_resource_sample(pid)
    return int(sample["rss_bytes"]) if sample and sample.get("rss_bytes") is not None else None


def _nvidia_sample() -> Optional[Dict[str, Any]]:
    executable = shutil.which("nvidia-smi")
    if not executable:
        return None
    query = "name,utilization.gpu,memory.used,memory.total,temperature.gpu,power.draw"
    try:
        result = subprocess.run(
            [executable, f"--query-gpu={query}", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0 or not result.stdout.strip():
        return None
    rows = []
    for line in result.stdout.splitlines():
        parts = [item.strip() for item in line.split(",")]
        if len(parts) != 6:
            continue
        try:
            rows.append(
                {
                    "name": parts[0],
                    "utilization_percent": float(parts[1]),
                    "memory_used_mib": float(parts[2]),
                    "memory_total_mib": float(parts[3]),
                    "temperature_c": float(parts[4]),
                    "power_w": float(parts[5]),
                }
            )
        except ValueError:
            continue
    return {
        "sampled_at": utc_now(),
        "source": "nvidia-smi",
        "scope": "device_total",
        "gpus": rows,
    } if rows else None


def _validate_artifact_evidence(entry: Dict[str, Any], hash_cache: Dict[str, str]) -> None:
    source = Path(entry["absolute_path"]).expanduser().resolve()
    if not source.is_file():
        raise ExecutionRefused(f"{entry.get('entry_id')}: model artifact no longer exists")
    stat = source.stat()
    expected_bytes = entry.get("bytes")
    if expected_bytes is not None and stat.st_size != int(expected_bytes):
        raise ExecutionRefused(f"{entry.get('entry_id')}: model size changed; create a new inventory and plan")
    expected_mtime = entry.get("modified_at_ns")
    if expected_mtime is not None and stat.st_mtime_ns != int(expected_mtime):
        raise ExecutionRefused(f"{entry.get('entry_id')}: model modification time changed; create a new inventory and plan")
    expected_hash = entry.get("content_sha256")
    if expected_hash:
        key = str(source)
        digest = hash_cache.get(key)
        if digest is None:
            digest = sha256_file(source)
            hash_cache[key] = digest
        if digest != expected_hash:
            raise ExecutionRefused(f"{entry.get('entry_id')}: model SHA-256 differs from the plan")


def _telemetry_summary(
    gpu_samples: List[Dict[str, Any]],
    process_samples: List[Dict[str, Any]],
    duration_seconds: float,
) -> Dict[str, Any]:
    gpu_rows = [gpu for sample in gpu_samples for gpu in sample.get("gpus", [])]

    def maximum(key: str) -> Optional[float]:
        values = [float(row[key]) for row in gpu_rows if row.get(key) is not None]
        return max(values) if values else None

    def process_maximum(key: str) -> Optional[float]:
        values = [float(row[key]) for row in process_samples if row.get(key) is not None]
        return max(values) if values else None

    user_seconds = process_maximum("cpu_user_seconds") or 0.0
    kernel_seconds = process_maximum("cpu_kernel_seconds") or 0.0
    cpu_seconds = user_seconds + kernel_seconds
    return {
        "gpu_sample_count": len(gpu_samples),
        "process_sample_count": len(process_samples),
        "process_peak_rss_bytes": process_maximum("peak_rss_bytes") or process_maximum("rss_bytes"),
        "process_cpu_user_seconds": user_seconds if process_samples else None,
        "process_cpu_kernel_seconds": kernel_seconds if process_samples else None,
        "process_average_cpu_cores": cpu_seconds / duration_seconds if duration_seconds > 0 and process_samples else None,
        "process_io_read_bytes": process_maximum("io_read_bytes"),
        "process_io_write_bytes": process_maximum("io_write_bytes"),
        "process_page_fault_count": process_maximum("page_fault_count"),
        "gpu_peak_utilization_percent": maximum("utilization_percent"),
        "gpu_peak_memory_used_mib": maximum("memory_used_mib"),
        "gpu_peak_temperature_c": maximum("temperature_c"),
        "gpu_peak_power_w": maximum("power_w"),
    }


def _gpu_envelope(gpu_samples: List[Dict[str, Any]]) -> Dict[str, Any]:
    gpu_rows = [gpu for sample in gpu_samples for gpu in sample.get("gpus", [])]

    def bounds(key: str) -> Dict[str, Optional[float]]:
        values = [float(row[key]) for row in gpu_rows if row.get(key) is not None]
        return {
            "minimum": min(values) if values else None,
            "maximum": max(values) if values else None,
        }

    return {
        "sample_count": len(gpu_samples),
        "scope": "device_total",
        "memory_used_mib": bounds("memory_used_mib"),
        "utilization_percent": bounds("utilization_percent"),
        "temperature_c": bounds("temperature_c"),
        "power_w": bounds("power_w"),
    }


def _parse_jsonl(stdout: str) -> List[Dict[str, Any]]:
    rows = []
    for line in stdout.splitlines():
        candidate = line.strip()
        if not candidate.startswith("{"):
            continue
        try:
            value = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            rows.append(value)
    return rows


def _execute_entry(
    entry: Dict[str, Any],
    provider: Dict[str, Any],
    run_directory: Path,
    timeout_seconds: float,
    telemetry_interval_seconds: float,
) -> Dict[str, Any]:
    _validate_command(entry, provider)
    command = list(entry["command"])
    background_gpu_telemetry: List[Dict[str, Any]] = []
    for sample_index in range(5):
        background_sample = _nvidia_sample()
        if background_sample:
            background_gpu_telemetry.append(background_sample)
        if sample_index < 4:
            time.sleep(telemetry_interval_seconds)
    started_at = utc_now()
    started = time.perf_counter()
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
    process = subprocess.Popen(
        command,
        cwd=str(run_directory),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        shell=False,
        creationflags=creationflags,
    )
    gpu_telemetry: List[Dict[str, Any]] = []
    process_telemetry: List[Dict[str, Any]] = []
    timed_out = False
    while process.poll() is None:
        elapsed = time.perf_counter() - started
        if elapsed > timeout_seconds:
            timed_out = True
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
            break
        process_sample = process_resource_sample(process.pid)
        if process_sample:
            process_telemetry.append(process_sample)
        sample = _nvidia_sample()
        if sample:
            gpu_telemetry.append(sample)
        time.sleep(telemetry_interval_seconds)

    stdout, stderr = process.communicate()
    duration = time.perf_counter() - started
    safe = _safe_name(entry["entry_id"])
    stdout_path = run_directory / f"{safe}.stdout.txt"
    stderr_path = run_directory / f"{safe}.stderr.txt"
    atomic_write_text(stdout_path, stdout)
    atomic_write_text(stderr_path, stderr)
    rows = _parse_jsonl(stdout)
    status = "timed_out" if timed_out else ("succeeded" if process.returncode == 0 and rows else "failed")
    promotion_blockers = list(entry.get("promotion_blockers", []))
    if status != "succeeded":
        promotion_blockers.append("benchmark_execution_failed")
    return {
        "entry_id": entry["entry_id"],
        "status": status,
        "started_at": started_at,
        "completed_at": utc_now(),
        "duration_seconds": duration,
        "return_code": process.returncode,
        "command": command,
        "benchmark_rows": rows,
        "telemetry": {
            "summary": _telemetry_summary(gpu_telemetry, process_telemetry, duration),
            "background_gpu_envelope": _gpu_envelope(background_gpu_telemetry),
            "background_gpu_samples": background_gpu_telemetry,
            "gpu_samples": gpu_telemetry,
            "process_samples": process_telemetry,
        },
        "stdout": {"path": str(stdout_path), "sha256": sha256_file(stdout_path)},
        "stderr": {"path": str(stderr_path), "sha256": sha256_file(stderr_path)},
        "promotion": {
            "eligible": status == "succeeded" and not promotion_blockers,
            "blockers": sorted(set(promotion_blockers)),
        },
    }


def run_plan(
    plan: Dict[str, Any],
    output_root: Path,
    execute: bool,
    selected_entry_ids: Optional[Iterable[str]] = None,
    allow_experimental_identity: bool = False,
    timeout_seconds: float = 1800,
    telemetry_interval_seconds: float = 0.5,
) -> Dict[str, Any]:
    if not execute:
        raise ExecutionRefused("Benchmark execution requires the explicit --execute flag")
    if plan.get("schema") != PLAN_SCHEMA:
        raise ValueError(f"Plan schema must be {PLAN_SCHEMA!r}")
    if timeout_seconds <= 0 or telemetry_interval_seconds <= 0:
        raise ValueError("Timeout and telemetry interval must be positive")

    provider = plan["provider"]
    executable = Path(provider["executable"]).expanduser().resolve()
    if not executable.is_file():
        raise ExecutionRefused(f"Probed provider no longer exists: {executable}")
    current_hash = sha256_file(executable)
    if current_hash != provider["executable_sha256"]:
        raise ExecutionRefused("Provider executable hash differs from the probe; create a new plan")

    selected = set(selected_entry_ids or [])
    entries = [item for item in plan["entries"] if not selected or item["entry_id"] in selected]
    unknown = selected - {item["entry_id"] for item in entries}
    if unknown:
        raise ExecutionRefused(f"Unknown selected entry IDs: {sorted(unknown)}")
    if not entries:
        raise ExecutionRefused("No benchmark entries selected")

    hash_cache: Dict[str, str] = {}
    for entry in entries:
        if not entry.get("ready"):
            continue
        if entry.get("requires_experimental_identity_override") and not allow_experimental_identity:
            continue
        _validate_command(entry, provider)
        _validate_artifact_evidence(entry, hash_cache)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    run_id = f"run-{timestamp}-{str(plan['plan_id']).split(':')[-1][:12]}"
    run_directory = output_root.expanduser().resolve() / run_id
    run_directory.mkdir(parents=True, exist_ok=False)
    run_started_at = utc_now()
    results = []
    for entry in entries:
        if not entry.get("ready"):
            results.append(
                {
                    "entry_id": entry["entry_id"],
                    "status": "blocked",
                    "execution_blockers": entry.get("execution_blockers", []),
                    "promotion": {"eligible": False, "blockers": entry.get("promotion_blockers", [])},
                }
            )
            continue
        if entry.get("requires_experimental_identity_override") and not allow_experimental_identity:
            results.append(
                {
                    "entry_id": entry["entry_id"],
                    "status": "blocked",
                    "execution_blockers": ["experimental_identity_override_required"],
                    "promotion": {"eligible": False, "blockers": entry.get("promotion_blockers", [])},
                }
            )
            continue
        results.append(
            _execute_entry(
                entry,
                provider,
                run_directory,
                timeout_seconds,
                telemetry_interval_seconds,
            )
        )

    success = bool(results) and all(item["status"] == "succeeded" for item in results)
    manifest = {
        "schema": RUN_SCHEMA,
        "schema_version": 1,
        "run_id": run_id,
        "plan_id": plan["plan_id"],
        "started_at": run_started_at,
        "completed_at": utc_now(),
        "success": success,
        "experimental_identity_override": allow_experimental_identity,
        "results": results,
    }
    atomic_write_json(run_directory / "run.json", manifest)
    return {**manifest, "manifest_path": str(run_directory / "run.json")}
