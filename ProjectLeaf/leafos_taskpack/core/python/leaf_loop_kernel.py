#!/usr/bin/env python3
"""Shared loop kernel for LeafOS agentic and continual runtimes.

This module extracts the primitives that were duplicated across
`leaf_agent_loop.py`, `leaf_loop_inlet.py`, and `continual_live.py`:

- atomic JSON/JSONL/NDJSON writes with Windows-safe replace
- per-directory file locking
- append-only event streams with auto sequence numbers
- universal telemetry append
- typed tick/cycle lifecycle registration
- subprocess lifecycle tracking with explicit cleanup
- optional memory cleanup hooks (gc, torch/llama-cpp caches)

Design goal: any new loop script imports one kernel and gets the same
on-disk contracts and cleanup discipline as the existing loops, but future
continual loops can plug in via the ContinualLoopAdapter instead of copying
boilerplate.
"""

from __future__ import annotations

import contextlib
import gc
import hashlib
import json
import os
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

PYTHON_DIR = Path(__file__).resolve().parent
if str(PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(PYTHON_DIR))

import leaf_telemetry as telemetry  # noqa: E402

try:
    from leaf_authority import AuthorityError, cap_check_naive, require_capability
except Exception:  # pragma: no cover - optional during migrations
    require_capability = None  # type: ignore
    cap_check_naive = None  # type: ignore
    AuthorityError = RuntimeError  # type: ignore


# Track locks already held by the current thread so that nested lock
# acquisition on the same run directory (e.g. queue_write_lock + append_event)
# does not deadlock on Windows/msvcrt.locking, which is not re-entrant.
_LOCK_LOCALS = threading.local()

# Per-path in-process threading lock.  msvcrt.locking can report EDEADLK when
# multiple threads in the same process contend for the same file lock region,
# so we serialize those threads in-process before touching the OS lock.
_IN_PROCESS_LOCKS: Dict[Path, threading.Lock] = {}
_IN_PROCESS_LOCKS_GUARD = threading.Lock()


def _thread_lock_for(path: Path) -> threading.Lock:
    with _IN_PROCESS_LOCKS_GUARD:
        lock = _IN_PROCESS_LOCKS.get(path)
        if lock is None:
            lock = threading.Lock()
            _IN_PROCESS_LOCKS[path] = lock
        return lock


KERNEL_OBJECT = "leafos.loop_kernel.v1"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _slug(value: str) -> str:
    out = "".join(ch.lower() if ch.isalnum() else "-" for ch in value.strip())
    out = "-".join(part for part in out.split("-") if part)
    return out or "leafos-run"


@contextlib.contextmanager
def _file_lock(lock_path: Path) -> Iterator[None]:
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    held = getattr(_LOCK_LOCALS, "locks", None) or {}
    if held.get(lock_path, 0) > 0:
        # Same thread already holds this lock; do not re-acquire.
        held[lock_path] += 1
        try:
            yield
        finally:
            held[lock_path] -= 1
        return

    with _thread_lock_for(lock_path):
        with lock_path.open("a+b") as handle:
            handle.seek(0, os.SEEK_END)
            if handle.tell() == 0:
                handle.write(b"0")
                handle.flush()
            handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
                held[lock_path] = 1
                _LOCK_LOCALS.locks = held
                try:
                    yield
                finally:
                    held[lock_path] -= 1
                    try:
                        handle.seek(0)
                        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                    except OSError:
                        pass
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
                held[lock_path] = 1
                _LOCK_LOCALS.locks = held
                try:
                    yield
                finally:
                    held[lock_path] -= 1
                    try:
                        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
                    except OSError:
                        pass


