#!/usr/bin/env python3
"""Condensed loop and hardware summary renderer."""

from __future__ import annotations

from typing import Any


def metric(value: Any, suffix: str = "", decimals: int = 1) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, (int, float)):
        return f"{value:.{decimals}f}{suffix}"
    return f"{value}{suffix}"


def render(snapshot: dict[str, Any]) -> list[str]:
    queue = snapshot["queue"]
    hardware = snapshot["hardware"]
    gpu = hardware["gpu"]
    control = snapshot.get("control", {})
    resident = snapshot.get("resident", {})
    active_process = control.get("active_process", {})
    return [
        f"State {snapshot['run']['state'].upper()} | provider {hardware['provider_health']} | PID {hardware['provider_pid'] or 'n/a'}",
        f"Resident {resident.get('status', 'offline').upper()} | {resident.get('profile', 'offline')} | {resident.get('reason', 'not_started')}",
        f"Targets CPU {metric(resident.get('targets', {}).get('cpu_percent'), '%')} | GPU {metric(resident.get('targets', {}).get('gpu_percent'), '%')} | slots {resident.get('cpu_slots', 0)}",
        f"Queue {queue['waiting']} waiting | {queue['running']} running | {queue['blocked']} blocked",
        f"GPU {metric(gpu['utilization_percent'], '%')} | VRAM {metric(gpu['vram_used_gb'], ' GB')} / {metric(gpu['vram_total_gb'], ' GB')}",
        f"Brain {metric(hardware['brain_generation_tk_s'], ' tk/s', 2)} | CPU {metric(hardware['cpu_percent'], '%')}",
        f"Control {control.get('transport', 'none')} | authenticated {'yes' if control.get('authenticated') else 'no'} | connected {'yes' if control.get('connected') else 'no'}",
        f"Child PID {active_process.get('pid') or 'none'} | task {active_process.get('task_id') or '-'}",
    ]
