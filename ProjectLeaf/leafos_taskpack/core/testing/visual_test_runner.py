#!/usr/bin/env python3
"""Animated, isolated test observatory for the LeafOS regression suite."""

from __future__ import annotations

import argparse
import ast
import contextlib
import hashlib
import importlib
import json
import os
import queue
import re
import subprocess
import sys
import threading
import time
import traceback
import unittest
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, TextIO


ROOT = Path(__file__).resolve().parents[2]
TEST_ROOT = ROOT / "tests"
RUN_ROOT = ROOT / "runs" / "test-observatory"
SCHEMA = "leafos.visual_test_event.v1"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DOMAIN_FRAMES = {
    "stack": ("GPU .   ", "GPU >>  ", "GPU >>>>", "CPU GATE"),
    "loop": ("PLAN    ", "EXECUTE ", "VALIDATE", "CHECKPT "),
    "memory": ("APPEND  ", "HASH    ", "INDEX   ", "REPLAY  "),
    "interface": ("INPUT   ", "SNAPSHOT", "LAYOUT  ", "PAINT   "),
    "telemetry": ("CPU [..]", "CPU [##]", "GPU [..]", "GPU [##]"),
    "game": ("TILE .  ", "TILE .. ", "TILE ...", "HARVEST "),
    "runtime": ("DETECT  ", "ROUTE   ", "FALLBACK", "READY   "),
    "general": ("LOAD    ", "RUN     ", "ASSERT  ", "RECORD  "),
}

DOMAIN_COLORS = {
    "stack": "\033[1;35m",
    "loop": "\033[1;36m",
    "memory": "\033[1;34m",
    "interface": "\033[1;33m",
    "telemetry": "\033[1;32m",
    "game": "\033[1;31m",
    "runtime": "\033[1;37m",
    "general": "\033[1;37m",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def discover_test_ids(test_root: Path = TEST_ROOT, match: str = "") -> dict[str, list[str]]:
    """Discover unittest methods without importing test modules into the controller."""
    discovered: dict[str, list[str]] = {}
    needle = match.lower().strip()
    for path in sorted(test_root.glob("test_*.py")):
        module = f"tests.{path.stem}"
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        ids: list[str] = []
        for node in tree.body:
            if not isinstance(node, ast.ClassDef):
                continue
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name.startswith("test_"):
                    test_id = f"{module}.{node.name}.{item.name}"
                    if not needle or needle in test_id.lower():
                        ids.append(test_id)
        if ids:
            discovered[module] = ids
    return discovered


def classify_test(test_id: str) -> str:
    value = test_id.lower()
    if any(word in value for word in ("provider", "llama", "model_profile", "runtime_capabilit", "stack")):
        return "stack"
    if any(word in value for word in ("agent_loop", "work_order", "loop_inlet", "task_control", "dual_harness", "sandbox")):
        return "loop"
    if any(word in value for word in ("memory", "thinking", "reasoning", "checkpoint", "reflection")):
        return "memory"
    if any(word in value for word in ("tui", "dashboard", "home_state", "leafctl_dispatch")):
        return "interface"
    if "telemetry" in value or "hardware" in value:
        return "telemetry"
    if any(word in value for word in ("board", "catan", "monday_report")):
        return "game"
    if any(word in value for word in ("runtime", "wakeup")):
        return "runtime"
    return "general"


def flatten_suite(suite: unittest.TestSuite) -> Iterable[unittest.TestCase]:
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from flatten_suite(item)
        else:
            yield item


class EvidenceJournal:
    def __init__(self, run_dir: Path):
        self.run_dir = run_dir
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.events_path = self.run_dir / "events.jsonl"
        self._sequence = 0
        self._lock = threading.Lock()

    def append(self, kind: str, **fields: Any) -> dict[str, Any]:
        with self._lock:
            self._sequence += 1
            event = {
                "schema": SCHEMA,
                "sequence": self._sequence,
                "timestamp": utc_now(),
                "kind": kind,
                **fields,
            }
            with self.events_path.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n")
            return event

    def write_json(self, name: str, payload: dict[str, Any]) -> Path:
        path = self.run_dir / name
        temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(temporary, path)
        return path


class HardwareMonitor:
    def __init__(self, journal: EvidenceJournal, enabled: bool = True, interval: float = 1.0):
        self.journal = journal
        self.enabled = enabled
        self.interval = max(0.25, interval)
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._latest: dict[str, Any] = {}
        self._samples: list[dict[str, Any]] = []
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if not self.enabled:
            return
        self._thread = threading.Thread(target=self._run, name="leafos-test-hardware", daemon=True)
        self._thread.start()

    def _run(self) -> None:
        python_dir = ROOT / "core" / "python"
        if str(python_dir) not in sys.path:
            sys.path.insert(0, str(python_dir))
        try:
            telemetry = importlib.import_module("leaf_telemetry")
        except (ImportError, OSError) as error:
            self.journal.append("hardware.unavailable", reason=str(error))
            return
        while not self._stop.is_set():
            try:
                collected = telemetry.collect_fast_hardware(timeout=0.35, cpu_interval=0.03)
                hardware = collected.get("hardware", {})
                cpu = hardware.get("cpu", {}).get("utilization_percent")
                gpu = hardware.get("gpu", {}).get("utilization_percent")
                sample = {
                    "cpu_percent": cpu,
                    "gpu_percent": gpu,
                    "gpu_name": hardware.get("gpu", {}).get("name"),
                    "vram_used_gb": hardware.get("gpu", {}).get("vram_used_gb"),
                    "vram_total_gb": hardware.get("gpu", {}).get("vram_total_gb"),
                }
                with self._lock:
                    self._latest = sample
                    self._samples.append(sample)
                self.journal.append("hardware.sample", **sample)
            except (OSError, RuntimeError, ValueError) as error:
                self.journal.append("hardware.sample_failed", reason=str(error))
            self._stop.wait(self.interval)

    def latest(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._latest)

    def summary(self) -> dict[str, Any]:
        with self._lock:
            samples = list(self._samples)
        result: dict[str, Any] = {"sample_count": len(samples)}
        for key in ("cpu_percent", "gpu_percent"):
            values = [float(item[key]) for item in samples if isinstance(item.get(key), (int, float))]
            result[f"{key}_average"] = round(sum(values) / len(values), 2) if values else None
            result[f"{key}_maximum"] = round(max(values), 2) if values else None
        if samples:
            result["gpu_name"] = next((item.get("gpu_name") for item in samples if item.get("gpu_name")), None)
        return result

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2.0)


