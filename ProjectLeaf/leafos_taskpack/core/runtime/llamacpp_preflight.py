#!/usr/bin/env python3
"""Read-only llama.cpp binary, GGUF, backend, and host capability preflight.

This module deliberately cannot launch inference: the only permitted subprocess
arguments are ``--version`` and ``--list-devices`` and no model path is ever
passed to the executable.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import subprocess
from pathlib import Path
from typing import Any


SCHEMA = "leafos.llamacpp_capability_preflight.v1"
OPT_IN_ENV = "LEAFOS_RUN_LLAMACPP_TESTS"
ALLOWED_BACKENDS = {"cpu", "cuda", "hip", "metal", "sycl", "vulkan"}
ALLOWED_PROBES = {"version": "--version", "devices": "--list-devices"}
RESULT_FIELDS = {
    "schema", "mode", "capable", "inference_started", "server_started", "network_used",
    "task_digest", "inputs", "binary", "model", "backend", "host", "failures",
    "capability_digest",
}


def _digest_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return "sha256:" + digest.hexdigest()


def _digest_value(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _failure(code: str, field: str, message: str) -> dict[str, str]:
    return {"code": code, "field": field, "message": message}


def _host_memory_bytes() -> tuple[int | None, str | None]:
    try:
        if os.name == "nt":
            import ctypes

            class MemoryStatus(ctypes.Structure):
                _fields_ = [
                    ("length", ctypes.c_ulong), ("memory_load", ctypes.c_ulong),
                    ("total_physical", ctypes.c_ulonglong), ("available_physical", ctypes.c_ulonglong),
                    ("total_page_file", ctypes.c_ulonglong), ("available_page_file", ctypes.c_ulonglong),
                    ("total_virtual", ctypes.c_ulonglong), ("available_virtual", ctypes.c_ulonglong),
                    ("available_extended_virtual", ctypes.c_ulonglong),
                ]

            status = MemoryStatus()
            status.length = ctypes.sizeof(status)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                return int(status.total_physical), None
        page_size = os.sysconf("SC_PAGE_SIZE")
        pages = os.sysconf("SC_PHYS_PAGES")
        return int(page_size * pages), None
    except (AttributeError, OSError, ValueError):
        return None, "physical memory discovery is unavailable on this host"


def host_facts() -> dict[str, Any]:
    memory_bytes, memory_unavailable_reason = _host_memory_bytes()
    return {
        "system": platform.system(),
        "release": platform.release(),
        "machine": platform.machine(),
        "processor": platform.processor() or None,
        "logical_cpu_count": os.cpu_count(),
        "physical_memory_bytes": memory_bytes,
        "memory_unavailable_reason": memory_unavailable_reason,
        "python": platform.python_version(),
    }


def validate_result(value: dict[str, Any]) -> None:
    """Fail closed if the native result drifts from its versioned contract."""
    if set(value) != RESULT_FIELDS:
        raise ValueError("llama.cpp preflight result has unknown or missing fields")
    if value["schema"] != SCHEMA or value["mode"] != "preflight_only":
        raise ValueError("llama.cpp preflight result identity is invalid")
    if any(value[field] is not False for field in ("inference_started", "server_started", "network_used")):
        raise ValueError("llama.cpp preflight cannot claim runtime side effects")
    if value["capable"] is not (len(value["failures"]) == 0):
        raise ValueError("llama.cpp preflight capability disposition disagrees with failures")
    digest = value["capability_digest"]
    bound = dict(value)
    bound.pop("capability_digest")
    if digest != _digest_value(bound):
        raise ValueError("llama.cpp preflight capability digest verification failed")


def _run_metadata_probe(executable: Path, probe: str, timeout_seconds: int) -> dict[str, Any]:
    argument = ALLOWED_PROBES[probe]
    completed = subprocess.run(
        [str(executable), argument],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout_seconds,
        check=False,
        shell=False,
    )
    return {
        "argument": argument,
        "exit_code": completed.returncode,
        "stdout": completed.stdout.strip()[:65536],
        "stderr": completed.stderr.strip()[:65536],
    }


def _binary_identity(
    executable: Path,
    expected_version: str | None,
    timeout_seconds: int,
    failures: list[dict[str, str]],
) -> dict[str, Any]:
    identity: dict[str, Any] = {
        "path": str(executable), "exists": executable.is_file(), "size_bytes": None,
        "sha256": None, "version": None, "commit": None, "version_probe": None,
    }
    if not executable.is_file():
        failures.append(_failure("EXECUTABLE_MISSING", "executable", "explicit llama.cpp executable is not a file"))
        return identity
    try:
        identity["size_bytes"] = executable.stat().st_size
        identity["sha256"] = _digest_file(executable)
        probe = _run_metadata_probe(executable, "version", timeout_seconds)
        identity["version_probe"] = probe
        combined = "\n".join(value for value in (probe["stdout"], probe["stderr"]) if value)
        match = re.search(r"(?i)\b(?:version|build)\s*[:=]?\s*([A-Za-z0-9._+-]+)", combined)
        commit = re.search(r"(?i)\b(?:commit|revision|git)\s*[:=]?\s*([0-9a-f]{7,40})\b", combined)
        identity["version"] = match.group(1) if match else (combined.splitlines()[0] if combined else None)
        identity["commit"] = commit.group(1).lower() if commit else None
        if probe["exit_code"] != 0:
            failures.append(_failure("VERSION_PROBE_FAILED", "executable", f"--version exited {probe['exit_code']}"))
        elif not combined:
            failures.append(_failure("VERSION_UNREPORTED", "executable", "llama.cpp reported no binary identity"))
        if expected_version and expected_version not in combined:
            failures.append(_failure("VERSION_MISMATCH", "expected_version", f"binary identity does not contain {expected_version!r}"))
    except PermissionError:
        failures.append(_failure("EXECUTABLE_INACCESSIBLE", "executable", "llama.cpp executable is not accessible"))
    except subprocess.TimeoutExpired:
        failures.append(_failure("VERSION_PROBE_TIMEOUT", "executable", "llama.cpp --version exceeded the timeout"))
    except OSError as error:
        failures.append(_failure("EXECUTABLE_FAILED", "executable", f"llama.cpp metadata probe failed: {error}"))
    return identity


def _model_identity(model: Path, failures: list[dict[str, str]]) -> dict[str, Any]:
    identity: dict[str, Any] = {
        "path": str(model), "exists": model.is_file(), "size_bytes": None,
        "sha256": None, "magic": None, "gguf_version": None,
    }
    if not model.is_file():
        failures.append(_failure("MODEL_MISSING", "model", "explicit model path is not a file"))
        return identity
    try:
        size = model.stat().st_size
        identity["size_bytes"] = size
        if size == 0:
            failures.append(_failure("MODEL_ZERO_BYTES", "model", "model file is empty"))
            return identity
        with model.open("rb") as stream:
            header = stream.read(8)
        identity["magic"] = header[:4].decode("ascii", errors="replace")
        if header[:4] != b"GGUF":
            failures.append(_failure("MODEL_NOT_GGUF", "model", "model header does not contain GGUF magic"))
        elif len(header) < 8:
            failures.append(_failure("MODEL_TRUNCATED", "model", "GGUF header is truncated"))
        else:
            identity["gguf_version"] = int.from_bytes(header[4:8], "little")
            if identity["gguf_version"] not in {2, 3}:
                failures.append(_failure("GGUF_VERSION_UNSUPPORTED", "model", f"GGUF version {identity['gguf_version']} is unsupported"))
        identity["sha256"] = _digest_file(model)
    except PermissionError:
        failures.append(_failure("MODEL_INACCESSIBLE", "model", "model file is not readable"))
    except OSError as error:
        failures.append(_failure("MODEL_READ_FAILED", "model", f"model inspection failed: {error}"))
    return identity


def _backend_identity(
    executable: Path,
    requested_backend: str,
    timeout_seconds: int,
    failures: list[dict[str, str]],
) -> dict[str, Any]:
    identity: dict[str, Any] = {
        "requested": requested_backend, "discovered": [], "devices": [], "device_probe": None,
    }
    if not executable.is_file():
        return identity
    try:
        probe = _run_metadata_probe(executable, "devices", timeout_seconds)
        identity["device_probe"] = probe
        combined = "\n".join(value for value in (probe["stdout"], probe["stderr"]) if value)
        lowered = combined.lower()
        identity["discovered"] = sorted(backend for backend in ALLOWED_BACKENDS if backend in lowered)
        identity["devices"] = [line.strip() for line in combined.splitlines() if line.strip()][:256]
        if probe["exit_code"] != 0:
            failures.append(_failure("DEVICE_PROBE_FAILED", "backend", f"--list-devices exited {probe['exit_code']}"))
        elif requested_backend == "cpu":
            if "cpu" not in identity["discovered"]:
                identity["discovered"].append("cpu")
        elif requested_backend not in identity["discovered"]:
            failures.append(_failure("BACKEND_UNAVAILABLE", "backend", f"requested backend {requested_backend!r} was not reported"))
    except PermissionError:
        failures.append(_failure("DEVICE_PROBE_INACCESSIBLE", "backend", "backend discovery is not permitted"))
    except subprocess.TimeoutExpired:
        failures.append(_failure("DEVICE_PROBE_TIMEOUT", "backend", "llama.cpp --list-devices exceeded the timeout"))
    except OSError as error:
        failures.append(_failure("DEVICE_PROBE_FAILED", "backend", f"backend discovery failed: {error}"))
    return identity


def probe(
    *,
    executable: str | Path,
    model: str | Path,
    backend: str,
    expected_version: str | None = None,
    timeout_seconds: int = 10,
    task_digest: str | None = None,
    opt_in: bool | None = None,
) -> dict[str, Any]:
    """Return bounded preflight evidence without starting inference or networking."""
    executable_path = Path(executable).expanduser().resolve(strict=False)
    model_path = Path(model).expanduser().resolve(strict=False)
    requested_backend = backend.strip().lower()
    failures: list[dict[str, str]] = []
    enabled = os.environ.get(OPT_IN_ENV) == "1" if opt_in is None else bool(opt_in)
    if not enabled:
        failures.append(_failure("OPT_IN_REQUIRED", OPT_IN_ENV, f"set {OPT_IN_ENV}=1 to authorize local metadata probes"))
    if requested_backend not in ALLOWED_BACKENDS:
        failures.append(_failure("BACKEND_UNSUPPORTED", "backend", f"unsupported backend {requested_backend!r}"))
    if timeout_seconds < 1:
        failures.append(_failure("TIMEOUT_INVALID", "timeout_seconds", "timeout must be at least one second"))

    binary = {
        "path": str(executable_path), "exists": executable_path.is_file(), "size_bytes": None,
        "sha256": None, "version": None, "commit": None, "version_probe": None,
    }
    model_identity = {
        "path": str(model_path), "exists": model_path.is_file(), "size_bytes": None,
        "sha256": None, "magic": None, "gguf_version": None,
    }
    backend_identity = {"requested": requested_backend, "discovered": [], "devices": [], "device_probe": None}
    if enabled and requested_backend in ALLOWED_BACKENDS and timeout_seconds >= 1:
        binary = _binary_identity(executable_path, expected_version, timeout_seconds, failures)
        model_identity = _model_identity(model_path, failures)
        backend_identity = _backend_identity(executable_path, requested_backend, timeout_seconds, failures)

    evidence: dict[str, Any] = {
        "schema": SCHEMA,
        "mode": "preflight_only",
        "capable": not failures,
        "inference_started": False,
        "server_started": False,
        "network_used": False,
        "task_digest": task_digest,
        "inputs": {
            "executable": str(executable_path), "model": str(model_path),
            "backend": requested_backend, "expected_version": expected_version,
        },
        "binary": binary,
        "model": model_identity,
        "backend": backend_identity,
        "host": host_facts(),
        "failures": failures,
    }
    evidence["capability_digest"] = _digest_value(evidence)
    validate_result(evidence)
    return evidence
