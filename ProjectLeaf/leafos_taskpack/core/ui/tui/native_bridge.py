#!/usr/bin/env python3
"""Atomic snapshot and authenticated loopback-control bridge for the native C TUI."""

from __future__ import annotations

import json
import os
import re
import secrets
import socket
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

import inlet_pipe
import hardware_sampler


ROOT = Path(__file__).resolve().parents[3]
CONTROL_ACTIONS = {"pause_toggle", "approve", "stop", "live_command", "task_retry", "task_cancel", "task_approve", "task_prioritize"}
MAX_CONTROL_BYTES = 4096
MAX_LIVE_COMMAND_CHARS = 512
TASK_ID_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9._-]{2,63}$")


class ControlSocketServer:
    def __init__(self):
        self.token = secrets.token_hex(32)
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket.bind(("127.0.0.1", 0))
        self.socket.listen(4)
        self.socket.setblocking(False)
        self.host, self.port = self.socket.getsockname()

    @property
    def endpoint(self) -> str:
        return f"{self.host}:{self.port}"

    def poll(self) -> list[dict[str, Any]]:
        actions: list[dict[str, Any]] = []
        while True:
            try:
                connection, address = self.socket.accept()
            except BlockingIOError:
                break
            with connection:
                connection.settimeout(0.2)
                if address[0] != "127.0.0.1":
                    continue
                chunks = bytearray()
                while len(chunks) <= MAX_CONTROL_BYTES:
                    try:
                        chunk = connection.recv(min(512, MAX_CONTROL_BYTES + 1 - len(chunks)))
                    except (socket.timeout, OSError):
                        break
                    if not chunk:
                        break
                    chunks.extend(chunk)
                    if b"\n" in chunks:
                        break
                if len(chunks) > MAX_CONTROL_BYTES:
                    continue
                try:
                    value = json.loads(bytes(chunks).split(b"\n", 1)[0])
                except (json.JSONDecodeError, UnicodeDecodeError):
                    continue
                token = str(value.get("token", ""))
                action = str(value.get("action", ""))
                if not secrets.compare_digest(token, self.token) or action not in CONTROL_ACTIONS:
                    continue
                request: dict[str, Any] = {"action": action}
                if action == "live_command":
                    command = value.get("command")
                    if (
                        not isinstance(command, str) or not 1 <= len(command) <= MAX_LIVE_COMMAND_CHARS
                        or any(ord(char) < 32 for char in command)
                    ):
                        continue
                    request["command"] = command
                elif action.startswith("task_"):
                    task_id = str(value.get("task_id", ""))
                    if not TASK_ID_PATTERN.fullmatch(task_id):
                        continue
                    request["task_id"] = task_id
                if action == "task_prioritize":
                    priority = value.get("priority")
                    if not isinstance(priority, int) or isinstance(priority, bool) or not 0 <= priority <= 9:
                        continue
                    request["priority"] = priority
                actions.append(request)
        return actions

    def close(self) -> None:
        self.socket.close()

    def __enter__(self) -> "ControlSocketServer":
        return self

    def __exit__(self, *_args: Any) -> None:
        self.close()


def native_binary() -> Path | None:
    candidates = (ROOT / "build" / "leaf-tui.exe", ROOT / "build" / "leaf-tui")
    return next((path for path in candidates if path.is_file()), None)


def _atomic_text(path: Path, text: str) -> None:
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(text, encoding="utf-8")
    for attempt in range(20):
        try:
            os.replace(temporary, path)
            return
        except PermissionError:
            if attempt == 19:
                temporary.unlink(missing_ok=True)
                raise
            time.sleep(0.005)


def _write_snapshot(path: Path, snapshot: dict[str, Any]) -> None:
    _atomic_text(path, json.dumps(snapshot, separators=(",", ":"), ensure_ascii=True))


def run_native(args: Any, first_snapshot: dict[str, Any]) -> int:
    binary = native_binary()
    if binary is None:
        raise FileNotFoundError("native TUI is not built; run bin/build_tui.sh")
    sampler = hardware_sampler.HardwareSampler(getattr(args, "hardware_interval", 0.25))
    hardware_sampler.apply_live_hardware(first_snapshot, sampler.sample_once())
    with tempfile.TemporaryDirectory(prefix="leafos-tui-") as directory:
        bridge_dir = Path(directory)
        snapshot_path = bridge_dir / "snapshot.json"
        message_path = bridge_dir / "message.txt"
        message_path.write_text("", encoding="utf-8")
        with ControlSocketServer() as control_server:
            first_snapshot.setdefault("control", {}).update({"transport": "tcp", "endpoint": control_server.endpoint, "authenticated": True, "connected": True})
            _write_snapshot(snapshot_path, first_snapshot)
            command = [
                str(binary), "--snapshot", str(snapshot_path), "--control-endpoint", control_server.endpoint,
                "--control-token", control_server.token, "--message", str(message_path),
                "--refresh", str(int(args.refresh * 1000)), "--page", str(args.page_index + 1),
            ]
            if args.once or args.plain or not (args.stdin_tty and args.stdout_tty):
                command.extend(["--plain", "--width", str(args.width_value), "--height", str(args.height_value)])
                return subprocess.run(command, cwd=ROOT, check=False).returncode
            sampler.start()
            process = subprocess.Popen(command, cwd=ROOT)
            cursor = int(first_snapshot.get("event_cursor", 0))
            snapshot = first_snapshot
            try:
                while process.poll() is None:
                    started = time.monotonic()
                    try:
                        snapshot = inlet_pipe.build_snapshot(args.run, after=cursor, event_limit=args.event_limit)
                        cursor = int(snapshot.get("event_cursor", cursor))
                        hardware_sampler.apply_live_hardware(snapshot, sampler.latest())
                        snapshot.setdefault("control", {}).update({"transport": "tcp", "endpoint": control_server.endpoint, "authenticated": True, "connected": True})
                        _write_snapshot(snapshot_path, snapshot)
                    except (OSError, ValueError) as error:
                        _atomic_text(message_path, f"Snapshot refresh failed: {error}")
                    for request in control_server.poll():
                        ok, detail = inlet_pipe.controller_request(snapshot, request)
                        _atomic_text(message_path, ("OK: " if ok else "NO ACTION: ") + detail)
                    remaining = args.refresh - (time.monotonic() - started)
                    if remaining > 0:
                        time.sleep(remaining)
                return int(process.returncode or 0)
            except KeyboardInterrupt:
                process.terminate()
                try:
                    return process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    return process.wait(timeout=5)
            finally:
                sampler.stop()
