#!/usr/bin/env python3
"""Real llama.cpp conversation and token-throughput measurements."""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Iterable, Optional


_HERE = Path(__file__).resolve()
_ROOT = _HERE.parents[2]
_PYTHON_DIR = _ROOT / "core" / "python"
if str(_PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(_PYTHON_DIR))

from inference_matrix import run_matrix  # noqa: E402
from leaf_economics import normalize_policy, summarize_benchmark  # noqa: E402
_DEFAULT_MODEL = (
    _ROOT.parent / "leaf_model_installer" / "models" / "Gemma4-Coder"
    / "gemma4-coding-Q4_K_M.gguf"
)


def _default_llama_dir() -> Path:
    if platform.system().lower().startswith("win"):
        return _ROOT.parent.parent / "tmp" / "llama-cpp-win-cpu-b9828"
    return _ROOT.parent.parent / "tmp" / "llama-cpp-ubuntu-x64-b9828" / "llama-b9828"


def _resolve_executable(name: str, explicit: str) -> Path:
    if explicit:
        path = Path(explicit).expanduser().resolve()
    else:
        suffix = ".exe" if platform.system().lower().startswith("win") else ""
        path = _default_llama_dir() / f"{name}{suffix}"
    if not path.is_file():
        raise SystemExit(f"llama.cpp executable not found: {path}")
    return path


def _resolve_model(explicit: str) -> Path:
    path = Path(explicit).expanduser().resolve() if explicit else _DEFAULT_MODEL
    if not path.is_file():
        raise SystemExit(f"GGUF model not found: {path}")
    return path


def _json_numbers(value: Any, keys: Iterable[str]) -> list[float]:
    wanted = {key.lower() for key in keys}
    found: list[float] = []
    if isinstance(value, dict):
        for key, item in value.items():
            if key.lower() in wanted and isinstance(item, (int, float)):
                found.append(float(item))
            found.extend(_json_numbers(item, wanted))
    elif isinstance(value, list):
        for item in value:
            found.extend(_json_numbers(item, wanted))
    return found


def _extract_generation_rate(stdout: str, stderr: str) -> Optional[float]:
    for text in (stdout, stderr):
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            payload = None
        if payload is not None:
            values = _json_numbers(
                payload,
                ("avg_ts", "eval_ts", "tg_avg", "generation_tk_s", "tokens_per_second"),
            )
            if values:
                return round(values[-1], 3)
        matches = re.findall(
            r"(?:eval|generation|tg)[^\n]*?(\d+(?:\.\d+)?)\s*(?:t/s|tk/s|tokens/s)",
            text,
            flags=re.IGNORECASE,
        )
        if matches:
            return round(float(matches[-1]), 3)
    return None


def _run_raw(args: argparse.Namespace) -> dict[str, Any]:
    bench = _resolve_executable("llama-bench", args.bench)
    model = _resolve_model(args.model)
    command = [
        str(bench), "-m", str(model), "-p", str(args.prompt_tokens),
        "-n", str(args.generated_tokens), "-r", str(args.repetitions),
        "-o", "json", "--no-warmup",
    ]
    started = time.perf_counter()
    proc = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
    elapsed = time.perf_counter() - started
    if proc.returncode != 0:
        raise SystemExit(
            f"llama-bench failed with exit code {proc.returncode}:\n"
            f"{proc.stderr.strip() or proc.stdout.strip()}"
        )
    rate = _extract_generation_rate(proc.stdout, proc.stderr)
    if rate is None:
        raise SystemExit("llama-bench completed but no generation token rate was found in its output")
    report = {
        "benchmark": "llama.cpp raw generation throughput",
        "runner": "llama-bench",
        "model": str(model),
        "command": command,
        "elapsed_seconds": round(elapsed, 3),
        "prompt_tokens": args.prompt_tokens,
        "generated_tokens": args.generated_tokens,
        "repetitions": args.repetitions,
        "generation_tk_s": rate,
        "target_tk_s": args.target,
        "target_met": rate >= args.target,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }
    return report


