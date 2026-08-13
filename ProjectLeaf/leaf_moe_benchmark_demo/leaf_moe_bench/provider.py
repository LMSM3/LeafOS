"""Read-only llama-bench capability probe."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any, Dict, List

from .util import sha256_file, utc_now


PROVIDER_SCHEMA = "leafos.moe.provider-probe/0.1"


def _capture(command: List[str], timeout: int = 20) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
    )


def _loaded_backends(text: str) -> List[str]:
    values = {
        match.group(1).lower()
        for match in re.finditer(r"loaded\s+([a-z0-9_-]+)\s+backend", text, flags=re.IGNORECASE)
    }
    return sorted(values)


def _device_lines(text: str) -> List[str]:
    devices = []
    in_devices = False
    for raw in text.splitlines():
        line = raw.strip()
        if line.lower().startswith("available devices"):
            in_devices = True
            continue
        if in_devices and line:
            if line == "(none)":
                continue
            devices.append(line)
    return devices


def probe_llama_bench(executable: Path) -> Dict[str, Any]:
    source = executable.expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(f"llama-bench executable not found: {source}")

    help_result = _capture([str(source), "--help"])
    devices_result = _capture([str(source), "--list-devices"])
    help_text = "\n".join([help_result.stdout, help_result.stderr])
    device_text = "\n".join([devices_result.stdout, devices_result.stderr])
    backends = sorted(set(_loaded_backends(help_text) + _loaded_backends(device_text)))
    devices = _device_lines(devices_result.stdout)
    gpu_markers = ("cuda", "vulkan", "metal", "hip", "rocm", "sycl", "kompute")
    gpu_available = any(marker in value.casefold() for value in [*devices, *backends] for marker in gpu_markers)

    capabilities = {
        "jsonl_output": "jsonl" in help_text,
        "output_err": "--output-err" in help_text,
        "offline": "--offline" in help_text,
        "n_gpu_layers": "--n-gpu-layers" in help_text,
        "n_cpu_moe": "--n-cpu-moe" in help_text,
        "device": "--device" in help_text,
        "no_op_offload": "--no-op-offload" in help_text,
        "fit_target": "--fit-target" in help_text,
        "mmap": "--mmap" in help_text,
        "direct_io": "--direct-io" in help_text,
        "flash_attn": "--flash-attn" in help_text,
    }
    required = ["jsonl_output", "output_err", "offline", "n_gpu_layers", "mmap"]
    missing_required = [name for name in required if not capabilities[name]]
    return {
        "schema": PROVIDER_SCHEMA,
        "schema_version": 1,
        "generated_at": utc_now(),
        "executable": str(source),
        "executable_sha256": sha256_file(source),
        "help_return_code": help_result.returncode,
        "list_devices_return_code": devices_result.returncode,
        "loaded_backends": backends,
        "devices": devices,
        "cpu_available": "cpu" in backends or not devices,
        "gpu_available": gpu_available,
        "capabilities": capabilities,
        "usable": help_result.returncode == 0 and devices_result.returncode == 0 and not missing_required,
        "missing_required_capabilities": missing_required,
    }
