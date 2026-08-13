#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""LeafOS full stack raw benchmark.

The default runner is intentionally local and deterministic. It measures the
LeafOS runtime-selection/orchestration path plus a CPU token-pump workload for
each configured quant tier of the active action model. It does not download
weights and it does not claim to measure real model inference.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set


_HERE = Path(__file__).resolve()
_ROOT = _HERE.parents[2]
_PYTHON_DIR = _ROOT / "core" / "python"
_REPORT_DIR = _ROOT / "reports" / "fullstackbench"
_LATEST_REPORT = _REPORT_DIR / "latest.json"

if str(_PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(_PYTHON_DIR))

try:
    from leaf_runtime import LeafRuntimeSelector
except Exception:  # pragma: no cover - only used in damaged installs
    LeafRuntimeSelector = None  # type: ignore

from leaf_telemetry import UNIVERSAL_LOG_NAME, append_universal_event, make_universal_event  # noqa: E402


DEFAULT_TASK = (
    "Implement a tiny function that validates a path, reports one edge case, "
    "and returns a structured result."
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _atomic_write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.tmp.{os.getpid()}")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def _tokenize(text: str) -> List[str]:
    return re.findall(r"\w+|[^\w\s]", text, flags=re.UNICODE)


def _quant_bits(quant: str) -> float:
    match = re.match(r"Q(\d+)(?:_(\d+))?", quant.upper())
    if not match:
        return 4.0
    major = float(match.group(1))
    minor = float(match.group(2) or 0) / 10.0
    return major + minor


def _dedupe_quant_tiers(tiers: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen: Set[str] = set()
    out: List[Dict[str, Any]] = []
    for tier in tiers:
        quant = str(tier.get("quant", "")).strip()
        key = quant.upper()
        if not quant or key in seen:
            continue
        seen.add(key)
        out.append(dict(tier))
    return out


def _raw_token_pump(seed: int, token_count: int, inner_iterations: int) -> int:
    value = seed & 0xFFFFFFFF
    for token_index in range(max(0, token_count)):
        value ^= (token_index + 0x9E3779B9) & 0xFFFFFFFF
        for inner_index in range(inner_iterations):
            value = (value * 1664525 + 1013904223 + inner_index) & 0xFFFFFFFF
    return value


def _rate(count: int, seconds: float) -> float:
    if seconds <= 0:
        return 0.0
    return round(count / seconds, 3)


def _run_raw_quant(
    *,
    tier: Dict[str, Any],
    prompt_tokens: Sequence[str],
    generated_tokens: int,
    rounds: int,
    work: int,
) -> Dict[str, Any]:
    quant = str(tier.get("quant", "Q4_K_M"))
    bits = _quant_bits(quant)
    inner = max(1, int(bits * max(1, work)))
    prompt_count = len(prompt_tokens)
    prompt_seconds: List[float] = []
    generate_seconds: List[float] = []
    checksum = 0xC0DEC0DE

    for round_index in range(max(1, rounds)):
        prompt_seed = checksum ^ (round_index + 1)
        start = time.perf_counter()
        checksum ^= _raw_token_pump(prompt_seed, prompt_count, inner)
        prompt_seconds.append(time.perf_counter() - start)

        generate_seed = checksum ^ 0xA511CE
        start = time.perf_counter()
        checksum ^= _raw_token_pump(generate_seed, generated_tokens, inner)
        generate_seconds.append(time.perf_counter() - start)

    prompt_total = sum(prompt_seconds)
    generate_total = sum(generate_seconds)
    total_tokens = (prompt_count + generated_tokens) * max(1, rounds)
    total_seconds = prompt_total + generate_total

    return {
        "tier": tier.get("name", ""),
        "quant": quant,
        "mode": tier.get("mode", ""),
        "purpose": tier.get("purpose", ""),
        "raw_quant_bits": bits,
        "raw_inner_iterations": inner,
        "rounds": max(1, rounds),
        "prompt_tokens": prompt_count,
        "generated_tokens": generated_tokens,
        "prompt_seconds": round(prompt_total, 6),
        "generation_seconds": round(generate_total, 6),
        "total_seconds": round(total_seconds, 6),
        "prompt_tk_s": _rate(prompt_count * max(1, rounds), prompt_total),
        "generation_tk_s": _rate(generated_tokens * max(1, rounds), generate_total),
        "total_tk_s": _rate(total_tokens, total_seconds),
        "checksum": f"{checksum & 0xFFFFFFFF:08x}",
    }


def _run_command(args: Sequence[str], timeout: float) -> subprocess.CompletedProcess:
    return subprocess.run(
        list(args),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
    )


def _safe_int(value: str) -> Optional[int]:
    try:
        return int(float(value))
    except ValueError:
        return None


def _collect_nvidia_smi(timeout: float) -> Optional[Dict[str, Any]]:
    exe = shutil.which("nvidia-smi")
    if not exe:
        return None
    query = "name,memory.total,memory.free,utilization.gpu,driver_version"
    proc = _run_command(
        [exe, f"--query-gpu={query}", "--format=csv,noheader,nounits"],
        timeout=timeout,
    )
    if proc.returncode != 0:
        return {
            "source": "nvidia-smi",
            "available": False,
            "error": (proc.stderr or proc.stdout).strip(),
            "gpus": [],
        }
    gpus = []
    for line in proc.stdout.splitlines():
        parts = [part.strip() for part in line.split(",")]
        if len(parts) < 5:
            continue
        gpus.append(
            {
                "name": parts[0],
                "memory_total_mb": _safe_int(parts[1]),
                "memory_free_mb": _safe_int(parts[2]),
                "utilization_gpu_percent": _safe_int(parts[3]),
                "driver_version": parts[4],
            }
        )
    return {"source": "nvidia-smi", "available": bool(gpus), "gpus": gpus}


def _collect_windows_gpu(timeout: float) -> Optional[Dict[str, Any]]:
    if platform.system() != "Windows":
        return None
    ps = shutil.which("pwsh") or shutil.which("powershell")
    if not ps:
        return None
    command = (
        "Get-CimInstance Win32_VideoController | "
        "Select-Object Name,AdapterRAM,DriverVersion | "
        "ConvertTo-Json -Compress"
    )
    proc = _run_command([ps, "-NoProfile", "-Command", command], timeout=timeout)
    if proc.returncode != 0 or not proc.stdout.strip():
        return {
            "source": "win32_videocontroller",
            "available": False,
            "error": (proc.stderr or proc.stdout).strip(),
            "gpus": [],
        }
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {
            "source": "win32_videocontroller",
            "available": False,
            "error": "could not parse PowerShell GPU JSON",
            "gpus": [],
        }
    rows = payload if isinstance(payload, list) else [payload]
    gpus = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        ram = row.get("AdapterRAM")
        gpus.append(
            {
                "name": row.get("Name"),
                "memory_total_mb": int(ram / (1024 * 1024)) if isinstance(ram, int) and ram > 0 else None,
                "driver_version": row.get("DriverVersion"),
            }
        )
    return {"source": "win32_videocontroller", "available": bool(gpus), "gpus": gpus}


def _collect_lspci_gpu(timeout: float) -> Optional[Dict[str, Any]]:
    exe = shutil.which("lspci")
    if not exe:
        return None
    proc = _run_command([exe], timeout=timeout)
    if proc.returncode != 0:
        return None
    gpus = []
    for line in proc.stdout.splitlines():
        low = line.lower()
        if "vga compatible controller" in low or "3d controller" in low:
            gpus.append({"name": line.strip()})
    return {"source": "lspci", "available": bool(gpus), "gpus": gpus}


def collect_hardware(timeout: float = 2.0) -> Dict[str, Any]:
    started = time.perf_counter()
    gpu = (
        _collect_nvidia_smi(timeout)
        or _collect_windows_gpu(timeout)
        or _collect_lspci_gpu(timeout)
        or {"source": "none", "available": False, "gpus": []}
    )
    return {
        "collected_at": _utc_now(),
        "elapsed_seconds": round(time.perf_counter() - started, 6),
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "processor": platform.processor(),
            "python": platform.python_version(),
            "cpu_count": os.cpu_count(),
        },
        "gpu": gpu,
    }


def _selection(root: Path) -> Dict[str, Any]:
    if LeafRuntimeSelector is None:
        cfg = _read_json(root / "config" / "runtime.json")
        runtime = cfg.get("leafos_runtime", {})
        defaults = runtime.get("defaults", {})
        coder = next(
            (item for item in runtime.get("coder_models", []) if item.get("key") == defaults.get("coder_model")),
            (runtime.get("coder_models") or [{}])[0],
        )
        main = next(
            (item for item in runtime.get("main_models", []) if item.get("key") == defaults.get("main_model")),
            (runtime.get("main_models") or [{}])[0],
        )
        return {
            "schema_version": cfg.get("schema_version", 1),
            "selection": {
                "main_model": main,
                "scheduler_model": main,
                "coder_model": coder,
                "coding_choice": {
                    "language": defaults.get("coding_language", "python"),
                    "model_key": defaults.get("coding_model_choice", coder.get("key")),
                    "tier": defaults.get("coding_tier", "builder"),
                    "backend": "python",
                    "source": "runtime-config-fallback",
                },
                "persona": {"key": defaults.get("persona", "monday")},
                "mode": defaults.get("mode", "loop"),
            },
        }
    return LeafRuntimeSelector(root).select()


def build_report(args: argparse.Namespace) -> Dict[str, Any]:
    started = time.perf_counter()
    task = args.task or DEFAULT_TASK
    prompt_tokens = _tokenize(task)

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        hardware_future = None if args.no_gpu else pool.submit(collect_hardware, args.gpu_timeout)

        selected = _selection(_ROOT)
        select_elapsed = time.perf_counter() - started
        sel = selected.get("selection", {})
        action_model = sel.get("coder_model", {})
        tiers = _dedupe_quant_tiers(action_model.get("tiers", []))
        if args.quant:
            wanted = {item.upper() for item in args.quant}
            tiers = [tier for tier in tiers if str(tier.get("quant", "")).upper() in wanted]
        if not tiers:
            default_quant = action_model.get("default_quant", "Q4_K_M")
            tiers = [
                {
                    "name": "default",
                    "quant": default_quant,
                    "mode": "single",
                    "purpose": "default action model quant",
                }
            ]

        bench_started = time.perf_counter()
        results = [
            _run_raw_quant(
                tier=tier,
                prompt_tokens=prompt_tokens,
                generated_tokens=args.generated_tokens,
                rounds=args.rounds,
                work=args.work,
            )
            for tier in tiers
        ]
        bench_elapsed = time.perf_counter() - bench_started

        hardware = None
        if hardware_future is not None:
            try:
                hardware = hardware_future.result(timeout=args.gpu_timeout + 1.0)
            except Exception as exc:  # pragma: no cover - defensive timeout path
                hardware = {
                    "collected_at": _utc_now(),
                    "elapsed_seconds": None,
                    "platform": {"system": platform.system(), "machine": platform.machine()},
                    "gpu": {"source": "error", "available": False, "error": str(exc), "gpus": []},
                }

    return {
        "schema_version": 1,
        "leafos_object": "fullstackbench",
        "generated_at": _utc_now(),
        "root": str(_ROOT),
        "runner": {
            "name": "raw_token_pump",
            "real_model_inference": False,
            "description": "deterministic local raw benchmark for orchestration and token-pump overhead",
        },
        "stack": {
            "main_model": sel.get("main_model", {}),
            "scheduler_model": sel.get("scheduler_model", {}),
            "action_model": action_model,
            "coding_choice": sel.get("coding_choice", {}),
            "persona": sel.get("persona", {}),
            "mode": sel.get("mode", ""),
        },
        "task": {
            "text": task,
            "prompt_tokens": len(prompt_tokens),
            "generated_tokens": args.generated_tokens,
            "rounds": max(1, args.rounds),
        },
        "timing": {
            "runtime_selection_seconds": round(select_elapsed, 6),
            "benchmark_seconds": round(bench_elapsed, 6),
            "total_seconds": round(time.perf_counter() - started, 6),
        },
        "quantization": results,
        "hardware": hardware,
        "safety": {
            "downloads_model_weights": False,
            "network_required": False,
            "real_model_inference": False,
            "notes": [
                "raw_token_pump is not a llama.cpp or GGUF inference benchmark",
                "use these numbers to compare local orchestration overhead, not model quality or true decode speed",
            ],
        },
    }


def _print_text(report: Dict[str, Any]) -> None:
    stack = report["stack"]
    choice = stack.get("coding_choice", {})
    action = stack.get("action_model", {})
    print("LeafOS fullstackbench")
    print(f"  runner       : {report['runner']['name']} (raw, no model inference)")
    print(f"  action model : {action.get('key', 'unknown')} / {choice.get('tier', 'unknown')}")
    print(f"  main model   : {stack.get('main_model', {}).get('key', 'unknown')}")
    print(f"  scheduler    : {stack.get('scheduler_model', {}).get('key', 'unknown')}")
    print(f"  persona      : {stack.get('persona', {}).get('key', 'unknown')}")
    print(f"  prompt toks  : {report['task']['prompt_tokens']}")
    print(f"  gen toks     : {report['task']['generated_tokens']}")
    print("")
    print(f"{'tier':<11} {'quant':<8} {'prompt tk/s':>12} {'gen tk/s':>12} {'total tk/s':>12} {'seconds':>10}")
    print("-" * 72)
    for row in report["quantization"]:
        print(
            f"{str(row['tier']):<11} "
            f"{str(row['quant']):<8} "
            f"{row['prompt_tk_s']:>12.3f} "
            f"{row['generation_tk_s']:>12.3f} "
            f"{row['total_tk_s']:>12.3f} "
            f"{row['total_seconds']:>10.4f}"
        )
    hardware = report.get("hardware") or {}
    gpu = hardware.get("gpu") or {}
    print("")
    print(f"  gpu source   : {gpu.get('source', 'none')}")
    gpus = gpu.get("gpus") or []
    if gpus:
        for index, item in enumerate(gpus):
            mem = item.get("memory_total_mb")
            suffix = f", {mem} MB" if mem else ""
            print(f"  gpu {index}       : {item.get('name', 'unknown')}{suffix}")
    else:
        print("  gpu          : not detected")
    print("")
    print("  note         : raw benchmark only; no downloads and no true model inference")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fullstackbench",
        description="Run a raw LeafOS full-stack benchmark across active action-model quant tiers.",
    )
    parser.add_argument("--json", action="store_true", help="emit JSON")
    parser.add_argument("--write", action="store_true", help="write reports/fullstackbench/latest.json")
    parser.add_argument("--out", default="", help="optional JSON output path")
    parser.add_argument("--run-dir", default="", help="universal run artifact directory")
    parser.add_argument("--task", default=DEFAULT_TASK, help="benchmark prompt/task text")
    parser.add_argument("--generated-tokens", type=int, default=128, help="synthetic generated token count")
    parser.add_argument("--rounds", type=int, default=2, help="rounds per quant tier")
    parser.add_argument("--work", type=int, default=800, help="raw CPU work factor per quant bit")
    parser.add_argument("--quant", action="append", default=[], help="restrict to a quant, repeatable")
    parser.add_argument("--no-gpu", action="store_true", help="skip background GPU hardware probe")
    parser.add_argument("--gpu-timeout", type=float, default=2.0, help="GPU probe timeout seconds")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    if args.generated_tokens < 1:
        raise SystemExit("--generated-tokens must be positive")
    if args.rounds < 1:
        raise SystemExit("--rounds must be positive")
    if args.work < 1:
        raise SystemExit("--work must be positive")

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = Path(args.run_dir).expanduser().resolve() if args.run_dir else (_ROOT / "runs" / "fullstackbench" / stamp)
    run_dir.mkdir(parents=True, exist_ok=True)
    run_id = run_dir.name
    universal_path = run_dir / UNIVERSAL_LOG_NAME
    append_universal_event(
        universal_path,
        make_universal_event(
            run_id,
            "fullstackbench",
            "run_start",
            "startup",
            run_dir=run_dir,
            provider={"mode": "off", "backend": "cpu", "endpoint": None, "status": "off", "pid": None},
            instances={
                "initiated": 1, "alive": 1, "brain_initiated": 0, "brain_alive": 0,
                "coder_initiated": 1, "coder_alive": 1, "provider_initiated": 0,
                "provider_alive": 0, "crashed": 0, "restarted": 0,
            },
            quality={"validation_status": "pending", "checkpoint_valid": None, "accepted_changes": None, "rejected_changes": None, "score_delta": None},
            collect_hardware=False,
        ),
    )
    report = build_report(args)
    run_summary = run_dir / "summary.json"
    _atomic_write_json(run_summary, report)
    quantization = report.get("quantization", [])
    coder_rates = [row.get("generation_tk_s") for row in quantization if isinstance(row.get("generation_tk_s"), (int, float))]
    coder_rate = round(sum(coder_rates) / len(coder_rates), 3) if coder_rates else None
    action_model = report.get("stack", {}).get("action_model", {})
    main_model = report.get("stack", {}).get("main_model", {})
    common = {
        "run_dir": run_dir,
        "stack": {
            "local_stack_id": "local-stack:runtime-selection",
            "brain_stack_entry": main_model.get("key"),
            "coder_stack_entry": action_model.get("key"),
            "helper_stack_entry": None,
            "quantization": action_model.get("default_quant"),
        },
        "provider": {"mode": "off", "backend": "cpu", "endpoint": None, "status": "off", "pid": None},
        "throughput": {
            "brain_prompt_tk_s": None, "brain_generation_tk_s": None,
            "coder_prompt_tk_s": None, "coder_generation_tk_s": coder_rate,
            "helper_generation_tk_s": None, "aggregate_generation_tk_s": coder_rate,
            "time_to_first_token_seconds": None,
            "prompt_tokens": report.get("task", {}).get("prompt_tokens"),
            "generated_tokens": report.get("task", {}).get("generated_tokens"),
        },
        "artifacts": [{"kind": "fullstackbench_summary", "path": str(run_summary), "sha256": None}],
    }
    append_universal_event(
        universal_path,
        make_universal_event(
            run_id,
            "fullstackbench",
            "sample",
            "coder",
            instances={
                "initiated": 1, "alive": 1, "brain_initiated": 0, "brain_alive": 0,
                "coder_initiated": 1, "coder_alive": 1, "provider_initiated": 0,
                "provider_alive": 0, "crashed": 0, "restarted": 0,
            },
            quality={"validation_status": "passed", "checkpoint_valid": None, "accepted_changes": None, "rejected_changes": None, "score_delta": None},
            **common,
        ),
    )
    append_universal_event(
        universal_path,
        make_universal_event(
            run_id,
            "fullstackbench",
            "run_end",
            "shutdown",
            instances={
                "initiated": 1, "alive": 0, "brain_initiated": 0, "brain_alive": 0,
                "coder_initiated": 1, "coder_alive": 0, "provider_initiated": 0,
                "provider_alive": 0, "crashed": 0, "restarted": 0,
            },
            quality={"validation_status": "passed", "checkpoint_valid": True, "accepted_changes": None, "rejected_changes": None, "score_delta": None},
            collect_hardware=False,
            **common,
        ),
    )
    if args.write:
        _atomic_write_json(_LATEST_REPORT, report)
    if args.out:
        _atomic_write_json(Path(args.out).expanduser().resolve(), report)
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=True))
    else:
        _print_text(report)
        if args.write:
            print(f"  wrote        : {_LATEST_REPORT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
