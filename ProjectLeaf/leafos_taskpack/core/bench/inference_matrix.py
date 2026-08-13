#!/usr/bin/env python3
"""Resumable, condition-aware llama.cpp inference benchmark matrices."""

from __future__ import annotations

import csv
import ctypes
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any, Optional


ROOT = Path(__file__).resolve().parents[2]
PYTHON_DIR = ROOT / "core" / "python"
if str(PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(PYTHON_DIR))

from leaf_economics import benchmark_cell_economics, normalize_policy, summarize_benchmark  # noqa: E402


SCHEMA = "leafos.inference-benchmark-matrix.v1"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _manifest_hash(value: dict[str, Any]) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class _WindowsCpuLoad:
    class _FileTime(ctypes.Structure):
        _fields_ = [("low", ctypes.c_ulong), ("high", ctypes.c_ulong)]

    def __init__(self) -> None:
        self._last: Optional[tuple[int, int, int]] = None

    @staticmethod
    def _integer(value: "_WindowsCpuLoad._FileTime") -> int:
        return (int(value.high) << 32) | int(value.low)

    def sample(self) -> Optional[float]:
        idle, kernel, user = self._FileTime(), self._FileTime(), self._FileTime()
        if not ctypes.windll.kernel32.GetSystemTimes(
            ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user)
        ):
            return None
        current = (self._integer(idle), self._integer(kernel), self._integer(user))
        if self._last is None:
            self._last = current
            return None
        idle_delta = current[0] - self._last[0]
        total_delta = (current[1] - self._last[1]) + (current[2] - self._last[2])
        self._last = current
        if total_delta <= 0:
            return None
        return round(max(0.0, min(100.0, 100.0 * (1.0 - idle_delta / total_delta))), 2)


class _ProcCpuLoad:
    def __init__(self) -> None:
        self._last: Optional[tuple[int, int]] = None

    def sample(self) -> Optional[float]:
        try:
            fields = Path("/proc/stat").read_text(encoding="utf-8").splitlines()[0].split()[1:]
            values = [int(item) for item in fields]
        except (OSError, ValueError, IndexError):
            return None
        idle = values[3] + (values[4] if len(values) > 4 else 0)
        total = sum(values)
        if self._last is None:
            self._last = (idle, total)
            return None
        idle_delta, total_delta = idle - self._last[0], total - self._last[1]
        self._last = (idle, total)
        if total_delta <= 0:
            return None
        return round(max(0.0, min(100.0, 100.0 * (1.0 - idle_delta / total_delta))), 2)


def _cpu_sampler() -> Any:
    return _WindowsCpuLoad() if os.name == "nt" else _ProcCpuLoad()


def _memory_sample() -> dict[str, Optional[float]]:
    if os.name == "nt":
        class MemoryStatus(ctypes.Structure):
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

        status = MemoryStatus()
        status.length = ctypes.sizeof(status)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            gib = 1024 ** 3
            return {
                "load_percent": float(status.memory_load),
                "total_gib": round(status.total_physical / gib, 3),
                "available_gib": round(status.available_physical / gib, 3),
            }
    try:
        values: dict[str, int] = {}
        for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
            key, raw = line.split(":", 1)
            values[key] = int(raw.strip().split()[0])
        return {
            "load_percent": round(100.0 * (1.0 - values["MemAvailable"] / values["MemTotal"]), 2),
            "total_gib": round(values["MemTotal"] / 1024 / 1024, 3),
            "available_gib": round(values["MemAvailable"] / 1024 / 1024, 3),
        }
    except (OSError, ValueError, KeyError):
        return {"load_percent": None, "total_gib": None, "available_gib": None}


def _float_or_none(value: str) -> Optional[float]:
    try:
        return float(value.strip())
    except (TypeError, ValueError):
        return None