def _run_conversation(args: argparse.Namespace) -> dict[str, Any]:
    cli = _resolve_executable("llama-cli", args.cli)
    model = _resolve_model(args.model)
    command = [
        str(cli), "-m", str(model), "-c", str(args.context), "-n", str(args.tokens),
        "-cnv", "--simple-io", "--no-display-prompt", "--no-show-timings",
        "--no-warmup", "--reasoning-budget", "0",
    ]
    prompts = (
        "Summarize one practical software engineering idea in two sentences.",
        "Give one concrete example and one edge case.",
        "State the key tradeoff in one sentence.",
    )
    started = time.perf_counter()
    sent = 0
    with tempfile.TemporaryFile(mode="w+t", encoding="utf-8") as output, tempfile.TemporaryFile(
        mode="w+t", encoding="utf-8"
    ) as errors:
        process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=output, stderr=errors, text=True, encoding="utf-8")
        try:
            while time.perf_counter() - started < args.duration:
                if process.poll() is not None:
                    raise SystemExit(f"llama-cli exited early with code {process.returncode}")
                assert process.stdin is not None
                process.stdin.write(prompts[sent % len(prompts)] + "\n")
                process.stdin.flush()
                sent += 1
                time.sleep(args.interval)
        finally:
            if process.stdin is not None:
                process.stdin.close()
            try:
                process.wait(timeout=args.shutdown_timeout)
            except subprocess.TimeoutExpired:
                process.terminate()
                process.wait(timeout=10)
        elapsed = time.perf_counter() - started
        output.seek(0)
        errors.seek(0)
        stdout = output.read()
        stderr = errors.read()
    return {
        "benchmark": "llama.cpp real conversation",
        "runner": "llama-cli",
        "model": str(model),
        "command": command,
        "requested_duration_seconds": args.duration,
        "elapsed_seconds": round(elapsed, 3),
        "turns_sent": sent,
        "output_characters": len(stdout),
        "stderr": stderr,
        "duration_met": elapsed >= args.duration,
    }


def _run_summary(args: argparse.Namespace) -> dict[str, Any]:
    path = Path(args.report).expanduser().resolve()
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SystemExit(f"benchmark report could not be read: {error}")
    policy = report.get("economics") if isinstance(report.get("economics"), dict) else {}
    if args.output_usd_per_million is not None:
        policy = {**policy, "comparison_output_usd_per_million": args.output_usd_per_million}
    summary = summarize_benchmark(report, normalize_policy(policy))
    summary["report"] = str(path)
    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run real llama.cpp measurements.")
    subparsers = parser.add_subparsers(dest="mode", required=True)

    raw = subparsers.add_parser("raw", help="measure llama-bench generation tk/s")
    raw.add_argument("--model", default=os.environ.get("LEAF_REAL_MODEL", ""))
    raw.add_argument("--bench", default=os.environ.get("LEAF_LLAMA_BENCH", ""))
    raw.add_argument("--prompt-tokens", type=int, default=128)
    raw.add_argument("--generated-tokens", type=int, default=256)
    raw.add_argument("--repetitions", type=int, default=3)
    raw.add_argument("--target", type=float, default=66.0)

    conversation = subparsers.add_parser("conversation", help="run a real persistent conversation")
    conversation.add_argument("--model", default=os.environ.get("LEAF_REAL_MODEL", ""))
    conversation.add_argument("--cli", default=os.environ.get("LEAF_LLAMA_CLI", ""))
    conversation.add_argument("--duration", type=float, default=60.0)
    conversation.add_argument("--interval", type=float, default=5.0)
    conversation.add_argument("--shutdown-timeout", type=float, default=10.0)
    conversation.add_argument("--context", type=int, default=4096)
    conversation.add_argument("--tokens", type=int, default=128)

    matrix = subparsers.add_parser(
        "matrix", help="run or resume a condition-aware llama-bench matrix"
    )
    matrix.add_argument("--manifest", required=True, help="benchmark matrix JSON")
    matrix.add_argument("--output-dir", default="", help="artifact directory")
    matrix.add_argument("--bench", default=os.environ.get("LEAF_LLAMA_BENCH", ""))
    matrix.add_argument("--resume", action="store_true", help="skip completed cells")
    matrix.add_argument("--dry-run", action="store_true", help="validate and capture preflight only")
    matrix.add_argument(
        "--allow-busy", action="store_true", help="record but override idle-policy violations"
    )

    summary = subparsers.add_parser("summary", help="summarize a saved matrix report")
    summary.add_argument("--report", required=True, help="benchmark report.json")
    summary.add_argument(
        "--output-usd-per-million", type=float, default=None,
        help="override the report's gross output-token comparison rate",
    )
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    if args.mode == "raw":
        if min(args.prompt_tokens, args.generated_tokens, args.repetitions) < 1:
            raise SystemExit("raw token and repetition arguments must be positive")
        report = _run_raw(args)
    elif args.mode == "conversation":
        if args.duration < 1 or args.interval <= 0:
            raise SystemExit("conversation duration must be positive and interval must be greater than zero")
        report = _run_conversation(args)
    elif args.mode == "matrix":
        exit_code, report = run_matrix(args)
        summary = {
            "status": report.get("status"),
            "benchmark_id": report.get("benchmark_id"),
            "report": str(
                (Path(args.output_dir).expanduser().resolve() if args.output_dir else
                 Path.cwd() / "reports" / "inference-benchmark" / str(report.get("benchmark_id", "unknown")))
                / "report.json"
            ),
            "preflight_violations": (report.get("preflight") or {}).get("violations", []),
            "completed_cells": sum(cell.get("status") == "completed" for cell in report.get("cells", [])),
            "error": report.get("error"),
            "errors": report.get("errors"),
        }
        print(json.dumps(summary, indent=2, ensure_ascii=True))
        return exit_code
    else:
        report = _run_summary(args)
    print(json.dumps(report, indent=2, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