class VisualRenderer:
    RESET = "\033[0m"
    OK = "\033[1;32m"
    BAD = "\033[1;31m"
    WARN = "\033[1;33m"
    DIM = "\033[2m"

    def __init__(self, total: int, *, animation: bool = True, plain: bool = False, stream: TextIO = sys.stdout):
        self.total = total
        self.animation = animation
        self.stream = stream
        self.tty = bool(getattr(stream, "isatty", lambda: False)())
        self.color = self.tty and not plain and not os.environ.get("NO_COLOR")
        self.tick_index = 0
        self.active_id = ""
        self.active_domain = "general"
        self.completed = 0
        self._line_active = False

    def c(self, code: str, text: str) -> str:
        return f"{code}{text}{self.RESET}" if self.color else text

    @staticmethod
    def bar(current: int, total: int, width: int = 24) -> str:
        filled = min(width, int(width * current / max(1, total)))
        return "[" + "#" * filled + "." * (width - filled) + "]"

    @staticmethod
    def percent(value: Any) -> str:
        return f"{float(value):5.1f}%" if isinstance(value, (int, float)) else "  n/a "

    def banner(self, run_id: str, live_stack: bool) -> None:
        mode = "visual + real stack" if live_stack else "visual + deterministic fixtures"
        noun = "test" if self.total == 1 else "tests"
        self.stream.write("\n")
        self.stream.write(self.c("\033[1;36m", "LEAFOS TEST OBSERVATORY") + "\n")
        self.stream.write(f"run {run_id} | {self.total} {noun} | {mode}\n")
        self.stream.write("-" * 78 + "\n")
        self.stream.flush()

    def module(self, module: str, count: int) -> None:
        self.clear_active()
        noun = "test" if count == 1 else "tests"
        self.stream.write(f"\n{self.c(self.DIM, 'module')} {module} ({count} {noun})\n")
        self.stream.flush()

    def start_test(self, test_id: str) -> None:
        self.active_id = test_id
        self.active_domain = classify_test(test_id)
        if not self.tty or not self.animation:
            motif = DOMAIN_FRAMES[self.active_domain][self.tick_index % 4]
            self.stream.write(
                f"  [{self.completed + 1:03d}/{self.total:03d}] "
                f"{self.active_domain.upper():9s} {motif} {test_id.rsplit('.', 1)[-1]}\n"
            )
            self.stream.flush()

    def animate(self, hardware: dict[str, Any]) -> None:
        if not self.tty or not self.animation or not self.active_id:
            return
        self.tick_index += 1
        motif = DOMAIN_FRAMES[self.active_domain][self.tick_index % len(DOMAIN_FRAMES[self.active_domain])]
        line = (
            f"  [{self.completed + 1:03d}/{self.total:03d}] "
            f"{motif} {self.active_id.rsplit('.', 1)[-1][:38]:38s} "
            f"CPU {self.percent(hardware.get('cpu_percent'))} "
            f"GPU {self.percent(hardware.get('gpu_percent'))}"
        )
        self.stream.write("\r\033[2K" + self.c(DOMAIN_COLORS[self.active_domain], line))
        self.stream.flush()
        self._line_active = True

    def clear_active(self) -> None:
        if self._line_active:
            self.stream.write("\r\033[2K")
            self.stream.flush()
            self._line_active = False

    def finish_test(self, event: dict[str, Any]) -> None:
        self.clear_active()
        outcome = str(event.get("outcome", "error"))
        labels = {
            "passed": ("PASS", self.OK),
            "failed": ("FAIL", self.BAD),
            "error": ("ERR ", self.BAD),
            "skipped": ("SKIP", self.WARN),
            "expected_failure": ("XFAIL", self.WARN),
            "unexpected_success": ("XPASS", self.BAD),
        }
        label, color = labels.get(outcome, (outcome.upper()[:5], self.BAD))
        self.completed += 1
        test_id = str(event.get("test_id", self.active_id))
        duration = float(event.get("duration_seconds", 0.0))
        domain = classify_test(test_id)
        motif = DOMAIN_FRAMES[domain][(self.completed - 1) % len(DOMAIN_FRAMES[domain])]
        self.stream.write(
            f"  {self.c(color, label):9s} {duration:7.3f}s {self.bar(self.completed, self.total)} "
            f"{motif} {test_id.rsplit('.', 1)[-1]}\n"
        )
        detail = event.get("detail")
        if detail and outcome in {"failed", "error", "unexpected_success"}:
            for line in str(detail).splitlines()[-12:]:
                self.stream.write(f"      {line}\n")
        self.stream.flush()
        self.active_id = ""

    def live_demo_start(self, endpoint: str) -> None:
        self.clear_active()
        self.stream.write("\n" + self.c("\033[1;35m", "REAL STACK DEMONSTRATION") + "\n")
        self.stream.write(f"  endpoint {endpoint} | streamed llama.cpp response | CPU validates\n")
        self.stream.flush()

    def live_demo_tick(self, pieces: int, hardware: dict[str, Any]) -> None:
        if self.tty and self.animation:
            self.tick_index += 1
            frame = DOMAIN_FRAMES["stack"][self.tick_index % len(DOMAIN_FRAMES["stack"])]
            line = (
                f"  {frame} chunks {pieces:03d} | CPU {self.percent(hardware.get('cpu_percent'))} "
                f"GPU {self.percent(hardware.get('gpu_percent'))}"
            )
            self.stream.write("\r\033[2K" + self.c(DOMAIN_COLORS["stack"], line))
            self.stream.flush()
            self._line_active = True

    def live_demo_finish(self, result: dict[str, Any]) -> None:
        self.clear_active()
        status = str(result.get("status", "failed"))
        color = self.OK if status == "passed" else self.BAD
        self.stream.write(
            f"  {self.c(color, status.upper())} | {result.get('duration_seconds', 0):.2f}s | "
            f"~{result.get('estimated_tokens', 0)} tokens | ~{result.get('estimated_tk_s', 0):.2f} tk/s\n"
        )
        if result.get("visible_output"):
            for line in str(result["visible_output"]).splitlines():
                self.stream.write(f"    > {line}\n")
        hidden = int(result.get("private_reasoning_chars", 0))
        if hidden:
            self.stream.write(f"    private reasoning observed: {hidden} chars (content withheld)\n")
        if result.get("reason"):
            self.stream.write(f"    reason: {result['reason']}\n")
        self.stream.flush()

    def summary(self, payload: dict[str, Any]) -> None:
        self.clear_active()
        counts = payload["counts"]
        noun = "test" if counts["total"] == 1 else "tests"
        self.stream.write("\n" + "=" * 78 + "\n")
        self.stream.write(
            f"{payload['status'].upper()} | {counts['total']} {noun} | {counts['passed']} passed | "
            f"{counts['failed']} failed | {counts['errors']} errors | {counts['skipped']} skipped\n"
        )
        hardware = payload.get("hardware", {})
        self.stream.write(
            f"hardware samples {hardware.get('sample_count', 0)} | "
            f"CPU avg {self.percent(hardware.get('cpu_percent_average'))} | "
            f"GPU avg {self.percent(hardware.get('gpu_percent_average'))}\n"
        )
        self.stream.write(f"evidence {payload['run_dir']}\n")
        self.stream.flush()


