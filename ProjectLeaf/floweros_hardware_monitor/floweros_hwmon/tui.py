from __future__ import annotations

import time
from datetime import timedelta
from typing import Any

from rich import box
from rich.console import Console, Group
from rich.live import Live
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .sensors import SensorCollector


def bytes_human(value: float | int | None) -> str:
    if value is None:
        return "--"
    amount = float(value)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB", "PiB"):
        if abs(amount) < 1024.0 or unit == "PiB":
            return f"{amount:,.1f} {unit}" if unit != "B" else f"{amount:,.0f} {unit}"
        amount /= 1024.0
    return f"{amount:,.1f} PiB"


def rate_human(value: float | int | None) -> str:
    if value is None:
        return "--"
    return f"{bytes_human(value)}/s"


def percent_style(percent: float | int | None) -> str:
    if percent is None:
        return "dim"
    value = float(percent)
    if value >= 90:
        return "bold red"
    if value >= 75:
        return "yellow"
    return "green"


def bar(percent: float | int | None, width: int = 24) -> str:
    if percent is None:
        return "[dim]" + ("-" * width) + "[/] --"
    value = max(0.0, min(100.0, float(percent)))
    filled = round(width * (value / 100.0))
    text = "#" * filled + "-" * (width - filled)
    return f"[{percent_style(value)}]{text}[/] {value:5.1f}%"


def render_snapshot(snapshot: dict[str, Any], width: int | None = None) -> Group:
    header = _header(snapshot)
    if width is not None and width >= 140:
        top = Table.grid(expand=True)
        top.add_column(ratio=1)
        top.add_column(ratio=1)
        top.add_column(ratio=1)
        top.add_row(_cpu_panel(snapshot), _memory_panel(snapshot), _thermal_panel(snapshot))

        bottom = Table.grid(expand=True)
        bottom.add_column(ratio=1)
        bottom.add_column(ratio=1)
        bottom.add_row(_disk_panel(snapshot), _network_panel(snapshot))
    else:
        top = Group(_cpu_panel(snapshot), _memory_panel(snapshot), _thermal_panel(snapshot))
        bottom = Group(_disk_panel(snapshot), _network_panel(snapshot))

    return Group(header, top, bottom, _gpu_panel(snapshot), _note_panel(snapshot))


def run_live(
    collector: SensorCollector,
    interval: float = 1.5,
    console: Console | None = None,
    alt_screen: bool = True,
) -> None:
    console = console or Console()
    snapshot = collector.sample()
    refresh = max(1.0, min(12.0, 1.0 / max(interval, 0.1)))
    with Live(
        render_snapshot(snapshot, console.size.width),
        console=console,
        refresh_per_second=refresh,
        screen=alt_screen,
        transient=False,
    ) as live:
        while True:
            time.sleep(max(0.1, interval))
            live.update(render_snapshot(collector.sample(), console.size.width))


def _header(snapshot: dict[str, Any]) -> Panel:
    grid = Table.grid(expand=True)
    grid.add_column(ratio=2)
    grid.add_column(ratio=1, justify="right")
    uptime = snapshot.get("uptime_seconds")
    uptime_text = str(timedelta(seconds=int(uptime))) if isinstance(uptime, (int, float)) else "--"
    left = Text.assemble(
        ("FlowerOS", "bold magenta"),
        (" Hardware Monitor", "bold green"),
        ("  read-only sensor deck", "dim"),
    )
    right = Text.assemble(
        (escape(snapshot.get("timestamp", "--")), "cyan"),
        "\n",
        (escape(snapshot.get("host", "--")), "bold"),
        "  ",
        (escape(snapshot.get("platform", "--")), "dim"),
        f"  uptime {uptime_text}",
    )
    grid.add_row(left, right)
    return Panel(grid, border_style="magenta", box=box.ASCII)


