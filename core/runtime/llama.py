from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any, Callable

from core.config import Settings, resolve_llama_cli
from core.models.inventory import local_model_path
from core.state import append_event, atomic_json, read_json, utc_now


class RuntimeError(ValueError):
    pass


def runtime_identity(settings: Settings) -> dict[str, Any]:
    executable = resolve_llama_cli(settings)
    if not executable:
        return {"reachable": False, "path": None, "version": None, "backend": "llama.cpp", "device": None}
    version = None
    device = None
    try:
        probe = subprocess.run([str(executable), "--version"], capture_output=True, text=True, timeout=10, check=False)
        version = (probe.stdout or probe.stderr).strip().splitlines()[0]
        devices = subprocess.run([str(executable), "--list-devices"], capture_output=True, text=True, timeout=10, check=False)
        lines = [
            line.strip() for line in (devices.stdout + devices.stderr).splitlines()
            if ":" in line and not line.strip().casefold().startswith("available devices")
        ]
        device = lines[0] if lines else None
        reachable = probe.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        reachable = False
    return {"reachable": reachable, "path": str(executable), "version": version, "backend": "llama.cpp", "device": device}


def process_alive(pid: int | None) -> bool:
    if not isinstance(pid, int) or pid <= 0:
        return False
    try:
        if os.name == "nt":
            result = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"], capture_output=True, text=True, timeout=5)
            return result.returncode == 0 and f'"{pid}"' in result.stdout
        os.kill(pid, 0)
        return True
    except (OSError, subprocess.TimeoutExpired):
        return False


def _record_load_result(settings: Settings, model_id: str, return_code: int) -> None:
    inventory = read_json(settings.inventory_path, {})
    for item in inventory.get("models", []):
        if item.get("id") != model_id:
            continue
        item["load_status"] = "verified" if return_code == 0 else ("interrupted" if return_code == 130 else "failed")
        item["last_exit_code"] = return_code
        item["last_load_at"] = utc_now()
        if return_code == 0:
            item["runtime_compatibility"] = "verified"
            item["runtime_compatible"] = True
        break
    if inventory:
        atomic_json(settings.inventory_path, inventory)


def _model_command(
    settings: Settings,
    model: dict[str, Any],
    prompt: str | None,
    tokens: int,
    context: int | None,
    cpu: bool,
) -> list[str]:
    executable = resolve_llama_cli(settings)
    if not executable:
        raise RuntimeError("llama-cli is missing; install llama.cpp or set runtime.llama_cli")
    model_path = Path(model["path"])
    if not model_path.is_file():
        raise RuntimeError(f"model is missing: {model_path}")
    model_argument = str(model_path)
    if os.name != "nt" and executable.suffix.casefold() == ".exe":
        model_argument = str(local_model_path(str(model_path), "nt"))
    command = [str(executable), "-m", model_argument, "-c", str(context or settings.context)]
    if cpu:
        command.extend(["-ngl", "0"])
    elif settings.gpu_layers is None:
        command.extend(["-ngl", "999", "--fit", "on"])
    else:
        command.extend(["-ngl", str(settings.gpu_layers)])
    if prompt is not None:
        command.extend([
            "-p", prompt, "-n", str(tokens), "--no-display-prompt",
            "--single-turn", "--simple-io", "--reasoning", "off",
        ])
    return command


def _extract_response(stdout: str, prompt: str | None) -> str:
    if not prompt:
        return stdout.strip()
    normalized = stdout.replace("\r\n", "\n").replace("\r", "\n")
    marker = "> " + prompt.replace("\r\n", "\n").replace("\r", "\n")
    start = normalized.rfind(marker)
    if start >= 0:
        response = normalized[start + len(marker):].lstrip("\n")
    else:
        # llama.cpp abbreviates sufficiently long prompt echoes with a final
        # `` ... (truncated)`` line even when --no-display-prompt is selected.
        # Keep the full stdout as evidence, but isolate the response after that
        # runtime-owned marker for the worker-output artifact.
        truncated = " ... (truncated)\n"
        start = normalized.rfind(truncated)
        if start < 0:
            return normalized.strip()
        response = normalized[start + len(truncated):].lstrip("\n")
    for terminator in ("\n[ Prompt:", "\n\nExiting...", "\nExiting..."):
        position = response.find(terminator)
        if position >= 0:
            response = response[:position]
    return response.strip()


