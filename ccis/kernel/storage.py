from __future__ import annotations

import hashlib
import json
import os
import subprocess
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator


class CCISError(RuntimeError):
    """Fail-closed CCIS runtime error."""


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical(value)).hexdigest()


def file_digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(block)
    return "sha256:" + hasher.hexdigest()


def read_json(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return default


def atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(text, encoding="utf-8", newline="\n")
    os.replace(temporary, path)


def atomic_json(path: Path, value: Any) -> None:
    atomic_text(path, json.dumps(value, indent=2, ensure_ascii=False) + "\n")


@contextmanager
def run_lock(run_dir: Path, timeout: float = 10.0) -> Iterator[None]:
    lock_path = run_dir / ".ccis.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = lock_path.open("a+b")
    deadline = time.monotonic() + timeout
    acquired = False
    try:
        while not acquired:
            try:
                if os.name == "nt":
                    import msvcrt

                    handle.seek(0)
                    if handle.read(1) == b"":
                        handle.seek(0)
                        handle.write(b"0")
                        handle.flush()
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                acquired = True
            except (OSError, BlockingIOError):
                if time.monotonic() >= deadline:
                    raise CCISError("timed out waiting for CCIS run lock")
                time.sleep(0.05)
        yield
    finally:
        if acquired:
            try:
                if os.name == "nt":
                    import msvcrt

                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            except OSError:
                pass
        handle.close()


def events_path(run_dir: Path) -> Path:
    return run_dir / "events.jsonl"


def read_events(run_dir: Path) -> list[dict[str, Any]]:
    path = events_path(run_dir)
    if not path.is_file():
        return []
    events: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as error:
            raise CCISError(f"invalid events.jsonl at line {line_number}: {error}") from error
        if not isinstance(value, dict):
            raise CCISError(f"invalid event object at line {line_number}")
        events.append(value)
    return events


def verify_events(events: list[dict[str, Any]]) -> None:
    previous: str | None = None
    for sequence, event in enumerate(events, 1):
        if event.get("sequence") != sequence:
            raise CCISError(f"event sequence mismatch at line {sequence}")
        if event.get("previous_event_hash") != previous:
            raise CCISError(f"event chain mismatch at line {sequence}")
        payload = event.get("payload", {})
        if event.get("payload_hash") != digest(payload):
            raise CCISError(f"event payload hash mismatch at line {sequence}")
        unsigned = {key: value for key, value in event.items() if key != "event_hash"}
        if event.get("event_hash") != digest(unsigned):
            raise CCISError(f"event hash mismatch at line {sequence}")
        previous = event["event_hash"]


def make_event(
    events: list[dict[str, Any]], task_id: str, event_type: str,
    payload: dict[str, Any], evidence_refs: list[str] | None = None,
    transition_id: str | None = None,
) -> dict[str, Any]:
    previous = events[-1]["event_hash"] if events else None
    event = {
        "ccis_object": "ccis.event",
        "schema_version": 1,
        "event_id": f"evt_{task_id}_{len(events) + 1:06d}",
        "sequence": len(events) + 1,
        "recorded_at": now(),
        "task_id": task_id,
        "event_type": event_type,
        "transition_id": transition_id,
        "previous_event_hash": previous,
        "payload_hash": digest(payload),
        "payload": payload,
        "evidence_refs": evidence_refs or [],
    }
    event["event_hash"] = digest(event)
    return event


def append_event_unlocked(run_dir: Path, event: dict[str, Any]) -> None:
    path = events_path(run_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(event, sort_keys=True, ensure_ascii=False) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def project_state(events: list[dict[str, Any]]) -> dict[str, Any]:
    if not events:
        raise CCISError("CCIS run has no authoritative events")
    task_id = events[0].get("task_id")
    state = "CREATED"
    last_transition = None
    for event in events:
        if event.get("event_type") == "ccis.transition.committed":
            state = event["payload"]["to_state"]
            last_transition = event["transition_id"]
    return {
        "ccis_object": "ccis.run_state",
        "schema_version": 1,
        "task_id": task_id,
        "state": state,
        "event_sequence": events[-1]["sequence"],
        "last_event_hash": events[-1]["event_hash"],
        "last_transition_id": last_transition,
        "updated_at": events[-1]["recorded_at"],
    }


def write_projection(run_dir: Path, events: list[dict[str, Any]]) -> dict[str, Any]:
    state = project_state(events)
    atomic_json(run_dir / "state.json", state)
    atomic_json(run_dir / "checkpoint.json", {
        "ccis_object": "ccis.checkpoint",
        "schema_version": 1,
        "task_id": state["task_id"],
        "event_sequence": state["event_sequence"],
        "event_hash": state["last_event_hash"],
        "state": state["state"],
        "written_at": now(),
    })
    return state


def resume(run_dir: Path) -> dict[str, Any]:
    with run_lock(run_dir):
        events = read_events(run_dir)
        verify_events(events)
        return write_projection(run_dir, events)


def git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[bytes]:
    result = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, check=False)
    if check and result.returncode != 0:
        detail = (result.stderr or result.stdout).decode("utf-8", errors="replace").strip()
        raise CCISError(f"git {' '.join(args)} failed: {detail}")
    return result


def repository_snapshot(repo: Path) -> str:
    if not (repo / ".git").exists():
        raise CCISError(f"repository is not a Git worktree: {repo}")
    parts = [
        git(repo, "rev-parse", "HEAD").stdout,
        git(repo, "status", "--porcelain=v1", "-z").stdout,
        git(repo, "diff", "--binary", "--no-ext-diff").stdout,
        git(repo, "diff", "--cached", "--binary", "--no-ext-diff").stdout,
    ]
    hasher = hashlib.sha256()
    for part in parts:
        hasher.update(len(part).to_bytes(8, "big"))
        hasher.update(part)
    return "sha256:" + hasher.hexdigest()


def index_tree(repo: Path) -> str:
    return git(repo, "write-tree").stdout.decode("ascii", errors="strict").strip()


def tracked_worktree_snapshot(repo: Path) -> str:
    """Hash HEAD-tracked filesystem content without consulting the mutable index."""
    names = git(repo, "ls-tree", "-r", "--name-only", "HEAD").stdout.decode("utf-8", errors="surrogateescape").splitlines()
    hasher = hashlib.sha256()
    for name in sorted(names):
        encoded = name.encode("utf-8", errors="surrogateescape")
        hasher.update(len(encoded).to_bytes(8, "big"))
        hasher.update(encoded)
        path = repo / name
        if path.is_file():
            content = path.read_bytes()
            hasher.update(b"F")
            hasher.update(len(content).to_bytes(8, "big"))
            hasher.update(content)
        else:
            hasher.update(b"M")
    return "sha256:" + hasher.hexdigest()