def _cpu_panel(snapshot: dict[str, Any]) -> Panel:
    cpu = snapshot.get("cpu", {})
    table = Table.grid(expand=True)
    table.add_column()
    table.add_row(f"[bold]CPU[/]  {bar(cpu.get('percent'))}")
    table.add_row(
        f"cores physical/logical: [cyan]{cpu.get('physical') or '--'}[/]/[cyan]{cpu.get('logical') or '--'}[/]"
    )
    freq = cpu.get("frequency_mhz")
    if freq:
        table.add_row(
            "clock: "
            f"[cyan]{_mhz(freq.get('current'))}[/] "
            f"min {_mhz(freq.get('min'))} max {_mhz(freq.get('max'))}"
        )
    if cpu.get("load_avg"):
        load = " ".join(f"{value:.2f}" for value in cpu["load_avg"])
        table.add_row(f"load avg: [cyan]{load}[/]")
    per_core = cpu.get("per_core") or []
    if per_core:
        core_table = Table.grid(expand=True)
        core_table.add_column()
        lines = []
        for index, value in enumerate(per_core[:32]):
            lines.append(f"C{index:02d} {value:5.1f}%")
        for offset in range(0, len(lines), 4):
            core_table.add_row("   ".join(lines[offset : offset + 4]))
        if len(per_core) > 32:
            core_table.add_row(f"[dim]+ {len(per_core) - 32} more logical cores[/]")
        table.add_row(core_table)
    return Panel(table, title="Processor", border_style="green", box=box.ASCII)


def _memory_panel(snapshot: dict[str, Any]) -> Panel:
    memory = snapshot.get("memory", {})
    table = Table.grid(expand=True)
    table.add_column()
    ram = memory.get("ram") or {}
    swap = memory.get("swap") or {}
    if ram:
        table.add_row(f"[bold]RAM[/]   {bar(ram.get('percent'))}")
        table.add_row(f"used {bytes_human(ram.get('used'))} / {bytes_human(ram.get('total'))}")
        table.add_row(f"free {bytes_human(ram.get('available'))}")
    else:
        table.add_row("[dim]RAM unavailable[/]")
    if swap:
        table.add_row("")
        table.add_row(f"[bold]Swap[/]  {bar(swap.get('percent'))}")
        table.add_row(f"used {bytes_human(swap.get('used'))} / {bytes_human(swap.get('total'))}")
    battery = snapshot.get("battery")
    if battery:
        plugged = "plugged" if battery.get("plugged") else "battery"
        table.add_row("")
        table.add_row(f"[bold]Power[/] {bar(battery.get('percent'), 18)} {plugged}")
    return Panel(table, title="Memory + Power", border_style="cyan", box=box.ASCII)


def _thermal_panel(snapshot: dict[str, Any]) -> Panel:
    table = Table(expand=True, box=box.ASCII, pad_edge=False)
    table.add_column("Sensor")
    table.add_column("Value", justify="right")
    table.add_column("Source", style="dim")
    temps = snapshot.get("temperatures") or []
    fans = snapshot.get("fans") or []
    if temps:
        for temp in temps[:8]:
            value = temp.get("celsius")
            style = _temp_style(value)
            table.add_row(
                escape(str(temp.get("name", "temp")))[:32],
                f"[{style}]{value:.1f} C[/]" if isinstance(value, (int, float)) else "--",
                escape(str(temp.get("source", ""))),
            )
        if len(temps) > 8:
            table.add_row("[dim]more temps[/]", f"[dim]+{len(temps) - 8}[/]", "")
    else:
        table.add_row("[dim]No temperature sensor[/]", "--", "")
    table.add_section()
    for fan in fans[:6]:
        rpm = fan.get("rpm")
        pct = fan.get("percent")
        estimated = fan.get("estimated")
        badge = "[yellow]EST[/] " if estimated else ""
        if rpm is not None and pct is not None:
            value = f"{badge}{rpm:,.0f} RPM / {pct:.1f}%"
        elif rpm is not None:
            value = f"{badge}{rpm:,.0f} RPM"
        elif pct is not None:
            value = f"{badge}{pct:.1f}%"
        else:
            value = f"{badge}--"
        table.add_row(
            escape(str(fan.get("name", "fan")))[:32],
            value,
            escape(str(fan.get("source", ""))),
        )
    return Panel(table, title="Thermals + Fans", border_style="yellow", box=box.ASCII)


