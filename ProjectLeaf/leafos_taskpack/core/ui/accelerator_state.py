#!/usr/bin/env python3
"""Read-only accelerator/provider capability state for the operator interface."""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]


def _read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _process_alive(pid_path: Path) -> tuple[bool, int | None]:
    try:
        pid = int(pid_path.read_text(encoding="utf-8").strip())
        if os.name == "nt":
            handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)  # type: ignore[attr-defined]
            if not handle:
                return False, None
            ctypes.windll.kernel32.CloseHandle(handle)  # type: ignore[attr-defined]
        else:
            os.kill(pid, 0)
        return True, pid
    except (OSError, ValueError):
        return False, None


def _health(endpoint: str, timeout: float) -> tuple[str, str]:
    try:
        with urllib.request.urlopen(endpoint.rstrip("/") + "/health", timeout=timeout) as response:
            return ("ok", f"HTTP {response.status}") if 200 <= response.status < 300 else ("error", f"HTTP {response.status}")
    except urllib.error.HTTPError as exc:
        return "error", f"HTTP {exc.code}"
    except (OSError, TimeoutError, urllib.error.URLError) as exc:
        return "unavailable", str(exc)


def build_state(root: Path = ROOT, timeout: float = 0.25) -> dict[str, Any]:
    config_path = root / "config" / "vulkan-provider-stack.json"
    config = _read_json(config_path, {})
    server_config = config.get("server", {}) if isinstance(config, dict) else {}
    server = Path(str(server_config.get("executable", ""))) if server_config.get("executable") else None
    model = Path(str(server_config.get("model", ""))) if server_config.get("model") else None
    endpoint = f"http://{server_config.get('host', '127.0.0.1')}:{server_config.get('port', 8080)}"
    process_alive, pid = _process_alive(root / "runs" / "vulkan-provider" / "llama-server.pid")
    health, health_detail = _health(endpoint, timeout)
    backend_ready = bool(server and server.is_file() and config.get("backend") == "vulkan")
    model_ready = bool(model and model.is_file())
    if health == "ok" and backend_ready:
        state = "gpu_provider_ready"
    elif backend_ready or process_alive:
        state = "gpu_degraded"
    elif server and server.is_file():
        state = "cpu_fallback"
    else:
        state = "cpu_fallback"
    return {
        "schema": "leafos.accelerator-state.v1", "state": state,
        "gpu_available": backend_ready, "gpu_backend_ready": backend_ready,
        "gpu_provider_ready": health == "ok" and backend_ready,
        "gpu_degraded": state == "gpu_degraded", "cpu_fallback": True,
        "provider": {
            "name": config.get("provider", "llamacpp") if isinstance(config, dict) else "llamacpp",
            "endpoint": endpoint, "health": health, "health_detail": health_detail,
            "process_alive": process_alive, "pid": pid,
        },
        "backend": config.get("backend", "unknown") if isinstance(config, dict) else "unknown",
        "server": str(server) if server else "", "server_exists": bool(server and server.is_file()),
        "model": str(model) if model else "", "model_exists": model_ready,
        "safe_start_command": "leafctl provider-stack start" if backend_ready and model_ready else "leafctl provider-stack check",
    }


def main() -> int:
    parser = argparse.ArgumentParser(prog="leafctl accelerator")
    parser.add_argument("action", nargs="?", default="status", choices=["status", "test", "fallback"])
    parser.add_argument("mode", nargs="?", default="cpu")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    state = build_state()
    if args.action == "fallback":
        if args.mode != "cpu":
            parser.error("only the explicit cpu fallback is currently supported")
        state = dict(state)
        state.update({"state": "cpu_fallback", "selected_fallback": "cpu", "persistent_change": False})
    if args.json:
        print(json.dumps(state, sort_keys=True, separators=(",", ":")))
    else:
        print(f"Accelerator  {state['state']}")
        print(f"Provider     {state['provider']['health']} at {state['provider']['endpoint']}")
        print(f"Backend      {state['backend']} (ready={str(state['gpu_backend_ready']).lower()})")
        print(f"CPU fallback available")
        print(f"Next         {state['safe_start_command']}")
    return 0 if args.action != "test" or state["gpu_provider_ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
