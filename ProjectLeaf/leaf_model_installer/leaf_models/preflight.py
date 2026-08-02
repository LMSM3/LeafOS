from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from .catalog import ModelEntry


@dataclass(frozen=True)
class GPUInfo:
    name: str
    driver_version: str
    memory_total_mb: int


@dataclass(frozen=True)
class RAMModuleInfo:
    capacity_gb: float
    count: int


@dataclass(frozen=True)
class DNSFlushReport:
    requested: bool
    success: bool
    attempted: list[str]
    messages: list[str]


@dataclass(frozen=True)
class QuantRecommendation:
    model_key: str
    recommended_quant: Optional[str]
    reason: str
    memory_basis: str
    max_vram_gb: Optional[float]
    ram_total_gb: Optional[float]


@dataclass(frozen=True)
class PreflightReport:
    created_at_utc: str
    platform_system: str
    platform_release: str
    platform_version: str
    machine: str
    processor: str
    python_version: str
    cwd: str
    destination_root: str
    target_dir: str
    nvidia_smi_path: Optional[str]
    gpus: list[GPUInfo]
    ram_total_gb: Optional[float]
    ram_modules: list[RAMModuleInfo]
    dns_flush: DNSFlushReport
    recommendation: QuantRecommendation
    report_path: str


def _run_capture(cmd: list[str], timeout: int = 15) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        return proc.returncode, proc.stdout.strip(), proc.stderr.strip()
    except Exception as exc:  # noqa: BLE001
        return 999, "", str(exc)


def detect_nvidia() -> tuple[Optional[str], list[GPUInfo], list[str]]:
    exe = shutil.which("nvidia-smi")
    messages: list[str] = []
    if not exe:
        return None, [], ["NVIDIA SMI not found."]

    rc, out, err = _run_capture(
        [
            exe,
            "--query-gpu=name,driver_version,memory.total",
            "--format=csv,noheader,nounits",
        ],
        timeout=10,
    )
    if rc != 0:
        msg = err or out or f"nvidia-smi exited with {rc}"
        return exe, [], [msg]

    gpus: list[GPUInfo] = []
    for line in out.splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 3:
            messages.append(f"Unparsed nvidia-smi line: {line}")
            continue
        try:
            mem = int(float(parts[2]))
        except ValueError:
            mem = 0
            messages.append(f"Could not parse GPU memory from: {line}")
        gpus.append(GPUInfo(name=parts[0], driver_version=parts[1], memory_total_mb=mem))
    return exe, gpus, messages


def _ram_windows() -> tuple[Optional[float], list[RAMModuleInfo], list[str]]:
    ps = shutil.which("powershell") or shutil.which("pwsh")
    if not ps:
        return None, [], ["PowerShell not found for Windows RAM module scan."]
    command = r"""
$modules = Get-CimInstance Win32_PhysicalMemory | Group-Object Capacity | ForEach-Object {
  [pscustomobject]@{ capacity_gb = [math]::Round(([double]$_.Name / 1GB), 2); count = $_.Count }
}
$total = [math]::Round(((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory / 1GB), 2)
[pscustomobject]@{ total_gb = $total; modules = @($modules) } | ConvertTo-Json -Compress
""".strip()
    rc, out, err = _run_capture([ps, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command], timeout=20)
    if rc != 0:
        return None, [], [err or out or f"PowerShell RAM scan exited with {rc}"]
    try:
        data = json.loads(out)
        modules_raw = data.get("modules") or []
        if isinstance(modules_raw, dict):
            modules_raw = [modules_raw]
        modules = [RAMModuleInfo(float(item.get("capacity_gb", 0)), int(item.get("count", 0))) for item in modules_raw]
        return float(data.get("total_gb")), modules, []
    except Exception as exc:  # noqa: BLE001
        return None, [], [f"Could not parse Windows RAM JSON: {exc}"]


def _ram_linux() -> tuple[Optional[float], list[RAMModuleInfo], list[str]]:
    meminfo = Path("/proc/meminfo")
    if not meminfo.is_file():
        return None, [], ["/proc/meminfo not available."]
    for line in meminfo.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("MemTotal:"):
            parts = line.split()
            kb = float(parts[1])
            gb = round(kb / 1024 / 1024, 2)
            return gb, [], []
    return None, [], ["MemTotal not found in /proc/meminfo."]


def _ram_macos() -> tuple[Optional[float], list[RAMModuleInfo], list[str]]:
    rc, out, err = _run_capture(["sysctl", "-n", "hw.memsize"], timeout=10)
    if rc != 0:
        return None, [], [err or out or f"sysctl exited with {rc}"]
    try:
        gb = round(float(out.strip()) / 1024 / 1024 / 1024, 2)
        return gb, [], []
    except Exception as exc:  # noqa: BLE001
        return None, [], [f"Could not parse macOS RAM bytes: {exc}"]


def detect_ram() -> tuple[Optional[float], list[RAMModuleInfo], list[str]]:
    system = platform.system().lower()
    if system == "windows":
        return _ram_windows()
    if system == "linux":
        return _ram_linux()
    if system == "darwin":
        return _ram_macos()
    return None, [], [f"No RAM detector implemented for {platform.system()}."]