def _disk_panel(snapshot: dict[str, Any]) -> Panel:
    table = Table(expand=True, box=box.ASCII, pad_edge=False)
    table.add_column("Mount")
    table.add_column("Use")
    table.add_column("Used", justify="right")
    table.add_column("Free", justify="right")
    disks = snapshot.get("disks") or []
    for disk in disks[:8]:
        table.add_row(
            escape(str(disk.get("mountpoint", "")))[:24],
            bar(disk.get("percent"), 12),
            bytes_human(disk.get("used")),
            bytes_human(disk.get("free")),
        )
    if not disks:
        table.add_row("[dim]No disk data[/]", "--", "--", "--")
    if len(disks) > 8:
        table.add_row(f"[dim]+ {len(disks) - 8} more[/]", "", "", "")
    io = snapshot.get("disk_io") or {}
    footer = f"read {rate_human(io.get('read_bps'))}  write {rate_human(io.get('write_bps'))}"
    return Panel(Group(table, Text(footer, style="dim")), title="Storage", border_style="blue", box=box.ASCII)


def _network_panel(snapshot: dict[str, Any]) -> Panel:
    table = Table(expand=True, box=box.ASCII, pad_edge=False)
    table.add_column("Interface")
    table.add_column("RX", justify="right")
    table.add_column("TX", justify="right")
    table.add_column("Speed", justify="right")
    rows = snapshot.get("network") or []
    active = sorted(rows, key=lambda item: (item.get("recv_bps", 0) + item.get("sent_bps", 0)), reverse=True)
    for row in active[:8]:
        speed = row.get("speed_mbps")
        speed_text = f"{speed} Mb/s" if speed else "--"
        up = "[green]up[/]" if row.get("is_up") else "[dim]down[/]"
        table.add_row(
            f"{escape(str(row.get('name', 'net')))[:24]} {up}",
            rate_human(row.get("recv_bps")),
            rate_human(row.get("sent_bps")),
            speed_text,
        )
    if not rows:
        table.add_row("[dim]No network data[/]", "--", "--", "--")
    if len(rows) > 8:
        table.add_row(f"[dim]+ {len(rows) - 8} more[/]", "", "", "")
    return Panel(table, title="Network", border_style="magenta", box=box.ASCII)


def _gpu_panel(snapshot: dict[str, Any]) -> Panel:
    gpus = snapshot.get("gpus") or []
    if not gpus:
        return Panel("[dim]No GPU telemetry source found. NVIDIA cards report through nvidia-smi when available.[/]",
                     title="GPU", border_style="white", box=box.ASCII)
    table = Table(expand=True, box=box.ASCII, pad_edge=False)
    table.add_column("GPU")
    table.add_column("Load", justify="right")
    table.add_column("Mem", justify="right")
    table.add_column("Power", justify="right")
    for gpu in gpus:
        mem_used = gpu.get("memory_used_mib")
        mem_total = gpu.get("memory_total_mib")
        mem = "--"
        if isinstance(mem_used, (int, float)) and isinstance(mem_total, (int, float)) and mem_total:
            mem = f"{mem_used:,.0f}/{mem_total:,.0f} MiB"
        power = "--"
        if gpu.get("power_draw_w") is not None:
            power = f"{gpu.get('power_draw_w'):.1f} W"
            if gpu.get("power_limit_w") is not None:
                power += f" / {gpu.get('power_limit_w'):.0f} W"
        table.add_row(
            escape(str(gpu.get("name", "GPU")))[:36],
            f"{gpu.get('utilization_percent'):.1f}%" if gpu.get("utilization_percent") is not None else "--",
            mem,
            power,
        )
    return Panel(table, title="GPU", border_style="white", box=box.ASCII)


def _note_panel(snapshot: dict[str, Any]) -> Panel:
    notes = snapshot.get("notes") or []
    if not notes:
        text = "Ctrl+C to quit. Sensor visibility depends on OS and motherboard vendor."
    else:
        lines = ["Ctrl+C to quit. Sensor visibility depends on OS and motherboard vendor."]
        for note in notes[:3]:
            style = "yellow" if note.get("level") == "estimate" else "dim"
            lines.append(f"[{style}]{escape(str(note.get('message', '')))}[/]")
        text = "\n".join(lines)
    return Panel(text, border_style="dim", box=box.ASCII)


def _mhz(value: Any) -> str:
    if not isinstance(value, (int, float)) or value <= 0:
        return "--"
    return f"{value:,.0f} MHz"


def _temp_style(value: Any) -> str:
    if not isinstance(value, (int, float)):
        return "dim"
    if value >= 90:
        return "bold red"
    if value >= 75:
        return "yellow"
    return "green"