class WorkerResult(unittest.TestResult):
    def __init__(self, stream: TextIO):
        super().__init__()
        self.stream = stream
        self.started: dict[str, float] = {}
        self.outcomes: dict[str, str] = {}

    def emit(self, kind: str, **fields: Any) -> None:
        self.stream.write(json.dumps({"kind": kind, **fields}, sort_keys=True) + "\n")
        self.stream.flush()

    def startTest(self, test: unittest.TestCase) -> None:
        super().startTest(test)
        test_id = test.id()
        self.started[test_id] = time.monotonic()
        self.emit("test.started", test_id=test_id, domain=classify_test(test_id))

    def _finish(self, test: unittest.TestCase, outcome: str, detail: str = "") -> None:
        test_id = test.id()
        self.outcomes[test_id] = outcome
        self.emit(
            "test.finished",
            test_id=test_id,
            domain=classify_test(test_id),
            outcome=outcome,
            duration_seconds=round(time.monotonic() - self.started.get(test_id, time.monotonic()), 6),
            detail=detail[-12000:],
        )

    def addSuccess(self, test: unittest.TestCase) -> None:
        super().addSuccess(test)
        self._finish(test, "passed")

    def addFailure(self, test: unittest.TestCase, err: tuple[type[BaseException], BaseException, Any]) -> None:
        super().addFailure(test, err)
        self._finish(test, "failed", "".join(traceback.format_exception(*err)))

    def addError(self, test: unittest.TestCase, err: tuple[type[BaseException], BaseException, Any]) -> None:
        super().addError(test, err)
        self._finish(test, "error", "".join(traceback.format_exception(*err)))

    def addSkip(self, test: unittest.TestCase, reason: str) -> None:
        super().addSkip(test, reason)
        self._finish(test, "skipped", reason)

    def addExpectedFailure(self, test: unittest.TestCase, err: tuple[type[BaseException], BaseException, Any]) -> None:
        super().addExpectedFailure(test, err)
        self._finish(test, "expected_failure", "".join(traceback.format_exception(*err)))

    def addUnexpectedSuccess(self, test: unittest.TestCase) -> None:
        super().addUnexpectedSuccess(test)
        self._finish(test, "unexpected_success", "unexpected success")


