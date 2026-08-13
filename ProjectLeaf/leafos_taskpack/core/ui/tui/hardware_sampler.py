#!/usr/bin/env python3
"""Decoupled low-latency hardware sampler for TUI presentation snapshots."""

from __future__ import annotations

import copy
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[3]
PYTHON_DIR = ROOT / "core" / "python"
if str(PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(PYTHON_DIR))

import leaf_telemetry  # noqa: E402


Collector = Callable[..., dict[str, Any]]


class HardwareSampler:
    def __init__(self, interval: float = 0.25, collector: Collector | None = None):
        self.interval = max(0.1, min(float(interval), 5.0))
        self.collector = collector or leaf_telemetry.collect_fast_hardware
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._latest: dict[str, Any] = {}
        self._sequence = 0

    def sample_once(self) -> dict[str, Any]:
        started = time.monotonic()
        try:
            collected = self.collector(timeout=min(0.25, self.interval), cpu_interval=min(0.03, self.interval / 4))
            error = None
        except (OSError, ValueError, RuntimeError) as exception:
            collected = {"hardware": {}, "availability": {}}
            error = str(exception)
        self._sequence += 1
        sample = {
            "sequence": self._sequence,
            "sampled_at": datetime.now(timezone.utc).isoformat(),
            "collection_seconds": round(time.monotonic() - started, 6),
            "hardware": collected.get("hardware", {}),
            "availability": collected.get("availability", {}),
            "error": error,
        }
        with self._lock:
            self._latest = sample
        return copy.deepcopy(sample)

    def _run(self) -> None:
        while not self._stop.is_set():
            started = time.monotonic()
            self.sample_once()
            self._stop.wait(max(0.0, self.interval - (time.monotonic() - started)))

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="leafos-tui-hardware", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=max(1.0, self.interval * 3))

    def latest(self) -> dict[str, Any]:
        with self._lock:
            return copy.deepcopy(self._latest)


def apply_live_hardware(snapshot: dict[str, Any], sample: dict[str, Any]) -> dict[str, Any]:
    if not sample:
        return snapshot
    hardware = sample.get("hardware", {})
    gpu = hardware.get("gpu", {}) if isinstance(hardware.get("gpu"), dict) else {}
    cpu = hardware.get("cpu", {}) if isinstance(hardware.get("cpu"), dict) else {}
    memory = hardware.get("memory", {}) if isinstance(hardware.get("memory"), dict) else {}
    target = snapshot.setdefault("hardware", {})
    target_gpu = target.setdefault("gpu", {})
    for source, destination in (
        ("name", "name"), ("utilization_percent", "utilization_percent"),
        ("vram_used_gb", "vram_used_gb"), ("vram_total_gb", "vram_total_gb"),
        ("temperature_celsius", "temperature_c"), ("power_watts", "power_watts"),
    ):
        if gpu.get(source) is not None:
            target_gpu[destination] = gpu[source]
    if cpu.get("utilization_percent") is not None:
        target["cpu_percent"] = cpu["utilization_percent"]
    if memory.get("ram_used_gb") is not None:
        target["ram_used_gb"] = memory["ram_used_gb"]
    if memory.get("ram_total_gb") is not None:
        target["ram_total_gb"] = memory["ram_total_gb"]
    target["live"] = True
    target["sample_sequence"] = int(sample.get("sequence", 0))
    target["sampled_at"] = sample.get("sampled_at")
    try:
        sampled_at = datetime.fromisoformat(str(sample.get("sampled_at", "")).replace("Z", "+00:00"))
        target["sample_age_seconds"] = round(max(0.0, (datetime.now(timezone.utc) - sampled_at).total_seconds()), 3)
    except ValueError:
        target["sample_age_seconds"] = None
    target["collection_seconds"] = sample.get("collection_seconds")
    target["availability"] = sample.get("availability", {})
    target["sample_error"] = sample.get("error")
    return snapshot