def recommend_quant(model: ModelEntry, ram_total_gb: Optional[float], gpus: list[GPUInfo]) -> QuantRecommendation:
    if not model.quant_options:
        max_vram = max((gpu.memory_total_mb for gpu in gpus), default=0) / 1024 if gpus else None
        return QuantRecommendation(
            model_key=model.key,
            recommended_quant=None,
            reason="This model entry downloads all matching GGUF files, so there is no quant choice to recommend.",
            memory_basis="catalog has no quant options",
            max_vram_gb=round(max_vram, 2) if max_vram is not None else None,
            ram_total_gb=ram_total_gb,
        )

    max_vram_gb = max((gpu.memory_total_mb for gpu in gpus), default=0) / 1024 if gpus else None
    ram = ram_total_gb or 0.0
    vram = max_vram_gb or 0.0

    # Conservative thresholds include headroom for runtime overhead, context, KV cache, and the usual gremlins.
    if vram >= 15 or ram >= 48:
        quant = "Q8_0"
        reason = "Detected enough memory for the largest listed file with usable headroom. Still verify runtime requirements before getting brave."
        basis = "high VRAM/RAM"
    elif vram >= 11.5 or ram >= 32:
        quant = "Q6_K"
        reason = "Detected enough memory for a higher-quality quant while keeping some survival margin."
        basis = "moderate-high VRAM/RAM"
    elif vram >= 8.0 or ram >= 16:
        quant = "Q4_K_M"
        reason = "Recommended baseline: good quality/size balance and the least likely to turn your machine into a space heater with opinions."
        basis = "baseline VRAM/RAM"
    elif vram >= 6.5 or ram >= 12:
        quant = "Q3_K_M"
        reason = "Memory looks tight for the baseline, so this is the cautious fallback."
        basis = "limited VRAM/RAM"
    else:
        quant = "Q2_K"
        reason = "Very limited detected memory. This is the smallest option, not magic."
        basis = "low VRAM/RAM"

    if quant not in model.quant_options:
        quant = next(iter(model.quant_options))
        reason = "Catalog did not contain the computed quant, so the first available option was selected. Annoying, but explicit."
        basis = "catalog fallback"

    return QuantRecommendation(
        model_key=model.key,
        recommended_quant=quant,
        reason=reason,
        memory_basis=basis,
        max_vram_gb=round(max_vram_gb, 2) if max_vram_gb is not None else None,
        ram_total_gb=ram_total_gb,
    )


def flush_dns_cache() -> DNSFlushReport:
    system = platform.system().lower()
    attempted: list[str] = []
    messages: list[str] = []
    success = True

    commands: list[list[str]] = []
    if system == "windows":
        ps = shutil.which("powershell") or shutil.which("pwsh")
        if ps:
            commands.append([ps, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", "Clear-DnsClientCache"])
        commands.append(["ipconfig", "/flushdns"])
    elif system == "darwin":
        commands.append(["dscacheutil", "-flushcache"])
        commands.append(["killall", "-HUP", "mDNSResponder"])
    elif system == "linux":
        if shutil.which("resolvectl"):
            commands.append(["resolvectl", "flush-caches"])
        elif shutil.which("systemd-resolve"):
            commands.append(["systemd-resolve", "--flush-caches"])
        else:
            messages.append("No standard Linux DNS flush command found. Skipped.")
    else:
        messages.append(f"DNS flush not implemented for {platform.system()}.")

    for cmd in commands:
        attempted.append(" ".join(cmd))
        rc, out, err = _run_capture(cmd, timeout=20)
        if rc != 0:
            success = False
            messages.append(err or out or f"Command exited with {rc}: {' '.join(cmd)}")
        elif out:
            messages.append(out)

    return DNSFlushReport(requested=True, success=success, attempted=attempted, messages=messages)


def make_preflight_report(
    model: ModelEntry,
    destination_root: Path,
    flush_dns: bool = False,
) -> tuple[PreflightReport, list[str]]:
    dest = destination_root.expanduser().resolve()
    target = (dest / model.local_dir).resolve()
    dest.mkdir(parents=True, exist_ok=True)
    messages: list[str] = []

    nvidia_path, gpus, gpu_messages = detect_nvidia()
    messages.extend(gpu_messages)
    ram_total, ram_modules, ram_messages = detect_ram()
    messages.extend(ram_messages)
    dns = flush_dns_cache() if flush_dns else DNSFlushReport(False, True, [], [])
    recommendation = recommend_quant(model, ram_total, gpus)

    report_path = target / "leaf_preflight_report.json"
    report = PreflightReport(
        created_at_utc=datetime.now(timezone.utc).isoformat(),
        platform_system=platform.system(),
        platform_release=platform.release(),
        platform_version=platform.version(),
        machine=platform.machine(),
        processor=platform.processor(),
        python_version=sys.version.split()[0],
        cwd=str(Path.cwd()),
        destination_root=str(dest),
        target_dir=str(target),
        nvidia_smi_path=nvidia_path,
        gpus=gpus,
        ram_total_gb=ram_total,
        ram_modules=ram_modules,
        dns_flush=dns,
        recommendation=recommendation,
        report_path=str(report_path),
    )
    target.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(asdict(report), indent=2), encoding="utf-8")
    return report, messages


def animate_loading(seconds: float, frames: Optional[list[str]] = None) -> None:
    if seconds <= 0:
        return
    frames = frames or ["𒅒", "𒈔", "𒅒", "𒇫", "𒄆"]
    start = time.monotonic()
    i = 0
    while time.monotonic() - start < seconds:
        frame = frames[i % len(frames)]
        elapsed = time.monotonic() - start
        print(f"\rLoading... {frame}  {elapsed:4.1f}s", end="", flush=True)
        time.sleep(0.2)
        i += 1
    print("\rLoading complete. No success implied.          ")