def run_worker(module: str, match: str = "") -> int:
    suite = unittest.defaultTestLoader.loadTestsFromName(module)
    tests = list(flatten_suite(suite))
    if match:
        needle = match.lower()
        tests = [test for test in tests if needle in test.id().lower()]
    result = WorkerResult(sys.stdout)
    result.emit("worker.started", module=module, test_count=len(tests))
    with contextlib.redirect_stdout(sys.stderr):
        unittest.TestSuite(tests).run(result)
    result.emit(
        "worker.finished",
        module=module,
        tests_run=result.testsRun,
        successful=result.wasSuccessful(),
    )
    return 0 if result.wasSuccessful() else 1


def strip_private_reasoning(raw: str) -> tuple[str, int]:
    """Return presentation-safe final output and the number of withheld characters."""
    hidden = 0

    def remove_block(match: re.Match[str]) -> str:
        nonlocal hidden
        hidden += len(match.group(1))
        return ""

    visible = re.sub(r"<(?:think|analysis)>(.*?)</(?:think|analysis)>", remove_block, raw, flags=re.I | re.S)
    unmatched = re.search(r"<(?:think|analysis)>(.*)$", visible, flags=re.I | re.S)
    if unmatched:
        hidden += len(unmatched.group(1))
        visible = visible[:unmatched.start()]
    kept: list[str] = []
    for line in visible.splitlines():
        if re.match(r"\s*\[(?:thought|analysis)\]", line, flags=re.I):
            hidden += len(line)
            continue
        kept.append(line)
    visible = "\n".join(kept).replace("```text", "").replace("```", "").strip()
    return visible[:2000], hidden


