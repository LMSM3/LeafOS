#!/usr/bin/env python3
"""Run the three staged deterministic game modules as an isolated overnight chain."""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT / "config" / "fast_three_stack_overnight.json"


def utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path}")
    return value


def write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def validate(config: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if config.get("schema") != "leafos.fast-three-stack-overnight.v1":
        errors.append("unsupported schema")
    modules = config.get("modules", [])
    if len(modules) != 3:
        errors.append("exactly three modules are required")
    for module in modules:
        for key in ("id", "relative_path", "configure_command", "build_command", "test_command", "simulation_command"):
            if not module.get(key):
                errors.append(f"{module.get('id', 'unknown')}: missing {key}")
    return errors


def command_text(command: list[str]) -> str:
    return " ".join(command)


def executable_command(command: list[str], cwd: Path) -> list[str]:
    resolved = list(command)
    candidate = cwd / Path(resolved[0].replace("/", "\\"))
    if candidate.is_file():
        resolved[0] = str(candidate)
    elif candidate.with_suffix(".exe").is_file():
        resolved[0] = str(candidate.with_suffix(".exe"))
    return resolved


def run_module(module: dict[str, Any], source_root: Path, output_root: Path, execute: bool) -> dict[str, Any]:
    module_id = str(module["id"])
    source = source_root / str(module["relative_path"])
    output = output_root / module_id
    output.mkdir(parents=True, exist_ok=True)
    isolated_source = output / "source"
    result: dict[str, Any] = {"module": module_id, "source": str(source), "isolated_source": str(isolated_source), "output": str(output), "status": "planned", "commands": []}
    if not source.is_dir():
        result.update(status="failed", error=f"module source not found: {source}")
        return result

    shutil.copytree(source, isolated_source, dirs_exist_ok=True, ignore=shutil.ignore_patterns("build", "*.o", "*.obj", "*.a"))
    if not execute:
        result["commands"] = [command_text(module[key]) for key in ("configure_command", "build_command", "test_command", "simulation_command")]
        return result

    for phase, key in (("configure", "configure_command"), ("build", "build_command"), ("test", "test_command"), ("simulation", "simulation_command")):
        command = [str(part) for part in module[key]]
        launch_command = executable_command(command, isolated_source)
        started = time.monotonic()
        completed = subprocess.run(launch_command, cwd=isolated_source, capture_output=True, text=True, check=False)
        elapsed = round(time.monotonic() - started, 3)
        stdout_path = output / f"{phase}.stdout.txt"
        stderr_path = output / f"{phase}.stderr.txt"
        stdout_path.write_text(completed.stdout, encoding="utf-8")
        stderr_path.write_text(completed.stderr, encoding="utf-8")
        command_result = {"phase": phase, "command": command, "launch_command": launch_command, "returncode": completed.returncode, "elapsed_seconds": elapsed, "stdout": str(stdout_path), "stderr": str(stderr_path)}
        result["commands"].append(command_result)
        if completed.returncode != 0:
            result.update(status="failed", failed_phase=phase)
            return result
    result["status"] = "completed"
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--run", action="store_true", help="execute commands; without this flag only validate/plan")
    args = parser.parse_args()
    config = load(args.config)
    errors = validate(config)
    if errors:
        for error in errors:
            print(f"invalid chain: {error}")
        return 1

    run_id = f"{config['run_id']}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    source_root = (ROOT / config["source_sandbox"]).resolve()
    output_root = (ROOT / config["output_root"] / run_id).resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    manifest = {"schema": config["schema"], "run_id": run_id, "started_at": utc(), "execute": args.run, "source_root": str(source_root), "output_root": str(output_root), "modules": [module["id"] for module in config["modules"]]}
    write(output_root / "manifest.json", manifest)
    events: list[dict[str, Any]] = [{"time": utc(), "event": "chain.started", "data": manifest}]
    results: list[dict[str, Any]] = []
    for module in config["modules"]:
        events.append({"time": utc(), "event": "module.started", "data": {"module": module["id"]}})
        result = run_module(module, source_root, output_root, args.run)
        results.append(result)
        events.append({"time": utc(), "event": "module.completed" if result["status"] == "completed" else ("module.planned" if result["status"] == "planned" else "module.failed"), "data": result})
        if args.run and result["status"] != "completed" and config.get("stop_on_failure", True):
            events.append({"time": utc(), "event": "chain.stopped", "data": {"reason": "module_failure", "module": module["id"]}})
            break
    status = "planned" if not args.run else ("completed" if len(results) == 3 and all(item["status"] == "completed" for item in results) else "failed")
    report = {"schema": "leafos.fast-three-stack-report.v1", "run_id": run_id, "status": status, "finished_at": utc(), "results": results, "events": str(output_root / "events.jsonl")}
    (output_root / "events.jsonl").write_text("\n".join(json.dumps(event, separators=(",", ":")) for event in events) + "\n", encoding="utf-8")
    write(output_root / "report.json", report)
    print(json.dumps(report, indent=2))
    return 0 if status in ("planned", "completed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
