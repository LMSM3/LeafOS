#!/usr/bin/env python3
"""LeafOS seven-page terminal observation and control surface."""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import select
import shutil
import sys
import time
from pathlib import Path
from typing import Iterator


TUI_DIR = Path(__file__).resolve().parent
ROOT = TUI_DIR.parents[2]
PYTHON_DIR = ROOT / "core" / "python"
if str(TUI_DIR) not in sys.path:
    sys.path.insert(0, str(TUI_DIR))

import inlet_pipe  # noqa: E402
import hardware_sampler  # noqa: E402
import main_screen  # noqa: E402
from router import RouterState, prompt, route_key  # noqa: E402


PAGE_INDEX = {name: index for index, name in enumerate(main_screen.PAGE_NAMES)}
PROJECT_WIZARD_EXIT = 20


@contextlib.contextmanager
def terminal_session(active: bool) -> Iterator[None]:
    if not active:
        yield
        return
    fd = None
    old_settings = None
    if os.name != "nt":
        import termios
        import tty

        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        tty.setcbreak(fd)
    sys.stdout.write("\033[?1049h\033[?25l\033[2J\033[H")
    sys.stdout.flush()
    try:
        yield
    finally:
        if fd is not None and old_settings is not None:
            import termios

            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        sys.stdout.write("\033[?25h\033[?1049l")
        sys.stdout.flush()


def _read_key(timeout: float) -> str | None:
    if os.name == "nt":
        import msvcrt

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if msvcrt.kbhit():
                key = msvcrt.getwch()
                if key in {"\x00", "\xe0"}:
                    code = msvcrt.getwch()
                    return {"H": "UP", "P": "DOWN", "K": "LEFT", "M": "RIGHT", "\x0f": "SHIFT_TAB"}.get(code, code)
                return {"\r": "ENTER", "\x08": "BACKSPACE", "\x1b": "ESC", "\t": "TAB"}.get(key, key)
            time.sleep(min(0.02, timeout))
        return None
    ready, _, _ = select.select([sys.stdin], [], [], timeout)
    if not ready:
        return None
    key = sys.stdin.read(1)
    if key == "\x1b":
        sequence = ""
        while select.select([sys.stdin], [], [], 0.002)[0]:
            sequence += sys.stdin.read(1)
        return {"[A": "UP", "[B": "DOWN", "[Z": "SHIFT_TAB", "": "ESC"}.get(sequence, "ESC")
    return {"\n": "ENTER", "\r": "ENTER", "\x7f": "BACKSPACE", "\t": "TAB"}.get(key, key)


def _dimensions(args: argparse.Namespace) -> tuple[int, int]:
    terminal = shutil.get_terminal_size((100, 30))
    return args.width or terminal.columns, args.height or terminal.lines