def configured_endpoint() -> str:
    path = ROOT / "config" / "vulkan-provider-stack.json"
    config = json.loads(path.read_text(encoding="utf-8"))
    server = config.get("server", {})
    api = config.get("api", {})
    host = server.get("host", "127.0.0.1")
    port = int(server.get("port", 8080))
    api_path = str(api.get("path", "/v1/chat/completions"))
    return f"http://{host}:{port}{api_path}"


def run_live_stack_demo(
    renderer: VisualRenderer,
    hardware: HardwareMonitor,
    journal: EvidenceJournal,
    timeout: float,
) -> dict[str, Any]:
    endpoint = configured_endpoint()
    health_url = endpoint.split("/v1/", 1)[0] + "/health"
    renderer.live_demo_start(endpoint)
    started = time.monotonic()
    journal.append("stack.demo.started", endpoint=endpoint)
    try:
        with urllib.request.urlopen(health_url, timeout=min(5.0, timeout)) as response:
            if response.status != 200:
                raise RuntimeError(f"provider health returned HTTP {response.status}")
    except (OSError, urllib.error.URLError, RuntimeError) as error:
        result = {"status": "failed", "duration_seconds": round(time.monotonic() - started, 3), "reason": str(error)}
        journal.append("stack.demo.finished", **result)
        renderer.live_demo_finish(result)
        return result

    prompt = (
        "LeafOS local stack demonstration. Do not provide analysis. Reply with exactly these three lines:\n"
        "STACK DEMO: READY\nPROVIDER: LLAMA.CPP VULKAN\nAUTHORITY: CPU VALIDATES"
    )
    pieces: queue.Queue[tuple[str, str]] = queue.Queue()

    def generate() -> None:
        try:
            chat = importlib.import_module("core.ui.chat")
            reasoning_listener = lambda size: pieces.put(("reasoning", str(size)))
            for piece in chat._stream_from_llama_server(
                endpoint, prompt, 256, object(), timeout=timeout,
                private_reasoning_listener=reasoning_listener,
            ):
                pieces.put(("piece", piece))
            pieces.put(("done", ""))
        except BaseException as error:  # Worker boundary records provider/protocol failures.
            pieces.put(("error", f"{type(error).__name__}: {error}"))

    thread = threading.Thread(target=generate, name="leafos-live-stack-demo", daemon=True)
    thread.start()
    chunks: list[str] = []
    server_private_chars = 0
    error = ""
    done = False
    while not done and time.monotonic() - started <= timeout + 5.0:
        try:
            kind, value = pieces.get(timeout=0.08)
            if kind == "piece":
                chunks.append(value)
            elif kind == "reasoning":
                server_private_chars += int(value)
            elif kind == "error":
                error = value
                done = True
            else:
                done = True
        except queue.Empty:
            pass
        renderer.live_demo_tick(len(chunks), hardware.latest())
    if not done and not error:
        error = "live stack demonstration timed out"

    raw = "".join(chunks).strip()
    visible, tagged_hidden_chars = strip_private_reasoning(raw)
    hidden_chars = server_private_chars + tagged_hidden_chars
    duration = max(0.001, time.monotonic() - started)
    estimated_tokens = max(0, round((len(raw) + hidden_chars) / 4))
    accepted = "STACK DEMO" in visible.upper() and "READY" in visible.upper() and "CPU" in visible.upper()
    result = {
        "status": "passed" if accepted and not error else "failed",
        "endpoint": endpoint,
        "duration_seconds": round(duration, 3),
        "response_chunks": len(chunks),
        "visible_response_sha256": hashlib.sha256(raw.encode("utf-8")).hexdigest(),
        "visible_output": visible,
        "private_reasoning_chars": hidden_chars,
        "estimated_tokens": estimated_tokens,
        "estimated_tk_s": round(estimated_tokens / duration, 2),
        "reason": error or ("" if accepted else "response did not satisfy the bounded CPU validation contract"),
    }
    journal.write_json("live-stack.json", result)
    journal.append("stack.demo.finished", **{key: value for key, value in result.items() if key != "visible_output"})
    renderer.live_demo_finish(result)
    return result


