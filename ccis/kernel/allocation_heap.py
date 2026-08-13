from __future__ import annotations

import heapq
from pathlib import Path
from typing import Any

from . import allocation_events, allocation_reducer, storage, task_registry


def snapshot_path(allocation_root: Path) -> Path:
    return allocation_root / "allocation-snapshot.json"


def _ready_key(record: dict[str, Any]) -> list[Any]:
    task = record["task"]
    deadline = task["deadline_tick"] if task["deadline_tick"] is not None else 9_223_372_036_854_775_807
    return [-record["effective_priority"], deadline, record["enqueue_sequence"], task["task_id"]]


def _delayed_key(record: dict[str, Any]) -> list[Any]:
    task = record["task"]
    return [task["not_before_tick"], record["enqueue_sequence"], task["task_id"]]


def project(state: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    ready_heap: list[tuple[tuple[Any, ...], str]] = []
    delayed_heap: list[tuple[tuple[Any, ...], str]] = []
    blocked: list[dict[str, Any]] = []
    for task_id in sorted(state["tasks"]):
        record = state["tasks"][task_id]
        task = record["task"]
        if record["state"] != "QUEUED":
            if record["state"] == "ADMITTED":
                blocked.append({"task_id": task_id, "reason": "NOT_QUEUED"})
            continue
        dependency = allocation_reducer.dependency_blockers(state, task)
        resources = allocation_reducer.resource_blockers(state, task)
        if dependency or resources:
            blocked.append({"task_id": task_id, "reason": "DEPENDENCY_OR_RESOURCE", "details": dependency + resources})
        elif task["not_before_tick"] > state["logical_tick"]:
            key = _delayed_key(record)
            heapq.heappush(delayed_heap, (tuple(key), task_id))
        else:
            key = _ready_key(record)
            heapq.heappush(ready_heap, (tuple(key), task_id))
    ready = [
        {"task_id": task_id, "stable_key": list(key)}
        for key, task_id in (heapq.heappop(ready_heap) for _ in range(len(ready_heap)))
    ]
    delayed = [
        {"task_id": task_id, "stable_key": list(key)}
        for key, task_id in (heapq.heappop(delayed_heap) for _ in range(len(delayed_heap)))
    ]
    blocked.sort(key=lambda item: item["task_id"])
    return {"ready": ready, "delayed": delayed, "blocked": blocked}


def build_snapshot(events: list[dict[str, Any]]) -> dict[str, Any]:
    allocation_events.verify_events(events)
    state = allocation_reducer.reduce_events(events)
    queues = project(state)
    leases = [state["leases"][key] for key in sorted(state["leases"])]
    tasks = [{
        "task_id": key, "state": value["state"], "effective_priority": value["effective_priority"],
        "enqueue_sequence": value["enqueue_sequence"], "attempts": value["attempts"],
        "lease_id": value["lease_id"], "last_reason": value["last_reason"],
        "task_digest": value["task"]["task_digest"],
    } for key, value in sorted(state["tasks"].items())]
    projection = {
        "reducer_version": allocation_reducer.REDUCER_VERSION,
        "registry_digest": task_registry.registry_digest(),
        "source_seq": events[-1]["sequence"] if events else 0,
        "source_event_hash": events[-1]["event_hash"] if events else None,
        "logical_tick": state["logical_tick"], "ready": queues["ready"],
        "delayed": queues["delayed"], "blocked": queues["blocked"],
        "leases": leases, "tasks": tasks,
        "ready_digest": storage.digest(queues["ready"]),
        "delayed_digest": storage.digest(queues["delayed"]),
        "lease_digest": storage.digest(leases), "task_digest": storage.digest(tasks),
    }
    snapshot = {
        "ccis_object": "ccis.allocation_snapshot", "schema_version": 1,
        **projection, "projection_digest": storage.digest(projection),
    }
    task_registry.validate_contract("allocation-snapshot", snapshot)
    return snapshot


def write_snapshot(allocation_root: Path, events: list[dict[str, Any]]) -> dict[str, Any]:
    snapshot = build_snapshot(events)
    storage.atomic_json(snapshot_path(allocation_root), snapshot)
    return snapshot


def rebuild(allocation_root: Path) -> dict[str, Any]:
    allocation_root = allocation_root.expanduser().resolve()
    events = allocation_events.read_events(allocation_root)
    return write_snapshot(allocation_root, events)


def verify_or_rebuild(allocation_root: Path) -> tuple[dict[str, Any], str]:
    """Return a verified cache, rebuilding missing/corrupt/stale projections automatically."""
    allocation_root = allocation_root.expanduser().resolve()
    events = allocation_events.read_events(allocation_root)
    expected = build_snapshot(events)
    path = snapshot_path(allocation_root)
    existing = storage.read_json(path)
    action = "VERIFIED"
    try:
        task_registry.validate_contract("allocation-snapshot", existing)
    except (storage.CCISError, TypeError):
        action = "REBUILT_CORRUPT_CACHE" if path.exists() else "REBUILT_MISSING_CACHE"
        existing = None
    if existing != expected:
        if action == "VERIFIED":
            action = "REBUILT_STALE_CACHE"
        storage.atomic_json(path, expected)
        return expected, action
    return existing, action
