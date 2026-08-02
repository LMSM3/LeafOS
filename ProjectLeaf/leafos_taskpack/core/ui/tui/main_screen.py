#!/usr/bin/env python3
"""Responsive seven-page LeafOS terminal renderer."""

from __future__ import annotations

import textwrap
import sys
from pathlib import Path
from typing import Any, Callable

TUI_DIR = Path(__file__).resolve().parent
if str(TUI_DIR) not in sys.path:
    sys.path.insert(0, str(TUI_DIR))

from panels import events, header, loop, work_order


PAGE_NAMES = tuple(name.lower() for name in header.PAGES)


def _clip(value: Any, width: int) -> str:
    return header.clip(value, width)


def _section(title: str, width: int) -> list[str]:
    return [title.upper(), "-" * min(width, max(8, len(title)))]


def _wrap(value: Any, width: int, indent: str = "") -> list[str]:
    return textwrap.wrap(str(value or ""), width=max(12, width), subsequent_indent=indent) or [""]


def _active_or_last(snapshot: dict[str, Any]) -> dict[str, Any] | None:
    return snapshot.get("active_task") or next(iter(reversed(snapshot.get("tasks", []))), None)


def render_overview(snapshot: dict[str, Any], width: int, height: int) -> list[str]:
    lines = _section("Active work", width)
    project = snapshot.get("project", {})
    if project:
        label = "CATAN2" if project.get("catan2") else Path(str(project.get("target", "project"))).name
        lines.append(f"PROJECT {label} | {project.get('state', 'codebase')} | iteration {project.get('iteration', 0)}")
    active = _active_or_last(snapshot)
    if active:
        lines.append(f"{active['symbol']} {active['id']}  {active['objective']}")
        lines.append(f"  {active['status'].upper()} | {active['role']} | {active['worker']} | attempts {active['attempts']}/{active['max_attempts']}")
    else:
        lines.append("No task is active.")
    blocker = next((task for task in snapshot["tasks"] if task["status"] in {"failed", "blocked", "repair_queued"}), None)
    if blocker:
        lines.append(f"! BLOCKER {blocker['id']}: {blocker['blocker'] or blocker['objective']}")
    lines += [""] + _section("System summary", width) + loop.render(snapshot)
    lines += [""] + _section("Latest", width)
    validation = snapshot["latest_validation"]
    lines.append(f"TEST {validation['status'].upper()}  {validation['task_id'] or '-'}  {validation['summary']}")
    lines.append(f"NEXT {snapshot['run']['next_action']}")
    return lines


def render_tasks(snapshot: dict[str, Any], width: int, height: int) -> list[str]:
    counts = snapshot["queue"]["counts"]
    lines = [
        f"TASK GRAPH | root {snapshot['work_order']['id']} | {counts.get('complete', 0)} complete | "
        f"{snapshot['queue']['running']} active | {snapshot['queue']['waiting']} waiting",
        "",
    ]
    tasks = snapshot["tasks"]
    for index, task in enumerate(tasks):
        connector = "`--" if index == len(tasks) - 1 else "|--"
        marker = ">" if index == int(snapshot.get("_selection", 0)) else " "
        lines.append(_clip(f"{marker}{connector} {task['symbol']} {task['id']} {task['objective']}", width))
        lines.append(_clip(f"    role={task['role']} worker={task['worker']} model={task['model']} attempts={task['attempts']}/{task['max_attempts']} depth={task['correction_depth']}", width))
        if task["blocker"]:
            lines.append(_clip(f"    blocker: {task['blocker']}", width))
    return lines