def pipe_reader(stream: TextIO, channel: str, output: queue.Queue[tuple[str, str]]) -> None:
    try:
        for line in iter(stream.readline, ""):
            output.put((channel, line.rstrip("\r\n")))
    finally:
        output.put((f"{channel}.closed", ""))


def create_run_dir(override: str = "") -> tuple[str, Path]:
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S") + f"-{os.getpid()}"
    run_dir = Path(override).resolve() if override else RUN_ROOT / run_id
    return run_id, run_dir


def summarize_results(
    run_id: str,
    run_dir: Path,
    outcomes: list[dict[str, Any]],
    started: float,
    hardware: dict[str, Any],
    live_demo: dict[str, Any] | None,
) -> dict[str, Any]:
    counts = {
        "total": len(outcomes),
        "passed": sum(item.get("outcome") == "passed" for item in outcomes),
        "failed": sum(item.get("outcome") in {"failed", "unexpected_success"} for item in outcomes),
        "errors": sum(item.get("outcome") == "error" for item in outcomes),
        "skipped": sum(item.get("outcome") in {"skipped", "expected_failure"} for item in outcomes),
    }
    tests_ok = counts["failed"] == 0 and counts["errors"] == 0
    live_ok = live_demo is None or live_demo.get("status") == "passed"
    return {
        "leafos_object": "leafos.visual_test_summary",
        "version": 1,
        "run_id": run_id,
        "run_dir": str(run_dir),
        "generated_at": utc_now(),
        "status": "passed" if tests_ok and live_ok else "failed",
        "duration_seconds": round(time.monotonic() - started, 3),
        "counts": counts,
        "domains": {
            domain: sum(classify_test(str(item.get("test_id", ""))) == domain for item in outcomes)
            for domain in DOMAIN_FRAMES
        },
        "hardware": hardware,
        "live_stack": live_demo or {"status": "not_requested"},
    }