def _gpu_sample() -> dict[str, Any]:
    executable = shutil.which("nvidia-smi")
    if not executable:
        return {"available": False, "reason": "nvidia-smi not found"}
    fields = (
        "name,driver_version,temperature.gpu,utilization.gpu,utilization.memory,"
        "memory.used,memory.total,power.draw,power.limit,clocks.current.graphics,clocks.current.memory"
    )
    try:
        process = subprocess.run(
            [executable, f"--query-gpu={fields}", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=8,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return {"available": False, "reason": str(error)}
    if process.returncode != 0 or not process.stdout.strip():
        return {"available": False, "reason": process.stderr.strip() or "nvidia-smi returned no data"}
    row = next(csv.reader([process.stdout.splitlines()[0]]))
    if len(row) != 11:
        return {"available": False, "reason": "unexpected nvidia-smi field count"}
    return {
        "available": True,
        "name": row[0].strip(),
        "driver_version": row[1].strip(),
        "temperature_c": _float_or_none(row[2]),
        "gpu_utilization_percent": _float_or_none(row[3]),
        "memory_utilization_percent": _float_or_none(row[4]),
        "vram_used_mib": _float_or_none(row[5]),
        "vram_total_mib": _float_or_none(row[6]),
        "power_draw_w": _float_or_none(row[7]),
        "power_limit_w": _float_or_none(row[8]),
        "graphics_clock_mhz": _float_or_none(row[9]),
        "memory_clock_mhz": _float_or_none(row[10]),
    }


def _process_snapshot(limit: int = 30) -> list[dict[str, Any]]:
    if os.name == "nt":
        try:
            process = subprocess.run(
                ["tasklist", "/FO", "CSV", "/NH"], capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=12,
            )
            rows = []
            for row in csv.reader(process.stdout.splitlines()):
                if len(row) < 5:
                    continue
                memory_kib = int(re.sub(r"[^0-9]", "", row[4]) or 0)
                rows.append({"name": row[0], "pid": int(row[1]), "working_set_mib": round(memory_kib / 1024, 2)})
            return sorted(rows, key=lambda item: item["working_set_mib"], reverse=True)[:limit]
        except (OSError, ValueError, subprocess.TimeoutExpired):
            return []
    try:
        process = subprocess.run(
            ["ps", "-eo", "pid=,comm=,rss=", "--sort=-rss"], capture_output=True,
            text=True, encoding="utf-8", errors="replace", timeout=12,
        )
        rows = []
        for line in process.stdout.splitlines()[:limit]:
            pid, name, rss = line.strip().split(None, 2)
            rows.append({"name": name, "pid": int(pid), "working_set_mib": round(int(rss) / 1024, 2)})
        return rows
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return []


def _sample(cpu: Any) -> dict[str, Any]:
    return {
        "at": _utc_now(),
        "cpu_utilization_percent": cpu.sample(),
        "memory": _memory_sample(),
        "gpu": _gpu_sample(),
    }


class _TelemetrySampler:
    def __init__(self, interval_seconds: float) -> None:
        self.interval_seconds = interval_seconds
        self.samples: list[dict[str, Any]] = []
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._cpu = _cpu_sampler()

    def start(self) -> None:
        self._cpu.sample()
        self._thread = threading.Thread(target=self._run, name="leafos-benchmark-telemetry", daemon=True)
        self._thread.start()

    def _run(self) -> None:
        while not self._stop.is_set():
            self.samples.append(_sample(self._cpu))
            self._stop.wait(self.interval_seconds)

    def stop(self) -> list[dict[str, Any]]:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=max(2.0, self.interval_seconds * 2))
        self.samples.append(_sample(self._cpu))
        return self.samples


def _numeric_summary(values: list[Optional[float]]) -> dict[str, Optional[float]]:
    present = [float(value) for value in values if value is not None]
    if not present:
        return {"minimum": None, "mean": None, "maximum": None}
    return {
        "minimum": round(min(present), 3),
        "mean": round(mean(present), 3),
        "maximum": round(max(present), 3),
    }


def _telemetry_summary(samples: list[dict[str, Any]]) -> dict[str, Any]:
    gpu = [item.get("gpu", {}) for item in samples]
    memory = [item.get("memory", {}) for item in samples]
    return {
        "sample_count": len(samples),
        "cpu_utilization_percent": _numeric_summary([item.get("cpu_utilization_percent") for item in samples]),
        "available_memory_gib": _numeric_summary([item.get("available_gib") for item in memory]),
        "gpu_utilization_percent": _numeric_summary([item.get("gpu_utilization_percent") for item in gpu]),
        "gpu_temperature_c": _numeric_summary([item.get("temperature_c") for item in gpu]),
        "gpu_power_draw_w": _numeric_summary([item.get("power_draw_w") for item in gpu]),
        "gpu_vram_used_mib": _numeric_summary([item.get("vram_used_mib") for item in gpu]),
    }


def validate_manifest(manifest: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if manifest.get("schema") != SCHEMA:
        errors.append(f"schema must be {SCHEMA}")
    if not isinstance(manifest.get("benchmark_id"), str) or not manifest.get("benchmark_id"):
        errors.append("benchmark_id must be a non-empty string")
    runtime = manifest.get("runtime")
    if not isinstance(runtime, dict) or not isinstance(runtime.get("command"), list) or not runtime.get("command"):
        errors.append("runtime.command must be a non-empty string array")
    elif not all(isinstance(item, str) and item for item in runtime["command"]):
        errors.append("runtime.command entries must be non-empty strings")
    cells = manifest.get("cells")
    if not isinstance(cells, list) or not cells:
        errors.append("cells must be a non-empty array")
        return errors
    seen: set[str] = set()
    positive = ("prompt_tokens", "generated_tokens", "repetitions", "threads")
    for index, cell in enumerate(cells):
        prefix = f"cells[{index}]"
        if not isinstance(cell, dict):
            errors.append(f"{prefix} must be an object")
            continue
        cell_id = cell.get("id")
        if not isinstance(cell_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", cell_id):
            errors.append(f"{prefix}.id must be a filesystem-safe identifier")
        elif cell_id in seen:
            errors.append(f"duplicate cell id: {cell_id}")
        else:
            seen.add(cell_id)
        if not isinstance(cell.get("model"), str) or not cell.get("model"):
            errors.append(f"{prefix}.model must be a non-empty path")
        for key in positive:
            if not isinstance(cell.get(key), int) or cell[key] < 1:
                errors.append(f"{prefix}.{key} must be a positive integer")
        if not isinstance(cell.get("gpu_layers"), int) or cell["gpu_layers"] < 0:
            errors.append(f"{prefix}.gpu_layers must be a non-negative integer")
        for key in ("kv_key_type", "kv_value_type"):
            if not isinstance(cell.get(key), str) or not cell[key]:
                errors.append(f"{prefix}.{key} must be a non-empty string")
    return errors


def _resolve_command(manifest: dict[str, Any], override: str) -> list[str]:
    command = list(manifest["runtime"]["command"])
    if override:
        command = [str(Path(override).expanduser().resolve())]
    first = Path(command[0]).expanduser()
    resolved = shutil.which(str(first)) if not first.is_absolute() else str(first.resolve())
    if not resolved or not Path(resolved).is_file():
        raise ValueError(f"llama-bench command not found: {command[0]}")
    command[0] = resolved
    return command


def build_cell_command(base: list[str], cell: dict[str, Any]) -> list[str]:
    command = base + [
        "--offline", "-m", str(Path(cell["model"]).expanduser().resolve()),
        "-p", str(cell["prompt_tokens"]), "-n", str(cell["generated_tokens"]),
        "-r", str(cell["repetitions"]), "-t", str(cell["threads"]),
        "-ngl", str(cell["gpu_layers"]), "-ctk", cell["kv_key_type"],
        "-ctv", cell["kv_value_type"], "-o", "json",
    ]
    if cell.get("warmup") is False:
        command.append("--no-warmup")
    return command


def _parse_benchmark_rows(stdout: str, stderr: str) -> list[dict[str, Any]]:
    for text in (stdout, stderr):
        try:
            value = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(value, list) and all(isinstance(item, dict) for item in value):
            return value
        if isinstance(value, dict):
            return [value]
    raise ValueError("llama-bench produced no JSON result")


def _rate_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    def selected(kind: str) -> list[dict[str, Any]]:
        if kind == "generation":
            return [row for row in rows if int(row.get("n_gen", 0) or 0) > 0]
        return [row for row in rows if int(row.get("n_prompt", 0) or 0) > 0 and int(row.get("n_gen", 0) or 0) == 0]

    result: dict[str, Any] = {}
    for kind in ("prefill", "generation"):
        matches = selected(kind)
        rates = [float(row["avg_ts"]) for row in matches if isinstance(row.get("avg_ts"), (int, float))]
        result[kind] = {
            "tokens_per_second": round(rates[-1], 3) if rates else None,
            "row_count": len(matches),
            "rows": matches,
        }
    return result


def _preflight(idle_policy: dict[str, Any]) -> dict[str, Any]:
    cpu = _cpu_sampler()
    cpu.sample()
    time.sleep(float(idle_policy.get("settle_sample_seconds", 1.0)))
    sample = _sample(cpu)
    processes = _process_snapshot()
    violations: list[str] = []
    cpu_value = sample.get("cpu_utilization_percent")
    gpu = sample.get("gpu", {})
    memory = sample.get("memory", {})
    checks = (
        (cpu_value, idle_policy.get("max_cpu_percent"), "CPU utilization"),
        (gpu.get("gpu_utilization_percent"), idle_policy.get("max_gpu_percent"), "GPU utilization"),
        (gpu.get("vram_used_mib"), idle_policy.get("max_gpu_vram_used_mib"), "GPU VRAM use"),
    )
    for actual, maximum, label in checks:
        if maximum is not None and actual is not None and float(actual) > float(maximum):
            violations.append(f"{label} {actual} exceeds limit {maximum}")
    minimum_ram = idle_policy.get("minimum_available_ram_gib")
    available_ram = memory.get("available_gib")
    if minimum_ram is not None and available_ram is not None and float(available_ram) < float(minimum_ram):
        violations.append(f"available RAM {available_ram} GiB is below limit {minimum_ram} GiB")
    competing_names = {str(item).lower() for item in idle_policy.get("forbidden_process_names", [])}
    active = [item for item in processes if Path(str(item.get("name", ""))).stem.lower() in competing_names]
    if active:
        violations.append("forbidden processes are active: " + ", ".join(f"{item['name']}({item['pid']})" for item in active))
    return {"at": _utc_now(), "sample": sample, "top_processes": processes, "violations": violations}


def _runtime_identity(command: list[str]) -> dict[str, Any]:
    version_command = command + ["--version"]
    try:
        version = subprocess.run(
            version_command, capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=15,
        )
        version_text = (version.stdout + "\n" + version.stderr).strip()[:4000]
        executable = Path(command[0])
        sibling_cli = executable.with_name("llama-cli.exe" if os.name == "nt" else "llama-cli")
        if version_text.lower().startswith("usage:") and sibling_cli.is_file():
            version_command = [str(sibling_cli), "--version"]
            version = subprocess.run(
                version_command, capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=15,
            )
            version_text = (version.stdout + "\n" + version.stderr).strip()[:4000]
    except (OSError, subprocess.TimeoutExpired) as error:
        version_text = f"unavailable: {error}"
    executable = Path(command[0])
    component_names = {
        executable.name, "llama-bench-impl.dll", "llama.dll", "ggml.dll", "ggml-base.dll",
        "ggml-vulkan.dll",
    }
    components = []
    for candidate in sorted(executable.parent.iterdir(), key=lambda item: item.name.lower()):
        if candidate.is_file() and (
            candidate.name in component_names or candidate.name.lower().startswith("ggml-cpu-")
        ):
            components.append({
                "name": candidate.name,
                "size_bytes": candidate.stat().st_size,
                "sha256": _sha256_file(candidate),
            })
    return {
        "command": command,
        "executable": str(executable),
        "executable_size_bytes": executable.stat().st_size,
        "executable_sha256": _sha256_file(executable),
        "version_command": version_command,
        "version_output": version_text,
        "component_hashes": components,
    }


def _model_identity(path: Path, hash_model: bool) -> dict[str, Any]:
    stat = path.stat()
    return {
        "path": str(path),
        "size_bytes": stat.st_size,
        "modified_at": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat().replace("+00:00", "Z"),
        "sha256": _sha256_file(path) if hash_model else None,
        "sha256_status": "recorded" if hash_model else "disabled to avoid pre-run storage and thermal load",
    }


def _initial_report(manifest: dict[str, Any], manifest_sha: str, command: list[str]) -> dict[str, Any]:
    return {
        "schema": "leafos.inference-benchmark-report.v1",
        "benchmark_id": manifest["benchmark_id"],
        "manifest_sha256": manifest_sha,
        "status": "initializing",
        "started_at": _utc_now(),
        "finished_at": None,
        "host": {
            "node": platform.node(),
            "platform": platform.platform(),
            "processor": platform.processor(),
            "logical_cpu_count": os.cpu_count(),
            "python": platform.python_version(),
            "cpu_temperature": {
                "value_c": None,
                "status": "unavailable from portable OS interfaces; use a trusted sensor provider to add it",
            },
        },
        "runtime": _runtime_identity(command),
        "conditions": manifest.get("conditions", {}),
        "economics": normalize_policy(manifest.get("economics")),
        "planned_cell_count": sum(cell.get("enabled", True) for cell in manifest.get("cells", [])),
        "preflight": None,
        "models": {},
        "cells": [],
        "processes_after": [],
        "summary": None,
    }


def _write_report(path: Path, report: dict[str, Any]) -> None:
    report["summary"] = summarize_benchmark(report)
    _atomic_json(path, report)


def run_matrix(args: Any) -> tuple[int, dict[str, Any]]:
    manifest_path = Path(args.manifest).expanduser().resolve()
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return 2, {"status": "invalid_manifest", "error": str(error), "manifest": str(manifest_path)}
    errors = validate_manifest(manifest)
    if errors:
        return 2, {"status": "invalid_manifest", "errors": errors, "manifest": str(manifest_path)}
    try:
        command = _resolve_command(manifest, args.bench)
    except ValueError as error:
        return 2, {"status": "invalid_runtime", "error": str(error)}

    manifest_sha = _manifest_hash(manifest)
    output_dir = Path(args.output_dir).expanduser().resolve() if args.output_dir else (
        Path.cwd() / "reports" / "inference-benchmark" / manifest["benchmark_id"]
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "report.json"
    report: dict[str, Any]
    if args.resume and report_path.is_file():
        report = json.loads(report_path.read_text(encoding="utf-8"))
        if report.get("manifest_sha256") != manifest_sha:
            return 2, {"status": "resume_refused", "error": "manifest changed since the saved run"}
    else:
        report = _initial_report(manifest, manifest_sha, command)

    enabled_cells = [cell for cell in manifest["cells"] if cell.get("enabled", True)]
    hash_models = bool(manifest.get("protocol", {}).get("hash_models", False))
    try:
        for model_text in sorted({cell["model"] for cell in enabled_cells}):
            model = Path(model_text).expanduser().resolve()
            if not model.is_file():
                raise ValueError(f"model not found: {model}")
            report["models"][str(model)] = _model_identity(model, hash_models)
    except (OSError, ValueError) as error:
        report.update({"status": "invalid_model", "finished_at": _utc_now(), "error": str(error)})
        _write_report(report_path, report)
        return 2, report

    idle_policy = manifest.get("idle_policy", {})
    report["preflight"] = _preflight(idle_policy)
    require_idle = bool(idle_policy.get("required", False))
    if require_idle and report["preflight"]["violations"] and not args.allow_busy:
        report.update({"status": "blocked_busy", "finished_at": _utc_now()})
        _write_report(report_path, report)
        return 3, report
    if args.dry_run:
        report.update({"status": "dry_run_ready", "finished_at": _utc_now(), "planned_cell_count": len(enabled_cells)})
        _write_report(report_path, report)
        return 0, report

    completed = {cell.get("id") for cell in report.get("cells", []) if cell.get("status") == "completed"}
    protocol = manifest.get("protocol", {})
    cooldown = float(protocol.get("cooldown_seconds", 0.0))
    interval = float(protocol.get("telemetry_interval_seconds", 1.0))
    continue_on_error = bool(protocol.get("continue_on_error", False))
    report["status"] = "running"
    _write_report(report_path, report)
    for ordinal, cell in enumerate(enabled_cells, start=1):
        if cell["id"] in completed:
            continue
        if report["cells"] and cooldown > 0:
            time.sleep(cooldown)
        cell_command = build_cell_command(command, cell)
        sampler = _TelemetrySampler(interval)
        started_at = _utc_now()
        started = time.perf_counter()
        sampler.start()
        process = subprocess.run(
            cell_command, capture_output=True, text=True, encoding="utf-8", errors="replace"
        )
        samples = sampler.stop()
        elapsed = time.perf_counter() - started
        raw_dir = output_dir / "raw"
        raw_dir.mkdir(parents=True, exist_ok=True)
        stdout_path = raw_dir / f"{cell['id']}.stdout.json"
        stderr_path = raw_dir / f"{cell['id']}.stderr.txt"
        stdout_path.write_text(process.stdout, encoding="utf-8")
        stderr_path.write_text(process.stderr, encoding="utf-8")
        cell_report: dict[str, Any] = {
            "id": cell["id"], "ordinal": ordinal, "definition": cell,
            "status": "completed" if process.returncode == 0 else "failed",
            "started_at": started_at, "finished_at": _utc_now(),
            "elapsed_seconds": round(elapsed, 3), "return_code": process.returncode,
            "command": cell_command,
            "artifacts": {"stdout": str(stdout_path), "stderr": str(stderr_path)},
            "telemetry": {"summary": _telemetry_summary(samples), "samples": samples},
        }
        if process.returncode == 0:
            try:
                rows = _parse_benchmark_rows(process.stdout, process.stderr)
                cell_report["throughput"] = _rate_summary(rows)
                cell_report["economics"] = benchmark_cell_economics(cell_report, report["economics"])
            except ValueError as error:
                cell_report.update({"status": "failed", "error": str(error)})
        else:
            cell_report["error"] = (process.stderr.strip() or process.stdout.strip())[-4000:]
        report["cells"].append(cell_report)
        _write_report(report_path, report)
        if cell_report["status"] != "completed" and not continue_on_error:
            report["status"] = "failed"
            break

    if report["status"] != "failed":
        successful = sum(cell.get("status") == "completed" for cell in report["cells"])
        report["status"] = "completed" if successful == len(enabled_cells) else "partial"
    report["finished_at"] = _utc_now()
    report["processes_after"] = _process_snapshot()
    _write_report(report_path, report)
    return (0 if report["status"] == "completed" else 1), report