def render_hardware(snapshot: dict[str, Any], width: int, height: int) -> list[str]:
    hardware = snapshot["hardware"]
    gpu = hardware["gpu"]
    value = loop.metric
    resident = snapshot.get("resident", {})
    benchmark = snapshot.get("benchmark", {})
    best = benchmark.get("best_generation") or {}
    comparison = benchmark.get("comparison", {})
    lines = [
        f"HARDWARE | provider {hardware['provider_health']} | {'live' if hardware.get('live') else 'recorded'} | sample {value(hardware.get('sample_age_seconds'), 's old', 3)}",
        "",
        "GPU 0 | VULKAN | BRAIN STACK",
        f"Model        {hardware['model']}",
        f"Stack        {hardware['stack_entry'] or 'n/a'}",
        f"Provider PID {hardware['provider_pid'] or 'n/a'}",
        f"VRAM         {value(gpu['vram_used_gb'], ' GB')} / {value(gpu['vram_total_gb'], ' GB')}",
        f"Compute      {value(gpu['utilization_percent'], '%')}",
        f"Generation   {value(hardware['brain_generation_tk_s'], ' tk/s', 2)}",
        f"Prompt       {value(hardware['brain_prompt_tk_s'], ' tk/s', 2)}",
        f"Temperature  {value(gpu['temperature_c'], ' C')}",
        f"Power        {value(gpu['power_watts'], ' W')}",
        f"Benchmark    {benchmark.get('status', 'not_run')} | {benchmark.get('completed_cells', 0)}/{benchmark.get('planned_cells', 0)} cells",
        f"Local value  {value(best.get('projected_gross_cloud_equivalent_usd_per_hour'), ' USD/h', 4)} @ {value(comparison.get('comparison_output_usd_per_million'), ' USD/M', 2)}",
        "",
        "HOST",
        f"CPU          {value(hardware['cpu_percent'], '%')}",
        f"RAM          {value(hardware['ram_used_gb'], ' GB')} / {value(hardware['ram_total_gb'], ' GB')}",
        "",
        "SCHEDULER",
        f"Resident     {resident.get('status', 'offline')} | mode {resident.get('mode', 'auto')}",
        f"Profile      {resident.get('profile', 'offline')}",
        f"Reason       {resident.get('reason', 'not_started')}",
        f"Targets      CPU {value(resident.get('targets', {}).get('cpu_percent'), '%')} | GPU {value(resident.get('targets', {}).get('gpu_percent'), '%')}",
        f"Headroom     CPU {value(resident.get('headroom', {}).get('cpu_percent'), '%')} | GPU {value(resident.get('headroom', {}).get('gpu_percent'), '%')}",
        f"Input idle   {value(resident.get('input_idle_seconds'), 's')} | response {value(resident.get('responsiveness_ms'), 'ms')}",
        f"Waiting      {snapshot['queue']['waiting']}",
        f"Running      {snapshot['queue']['running']}",
        f"Blocked      {snapshot['queue']['blocked']}",
    ]
    return lines


def render_queue(snapshot: dict[str, Any], width: int, height: int) -> list[str]:
    queue = snapshot["queue"]
    resident = snapshot.get("resident", {})
    usage = resident.get("usage", {})
    budgets = resident.get("budgets", {})
    lines = [
        f"QUEUE | {queue.get('ready', queue.get('waiting', 0))} ready | {queue['running']} running | {queue.get('repair', 0)} repair | {queue['blocked']} blocked | {queue.get('generated', 0)} generated",
        f"RESIDENT {resident.get('profile', 'offline')} | {resident.get('reason', 'not_started')} | iterations {usage.get('iterations_generated', 0)}/{budgets.get('max_iterations', 0)} | elapsed {loop.metric(usage.get('elapsed_minutes'), 'm')}/{budgets.get('unattended_minutes', 0)}m",
        "",
    ]
    if width >= 100:
        lines.append("POS STATE          PRI DEPTH ROLE       WORKER        TASK")
        for position, task in enumerate(snapshot["tasks"], 1):
            marker = ">" if position - 1 == int(snapshot.get("_selection", 0)) else " "
            lines.append(_clip(f"{marker}{position:>3} {task['status'].upper():<14} P{task['priority']} {task['correction_depth']:>5} {task['role']:<10} {task['worker']:<13} {task['id']} {task['objective']}", width))
    else:
        for position, task in enumerate(snapshot["tasks"], 1):
            marker = ">" if position - 1 == int(snapshot.get("_selection", 0)) else " "
            lines.append(_clip(f"{marker}{position:>2} {task['symbol']} {task['status'].upper():<12} P{task['priority']} {task['id']} {task['objective']}", width))
    tasks = snapshot.get("tasks", [])
    selected = tasks[min(int(snapshot.get("_selection", 0)), len(tasks) - 1)] if tasks else None
    if selected:
        lines += ["", "SELECTED TASK", f"ID {selected['id']} | root {selected['root_id']} | parent {selected['parent_id'] or '-'}", f"Requires {selected['role']} | affinity {selected['worker']} | attempts {selected['attempts']}/{selected['max_attempts']}"]
    return lines