def atomic_write_json(path: Path, value: Any) -> None:
    """Write JSON atomically, retrying Windows PermissionError."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    for attempt in range(20):
        try:
            os.replace(temporary, path)
            return
        except PermissionError:
            if attempt == 19:
                temporary.unlink(missing_ok=True)
                raise
            time.sleep(0.005)


def read_json(path: Path, default: Any) -> Any:
    for attempt in range(20):
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except PermissionError:
            if attempt == 19:
                raise
            time.sleep(0.005)
        except (FileNotFoundError, json.JSONDecodeError):
            return default
    return default


def read_events(path: Path) -> list[dict[str, Any]]:
    """Read NDJSON events and validate sequence integrity."""
    events: list[dict[str, Any]] = []
    if not path.is_file():
        return events
    for index, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError(f"invalid event JSON at line {index}: {error.msg}") from error
        if not isinstance(item, dict):
            raise ValueError(f"event line {index} is not an object")
        events.append(item)
    return events


@dataclass
class LoopMemoryPolicy:
    """Configurable memory hygiene for a loop cycle."""

    gc_collect: bool = True
    gc_generations: int = 2  # 0, 1, or 2
    empty_torch_cuda_cache: bool = False
    empty_torch_mps_cache: bool = False
    clear_llama_cpp_kv: bool = False  # reserved for future llama.cpp context reset
    max_subprocess_shutdown_seconds: float = 15.0
    max_concurrent_spawns: int = 4


@contextlib.contextmanager
def loop_memory_context(policy: LoopMemoryPolicy | None = None) -> Iterator[LoopMemoryPolicy]:
    """Enter a loop step/cycle with explicit memory bounds.

    On exit the context runs gc.collect and optional backend cache flushes.
    Spawning inside the context is tracked by RunDirectory.spawn(); this
    helper handles the memory layer only.
    """
    policy = policy or LoopMemoryPolicy()
    try:
        yield policy
    finally:
        if policy.gc_collect:
            for generation in range(min(policy.gc_generations, 2), -1, -1):
                gc.collect(generation)
        if policy.empty_torch_cuda_cache:
            try:
                import torch  # type: ignore
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except Exception:
                pass
        if policy.empty_torch_mps_cache:
            try:
                import torch  # type: ignore
                if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                    torch.mps.empty_cache()
            except Exception:
                pass


@dataclass
class LoopTick:
    """A single typed tick record that any loop can emit."""

    tick_number: int
    recorded_at: str = field(default_factory=utc_now)
    phase: str = "idle"
    task_id: str | None = None
    next_action: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_event(self) -> dict[str, Any]:
        return {
            "leafos_object": "leafos.loop_tick.v1",
            "tick_number": self.tick_number,
            "recorded_at": self.recorded_at,
            "phase": self.phase,
            "task_id": self.task_id,
            "next_action": self.next_action,
            "metadata": self.metadata,
        }


class RunDirectory:
    """Authority object for one loop run directory.

    Owns atomic JSON writes, per-directory locks, event streams, telemetry,
    spawned subprocess cleanup, and tick recording.
    """

    def __init__(
        self,
        run_dir: Path | str,
        run_kind: str = "agent-loop",
        *,
        run_id: str | None = None,
        run_json: dict[str, Any] | None = None,
        memory_policy: LoopMemoryPolicy | None = None,
    ) -> None:
        self.run_dir = Path(run_dir).resolve()
        self.run_kind = run_kind
        self.run_id = run_id or self.run_dir.name
        self.memory_policy = memory_policy or LoopMemoryPolicy()
        self._metadata: dict[str, Any] = run_json or {}
        self._spawns: List[subprocess.Popen[Any]] = []
        self._tick: int = 0

        self.run_dir.mkdir(parents=True, exist_ok=True)
        self._paths = {
            "run": self.run_dir / "run.json",
            "state": self.run_dir / "state.json",
            "queue": self.run_dir / "queue.json",
            "events": self.run_dir / "events.jsonl",
            "journal": self.run_dir / "journal.jsonl",
            "checkpoint": self.run_dir / "checkpoint.json",
            "report": self.run_dir / "report.md",
            "universal": self.run_dir / telemetry.UNIVERSAL_LOG_NAME,
            "tick": self.run_dir / "ticks.jsonl",
        }

    @property
    def lock_path(self) -> Path:
        return self.run_dir / ".loop.lock"

    @contextlib.contextmanager
    def lock(self) -> Iterator[None]:
        with _file_lock(self.lock_path):
            yield

    def read(self, name: str, default: Any) -> Any:
        return read_json(self._paths[name], default)

    def read_events(self) -> list[dict[str, Any]]:
        """Read the run's event stream, validating sequence integrity."""
        events_path = self._paths["events"]
        events: list[dict[str, Any]] = []
        if not events_path.is_file():
            return events
        for index, line in enumerate(events_path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(f"invalid event JSON at line {index}: {error.msg}") from error
            if not isinstance(item, dict):
                raise ValueError(f"event line {index} is not an object")
            seq = item.get("seq")
            if seq != index:
                raise ValueError(f"event sequence mismatch at line {index}: got {seq}")
            events.append(item)
        return events

    def write(self, name: str, value: Any) -> None:
        atomic_write_json(self._paths[name], value)

    def _guard_mutation(self, capability: str | None, ticket: dict[str, Any] | None) -> dict[str, Any] | None:
        """Return a valid ticket or request one if authority is available.

        Read-only operations pass None.  Mutation operations must supply a
        ticket or the kernel will request one on their behalf.
        """
        if capability is None:
            return ticket
        if ticket is not None:
            if ticket.get("capability") != capability or not ticket.get("allowed"):
                raise AuthorityError(f"invalid ticket for capability: {capability}")
            return ticket
        if require_capability is None:
            return ticket
        response = require_capability(
            capability,
            actor=f"loop-kernel.{self.run_kind}",
            reason=f"run_dir mutation: {capability}",
            context={"run_id": self.run_id, "run_kind": self.run_kind},
            source="loop-kernel",
        )
        new_ticket = response.get("payload", response).get("ticket")
        if ticket is None:
            return new_ticket
        return ticket

    def append_event(
        self,
        kind: str,
        *,
        capability: str | None = "loop.event.append",
        ticket: dict[str, Any] | None = None,
        **data: Any,
    ) -> dict[str, Any]:
        self._guard_mutation(capability, ticket)
        with self.lock():
            events = self.read_events()
            seq = 1
            if events:
                seq = max(int(e.get("seq", 0)) for e in events) + 1
            ticket = ticket or new_ticket
            event = {"seq": seq, "time": utc_now(), "kind": kind, "ticket": ticket, **data}
            with self._paths["events"].open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(json.dumps(event, separators=(",", ":"), ensure_ascii=True) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            return event

    def append_telemetry(
        self,
        event_type: str,
        phase: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        event = telemetry.make_universal_event(
            self.run_id,
            self.run_kind,
            event_type=event_type,
            phase=phase,
            run_dir=self.run_dir,
            **kwargs,
        )
        return telemetry.append_universal_event(self._paths["universal"], event)

    def record_tick(
        self,
        phase: str,
        *,
        task_id: str | None = None,
        next_action: str | None = None,
        capability: str | None = "loop.tick.record",
        ticket: dict[str, Any] | None = None,
        **metadata: Any,
    ) -> LoopTick:
        self._guard_mutation(capability, ticket)
        self._tick += 1
        tick = LoopTick(self._tick, phase=phase, task_id=task_id, next_action=next_action, metadata=metadata)
        with self._paths["tick"].open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(tick.as_event(), separators=(",", ":"), ensure_ascii=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        return tick

    def spawn(
        self,
        *args: Any,
        capability: str | None = "loop.spawn",
        ticket: dict[str, Any] | None = None,
        track: bool = True,
        **kwargs: Any,
    ) -> subprocess.Popen[Any]:
        self._guard_mutation(capability, ticket)
        if track and len(self._spawns) >= self.memory_policy.max_concurrent_spawns:
            raise RuntimeError(
                f"loop spawn concurrency limit reached ({self.memory_policy.max_concurrent_spawns})"
            )
        proc = subprocess.Popen(*args, **kwargs)
        if track:
            self._spawns.append(proc)
        return proc

    def cleanup_spawns(
        self,
        *,
        capability: str | None = "loop.spawn.cleanup",
        ticket: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Wait or terminate tracked spawns; return summary."""
        self._guard_mutation(capability, ticket)
        timeout = self.memory_policy.max_subprocess_shutdown_seconds
        results: list[dict[str, Any]] = []
        for proc in self._spawns:
            try:
                if proc.poll() is None:
                    proc.terminate()
                    try:
                        proc.wait(timeout=timeout)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait(timeout=5.0)
            except Exception as error:
                results.append({"pid": proc.pid, "error": str(error)})
            else:
                results.append({"pid": proc.pid, "returncode": proc.returncode})
        self._spawns.clear()
        return {"terminated": results}

    @contextlib.contextmanager
    def cycle(self) -> Iterator[RunDirectory]:
        """Enter one loop cycle with memory and spawn cleanup bound on exit."""
        try:
            with loop_memory_context(self.memory_policy):
                yield self
        finally:
            self.cleanup_spawns()

    def checkpoint(
        self,
        reason: str,
        state: dict[str, Any] | None = None,
        *,
        capability: str | None = "loop.checkpoint",
        ticket: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self._guard_mutation(capability, ticket)
        events = read_events(self._paths["events"])
        queue = self.read("queue", {})
        payload = {
            "leafos_object": "leafos.loop_checkpoint.v1",
            "run_id": self.run_id,
            "recorded_at": utc_now(),
            "last_event_sequence": events[-1]["seq"] if events else 0,
            "queue_digest": self._queue_digest(queue),
            "reason": reason,
            "state": state or {},
        }
        atomic_write_json(self._paths["checkpoint"], payload)
        self.append_event("checkpoint.written", reason=reason, queue_digest=payload["queue_digest"])
        return payload

    @staticmethod
    def _queue_digest(queue: dict[str, Any]) -> str:
        return "sha256:" + hashlib.sha256(
            json.dumps(queue, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()


class ContinualLoopAdapter:
    """Bridge from the Monday durable transcript to the loop kernel.

    This is intentionally a thin adapter: the durable runtime owns state
    authority, and this class merely translates durable state into loop ticks,
    telemetry, and checkpoints.  Wednesday/Friday remain config-only.
    """

    def __init__(
        self,
        run_dir: Path | str,
        *,
        persona_key: str = "monday",
        durable_bridge: Any | None = None,
    ) -> None:
        if persona_key != "monday":
            raise ValueError(f"only monday is durable; {persona_key} is not yet supported")
        self.run_dir = Path(run_dir).resolve()
        self.persona_key = persona_key
        self.durable_bridge = durable_bridge
        self.kernel = RunDirectory(
            self.run_dir,
            run_kind=f"continual-{persona_key}",
            memory_policy=LoopMemoryPolicy(gc_collect=True, empty_torch_cuda_cache=False),
        )

    def bind_durable_bridge(self, bridge: Any) -> None:
        self.durable_bridge = bridge

    def durable_status_event(self) -> dict[str, Any]:
        status: dict[str, Any] = {"persona": self.persona_key}
        if self.durable_bridge is not None:
            try:
                response = self.durable_bridge.status()
                payload = response.get("payload", response)
                status.update(
                    {
                        "status": payload.get("status"),
                        "transcript_head": payload.get("transcript_head"),
                        "transcript_cursor": payload.get("transcript_cursor"),
                        "next_action": payload.get("next_action"),
                        "kv_cache_authoritative": payload.get("kv_cache_authoritative"),
                    }
                )
            except Exception as error:
                status["error"] = str(error)
        else:
            status["error"] = "no durable bridge bound"
        return status

    def tick(self) -> dict[str, Any]:
        with self.kernel.cycle():
            status = self.durable_status_event()
            next_action = (status.get("next_action") or {}).get("capability", "unknown")
            tick = self.kernel.record_tick(
                phase="durable_poll",
                next_action=next_action,
                durable_status=status,
            )
            telemetry_kwargs: dict[str, Any] = {"quality": {"validation_status": status.get("status", "unknown")}}
            self.kernel.append_telemetry("sample", "idle", **telemetry_kwargs)
            return {"tick": tick.as_event(), "durable_status": status}


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(prog="leaf-loop-kernel", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    self_test = sub.add_parser("self-test", help="run a kernel self test")
    self_test.add_argument("--run-dir", default=None)
    args = parser.parse_args(argv)

    if args.command == "self-test":
        run_dir = Path(args.run_dir).resolve() if args.run_dir else Path.cwd() / ".leafos-kernel-selftest"
        run_dir.mkdir(parents=True, exist_ok=True)
        kernel = RunDirectory(run_dir, run_kind="kernel-self-test")
        ev = kernel.append_event("kernel.self_test", ok=True)
        tick = kernel.record_tick(phase="self_test", note="kernel is operational")
        cp = kernel.checkpoint("self-test")
        print(json.dumps({"event": ev, "tick": tick.as_event(), "checkpoint": cp}, indent=2))
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
