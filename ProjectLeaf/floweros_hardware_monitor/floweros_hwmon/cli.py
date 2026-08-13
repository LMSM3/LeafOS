from __future__ import annotations

import argparse
import json
import time

from rich.console import Console

from . import __version__
from .sensors import SensorCollector
from .tui import render_snapshot, run_live


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="floweros-hwmon",
        description="FlowerOS branded terminal hardware monitor.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--interval", type=float, default=1.5, help="refresh interval in seconds")
    parser.add_argument("--once", action="store_true", help="print one dashboard snapshot and exit")
    parser.add_argument("--json", action="store_true", help="print one JSON snapshot and exit")
    parser.add_argument("--no-alt-screen", action="store_true", help="render in the current terminal buffer")
    parser.add_argument("--no-external-sensors", action="store_true", help="skip nvidia-smi, sensors, and Windows CIM probes")
    parser.add_argument("--external-sensor-interval", type=float, default=5.0, help="seconds between slower sensor probes")
    parser.add_argument("--fan-min-rpm", type=int, default=700, help="minimum RPM for estimated fan curve")
    parser.add_argument("--fan-max-rpm", type=int, default=4200, help="maximum RPM for estimated fan curve")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    collector = SensorCollector(
        fan_min_rpm=args.fan_min_rpm,
        fan_max_rpm=args.fan_max_rpm,
        external_sensor_interval=args.external_sensor_interval,
        include_external=not args.no_external_sensors,
    )
    if args.json:
        collector.sample()
        time.sleep(min(max(args.interval, 0.1), 0.4))
        print(json.dumps(collector.sample(), indent=2))
        return 0
    if args.once:
        collector.sample()
        time.sleep(min(max(args.interval, 0.1), 0.4))
        console = Console()
        console.print(render_snapshot(collector.sample(), console.size.width))
        return 0
    try:
        run_live(collector, interval=args.interval, alt_screen=not args.no_alt_screen)
    except KeyboardInterrupt:
        return 0
    return 0