def run_controller(args: argparse.Namespace) -> int:
    discovered = discover_test_ids(match=args.match)
    total = sum(len(ids) for ids in discovered.values())
    if args.list:
        payload = {"test_count": total, "modules": discovered}
        print(json.dumps(payload, indent=None if args.json else 2, sort_keys=True))
        return 0
    if not total:
        print("no tests matched", file=sys.stderr)
        return 2

    run_id, run_dir = create_run_dir(args.run_dir)
    journal = EvidenceJournal(run_dir)
    renderer = VisualRenderer(total, animation=not args.no_animation, plain=args.plain or args.json)
    monitor = HardwareMonitor(journal, enabled=not args.no_hardware)
    started = time.monotonic()
    outcomes: list[dict[str, Any]] = []
    module_failures: list[str] = []
    journal.append("suite.started", run_id=run_id, test_count=total, live_stack=args.live_stack)
    if not args.json:
        renderer.banner(run_id, args.live_stack)
    monitor.start()

    try:
        for module, expected_ids in discovered.items():
            if not args.json:
                renderer.module(module, len(expected_ids))
            journal.append("module.started", module=module, expected_tests=len(expected_ids))
            command = [sys.executable, "-B", str(Path(__file__).resolve()), "--worker", module]
            if args.match:
                command.extend(["--match", args.match])
            process = subprocess.Popen(
                command,
                cwd=ROOT,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            assert process.stdout is not None and process.stderr is not None
            messages: queue.Queue[tuple[str, str]] = queue.Queue()
            readers = [
                threading.Thread(target=pipe_reader, args=(process.stdout, "stdout", messages), daemon=True),
                threading.Thread(target=pipe_reader, args=(process.stderr, "stderr", messages), daemon=True),
            ]
            for reader in readers:
                reader.start()
            module_started = time.monotonic()
            closed: set[str] = set()
            timed_out = False
            while process.poll() is None or len(closed) < 2 or not messages.empty():
                try:
                    channel, line = messages.get(timeout=max(0.02, args.frame_delay))
                    if channel.endswith(".closed"):
                        closed.add(channel)
                    elif channel == "stderr":
                        if line:
                            journal.append("worker.output", module=module, stream="stderr", text=line[:4000])
                    elif line:
                        try:
                            event = json.loads(line)
                        except json.JSONDecodeError:
                            journal.append("worker.output", module=module, stream="stdout", text=line[:4000])
                        else:
                            kind = str(event.get("kind", "worker.event"))
                            fields = {key: value for key, value in event.items() if key != "kind"}
                            fields.setdefault("module", module)
                            journal.append(kind, **fields)
                            if kind == "test.started" and not args.json:
                                renderer.start_test(str(event["test_id"]))
                            elif kind == "test.finished":
                                outcomes.append(event)
                                if not args.json:
                                    renderer.finish_test(event)
                except queue.Empty:
                    pass
                if not args.json:
                    renderer.animate(monitor.latest())
                if process.poll() is None and time.monotonic() - module_started > args.module_timeout:
                    process.kill()
                    timed_out = True
                    journal.append("module.timeout", module=module, timeout_seconds=args.module_timeout)
            for reader in readers:
                reader.join(timeout=1.0)
            returncode = process.wait()
            if timed_out or returncode != 0:
                module_failures.append(module)
            journal.append(
                "module.finished",
                module=module,
                returncode=returncode,
                timed_out=timed_out,
                duration_seconds=round(time.monotonic() - module_started, 3),
            )
    except BaseException:
        monitor.stop()
        raise

    observed_ids = {str(item.get("test_id")) for item in outcomes}
    for test_id in [item for ids in discovered.values() for item in ids if item not in observed_ids]:
        event = {
            "kind": "test.finished",
            "test_id": test_id,
            "domain": classify_test(test_id),
            "outcome": "error",
            "duration_seconds": 0.0,
            "detail": "test worker exited before reporting an outcome",
        }
        outcomes.append(event)
        journal.append("test.finished", **{key: value for key, value in event.items() if key != "kind"})
        if not args.json:
            renderer.finish_test(event)

    live_demo = run_live_stack_demo(renderer, monitor, journal, args.live_timeout) if args.live_stack else None
    monitor.stop()
    summary = summarize_results(run_id, run_dir, outcomes, started, monitor.summary(), live_demo)
    summary["module_failures"] = module_failures
    journal.append("suite.finished", status=summary["status"], counts=summary["counts"])
    summary_path = journal.write_json("summary.json", summary)
    RUN_ROOT.mkdir(parents=True, exist_ok=True)
    latest = {
        "leafos_object": "leafos.visual_test_latest",
        "version": 1,
        "run_id": run_id,
        "run_dir": str(run_dir),
        "summary": str(summary_path),
        "status": summary["status"],
    }
    latest_path = RUN_ROOT / "latest.json"
    temporary = latest_path.with_name(f".{latest_path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(latest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, latest_path)
    if args.json:
        print(json.dumps(summary, sort_keys=True))
    else:
        renderer.summary(summary)
    return 0 if summary["status"] == "passed" else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the LeafOS suite as an animated, logged observatory.")
    parser.add_argument("--worker", metavar="MODULE", help=argparse.SUPPRESS)
    parser.add_argument("--match", default="", help="run tests whose full ID contains this text")
    parser.add_argument("--list", action="store_true", help="list discovered tests without running them")
    parser.add_argument("--live-stack", action="store_true", help="add one bounded real llama.cpp Vulkan demonstration")
    parser.add_argument("--live-timeout", type=float, default=45.0)
    parser.add_argument("--module-timeout", type=float, default=180.0)
    parser.add_argument("--frame-delay", type=float, default=0.08)
    parser.add_argument("--no-animation", action="store_true")
    parser.add_argument("--no-hardware", action="store_true")
    parser.add_argument("--plain", action="store_true", help="disable ANSI color while preserving visual traces")
    parser.add_argument("--json", action="store_true", help="suppress presentation and print only the final summary JSON")
    parser.add_argument("--run-dir", default="", help="write evidence to this directory")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.live_timeout <= 0 or args.module_timeout <= 0 or args.frame_delay <= 0:
        raise SystemExit("timeouts and frame delay must be positive")
    if args.worker:
        return run_worker(args.worker, args.match)
    return run_controller(args)


if __name__ == "__main__":
    raise SystemExit(main())