def render_brain(snapshot: dict[str, Any], width: int, height: int) -> list[str]:
    hardware = snapshot["hardware"]
    lines = [
        f"BRAIN STREAM | {hardware['model']} | {loop.metric(hardware['brain_generation_tk_s'], ' tk/s', 2)} | structured",
        "Raw reasoning text is transient and is not persisted by LeafOS.",
        "",
    ]
    available = max(3, height - 9)
    for record in snapshot["brain"][-available:]:
        timestamp = str(record["time"])[11:19]
        marker = "D" if record["durable"] else "T"
        lines.append(_clip(f"{timestamp} {record['category']:<9} [{marker}] {record['task_id'] or '-'} {record['summary']}", width))
    return lines


def render_ledger(snapshot: dict[str, Any], width: int, height: int) -> list[str]:
    lines = [f"LEDGER | run {snapshot['run']['id']} | cursor {snapshot['event_cursor']}", ""]
    available = max(3, height - 8)
    lines.extend(events.render(snapshot["ledger"], width, available))
    return lines


def render_results(snapshot: dict[str, Any], width: int, height: int) -> list[str]:
    results = snapshot["results"]
    gate = "READY" if results["gate_ready"] else "BLOCKED"
    lines = [f"RESULTS | gate status {gate}", "", "TESTS"]
    if results["validation"]:
        for result in results["validation"]:
            status = "+" if result.get("exit_code", 0) == 0 else "!"
            lines.append(_clip(f"{status} {result.get('step_id') or result.get('kind', 'validation')} exit={result.get('exit_code', '?')}", width))
    else:
        lines.append("o No validation evidence recorded.")
    lines += ["", "CHANGED FILES"]
    lines.extend([_clip(f"M {item['path']} {item['sha256']}", width) for item in results["changed_files"]] or ["- No changed-file hashes recorded."])
    lines += ["", "ARTIFACTS"]
    lines.extend(_clip(f"- {Path(path).name} | {path}", width) for path in results["artifacts"][: max(2, height // 4)])
    if results["failures"]:
        lines += ["", "FAILURES"] + [_clip(f"! {item['task_id']} {item['summary']}", width) for item in results["failures"]]
    return lines


RENDERERS: tuple[Callable[[dict[str, Any], int, int], list[str]], ...] = (
    render_overview, render_tasks, render_hardware, render_queue, render_brain, render_ledger, render_results,
)


def render_compact(snapshot: dict[str, Any], width: int, height: int) -> list[str]:
    active = _active_or_last(snapshot)
    hardware = snapshot["hardware"]
    resident = snapshot.get("resident", {})
    lines = [
        _clip(f"LeafOS {snapshot['run']['id']} | {snapshot['run']['state'].upper()} | {snapshot['run']['safety']}", width),
        _clip("1 Over  2 Task  3 HW  4 Queue  5 Brain  6 Ledg  7 Result", width),
        "",
        _clip(f"{active['symbol']} {active['id']} {active['objective']}" if active else "No active task", width),
        _clip(f"GPU {loop.metric(hardware['gpu']['utilization_percent'], '%')} | {loop.metric(hardware['brain_generation_tk_s'], ' tk/s', 2)} | CPU {loop.metric(hardware['cpu_percent'], '%')}", width),
        _clip(f"Resident {resident.get('profile', 'offline')} | {resident.get('reason', 'not_started')}", width),
        _clip(f"Queue {snapshot['queue']['waiting']} | Failed {snapshot['queue']['blocked']} | checkpoint {snapshot['run']['checkpoint_age']}", width),
        "",
        "n new/open | Tab next | ? help | q quit",
    ]
    return lines[:height]


def render(snapshot: dict[str, Any], page_index: int, width: int, height: int, *, message: str = "", help_visible: bool = False) -> str:
    width = max(40, width)
    height = max(10, height)
    if width < 80 or height < 24:
        lines = render_compact(snapshot, width, height)
    else:
        lines = header.render(snapshot, page_index, width)
        lines += ["=" * width]
        body_height = max(4, height - len(lines) - 2)
        lines += RENDERERS[page_index](snapshot, width, body_height)[:body_height]
        footer = message or (
            "KEYS n new/open | :improve | :mode | :targets | r retry | x cancel | p pause | :stop | q close"
            if help_visible else "n new/open | Tab next | 1-7 page | ? help | q close interface"
        )
        lines = lines[: height - 1] + [_clip(footer, width)]
    return "\n".join(_clip(line, width).ljust(width) for line in lines[:height])