def _stop_process(process: subprocess.Popen[Any], *, capture: bool) -> tuple[str, str]:
    stdout = ""
    stderr = ""
    if process.poll() is None:
        process.terminate()
    try:
        if capture:
            stdout, stderr = process.communicate(timeout=15)
        else:
            process.wait(timeout=15)
    except subprocess.TimeoutExpired:
        process.kill()
        if capture:
            stdout, stderr = process.communicate()
        else:
            process.wait()
    return stdout or "", stderr or ""


def _execute_model(
    settings: Settings,
    model: dict[str, Any],
    prompt: str | None,
    tokens: int,
    context: int | None,
    cpu: bool,
    *,
    capture: bool,
    timeout_seconds: int | None = None,
    process_started: Callable[[int], None] | None = None,
) -> dict[str, Any]:
    command = _model_command(settings, model, prompt, tokens, context, cpu)
    model_path = Path(model["path"])
    started_at = utc_now()
    state = read_json(settings.state_path, {})
    state.update({
        "runtime": "starting", "model_id": model["id"], "model_path": str(model_path),
        "backend": "llama.cpp", "started_at": started_at, "pid": None, "last_error": None,
    })
    atomic_json(settings.state_path, state)
    append_event(settings.events_path, "runtime.starting", model_id=model["id"], cpu=cpu)
    process: subprocess.Popen[Any] | None = None
    stdout = ""
    stderr = ""
    try:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE if capture else None,
            stderr=subprocess.PIPE if capture else None,
            text=capture,
            encoding="utf-8" if capture else None,
            errors="replace" if capture else None,
        )
        state.update({"runtime": "working", "pid": process.pid})
        atomic_json(settings.state_path, state)
        append_event(settings.events_path, "runtime.started", model_id=model["id"], pid=process.pid)
        if process_started is not None:
            try:
                process_started(process.pid)
            except Exception as error:
                _stop_process(process, capture=capture)
                raise RuntimeError(f"failed to bind llama.cpp process ownership: {error}") from error
        if capture:
            stdout, stderr = process.communicate(timeout=timeout_seconds)
            stdout = stdout or ""
            stderr = stderr or ""
            return_code = int(process.returncode or 0)
        else:
            return_code = process.wait()
    except subprocess.TimeoutExpired:
        if process is not None:
            stdout, stderr = _stop_process(process, capture=capture)
        return_code = 124
        state["last_error"] = f"llama-cli timed out after {timeout_seconds} seconds"
    except KeyboardInterrupt:
        if process is not None:
            stdout, stderr = _stop_process(process, capture=capture)
        return_code = 130
    except OSError as error:
        return_code = 127
        state["last_error"] = str(error)
        stderr = str(error)
    except RuntimeError as error:
        return_code = 127
        state["last_error"] = str(error)
        stderr = str(error)
    finished_at = utc_now()
    state.update({
        "runtime": "stopped" if return_code in {0, 130} else "degraded",
        "pid": None, "finished_at": finished_at, "exit_code": return_code,
    })
    if return_code not in {0, 130} and not state.get("last_error"):
        state["last_error"] = f"llama-cli exited with code {return_code}"
    elif return_code in {0, 130}:
        state["last_error"] = None
    atomic_json(settings.state_path, state)
    append_event(settings.events_path, "runtime.stopped", model_id=model["id"], exit_code=return_code)
    _record_load_result(settings, model["id"], return_code)
    return {
        "return_code": return_code,
        "stdout": stdout,
        "stderr": stderr,
        "response": _extract_response(stdout, prompt) if capture else "",
        "started_at": started_at,
        "finished_at": finished_at,
    }


def run_model(settings: Settings, model: dict[str, Any], prompt: str | None, tokens: int, context: int | None, cpu: bool) -> int:
    result = _execute_model(settings, model, prompt, tokens, context, cpu, capture=False)
    return int(result["return_code"])


def run_model_capture(
    settings: Settings,
    model: dict[str, Any],
    prompt: str,
    tokens: int,
    context: int | None,
    cpu: bool,
    *,
    timeout_seconds: int = 300,
    process_started: Callable[[int], None] | None = None,
) -> dict[str, Any]:
    if not prompt.strip():
        raise RuntimeError("captured model execution requires a prompt")
    return _execute_model(
        settings,
        model,
        prompt,
        tokens,
        context,
        cpu,
        capture=True,
        timeout_seconds=timeout_seconds,
        process_started=process_started,
    )
