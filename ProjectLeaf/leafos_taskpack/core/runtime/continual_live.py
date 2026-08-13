#!/usr/bin/env python3
"""Bounded real-inference continual runner with append-only evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import signal
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT / "config" / "continual-live.json"
DEFAULT_PROFILES = ROOT / "config" / "runtime-profiles.json"
STOP = threading.Event()
PYTHON_DIR = ROOT / "core" / "python"
if str(PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(PYTHON_DIR))

from leaf_telemetry import UNIVERSAL_LOG_NAME, append_universal_event, make_universal_event  # noqa: E402


def resolve_profile(config: dict[str, Any]) -> dict[str, Any]:
    """Resolve context_size/max_tokens from a named runtime profile.

    Precedence: explicit config context_size/max_tokens act only as the
    compat-4k fallback values; runtime_profile drives the effective budget
    unless the profile file is unavailable or the profile name is unknown,
    in which case the existing config values are used unchanged and the
    mismatch is reported in the returned manifest.
    """
    manifest: dict[str, Any] = {
        "requested_profile": config.get("runtime_profile"),
        "source": "config_literal",
        "context_size": config.get("context_size"),
        "max_output_tokens": config.get("max_tokens"),
        "reasoning_budget_requested": 0,
        "memory_pack_tokens": 0,
    }
    profile_name = config.get("runtime_profile")
    if not profile_name:
        return manifest
    profiles_path = ROOT / "config" / config.get("runtime_profiles_file", "runtime-profiles.json")
    try:
        profiles_doc = json.loads(profiles_path.read_text(encoding="utf-8"))
        profile = profiles_doc["profiles"][profile_name]
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        manifest["source"] = "fallback_profile_unavailable"
        manifest["error"] = str(exc)
        return manifest
    reasoning = profile.get("reasoning_budget_requested", 0)
    reasoning_tokens = 0 if reasoning in ("auto", None) else int(reasoning)
    manifest.update({
        "source": f"profile:{profile_name}",
        "context_size": int(profile["context_size"]),
        "max_output_tokens": int(profile["max_output_tokens"]),
        "reasoning_budget_requested": reasoning if reasoning == "auto" else reasoning_tokens,
        "memory_pack_tokens": int(profile.get("memory_pack_tokens", 0)),
    })
    return manifest


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.tmp.{os.getpid()}")
    temporary.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def append_jsonl(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(value, separators=(",", ":")) + "\n")
        handle.flush()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def hash_inventory(run_dir: Path, destination: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for path in sorted(run_dir.iterdir()):
        if not path.is_file() or path.name == destination.name:
            continue
        records.append({"path": path.name, "bytes": path.stat().st_size, "sha256": sha256(path)})
    atomic_json(destination, {"generated_at": utc_now(), "algorithm": "sha256", "artifacts": records})
    return records


def request_json(url: str, payload: dict[str, Any], timeout: int = 600) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def wait_for_server(url: str, timeout_seconds: int = 120) -> None:
    deadline = time.monotonic() + timeout_seconds
    health_url = url.rstrip("/") + "/health"
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(health_url, timeout=2) as response:
                if 200 <= response.status < 300:
                    return
        except (OSError, urllib.error.URLError):
            time.sleep(1)
    raise RuntimeError(f"llama.cpp server did not become healthy: {health_url}")


def start_server(config: dict[str, Any], run_dir: Path) -> subprocess.Popen[str]:
    model = (ROOT / config["model"]).resolve()
    server = (ROOT / config["llama_server"]).resolve()
    if not model.is_file():
        raise RuntimeError(f"model is missing: {model}")
    if not server.is_file():
        raise RuntimeError(f"llama-server is missing: {server}")
    command = [str(server), "-m", str(model), "--host", "127.0.0.1", "--port", "8080", "-c", str(config["context_size"])]
    if int(config.get("threads", 0)) > 0:
        command.extend(["-t", str(config["threads"])])
    output = (run_dir / "llama-server.log").open("a", encoding="utf-8", newline="\n")
    return subprocess.Popen(command, stdout=output, stderr=subprocess.STDOUT, text=True)


def extract_rate(payload: dict[str, Any], elapsed: float) -> tuple[float, int]:
    timings = payload.get("timings") if isinstance(payload.get("timings"), dict) else {}
    predicted = int(timings.get("predicted_n", 0) or 0)
    rate = timings.get("predicted_per_second") or timings.get("predicted_per_token")
    if isinstance(rate, (int, float)) and rate > 0:
        if "predicted_per_token" in timings and "predicted_per_second" not in timings:
            return round(1000.0 / float(rate), 3), predicted
        return round(float(rate), 3), predicted
    content = str(payload.get("content", ""))
    tokens = max(predicted, len(re.findall(r"\S+", content)))
    return round(tokens / max(elapsed, 0.001), 3), tokens


def tracker(state_path: Path, host: str, port: int) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path not in ("/", "/api/state"):
                self.send_error(404)
                return
            try:
                state = json.loads(state_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                state = {"status": "starting"}
            if self.path == "/api/state":
                body = json.dumps(state, indent=2).encode("utf-8")
                content_type = "application/json"
            else:
                body = ("<html><body><pre>" + json.dumps(state, indent=2) + "</pre></body></html>").encode("utf-8")
                content_type = "text/html; charset=utf-8"
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        def log_message(self, *_: Any) -> None:
            return
    server = ThreadingHTTPServer((host, port), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--run-dir", default="", help="optional run artifact directory")
    parser.add_argument("--run-id", default="", help="optional run identifier")
    args = parser.parse_args()
    config_path = Path(args.config).resolve()
    config = json.loads(config_path.read_text(encoding="utf-8"))
    if config.get("provider") == "mock" or not config.get("require_real_provider", False):
        raise SystemExit("continual live run requires a non-mock provider")
    if config.get("provider") != "llamacpp":
        raise SystemExit("continual live run currently supports only local llamacpp")

    profile_manifest = resolve_profile(config)
    config = {**config, "context_size": profile_manifest["context_size"], "max_tokens": profile_manifest["max_output_tokens"]}

    run_id = args.run_id or "continual-live-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = Path(args.run_dir).expanduser().resolve() if args.run_dir else ROOT / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    state_path = run_dir / "live-state.json"
    events_path = run_dir / "events.jsonl"
    rates_path = run_dir / "throughput.jsonl"
    hashes_path = run_dir / "hashes.json"
    manifest_path = run_dir / "runtime-profile-manifest.json"
    universal_path = run_dir / UNIVERSAL_LOG_NAME
    atomic_json(manifest_path, profile_manifest)
    end_at = time.monotonic() + float(config["duration_hours"]) * 3600
    state: dict[str, Any] = {
        "run_id": run_id, "status": "starting", "started_at": utc_now(), "provider": "llamacpp",
        "model": config["model"], "quantization": "Q4_K_M", "duration_hours": config["duration_hours"],
        "smoke_tests": False, "real_provider_required": True, "tracker": f"http://{config['status_host']}:{config['status_port']}/",
        "latest_tk_s": None, "requests_completed": 0, "runtime_profile": profile_manifest,
    }

    def append_universal(
        event_type: str,
        phase: str,
        *,
        provider_status: str,
        tk_s: float | None = None,
        tokens: int | None = None,
        validation_status: str = "unknown",
        collect_hardware: bool = False,
        notes: list[str] | None = None,
        alive: int = 1,
    ) -> None:
        append_universal_event(
            universal_path,
            make_universal_event(
                run_id,
                "continual-live",
                event_type,
                phase,
                run_dir=run_dir,
                stack={
                    "local_stack_id": "local-stack:continual",
                    "brain_stack_entry": str(config.get("model") or "") or None,
                    "coder_stack_entry": None,
                    "helper_stack_entry": None,
                    "quantization": str(state.get("quantization") or "") or None,
                },
                provider={
                    "mode": "llamacpp",
                    "backend": "llama.cpp",
                    "endpoint": str(config.get("server_url") or "") or None,
                    "status": provider_status,
                    "pid": state.get("server_pid") if isinstance(state.get("server_pid"), int) else None,
                },
                instances={
                    "initiated": 1,
                    "alive": alive,
                    "brain_initiated": 1,
                    "brain_alive": alive,
                    "coder_initiated": 0,
                    "coder_alive": 0,
                    "provider_initiated": 1,
                    "provider_alive": alive,
                    "crashed": 1 if provider_status == "failed" else 0,
                    "restarted": 0,
                },
                throughput={
                    "brain_prompt_tk_s": None,
                    "brain_generation_tk_s": tk_s,
                    "coder_prompt_tk_s": None,
                    "coder_generation_tk_s": None,
                    "helper_generation_tk_s": None,
                    "aggregate_generation_tk_s": tk_s,
                    "time_to_first_token_seconds": None,
                    "prompt_tokens": None,
                    "generated_tokens": tokens,
                },
                scheduler={
                    "queue_depth": 0,
                    "active_task_count": alive,
                    "blocked_task_count": 0,
                    "repair_task_count": 0,
                    "max_concurrency": 1,
                },
                quality={
                    "validation_status": validation_status,
                    "checkpoint_valid": None,
                    "accepted_changes": None,
                    "rejected_changes": None,
                    "score_delta": None,
                },
                availability={"throughput_counters": "collected" if tk_s is not None else "not_collected"},
                artifacts=[
                    {"kind": "live_state", "path": str(state_path), "sha256": None},
                    {"kind": "throughput", "path": str(rates_path), "sha256": None},
                ],
                notes=notes,
                collect_hardware=collect_hardware,
            ),
        )

    atomic_json(state_path, state)
    append_jsonl(events_path, {"time": utc_now(), "kind": "run.started", "provider": "llamacpp", "smoke_tests": False, "runtime_profile": profile_manifest})
    append_universal("run_start", "startup", provider_status="starting", validation_status="pending")
    server = tracker(state_path, config["status_host"], int(config["status_port"]))
    process: subprocess.Popen[str] | None = None
    try:
        process = start_server(config, run_dir)
        wait_for_server(config["server_url"])
        state["status"] = "running"
        state["server_pid"] = process.pid
        atomic_json(state_path, state)
        append_jsonl(events_path, {"time": utc_now(), "kind": "server.ready", "pid": process.pid})
        append_universal("provider_start", "provider_warmup", provider_status="ready", validation_status="pending", collect_hardware=True)
        while not STOP.is_set() and time.monotonic() < end_at:
            started = time.perf_counter()
            try:
                response = request_json(config["server_url"].rstrip("/") + "/completion", {"prompt": config["task"], "n_predict": int(config["max_tokens"]), "temperature": 0.2, "stop": ["```"]})
                elapsed = time.perf_counter() - started
                tk_s, tokens = extract_rate(response, elapsed)
                record = {"time": utc_now(), "kind": "throughput", "generation_tk_s": tk_s, "generated_tokens": tokens, "elapsed_seconds": round(elapsed, 3), "provider": "llamacpp"}
                append_jsonl(rates_path, record)
                append_jsonl(events_path, {"time": record["time"], "kind": "request.completed", "generation_tk_s": tk_s})
                state.update({"latest_tk_s": tk_s, "latest_tokens": tokens, "latest_completed_at": record["time"], "requests_completed": state["requests_completed"] + 1})
                append_universal("sample", "brain", provider_status="running", tk_s=tk_s, tokens=tokens, validation_status="passed", collect_hardware=True)
            except Exception as exc:
                append_jsonl(events_path, {"time": utc_now(), "kind": "request.failed", "error": str(exc)})
                state["last_error"] = str(exc)
                append_universal("run_error", "error", provider_status="degraded", validation_status="failed", notes=[str(exc)])
            state["hashes"] = hash_inventory(run_dir, hashes_path)
            atomic_json(state_path, state)
            wait_seconds = max(0.0, float(config["request_interval_seconds"]) - (time.perf_counter() - started))
            STOP.wait(wait_seconds)
        state["status"] = "completed" if not STOP.is_set() else "stopped"
    except Exception as exc:
        state.update({"status": "failed", "error": str(exc)})
        append_jsonl(events_path, {"time": utc_now(), "kind": "run.failed", "error": str(exc)})
        append_universal("run_error", "error", provider_status="failed", validation_status="failed", notes=[str(exc)], alive=0)
        return_code = 1
    else:
        append_jsonl(events_path, {"time": utc_now(), "kind": "run.finished", "status": state["status"]})
        return_code = 0
    finally:
        if process and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=20)
            except subprocess.TimeoutExpired:
                process.kill()
        final_validation = "passed" if state.get("status") in {"completed", "stopped"} else "failed"
        append_universal("provider_stop", "shutdown", provider_status="stopped", validation_status=final_validation, alive=0)
        append_universal("run_end", "shutdown" if final_validation == "passed" else "error", provider_status="stopped", validation_status=final_validation, alive=0)
        state["finished_at"] = utc_now()
        state["hashes"] = hash_inventory(run_dir, hashes_path)
        atomic_json(state_path, state)
        server.shutdown()
    return return_code


if __name__ == "__main__":
    signal.signal(signal.SIGINT, lambda *_: STOP.set())
    signal.signal(signal.SIGTERM, lambda *_: STOP.set())
    raise SystemExit(main())