def run_interactive(args: argparse.Namespace, first_snapshot: dict) -> int:
    state = RouterState(page_index=PAGE_INDEX[args.page])
    snapshot = first_snapshot
    cursor = int(snapshot.get("event_cursor", 0))
    previous_size = (0, 0)
    sampler = hardware_sampler.HardwareSampler(args.hardware_interval)
    hardware_sampler.apply_live_hardware(snapshot, sampler.sample_once())
    sampler.start()
    try:
        with terminal_session(True):
            while True:
                if not state.frozen:
                    try:
                        snapshot = inlet_pipe.build_snapshot(args.run, after=cursor, event_limit=args.event_limit)
                        cursor = int(snapshot.get("event_cursor", cursor))
                        hardware_sampler.apply_live_hardware(snapshot, sampler.latest())
                    except (OSError, ValueError) as error:
                        state.message = f"Snapshot refresh failed: {error}"
                width, height = _dimensions(args)
                if (width, height) != previous_size:
                    sys.stdout.write("\033[2J")
                    previous_size = (width, height)
                snapshot["_selection"] = min(state.selection, max(0, len(snapshot.get("tasks", [])) - 1))
                output = main_screen.render(snapshot, state.page_index, width, height, message=prompt(state), help_visible=state.help_visible)
                sys.stdout.write("\033[H" + output + "\033[J")
                sys.stdout.flush()
                key = _read_key(args.refresh)
                if key is None:
                    continue
                action = route_key(state, key)
                if state.confirmation_action == "task_cancel" and not state.confirmation_task_id and snapshot.get("tasks"):
                    selected = snapshot["tasks"][min(state.selection, len(snapshot["tasks"]) - 1)]
                    state.confirmation_task_id = selected["id"]
                if action == "quit":
                    return 0
                if action == "project_wizard":
                    return PROJECT_WIZARD_EXIT
                if action in {"pause_toggle", "approve", "stop", "live_command", "task_retry", "task_cancel", "task_approve", "task_priority_up", "task_priority_down"}:
                    request = {"action": action}
                    if action == "live_command":
                        request["command"] = state.pending_command
                        state.pending_command = ""
                    if action.startswith("task_"):
                        tasks = snapshot.get("tasks", [])
                        if not tasks:
                            state.message = "NO ACTION: no task is selected"
                            continue
                        selected = tasks[min(state.selection, len(tasks) - 1)]
                        request["task_id"] = state.confirmation_task_id if action == "task_cancel" and state.confirmation_task_id else selected["id"]
                        if action in {"task_priority_up", "task_priority_down"}:
                            request["action"] = "task_prioritize"
                            delta = -1 if action == "task_priority_up" else 1
                            request["priority"] = max(0, min(9, int(selected.get("priority", 2)) + delta))
                    ok, detail = inlet_pipe.controller_request(snapshot, request)
                    if action == "task_cancel":
                        state.confirmation_task_id = ""
                    state.message = ("OK: " if ok else "NO ACTION: ") + detail
    finally:
        sampler.stop()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="LeafOS seven-page terminal control surface")
    parser.add_argument("--run", default="active", help="active, latest, a run id, run directory, or target directory")
    parser.add_argument("--page", choices=main_screen.PAGE_NAMES, default="overview")
    parser.add_argument("--once", action="store_true", help="render one frame and exit")
    parser.add_argument("--json", action="store_true", help="emit the normalized snapshot")
    parser.add_argument("--plain", action="store_true", help="disable interactive terminal lifecycle")
    parser.add_argument("--refresh", type=float, default=0.25)
    parser.add_argument("--event-limit", type=int, default=250)
    parser.add_argument("--hardware-interval", type=float, default=0.25)
    parser.add_argument("--after", type=int, default=0, help="emit events after this reconnect cursor")
    parser.add_argument("--width", type=int)
    parser.add_argument("--height", type=int)
    renderer = parser.add_mutually_exclusive_group()
    renderer.add_argument("--native", action="store_true", help="require the ncursesw C renderer")
    renderer.add_argument("--python-renderer", action="store_true", help="force the ANSI Python renderer")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    args.refresh = max(0.1, min(args.refresh, 5.0))
    args.event_limit = max(20, min(args.event_limit, 1000))
    args.hardware_interval = max(0.1, min(args.hardware_interval, 5.0))
    interactive = sys.stdin.isatty() and sys.stdout.isatty() and not args.once and not args.plain
    while True:
        try:
            snapshot = inlet_pipe.build_snapshot(args.run, after=max(0, args.after), event_limit=args.event_limit)
        except (OSError, ValueError) as error:
            print(f"LeafOS TUI: {error}", file=sys.stderr)
            return 2
        if args.json:
            print(json.dumps(snapshot, separators=(",", ":"), ensure_ascii=True))
            return 0
        width, height = _dimensions(args)
        args.page_index = PAGE_INDEX[args.page]
        args.stdin_tty = sys.stdin.isatty()
        args.stdout_tty = sys.stdout.isatty()
        args.width_value = width
        args.height_value = height
        result = None
        if args.native or (interactive and not args.python_renderer):
            import native_bridge

            if args.native or native_bridge.native_binary() is not None:
                try:
                    result = native_bridge.run_native(args, snapshot)
                except (OSError, ValueError) as error:
                    print(f"LeafOS native TUI: {error}", file=sys.stderr)
                    return 2
        if result is None:
            if not interactive:
                print(main_screen.render(snapshot, PAGE_INDEX[args.page], width, height))
                return 0
            result = run_interactive(args, snapshot)
        if result != PROJECT_WIZARD_EXIT:
            return result
        import project_wizard

        try:
            onboarded = project_wizard.run_project_wizard(
                preview=inlet_pipe.live_projects.preview_project_onboarding,
                apply=inlet_pipe.live_projects.apply_project_onboarding,
                recent_targets=inlet_pipe.live_projects.recent_project_targets(),
            )
        except (OSError, ValueError, RuntimeError) as error:
            print(f"LeafOS project onboarding: {error}", file=sys.stderr)
            onboarded = None
        if onboarded is not None:
            args.run = onboarded["run_dir"]
            args.after = 0


if __name__ == "__main__":
    raise SystemExit(main())
